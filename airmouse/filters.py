"""Smoothing filters for the cursor."""

import math


def _alpha(cutoff, dt):
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter2D:
    """One Euro filter (Casiez et al., CHI 2012) for a 2D point.

    The cutoff frequency rises with speed: when the hand moves slowly the point
    is smoothed heavily (tremor disappears), when it moves fast it is smoothed
    lightly (no lag). Speed is measured in 2D so both axes get the same cutoff
    and diagonal moves stay straight.
    """

    def __init__(self, min_cutoff=1.0, beta=0.01, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self._x = self._y = None
        self._vx = self._vy = 0.0
        self._t = None

    def __call__(self, x, y, t):
        if self._x is None:
            self._x, self._y, self._t = x, y, t
            return x, y
        dt = t - self._t
        if dt <= 0:
            return self._x, self._y
        self._t = t
        a_d = _alpha(self.d_cutoff, dt)
        self._vx += a_d * ((x - self._x) / dt - self._vx)
        self._vy += a_d * ((y - self._y) / dt - self._vy)
        a = _alpha(self.min_cutoff + self.beta * math.hypot(self._vx, self._vy), dt)
        self._x += a * (x - self._x)
        self._y += a * (y - self._y)
        return self._x, self._y
