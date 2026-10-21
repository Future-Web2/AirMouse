"""Two hands, and the dwell click: control that asks less of each hand.

The pointer hand (the right one by default, «Курсор ведёт рука» in «Подробнее») does
all that one hand does (gestures.py). When the other hand is in view too, it becomes a
hand of buttons, so aiming and pressing are done by different hands and the cursor
stays steady while clicking:

  pinch (thumb + index)       left button: down while the fingers touch, up when they part.
                              A quick pinch is a click, two are a double click, holding it
                              drags while the pointer hand moves the cursor freely.
  thumb + middle finger       right click
  two fingers up / down       scroll
  thumbs up (held)            maximize the active window (again: restore it)
  thumbs down (held)          minimize the active window

Both hands together, with open palms:

  move them apart quickly     all windows (Task View): pick one with a pinch
  bring them together         show the desktop (every window minimized); again: back
  both thumbs up, held 1 s    pause / resume mouse control (also works while paused)

Only one hand in view: it is the pointer, whichever it is.

Dwell click («Клик задержкой»): the cursor kept still for a moment clicks by itself,
for people who cannot pinch. Like the gestures, it is pure logic and tested in tests/.
"""

import math
from collections import deque

from . import tuning
from .gestures import (
    MOVE, SCROLL_ENTER_TIME, SCROLL_EXIT_TIME, THUMB_GAP, GestureEngine, HandFeatures, leash_px, palm_center, since,
    zone_rect,
)

SWIPE_TIME = 0.6        # seconds: moving the hands apart / together must take no longer
SWIPE_EACH = 0.6        # ... each hand moving at least this many palm lengths sideways
SWIPE_GAP = 1.6         # ... and the gap between them changing by at least this many
TOGETHER_GAP = 2.8      # palm lengths between the palms that count as "together"
COMBO_PAUSE = 1.2       # seconds after a two-hand gesture before the next one
PAUSE_HOLD = 1.0        # both thumbs up this long: pause / resume

KEYS_ALL_WINDOWS, KEYS_DESKTOP = "win+tab", "win+d"


class ButtonHand:
    """The second hand: mouse buttons, scrolling and the active window. It never moves the cursor."""

    def __init__(self, settings, screen_w, screen_h):
        self.settings = settings
        self.screen_w, self.screen_h = screen_w, screen_h
        self._px = screen_w / 1920.0
        self._reset()

    def _reset(self):
        self.state = None            # None, "left" (button held), "right" (clicked, waiting to open), "scroll"
        self.progress = 0.0          # how near the fingers are to a click, 0..1
        self._closed_since = self._opened_since = self._pose_since = None
        self._thumb_since = {"up": None, "down": None}
        self._thumb_seen = {"up": None, "down": None}
        self._thumb_done = set()
        self._scroll_ref = self._wheel = 0.0
        self._lost_since = None

    @property
    def holding(self):
        return self.state == "left"

    def release_all(self):
        actions = [("up", "left")] if self.state == "left" else []
        self._reset()
        return actions

    def update(self, pts, frame_w, frame_h, t, other_thumb_up=False):
        """One frame of the second hand (None: not in view). other_thumb_up: the pointer hand is giving
        a thumbs up too (that is the pause gesture, not a window command)."""
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
                    self._thumbs(f, t, other_thumb_up, actions)
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
        return actions

    def _thumbs(self, f, t, other_thumb_up, actions):
        hold = tuning.seconds(self.settings, "thumb_ms")
        for kind, seen, command in (("up", f.thumb_up and not other_thumb_up, "maximize"),
                                    ("down", f.thumb_down, "minimize")):
            if seen:
                self._thumb_seen[kind] = t
                if self._thumb_since[kind] is None:
                    self._thumb_since[kind] = t
                elif kind not in self._thumb_done and t - self._thumb_since[kind] >= hold:
                    actions.append(("window", command))
                    self._thumb_done.add(kind)
            elif self._thumb_seen[kind] is None or t - self._thumb_seen[kind] >= THUMB_GAP - 1e-6:
                self._thumb_since[kind] = None
                self._thumb_done.discard(kind)

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
    """Gestures of both hands together: all windows, show the desktop, pause."""

    def __init__(self):
        self._track = deque()            # (t, left palm x, right palm x, palm length) while both palms are open
        self._quiet_until = 0.0
        self._thumbs_since = self._thumbs_seen = None
        self._thumbs_done = False
        self.thumbs = False              # both thumbs up right now

    def reset(self):
        self._track.clear()
        self._thumbs_since = self._thumbs_seen = None
        self._thumbs_done = False
        self.thumbs = False

    def update(self, a, b, t):
        """a, b: the landmarks of the two hands (either None: nothing to do)."""
        if a is None or b is None:
            self.reset()
            return []
        fa, fb = HandFeatures(a), HandFeatures(b)
        actions = []
        self.thumbs = fa.thumb_up and fb.thumb_up
        if self.thumbs:
            self._thumbs_seen = t
            if self._thumbs_since is None:
                self._thumbs_since = t
            elif not self._thumbs_done and t - self._thumbs_since >= PAUSE_HOLD:
                actions.append(("pause",))
                self._thumbs_done = True
                self._quiet_until = t + COMBO_PAUSE
        elif self._thumbs_seen is None or t - self._thumbs_seen >= THUMB_GAP - 1e-6:
            self._thumbs_since = None
            self._thumbs_done = False

        if not (fa.open and fb.open):
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


