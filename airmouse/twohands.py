"""Two hands, and the dwell click: control that asks less of each hand.

The pointer hand (the right one by default, «Курсор ведёт рука» in «Подробнее») does
all that one hand does (gestures.py), and one thing more: a thumbs down held for a
second pauses mouse control (and again resumes it), so one hand is enough for that too.

When the other hand is in view too, it becomes a hand of buttons, so aiming and
pressing are done by different hands and the cursor stays steady while clicking:

  pinch (thumb + index)       left button: down while the fingers touch, up when they part.
                              A quick pinch is a click, two are a double click, holding it
                              drags while the pointer hand moves the cursor freely.
  thumb + middle finger       right click
  two fingers up / down       scroll
  «L» (index up, thumb out)   the precise cursor: while it is held the cursor moves only part
                              of the way the pointer hand does, for small targets and fine work
  quick sideways swipe        a command the user picks: back / forward, slides, desktops, tracks
                              (nothing until one is picked)
  thumbs up (held)            maximize the active window (again: restore it)
  thumbs down (held)          minimize the active window

Both hands together:

  open palms apart quickly    all windows (Task View): pick one with a pinch
  open palms together         show the desktop (every window minimized); again: back
  both «V», apart / together  zoom in / out (Ctrl + wheel in the program, or the Windows magnifier)
  both thumbs up, held 1 s    pause / resume mouse control (also works while paused)

Only one hand in view: it is the pointer, whichever it is.

Dwell click («Клик задержкой»): the cursor kept still for a moment clicks by itself,
for people who cannot pinch. The panel «Клик задержкой» picks what the next one does:
a double click, a right click, or a drag (pressed at one dwell, let go at the next).
Like the gestures, it is pure logic and tested in tests/.
"""

import math
from collections import deque

from . import tuning
from .gestures import (
    MOVE, SCROLL_ENTER_TIME, SCROLL_EXIT_TIME, THUMB_GAP, GestureEngine, HandFeatures, leash_px, palm_center, since,
    zone_rect,
)

PRECISE, ZOOM = "precise", "zoom"   # modes on top of the gesture engine's, for the status line and the ring

SWIPE_TIME = 0.6        # seconds: moving the hands apart / together must take no longer
SWIPE_EACH = 0.6        # ... each hand moving at least this many palm lengths sideways
SWIPE_GAP = 1.6         # ... and the gap between them changing by at least this many
TOGETHER_GAP = 2.8      # palm lengths between the palms that count as "together"
COMBO_PAUSE = 1.2       # seconds after a two-hand gesture before the next one
PAUSE_HOLD = 1.0        # both thumbs up (or the pointer hand's thumb down) this long: pause / resume

PRECISE_ENTER = 0.15    # seconds the «L» is held before the cursor slows down
ZOOM_STEP = 0.5         # palm lengths the hands move apart (or together) for one step of zoom
SWIPE_HAND_TIME = 0.35  # a swipe of the second hand: at least SWIPE_HAND palm lengths sideways in this time
SWIPE_HAND = 1.6
SWIPE_STEADY = 0.5      # ... while the pointer hand moves less than this (both moving: a two-hand gesture)
SWIPE_SEEN = 0.3        # ... and only once the hand has been in view this long (coming into view is no swipe)
SWIPE_QUIET = 0.8       # seconds after a swipe before the next

KEYS_ALL_WINDOWS, KEYS_DESKTOP = "win+tab", "win+d"
MAGNIFIER = ("win+plus", "win+minus")
# «Взмах второй рукой»: (hand to the left: forward / next, hand to the right: back / previous)
SWIPES = {1: ("alt+right", "alt+left"), 2: ("right", "left"), 3: ("ctrl+win+right", "ctrl+win+left"),
          4: ("nexttrack", "prevtrack")}
DWELL_KINDS = ("left", "double", "right", "drag")


