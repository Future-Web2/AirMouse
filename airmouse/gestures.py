"""Hand landmarks -> mouse actions.

Pure logic with no camera or WinAPI calls: the tracker feeds in one frame at a
time and performs the actions that come back, which keeps this easy to test.

Stabilization, in the order it is applied:
  1. The cursor follows the palm, not a fingertip, so pinching does not move it.
  2. A 3-frame median drops single-frame tracking glitches.
  3. A One Euro filter smooths slow movement hard and fast movement lightly.
  4. A "leash" (see pointer.py): shaking smaller than it never reaches the screen.
  5. While fingers touch the cursor is held still, and the click goes where
     the cursor was just before the pinch began.
"""

import math
import statistics
from collections import deque

from . import tuning
from .filters import OneEuroFilter2D
from .pointer import Pointer

# MediaPipe hand landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20
PALM_POINTS = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)

# Modes
NO_HAND = "no_hand"
MOVE = "move"
PENDING = "pending"    # fingers just touched; left or right click not decided yet
PRESSED = "pressed"    # left button down, cursor held still
DRAG = "drag"          # left button down, cursor follows the hand
RIGHT = "right"        # right click sent, waiting for the fingers to open
SCROLL = "scroll"

EXTENDED_RATIO = 1.15       # straight finger: tip this much farther from the wrist than the middle joint
THUMB_ABOVE = 0.35          # thumbs up: thumb tip this far (in palm lengths) above the rest of the hand

# Seconds. Confirmations are times, not frame counts, so 60 frames per second
# behaves like 30 (only sooner). Most other numbers are in tuning.py («Подробнее»).
SCROLL_ENTER_TIME = 0.095   # two-finger pose held this long starts scrolling (4 frames at 30 per second)
SCROLL_EXIT_TIME = 0.06     # ... and left this long ends it (3 frames)
THUMB_GAP = 0.1             # a thumbs up survives losing sight of it this long
REWIND = 0.12               # click where the cursor was this long before the pinch
UNFREEZE_PX = 40            # screen pixels at 1920 px width: moving this far ends the hold after a click


def since(start, on, t):
    """Start time of a state that is on now (kept while it lasts), or None when it is off."""
    return (t if start is None else start) if on else None


def _dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _extended(pts, tip, pip):
    return _dist(pts[WRIST], pts[tip]) > EXTENDED_RATIO * _dist(pts[WRIST], pts[pip])


def palm_center(pts):
    n = len(PALM_POINTS)
    return sum(pts[i][0] for i in PALM_POINTS) / n, sum(pts[i][1] for i in PALM_POINTS) / n


def zone_rect(settings, frame_w, frame_h, screen_w, screen_h):
    """Part of the camera image mapped onto the screen, as (x0, y0, x1, y1) in 0..1.

    Its shape matches the screen, so the cursor moves equally fast in both directions.
    """
    zw = settings.zone_size
    zh = zw * (frame_w / frame_h) * (screen_h / screen_w)
    cx, cy = settings.zone_center_x, settings.zone_center_y
    return cx - zw / 2, cy - zh / 2, cx + zw / 2, cy + zh / 2


def leash_px(settings, px):
    """Leash length: how much shaking is ignored, grows with the stabilization setting («Мёртвая зона» scales it)."""
    return (1.0 + 9.0 * settings.smoothing) * px * tuning.get(settings, "deadzone")


def tune_filter(f, settings, px):
    f.min_cutoff = 3.0 - 2.7 * settings.smoothing
    f.beta = (0.02 - 0.016 * settings.smoothing) / px * tuning.get(settings, "fast_response")


class HandFeatures:
    """Measurements of one hand that do not depend on its distance from the camera."""

    def __init__(self, pts):
        size = max(_dist(pts[WRIST], pts[MIDDLE_MCP]), 1e-6)
        self.pinch_index = _dist(pts[THUMB_TIP], pts[INDEX_TIP]) / size
        self.pinch_middle = _dist(pts[THUMB_TIP], pts[MIDDLE_TIP]) / size
        straight = [_extended(pts, tip, pip) for tip, pip in
                    ((INDEX_TIP, INDEX_PIP), (MIDDLE_TIP, MIDDLE_PIP), (RING_TIP, RING_PIP), (PINKY_TIP, PINKY_PIP))]
        self.two_fingers = straight == [True, True, False, False]
        # Thumbs up: a fist with the thumb standing well above it.
        self.thumb_up = not any(straight) and (
            pts[THUMB_TIP][1] < min(p[1] for p in pts[INDEX_MCP:]) - THUMB_ABOVE * size)
        self.palm = palm_center(pts)