class Dwell:
    """«Клик задержкой»: the cursor kept within a small circle for a moment clicks once."""

    def __init__(self, settings, screen_w=1920):
        self.settings = settings
        self._px = screen_w / 1920.0
        self.reset()

    def reset(self):
        self._anchor = None
        self._since = None
        self._armed = False
        self.progress = 0.0

    def disarm(self, cursor):
        """Something else just clicked here: wait until the cursor moves away before the next dwell."""
        self._anchor, self._since, self._armed, self.progress = cursor, None, False, 0.0

    def update(self, cursor, t, active):
        s = self.settings
        if not active or not tuning.get(s, "dwell_click") or cursor is None:
            self.reset()
            return []
        radius = tuning.get(s, "dwell_radius") * self._px
        if self._anchor is None or math.dist(cursor, self._anchor) > radius:
            self._anchor, self._since, self._armed = cursor, t, True
        if not self._armed:
            self.progress = 0.0
            return []
        self.progress = min((t - self._since) / tuning.seconds(s, "dwell_ms"), 1.0)
        if self.progress >= 1.0:
            self._armed = False
            self.progress = 0.0
            return [("click", "left")]
        return []


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

    @property
    def mode(self):
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

    def update(self, hands, frame_w, frame_h, t, cursor, enabled=True):
        """hands: landmark lists of the hands in view (0, 1 or 2). enabled False (paused): only the
        pause gesture is watched for, and any held button is let go."""
        pointer, second = self.split(hands)
        self.pointer, self.second = pointer, second
        s = self.settings
        actions = []
        combos = self.both.update(pointer, second, t) if tuning.get(s, "hand_combos") else []
        if not tuning.get(s, "hand_combos"):
            self.both.reset()
        actions += [a for a in combos if a[0] == "pause"]
        if not enabled:
            self.dwell.reset()
            return actions + self.engine.release_all() + self.buttons.release_all()

        pointer_actions = self.engine.update(pointer, frame_w, frame_h, t, cursor)
        second_thumb = second is not None and HandFeatures(second).thumb_up
        if second_thumb or self.both.thumbs:      # two thumbs up mean pause, not «show the widgets»
            pointer_actions = [a for a in pointer_actions if a[0] != "widgets"]
        actions += pointer_actions
        actions += [a for a in combos if a[0] != "pause"]
        pointer_thumb = pointer is not None and HandFeatures(pointer).thumb_up
        actions += self.buttons.update(second, frame_w, frame_h, t, other_thumb_up=pointer_thumb)

        here = cursor
        for action in actions:
            if action[0] == "move":
                here = action[1:]
        if any(a[0] in ("click", "down", "up", "wheel") for a in actions):
            self.dwell.disarm(here)
        else:
            active = pointer is not None and self.engine.mode == MOVE and not self.buttons.holding
            actions += self.dwell.update(here, t, active)
        return actions