class Hold:
    """A pose held for a while does something once; letting go (for THUMB_GAP) arms it again.
    A noisy frame or two without the pose does not end it."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._since = self._seen = None
        self._done = False

    def update(self, seen, t, hold):
        """True once, in the frame the pose has been held for `hold` seconds."""
        if seen:
            self._seen = t
            if self._since is None:
                self._since = t
            elif not self._done and t - self._since >= hold:
                self._done = True
                return True
        elif self._seen is None or t - self._seen >= THUMB_GAP - 1e-6:
            self._since = None
            self._done = False
        return False


class ButtonHand:
    """The second hand: mouse buttons, scrolling, the precise cursor, swipes and the active window.
    It never moves the cursor."""

    def __init__(self, settings, screen_w, screen_h):
        self.settings = settings
        self.screen_w, self.screen_h = screen_w, screen_h
        self._px = screen_w / 1920.0
        self._reset()

    def _reset(self):
        self.state = None            # None, "left" (button held), "right" (clicked, waiting to open), "scroll"
        self.progress = 0.0          # how near the fingers are to a click, 0..1
        self.precise = False         # the «L» is held: the cursor goes slowly
        self._closed_since = self._opened_since = self._pose_since = None
        self._l_since = self._l_gone = None
        self._thumbs = {"up": Hold(), "down": Hold()}
        self._scroll_ref = self._wheel = 0.0
        self._lost_since = None
        self._seen_since = None
        self._track = deque()        # (t, x, y) of the open palm, for swipes
        self._quiet_until = 0.0

    @property
    def holding(self):
        return self.state == "left"

    def release_all(self):
        actions = [("up", "left")] if self.state == "left" else []
        self._reset()
        return actions

    def update(self, pts, frame_w, frame_h, t, other_thumb_up=False, other_thumb_down=False):
        """One frame of the second hand (None: not in view). other_thumb_up / _down: the pointer hand
        shows one too (both thumbs up is the pause gesture, and its thumb down pauses: no window command)."""
        if pts is None:
            if self.state is None:
                self._reset()
                return []
            if self._lost_since is None:
                self._lost_since = t
            if t - self._lost_since < tuning.seconds(self.settings, "hand_lost_ms"):
                return []
            return self.release_all()
        self._lost_since = None
        if self._seen_since is None:
            self._seen_since = t
        s = self.settings
        f = HandFeatures(pts)
        close = s.pinch_threshold
        apart_at = close * tuning.get(s, "release_factor")
        nearest = min(f.pinch_index, f.pinch_middle)
        self.progress = min(max((apart_at - nearest) / (apart_at - close), 0.0), 1.0)
        touching = f.pinch_index < close or f.pinch_middle < close
        apart = f.pinch_index > apart_at and f.pinch_middle > apart_at
        self._closed_since = since(self._closed_since, touching, t)
        self._opened_since = since(self._opened_since, apart, t)
        confirm = tuning.seconds(s, "pinch_confirm_ms") - 1e-6
        actions = []

        if self.state is None:
            if self._closed_since is not None and t - self._closed_since >= confirm:
                if f.pinch_middle < close and f.pinch_middle <= f.pinch_index + 0.05:
                    actions.append(("click", "right"))
                    self.state = "right"
                else:
                    actions.append(("down", "left"))
                    self.state = "left"
                self._pose_since = None
            else:
                self._pose_since = since(self._pose_since, f.two_fingers, t)
                if self._pose_since is not None and t - self._pose_since >= SCROLL_ENTER_TIME:
                    self.state = "scroll"
                    self._pose_since = None
                    self._scroll_ref = self._screen_y(f.palm[1], frame_w, frame_h)
                    self._wheel = 0.0
                else:
                    self._thumb_commands(f, t, other_thumb_up, other_thumb_down, actions)
                    self._swipe(f, t, actions)
        elif self.state in ("left", "right"):
            if self._opened_since is not None and t - self._opened_since >= confirm:
                if self.state == "left":
                    actions.append(("up", "left"))
                self.state = None
        elif self.state == "scroll":
            self._pose_since = since(self._pose_since, not f.two_fingers, t)
            if self._pose_since is not None and t - self._pose_since >= SCROLL_EXIT_TIME:
                self.state = None
                self._pose_since = None
            elif f.two_fingers:       # not while the pose is changing: the hand often jumps then
                self._scroll(self._screen_y(f.palm[1], frame_w, frame_h), actions)
        self._precise(f, t)
        return actions

    def _thumb_commands(self, f, t, other_thumb_up, other_thumb_down, actions):
        hold = tuning.seconds(self.settings, "thumb_ms")
        if self._thumbs["up"].update(f.thumb_up and not other_thumb_up, t, hold):
            actions.append(("window", "maximize"))
        if self._thumbs["down"].update(f.thumb_down and not other_thumb_down, t, hold):
            actions.append(("window", "minimize"))

    def _precise(self, f, t):
        """The «L» held a moment turns the precise cursor on; it goes off soon after the pose ends."""
        shown = f.l_shape and self.state is None
        self._l_since = since(self._l_since, shown, t)
        self._l_gone = since(self._l_gone, not shown, t)
        if self._l_since is not None and t - self._l_since >= PRECISE_ENTER:
            self.precise = True
        elif self._l_gone is not None and t - self._l_gone >= SCROLL_EXIT_TIME:
            self.precise = False

    def _swipe(self, f, t, actions):
        """A quick sideways swipe of the open hand: ("swipe", "left" or "right"), as the picture shows it."""
        if not f.open or t - self._seen_since < SWIPE_SEEN:
            self._track.clear()
            return
        self._track.append((t, f.palm[0], f.palm[1]))
        while t - self._track[0][0] > SWIPE_HAND_TIME:
            self._track.popleft()
        if t < self._quiet_until:
            return
        _t0, x0, y0 = self._track[0]
        dx, dy = (f.palm[0] - x0) / f.size, (f.palm[1] - y0) / f.size
        if abs(dx) >= SWIPE_HAND and abs(dy) <= 0.6 * abs(dx):
            actions.append(("swipe", "left" if dx < 0 else "right"))
            self._track.clear()
            self._quiet_until = t + SWIPE_QUIET

    def _screen_y(self, y, frame_w, frame_h):
        """Camera y of the palm in screen pixels, as the pointer hand's would be."""
        _x0, y0, _x1, y1 = zone_rect(self.settings, frame_w, frame_h, self.screen_w, self.screen_h)
        return (y / frame_h - y0) / (y1 - y0) * self.screen_h

    def _scroll(self, y, actions):
        s = self.settings
        d = y - self._scroll_ref
        r = leash_px(s, self._px)
        if abs(d) <= r:
            return
        moved = d - math.copysign(r, d)
        self._scroll_ref += moved
        direction = 1 if s.invert_scroll else -1        # hand up -> scroll up
        self._wheel += direction * moved / self._px * s.scroll_speed
        if abs(self._wheel) >= tuning.get(s, "wheel_step"):
            amount = int(self._wheel)
            self._wheel -= amount
            actions.append(("wheel", amount))


