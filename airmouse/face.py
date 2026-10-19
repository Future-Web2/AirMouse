"""Face landmarks -> mouse actions.

The cursor follows the eyes ("gaze" mode) or the head ("head" mode). Clicks are
made with the face, the same way in both modes:

  long blink (~0.4 s)         left click; two in a row = double click
  wink with one eye           right click
  open mouth                  hold the left button (drag); close it to let go
  raise eyebrows + tilt head  scroll

A webcam sees the eyes only coarsely (a few degrees, 100+ px on screen), so
gaze mode is a hybrid: a glance moves the cursor to the area you look at, then
small head movements fine-tune it. Ordinary short blinks are ignored, and the
cursor is pinned while the eyes are closed, since gaze is unknown then.
"""

import math

import numpy as np

from . import tuning
from .filters import OneEuroFilter2D
from .gestures import DRAG, MOVE, SCROLL, leash_px, since, tune_filter
from .pointer import Pointer

# MediaPipe face landmark indices (478-point model, with irises)
EYES = (
    (33, 133, (468, 469, 470, 471, 472)),    # corners and iris of one eye
    (362, 263, (473, 474, 475, 476, 477)),   # ... and of the other
)
OUTER_CORNERS = (33, 263)
NOSE_TIP = 1

# Modes
NO_FACE = "no_face"
EYES_CLOSED = "eyes_closed"

# Blendshape scores, 0..1. The engine takes the "closed", "mouth open" and "brows up"
# thresholds from tuning.py («Подробнее»); the other side sits a fixed step below.
EYE_OPEN = 0.4          # both eyes below this: open (calibration and gaze use this)
OPEN_BELOW = 0.15       # eyes count as open this far below the "closed" threshold
RELAX_BELOW = 0.2       # mouth closed / brows down this far below their thresholds

# Seconds
CONFIRM_TIME = 0.06     # mouth / eyebrows must hold a state this long (3 frames at 30 per second)
MAX_CLOSE_TIME = 2.0    # eyes closed longer than this: resting (or looking down), not clicking
DOUBLE_CLICK_GAP = 1.5  # second long blink within this -> double click
POST_CLICK_HOLD = 0.6
BLINK_SETTLE = 0.15     # eyes settle after reopening before the cursor moves again
REWIND = 0.1
FACE_LOST_TIMEOUT = 0.3

HEAD_RANGE = (0.18, 0.06)   # head offset (eye-distance units) for half the screen: slow .. fast
NUDGE_SHARE = 0.35          # gaze mode: head fine-tuning speed relative to head mode
WARP_MIN_PX = 120           # gaze mode: glances closer than this do not move the cursor (at 1920 px)
SCROLL_DEADZONE = 0.01      # head tilt (eye-distance units) ignored while scrolling
SCROLL_RATE = 15000         # wheel units per second per unit of tilt, times the scroll speed setting


class FaceFrame:
    """Measurements of one face that do not depend on its size or tilt in the image."""

    def __init__(self, gaze, head, blink, jaw, brow):
        self.gaze = gaze    # iris inside the eyes: x 0..1 from left to right corner, y below the corner line
        self.head = head    # nose tip relative to the middle of the eyes, in eye-distance units
        self.blink = blink  # (left, right) eye closed, 0..1
        self.jaw = jaw      # mouth open, 0..1
        self.brow = brow    # eyebrows raised, 0..1

    @property
    def eyes_open(self):
        return max(self.blink) < EYE_OPEN


def _along(p, a, b):
    """p in the frame of the line a->b: (along, across), in units of |ab|; across > 0 is below."""
    ux, uy = b[0] - a[0], b[1] - a[1]
    w2 = ux * ux + uy * uy or 1e-9
    dx, dy = p[0] - a[0], p[1] - a[1]
    return (dx * ux + dy * uy) / w2, (dy * ux - dx * uy) / w2


def _left_right(a, b):
    return (a, b) if a[0] <= b[0] else (b, a)


def read_face(pts, scores):
    """pts: the 478 face landmarks as (x, y) in pixels of the mirrored image.
    scores: blendshape name -> score."""
    gx = gy = 0.0
    for c1, c2, iris in EYES:
        a, b = _left_right(pts[c1], pts[c2])
        center = (sum(pts[i][0] for i in iris) / len(iris), sum(pts[i][1] for i in iris) / len(iris))
        x, y = _along(center, a, b)
        gx += x / 2
        gy += y / 2
    a, b = _left_right(pts[OUTER_CORNERS[0]], pts[OUTER_CORNERS[1]])
    hx, hy = _along(pts[NOSE_TIP], a, b)
    return FaceFrame(
        gaze=(gx, gy),
        head=(hx - 0.5, hy),
        blink=(scores.get("eyeBlinkLeft", 0.0), scores.get("eyeBlinkRight", 0.0)),
        jaw=scores.get("jawOpen", 0.0),
        brow=scores.get("browInnerUp", 0.0),
    )