class GestureEngine:
    """Turns a stream of hand landmarks into mouse actions.

    Actions: ("move", x, y), ("down", button), ("up", button),
    ("click", button), ("wheel", delta), and ("widgets",) for a held thumbs up.
    `pinch` tells how close the fingers are to a click: 0 apart .. 1 touching.
    """

    def __init__(self, settings, screen_w, screen_h):
        self.settings = settings
        self.screen_w, self.screen_h = screen_w, screen_h
        self._px = screen_w / 1920.0
        self._filter = OneEuroFilter2D()
        self._ptr = Pointer(screen_w, screen_h)
        self._reset()

    def _reset(self):
        self.mode = NO_HAND
        self.pinch = 0.0
        self._thumb_since = None           # when the thumbs up began
        self._thumb_seen = None            # when it was last seen
        self._thumb_done = False           # this thumbs up already toggled the widgets
        self._filter.reset()
        self._ptr.reset()
        self._raw = deque(maxlen=3)
        self._hold_hand = None             # hand position when the hold began
        self._hold_until = None            # None: held until the gesture ends
        self._closed_since = None          # when the fingers began to touch
        self._opened_since = None          # when they came apart
        self._pose_since = None            # when the two-finger pose began (while scrolling: ended)
        self._pinch_start = 0.0
        self._scroll_ref = 0.0
        self._wheel = 0.0
        self._lost_since = None

    def release_all(self):
        """Let go of any held button and forget the hand (hand lost, pause, stop)."""
        actions = [("up", "left")] if self.mode in (PRESSED, DRAG) else []
        self._reset()
        return actions

    def update(self, pts, frame_w, frame_h, t, cursor_pos=None):
        """Process one camera frame and return the mouse actions to perform.

        pts: the 21 hand landmarks as (x, y, z) in pixels of the mirrored
        camera image, or None when no hand is visible.
        cursor_pos: where the Windows cursor is now.
        """
        if pts is None:
            if self.mode == NO_HAND:
                return []
            if self._lost_since is None:
                self._lost_since = t
            if t - self._lost_since < tuning.seconds(self.settings, "hand_lost_ms"):
                return []
            return self.release_all()
        self._lost_since = None

        f = HandFeatures(pts)
        hand = self._hand_on_screen(f.palm, frame_w, frame_h, t)
        ptr = self._ptr
        ptr.glide = tuning.seconds(self.settings, "glide_ms")
        if cursor_pos is None:
            cursor_pos = ptr.sent or hand
        moved_by_mouse = (
            self.mode == MOVE and ptr.held is None
            and math.dist(cursor_pos, ptr.sent) > 50 * self._px
        )
        if self.mode == NO_HAND or moved_by_mouse:
            self.mode = MOVE
            ptr.start(cursor_pos, hand)

        actions = []
        self._gesture(f, hand, t, actions)
        if ptr.held is not None and self._hold_until is not None and (
            t >= self._hold_until or math.dist(hand, self._hold_hand) > UNFREEZE_PX * self._px
        ):
            self._end_hold(hand)
        ptr.follow(hand, t, leash_px(self.settings, self._px), actions)
        return actions

    # -- gestures ---------------------------------------------------------

    def _gesture(self, f, hand, t, actions):
        s = self.settings
        close = s.pinch_threshold
        apart_at = close * tuning.get(s, "release_factor")    # fingers count as apart this far apart
        nearest = min(f.pinch_index, f.pinch_middle)
        self.pinch = min(max((apart_at - nearest) / (apart_at - close), 0.0), 1.0)
        index_touch = f.pinch_index < close
        middle_touch = f.pinch_middle < close
        apart = f.pinch_index > apart_at and f.pinch_middle > apart_at
        self._closed_since = since(self._closed_since, index_touch or middle_touch, t)
        self._opened_since = since(self._opened_since, apart, t)
        confirm = tuning.seconds(s, "pinch_confirm_ms") - 1e-6
        pinched = self._closed_since is not None and t - self._closed_since >= confirm
        released = self._opened_since is not None and t - self._opened_since >= confirm

        mode = self.mode
        if mode in (MOVE, SCROLL) and pinched:
            self._begin_pinch(hand, t, middle_touch, actions)
        elif mode == MOVE:
            self._pose_since = since(self._pose_since, f.two_fingers, t)
            if self._pose_since is not None and t - self._pose_since >= SCROLL_ENTER_TIME:
                self._begin_scroll(hand, actions)
            else:
                self._thumbs_up(f.thumb_up, t, actions)
        elif mode == SCROLL:
            self._pose_since = since(self._pose_since, not f.two_fingers, t)
            if self._pose_since is not None and t - self._pose_since >= SCROLL_EXIT_TIME:
                self.mode = MOVE
                self._pose_since = None
                self._end_hold(hand)
            else:
                self._scroll(hand, actions)
        elif mode == PENDING:
            if middle_touch:
                actions.append(("click", "right"))
                self.mode = RIGHT
            elif released:
                actions.append(("click", "left"))
                self._after_click(t)
            elif t - self._pinch_start >= tuning.seconds(s, "right_click_ms"):
                actions.append(("down", "left"))
                self.mode = PRESSED
        elif mode == PRESSED:
            if released:
                actions.append(("up", "left"))
                self._after_click(t)
            elif math.dist(hand, self._hold_hand) > tuning.get(s, "drag_start_px") * self._px:
                self.mode = DRAG
                self._end_hold(hand)
        elif mode == DRAG:
            if released:
                actions.append(("up", "left"))
                self.mode = MOVE
        elif mode == RIGHT:
            if released:
                self._after_click(t)
        if self.mode != MOVE:
            self._thumb_since = None

    def _thumbs_up(self, seen, t, actions):
        # A noisy frame or two does not end the gesture; letting go (THUMB_GAP) arms it again.
        if seen:
            self._thumb_seen = t
            if self._thumb_since is None:
                self._thumb_since = t
            elif not self._thumb_done and t - self._thumb_since >= tuning.seconds(self.settings, "thumb_ms"):
                actions.append(("widgets",))
                self._thumb_done = True
            return
        if self._thumb_seen is None or t - self._thumb_seen >= THUMB_GAP - 1e-6:
            self._thumb_since = None
            self._thumb_done = False

    def _begin_pinch(self, hand, t, middle_touch, actions):
        # Already held right after a click: keep the same spot, so a second
        # tap makes a double click there.
        if self._ptr.held is None:
            self._ptr.hold(self._ptr.position_before(t - REWIND), actions)
        self._hold_hand = hand
        self._hold_until = None
        self._pinch_start = t
        self._pose_since = None
        if middle_touch:
            actions.append(("click", "right"))
            self.mode = RIGHT
        else:
            self.mode = PENDING

    def _after_click(self, t):
        self.mode = MOVE
        self._hold_until = t + tuning.seconds(self.settings, "post_click_ms")

    def _begin_scroll(self, hand, actions):
        self.mode = SCROLL
        self._pose_since = None
        if self._ptr.held is None:
            self._ptr.hold(self._ptr.cursor, actions)
        self._hold_hand = hand
        self._hold_until = None
        self._scroll_ref = hand[1]
        self._wheel = 0.0

    def _scroll(self, hand, actions):
        # Same leash as the cursor: shaking smaller than the leash does not scroll.
        d = hand[1] - self._scroll_ref
        r = leash_px(self.settings, self._px)
        if abs(d) <= r:
            return
        moved = d - math.copysign(r, d)
        self._scroll_ref += moved
        direction = 1 if self.settings.invert_scroll else -1   # hand up -> scroll up
        self._wheel += direction * moved / self._px * self.settings.scroll_speed
        if abs(self._wheel) >= tuning.get(self.settings, "wheel_step"):
            amount = int(self._wheel)
            self._wheel -= amount
            actions.append(("wheel", amount))

    def _end_hold(self, hand):
        self._ptr.release(hand)
        self._hold_hand = self._hold_until = None

    # -- cursor -----------------------------------------------------------

    def _hand_on_screen(self, palm, frame_w, frame_h, t):
        """Palm position in the camera image -> filtered screen pixels."""
        s = self.settings
        x0, y0, x1, y1 = zone_rect(s, frame_w, frame_h, self.screen_w, self.screen_h)
        x = (palm[0] / frame_w - x0) / (x1 - x0) * (self.screen_w - 1)
        y = (palm[1] / frame_h - y0) / (y1 - y0) * (self.screen_h - 1)
        # Let the target go a little past the edges so the leashed cursor can reach them.
        margin = 2 * leash_px(s, self._px)
        x = min(max(x, -margin), self.screen_w - 1 + margin)
        y = min(max(y, -margin), self.screen_h - 1 + margin)
        self._raw.append((x, y))
        if tuning.get(s, "outlier_filter"):
            x = statistics.median(p[0] for p in self._raw)
            y = statistics.median(p[1] for p in self._raw)
        tune_filter(self._filter, s, self._px)
        return self._filter(x, y, t)