class BothHands:
    """Gestures of both hands together: all windows, show the desktop, zoom, pause."""

    def __init__(self):
        self._track = deque()            # (t, left palm x, right palm x, palm length) while both palms are open
        self._quiet_until = 0.0
        self._thumbs = Hold()
        self.reset()

    def reset(self):
        self._track.clear()
        self._thumbs.reset()
        self.thumbs = False              # both thumbs up right now
        self.v_pose = False              # both hands show two fingers right now
        self.zooming = False
        self._v_since = self._v_gone = None
        self._zoom_ref = 0.0

    def update(self, fa, fb, t, combos=True, zoom=True):
        """fa, fb: HandFeatures of the two hands (either None: nothing to do). combos: the open-palm
        gestures and the pause; zoom: both «V» apart / together."""
        if fa is None or fb is None:
            self.reset()
            return []
        actions = []
        self.thumbs = fa.thumb_up and fb.thumb_up
        if self._thumbs.update(self.thumbs and combos, t, PAUSE_HOLD):
            actions.append(("pause",))
            self._quiet_until = t + COMBO_PAUSE
        self.v_pose = fa.two_fingers and fb.two_fingers and zoom
        self._zoom(fa, fb, t, actions)

        if not (combos and fa.open and fb.open):
            self._track.clear()
            return actions
        left, right = sorted((fa, fb), key=lambda f: f.palm[0])
        size = (fa.size + fb.size) / 2
        self._track.append((t, left.palm[0], right.palm[0], size))
        while t - self._track[0][0] > SWIPE_TIME:
            self._track.popleft()
        if t < self._quiet_until:
            return actions
        _t0, l0, r0, _s0 = self._track[0]
        moved_left, moved_right = (left.palm[0] - l0) / size, (right.palm[0] - r0) / size
        gap0, gap = (r0 - l0) / size, (right.palm[0] - left.palm[0]) / size
        if moved_left <= -SWIPE_EACH and moved_right >= SWIPE_EACH and gap - gap0 >= SWIPE_GAP:
            actions.append(("keys", KEYS_ALL_WINDOWS))
        elif moved_left >= SWIPE_EACH and moved_right <= -SWIPE_EACH and gap0 - gap >= SWIPE_GAP and gap <= TOGETHER_GAP:
            actions.append(("keys", KEYS_DESKTOP))
        if actions and actions[-1][0] == "keys":
            self._track.clear()
            self._quiet_until = t + COMBO_PAUSE
        return actions

    def _zoom(self, fa, fb, t, actions):
        """Both «V»: ("zoom", steps), more than 0 as the hands move apart, less as they come together."""
        self._v_since = since(self._v_since, self.v_pose, t)
        self._v_gone = since(self._v_gone, not self.v_pose, t)
        gap = math.dist(fa.palm, fb.palm) / ((fa.size + fb.size) / 2)
        if not self.zooming:
            if self._v_since is not None and t - self._v_since >= SCROLL_ENTER_TIME:
                self.zooming, self._zoom_ref = True, gap
            return
        if self._v_gone is not None and t - self._v_gone >= SCROLL_EXIT_TIME:
            self.zooming = False
        elif self.v_pose:
            steps = int((gap - self._zoom_ref) / ZOOM_STEP)
            if steps:
                self._zoom_ref += steps * ZOOM_STEP
                actions.append(("zoom", steps))