class GazeModel:
    """Maps eye position plus head pose to a point on the screen.

    Learned in calibration (calibration.py):
      1. Looking at one dot while turning the head shows how far the eyes
         counter-rotate, so turning the head does not move the estimate.
      2. Looking at 9 dots with the head still fits a quadratic map to the screen.
    """

    def __init__(self, data):
        self.data = data
        self.error = data["error"]   # typical miss in screen pixels, measured on the calibration dots

    def _eyes(self, gaze, head):
        c = self.data["c"]
        return gaze[0] + c[0] * head[0], gaze[1] + c[1] * head[1]

    def _screen(self, ex, ey):
        mean, scale = self.data["mean"], self.data["scale"]
        x, y = (ex - mean[0]) / scale[0], (ey - mean[1]) / scale[1]
        terms = (1.0, x, y, x * x, y * y, x * y)
        return (sum(a * v for a, v in zip(self.data["ax"], terms)),
                sum(a * v for a, v in zip(self.data["ay"], terms)))

    def predict(self, gaze, head):
        return self._screen(*self._eyes(gaze, head))

    @classmethod
    def fit(cls, head_samples, dot_samples):
        """head_samples: [(gaze, head)] looking at one dot while turning the head.
        dot_samples: [((x, y), gaze, head)] looking at the calibration dots.
        Returns the model, or None if there is too little data."""
        c = [0.0, 0.0]
        if len(head_samples) >= 20:
            g = np.array([s[0] for s in head_samples])
            h = np.array([s[1] for s in head_samples])
            for axis in (0, 1):
                hv = h[:, axis] - h[:, axis].mean()
                if hv.std() > 0.005:  # the head really turned
                    c[axis] = -float(hv @ (g[:, axis] - g[:, axis].mean()) / (hv @ hv))

        dots = {}
        for target, gaze, head in dot_samples:
            dots.setdefault(tuple(target), []).append((gaze[0] + c[0] * head[0], gaze[1] + c[1] * head[1]))
        eyes, targets = [], []
        for target, samples in dots.items():
            if len(samples) < 5:
                continue
            e = np.array(samples)
            # Drop glances away from the dot.
            d = np.linalg.norm(e - np.median(e, axis=0), axis=1)
            e = e[d <= max(3 * np.median(d), 1e-4)]
            eyes.append(e)
            targets.append(target)
        if len(eyes) < 6:
            return None

        all_eyes = np.vstack(eyes)
        all_targets = np.vstack([np.repeat([t], len(e), axis=0) for t, e in zip(targets, eyes)]).astype(float)
        mean = all_eyes.mean(axis=0)
        scale = np.maximum(all_eyes.std(axis=0), 1e-6)
        z = (all_eyes - mean) / scale
        a = np.column_stack([np.ones(len(z)), z[:, 0], z[:, 1], z[:, 0] ** 2, z[:, 1] ** 2, z[:, 0] * z[:, 1]])
        ridge = np.diag([0.0, 0.01, 0.01, 0.05, 0.05, 0.05]) * len(z)  # keeps the curve terms modest
        coef = np.linalg.solve(a.T @ a + ridge, a.T @ all_targets)

        model = cls({"c": c, "mean": mean.tolist(), "scale": scale.tolist(),
                     "ax": coef[:, 0].tolist(), "ay": coef[:, 1].tolist(), "error": 0.0})
        misses = [math.dist(model._screen(*np.median(e, axis=0)), t) for e, t in zip(eyes, targets)]
        model.error = model.data["error"] = float(np.sqrt(np.mean(np.square(misses))))
        return model


