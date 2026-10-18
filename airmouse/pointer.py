"""Cursor motion shared by the hand and face engines: glide, leash and hold."""

import math
from collections import deque

GLIDE_TIME = 0.15   # how quickly the cursor catches up after a jump of the target


class Pointer:
    """Moves the cursor toward a target position, one frame at a time.

    - Glide: when the target jumps (hand appears, a hold ends) the cursor
      slides over instead of teleporting.
    - Leash: the cursor is pulled along on a short string, so shaking smaller
      than the string never reaches the screen.
    - Hold: the cursor can be pinned in place for a click, and remembers where
      it was a moment ago so the click can go there.
    """

    def __init__(self, screen_w, screen_h):
        self.screen_w, self.screen_h = screen_w, screen_h
        self.reset()

    def reset(self):
        self.cursor = None     # where the cursor is, float pixels
        self.sent = None       # last position sent to Windows
        self.held = None       # position the cursor is pinned to, or None
        self._offset = (0.0, 0.0)
        self._history = deque(maxlen=30)   # (t, x, y) of recent cursor positions
        self._t = None

    def start(self, cursor_pos, target):
        """Begin from where the Windows cursor is now and glide over to the target."""
        self.cursor = (float(cursor_pos[0]), float(cursor_pos[1]))
        self.sent = (int(cursor_pos[0]), int(cursor_pos[1]))
        self._offset = (cursor_pos[0] - target[0], cursor_pos[1] - target[1])

    def hold(self, pos, actions):
        self.held = pos
        self.cursor = pos
        self._send(actions)

    def release(self, target):
        # Stay where it was held and glide back to the target.
        self._offset = (self.held[0] - target[0], self.held[1] - target[1])
        self.held = None

    def position_before(self, when):
        for t, x, y in reversed(self._history):
            if t <= when:
                return x, y
        return self._history[0][1:] if self._history else self.cursor

    def follow(self, target, t, leash, actions):
        """Move toward the target (unless held). Call once per frame."""
        dt = t - self._t if self._t is not None else None
        self._t = t
        if self.held is not None:
            return
        k = math.exp(-dt / GLIDE_TIME) if dt is not None else 1.0
        self._offset = (self._offset[0] * k, self._offset[1] * k)
        tx, ty = target[0] + self._offset[0], target[1] + self._offset[1]
        cx, cy = self.cursor
        d = math.hypot(tx - cx, ty - cy)
        if d > leash:
            pull = (d - leash) / d
            cx += (tx - cx) * pull
            cy += (ty - cy) * pull
        self.cursor = (min(max(cx, 0.0), self.screen_w - 1.0), min(max(cy, 0.0), self.screen_h - 1.0))
        self._history.append((t, *self.cursor))
        self._send(actions)

    def _send(self, actions):
        x = int(round(min(max(self.cursor[0], 0), self.screen_w - 1)))
        y = int(round(min(max(self.cursor[1], 0), self.screen_h - 1)))
        if (x, y) != self.sent:
            self.sent = (x, y)
            actions.append(("move", x, y))