class Dwell:
    """«Клик задержкой»: the cursor kept within a small circle for a moment clicks once.

    `kind` is what the next dwell does: "left" (always, unless the panel picks another for one
    click), "double", "right", or "drag": press the button, and let it go at the next dwell.
    """

    def __init__(self, settings, screen_w=1920):
        self.settings = settings
        self._px = screen_w / 1920.0
        self.kind = "left"
        self.dragging = False          # a dwell drag pressed the button, the next dwell lets it go
        self.reset()

    def reset(self):
        self._anchor = None
        self._since = None
        self._armed = False
        self.progress = 0.0

    def choose(self, kind):
        """The panel picked the kind of the next dwell click."""
        if kind in DWELL_KINDS:
            self.kind = kind

    def release_all(self):
        actions = [("up", "left")] if self.dragging else []
        self.dragging = False
        self.reset()
        return actions

    def disarm(self, cursor):
        """Something else just clicked here: wait until the cursor moves away before the next dwell."""
        self._anchor, self._since, self._armed, self.progress = cursor, None, False, 0.0

    def update(self, cursor, t, active, own=False):
        """own: the cursor is over AirMouse's own panel, which always gets a plain click (so the
        dwell panel itself can be worked whatever kind is picked)."""
        s = self.settings
        if not tuning.get(s, "dwell_click"):
            return self.release_all()
        if not active or cursor is None:
            self.reset()
            return []
        radius = tuning.get(s, "dwell_radius") * self._px
        if self._anchor is None or math.dist(cursor, self._anchor) > radius:
            self._anchor, self._since, self._armed = cursor, t, True
        if not self._armed:
            self.progress = 0.0
            return []
        self.progress = min((t - self._since) / tuning.seconds(s, "dwell_ms"), 1.0)
        if self.progress < 1.0:
            return []
        self._armed = False
        self.progress = 0.0
        if own and not self.dragging:
            return [("click", "left")]
        return self._fire()

    def _fire(self):
        if self.dragging:
            self.dragging = False
            self.kind = "left"
            return [("up", "left")]
        kind, self.kind = self.kind, "left"      # the other kinds are for one click
        if kind == "drag":
            self.kind = "drag"
            self.dragging = True
            return [("down", "left")]
        if kind == "double":
            return [("click", "left"), ("click", "left")]
        return [("click", "right" if kind == "right" else "left")]