class FaceEngine:
    """Turns a stream of FaceFrames into mouse actions (see the module docstring)."""

    def __init__(self, settings, screen_w, screen_h, use_gaze):
        self.settings = settings
        self.use_gaze = use_gaze
        self.screen_w, self.screen_h = screen_w, screen_h
        self._px = screen_w / 1920.0
        self._ptr = Pointer(screen_w, screen_h)
        self._head_filter = OneEuroFilter2D()
        self._gaze_filter = OneEuroFilter2D()
        self._center = None        # neutral head position, set from the first frame
        self._model_data = None
        self.model = None
        self._reset()

    def _reset(self):
        self.mode = NO_FACE
        self.progress = 0.0        # eyes shut long enough for a click: 0 .. 1
        self._ptr.reset()
        self._head_filter.reset()
        self._gaze_filter.reset()
        self._anchor = None        # gaze mode: where the last glance put the cursor
        self._nudge_ref = None     # gaze mode: head position at that glance
        self._hold_until = None
        self._eyes_shut = False
        self._shut_start = 0.0
        self._both_time = 0.0      # time both eyes were closed during this blink
        self._wink_time = 0.0      # time exactly one eye was closed
        self._last_click = None    # (t, position) of the last blink click
        self._dragging = False
        self._scrolling = False
        self._mouth_since = None   # when the mouth began to open (while dragging: to close)
        self._brows_since = None   # when the brows went up (while scrolling: down)
        self._scroll_ref = 0.0
        self._wheel = 0.0
        self._lost_since = None
        self._t = None

    def recenter(self):
        """Take the next head position as the neutral one (cursor in the screen centre)."""
        self._center = None

    def release_all(self):
        """Let go of any held button and forget the face (face lost, pause, stop)."""
        actions = [("up", "left")] if self._dragging else []
        self._reset()
        return actions

    def update(self, face, t, cursor_pos=None):
        """Process one camera frame (a FaceFrame, or None when no face is visible)."""
        if face is None:
            if self.mode == NO_FACE:
                return []
            if self._lost_since is None:
                self._lost_since = t
            if t - self._lost_since < FACE_LOST_TIMEOUT:
                return []
            return self.release_all()
        self._lost_since = None
        dt = t - self._t if self._t is not None else 0.0
        self._t = t

        target = self._target(face, t)
        if target is None:
            return []  # gaze mode before calibration
        ptr = self._ptr
        if cursor_pos is None:
            cursor_pos = ptr.sent or target
        moved_by_mouse = (
            self.mode == MOVE and ptr.held is None
            and math.dist(cursor_pos, ptr.sent) > 50 * self._px
        )
        if self.mode == NO_FACE or moved_by_mouse:
            ptr.start(cursor_pos, target)

        actions = []
        self._mouth_and_brows(face, target, t, actions)
        if not self._scrolling:
            self._eyes(face, t, dt, actions)
        if ptr.held is not None and self._hold_until is not None and t >= self._hold_until:
            ptr.release(target)
            self._hold_until = None
        ptr.follow(target, t, leash_px(self.settings, self._px), actions)
        if self._scrolling:
            self._scroll(face, dt, actions)

        if self._dragging:
            self.mode = DRAG
        elif self._scrolling:
            self.mode = SCROLL
        elif self._eyes_shut:
            self.mode = EYES_CLOSED
        else:
            self.mode = MOVE
        self.progress = min(self._both_time / self.settings.blink_time, 1.0) if self._eyes_shut else 0.0
        return actions

    # -- where the cursor should be ------------------------------------------

    def _target(self, face, t):
        s = self.settings
        half = HEAD_RANGE[0] + (HEAD_RANGE[1] - HEAD_RANGE[0]) * s.cursor_speed
        gain = self.screen_w / 2 / half
        if self._center is None:
            self._center = face.head
        tune_filter(self._head_filter, s, self._px)
        head = self._head_filter((face.head[0] - self._center[0]) * gain,
                                 (face.head[1] - self._center[1]) * gain, t)
        if not self.use_gaze:
            return self._clamp(self.screen_w / 2 + head[0], self.screen_h / 2 + head[1])

        if s.gaze_model is not self._model_data:
            self._model_data = s.gaze_model
            self.model = GazeModel(s.gaze_model) if s.gaze_model else None
            self._anchor = None
        if self.model is None:
            return None
        # With closed eyes the gaze is unknown: keep the last glance.
        if face.eyes_open or self._anchor is None:
            self._gaze_filter.min_cutoff = 1.5 - 1.2 * s.smoothing
            self._gaze_filter.beta = (0.01 - 0.008 * s.smoothing) / self._px
            gaze = self._gaze_filter(*self.model.predict(face.gaze, face.head), t)
            warp = max(WARP_MIN_PX * self._px, 1.3 * self.model.error)
            if self._anchor is None or math.dist(gaze, self._anchor) > warp:
                self._anchor = gaze
                self._nudge_ref = head
        return self._clamp(self._anchor[0] + (head[0] - self._nudge_ref[0]) * NUDGE_SHARE,
                           self._anchor[1] + (head[1] - self._nudge_ref[1]) * NUDGE_SHARE)

    def _clamp(self, x, y):
        # A little past the edges, so the leashed cursor can still reach them.
        m = 2 * leash_px(self.settings, self._px)
        return min(max(x, -m), self.screen_w - 1 + m), min(max(y, -m), self.screen_h - 1 + m)

    # -- gestures ---------------------------------------------------------

    def _mouth_and_brows(self, face, target, t, actions):
        s = self.settings
        mouth_open, brows_up = tuning.get(s, "mouth_open"), tuning.get(s, "brows_up")
        confirm = CONFIRM_TIME - 1e-6
        if not self._scrolling:
            if self._dragging:
                self._mouth_since = since(self._mouth_since, face.jaw < mouth_open - RELAX_BELOW, t)
                if self._mouth_since is not None and t - self._mouth_since >= confirm:
                    actions.append(("up", "left"))
                    self._dragging = False
                    self._mouth_since = None
            else:
                self._mouth_since = since(self._mouth_since, face.jaw > mouth_open, t)
                if self._mouth_since is not None and t - self._mouth_since >= confirm:
                    actions.append(("down", "left"))
                    self._dragging = True
                    self._mouth_since = None
        if self._dragging:
            return
        if self._scrolling:
            self._brows_since = since(self._brows_since, face.brow < brows_up - RELAX_BELOW, t)
            if self._brows_since is not None and t - self._brows_since >= confirm:
                self._scrolling = False
                self._brows_since = None
                self._ptr.release(target)
                self._hold_until = None
        else:
            self._brows_since = since(self._brows_since, face.brow > brows_up, t)
            if self._brows_since is not None and t - self._brows_since >= confirm:
                self._scrolling = True
                self._brows_since = None
                self._eyes_shut = False
                if self._ptr.held is None:
                    self._ptr.hold(self._ptr.cursor, actions)
                self._hold_until = None
                self._scroll_ref = face.head[1]
                self._wheel = 0.0

    def _scroll(self, face, dt, actions):
        # Tilt the head away from where it was when the eyebrows went up;
        # the further the tilt, the faster the scroll.
        d = face.head[1] - self._scroll_ref
        speed = max(0.0, abs(d) - SCROLL_DEADZONE) * SCROLL_RATE * self.settings.scroll_speed
        direction = 1 if self.settings.invert_scroll else -1   # head up -> scroll up
        self._wheel += direction * math.copysign(speed, d) * dt
        if abs(self._wheel) >= tuning.get(self.settings, "wheel_step"):
            amount = int(self._wheel)
            self._wheel -= amount
            actions.append(("wheel", amount))

    def _eyes(self, face, t, dt, actions):
        low, high = min(face.blink), max(face.blink)
        closed_at = tuning.get(self.settings, "eye_closed")
        open_below = closed_at - OPEN_BELOW
        if not self._eyes_shut:
            if high >= open_below:
                # Eyes start to close: pin the cursor where it was a moment ago.
                self._eyes_shut = True
                self._shut_start = t
                self._both_time = self._wink_time = 0.0
                if self._ptr.held is None:
                    self._ptr.hold(self._ptr.position_before(t - REWIND), actions)
                self._hold_until = None
            return

        if low > closed_at:
            self._both_time += dt
        elif high > closed_at and low < open_below:
            self._wink_time += dt
        shut_for = t - self._shut_start
        if high >= open_below:
            if shut_for > MAX_CLOSE_TIME and self._hold_until is None:
                self._hold_until = t  # resting eyes or looking down: let the cursor move again
            return

        self._eyes_shut = False
        settle = BLINK_SETTLE
        if not self._dragging and shut_for <= MAX_CLOSE_TIME:
            if self._both_time >= self.settings.blink_time:
                self._blink_click(t, actions)
                settle = POST_CLICK_HOLD
            elif self._wink_time >= tuning.seconds(self.settings, "wink_ms"):
                actions.append(("click", "right"))
                settle = POST_CLICK_HOLD
        if self._ptr.held is not None:
            self._hold_until = t + settle

    def _blink_click(self, t, actions):
        last = self._last_click
        if (last is not None and t - last[0] <= DOUBLE_CLICK_GAP
                and math.dist(last[1], self._ptr.cursor) < 60 * self._px):
            # Second long blink: double click on the same spot as the first.
            self._ptr.hold(last[1], actions)
            actions += [("click", "left"), ("click", "left")]
            self._last_click = None
        else:
            actions.append(("click", "left"))
            self._last_click = (t, self._ptr.cursor)