class HandControl:
    """Everything the hands do, frame by frame: which hand is which, the pointer hand's gestures,
    the second hand's buttons, the two-hand gestures and the dwell click."""

    def __init__(self, settings, screen_w, screen_h):
        self.settings = settings
        self.engine = GestureEngine(settings, screen_w, screen_h)
        self.buttons = ButtonHand(settings, screen_w, screen_h)
        self.both = BothHands()
        self.dwell = Dwell(settings, screen_w)
        self.pointer = self.second = None        # the landmarks of each, for the preview
        self._pause = Hold()                     # the pointer hand's thumb down
        self._pointer_track = deque()            # (t, palm x, palm length) of the pointer hand, for swipes

    @property
    def mode(self):
        if self.both.zooming:
            return ZOOM
        if self.engine.fine < 1.0 and self.engine.mode == MOVE:
            return PRECISE
        return self.engine.mode

    @property
    def progress(self):
        return max(self.engine.pinch, self.buttons.progress, self.dwell.progress)

    def split(self, hands):
        """(pointer, second) from the hands in view, left to right in the picture as the user sees it."""
        if not hands:
            return None, None
        if len(hands) == 1 or not tuning.get(self.settings, "two_hands"):
            return hands[0], None
        a, b = sorted(hands[:2], key=lambda pts: palm_center(pts)[0])
        # In the mirrored picture the right hand is the one on the right.
        right_is_pointer = bool(tuning.get(self.settings, "pointer_hand")) == bool(tuning.get(self.settings, "mirror"))
        return (b, a) if right_is_pointer else (a, b)

    def update(self, hands, frame_w, frame_h, t, cursor, enabled=True, own=False):
        """hands: landmark lists of the hands in view (0, 1 or 2). enabled False (paused): only the
        pause gestures are watched for, and any held button is let go. own: the cursor is over
        AirMouse's own panel (see Dwell.update)."""
        pointer, second = self.split(hands)
        self.pointer, self.second = pointer, second
        s = self.settings
        fp = HandFeatures(pointer) if pointer is not None else None
        fs = HandFeatures(second) if second is not None else None
        both = self.both.update(fp, fs, t, tuning.get(s, "hand_combos"), tuning.get(s, "zoom_mode"))
        actions = [a for a in both if a[0] == "pause"]
        pointer_down = fp is not None and fp.thumb_down and not (fs is not None and fs.thumb_down)
        if self._pause.update(pointer_down and tuning.get(s, "thumb_pause"), t, PAUSE_HOLD):
            actions.append(("pause",))
        if not enabled:
            self.engine.fine = 1.0
            return actions + self.engine.release_all() + self.buttons.release_all() + self.dwell.release_all()

        speed = tuning.get(s, "precise_speed")
        self.engine.fine = speed if self.buttons.precise and speed < 1.0 else 1.0
        pointer_actions = self.engine.update(pointer, frame_w, frame_h, t, cursor)
        if (fs is not None and fs.thumb_up) or self.both.thumbs:   # two thumbs up mean pause, not «show the widgets»
            pointer_actions = [a for a in pointer_actions if a[0] != "widgets"]
        second_actions = self.buttons.update(second, frame_w, frame_h, t,
                                             other_thumb_up=fp is not None and fp.thumb_up,
                                             other_thumb_down=fp is not None and fp.thumb_down)
        if self.both.zooming or self.both.v_pose:   # both «V»: zoom, not scrolling with each hand
            pointer_actions = [a for a in pointer_actions if a[0] != "wheel"]
            second_actions = [a for a in second_actions if a[0] != "wheel"]
        actions += pointer_actions
        actions += self._two_hand_commands(both)
        actions += self._second_hand_commands(second_actions, fp, t)

        here = cursor
        for action in actions:
            if action[0] == "move":
                here = action[1:]
        if any(a[0] in ("click", "down", "up", "wheel", "zoom") for a in actions):
            self.dwell.disarm(here)
        else:
            active = (pointer is not None and self.engine.mode == MOVE and not self.buttons.holding
                      and not self.both.zooming)
            actions += self.dwell.update(here, t, active, own)
        return actions

    def _two_hand_commands(self, both):
        """The gestures of both hands, but the pause (handled first): zoom as the user chose it."""
        actions = []
        for action in both:
            if action[0] == "zoom":
                if tuning.get(self.settings, "zoom_mode") == 2:      # the Windows magnifier
                    actions += [("keys", MAGNIFIER[0 if action[1] > 0 else 1])] * abs(action[1])
                else:
                    actions.append(action)
            elif action[0] != "pause":
                actions.append(action)
        return actions

    def _second_hand_commands(self, actions, fp, t):
        """The second hand's actions, with a swipe turned into the keys of the chosen command."""
        track = self._pointer_track
        if fp is None:
            track.clear()
        else:
            track.append((t, fp.palm[0], fp.size))
            while t - track[0][0] > SWIPE_HAND_TIME:
                track.popleft()
        result = []
        for action in actions:
            if action[0] != "swipe":
                result.append(action)
                continue
            command = SWIPES.get(int(tuning.get(self.settings, "swipe_action")))
            moved = max((abs(x - track[-1][1]) / size for _t, x, size in track), default=0.0)
            if command is None or moved >= SWIPE_STEADY:
                continue
            # The picture is mirrored by default: a hand moving to the user's left moves left in it.
            to_the_left = (action[1] == "left") == bool(tuning.get(self.settings, "mirror"))
            result.append(("keys", command[0 if to_the_left else 1]))
        return result
