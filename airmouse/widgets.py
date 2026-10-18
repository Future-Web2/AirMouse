"""Liquid Glass widgets. Every frame each widget draws itself into the window image.

Positions are in logical pixels; `s` (the display scale) turns them into real pixels.
Input arrives in logical pixels too: press / drag / release, and `hover` is set by the window.
"""

import math

from .glass import blit_text, capsule, ease, q, shape

ACCENT = (64, 140, 255)
TEXT = (245, 247, 250)
MUTED = (178, 186, 200)
DIM = (120, 126, 140)


class Widget:
    def __init__(self, x, y, w, h):
        self.rect = (x, y, w, h)
        self.hover = False
        self.pressed = False
        self.enabled = True

    def hit(self, x, y):
        rx, ry, rw, rh = self.rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def press(self, x, y):
        self.pressed = True

    def drag(self, x, y):
        pass

    def release(self, x, y):
        self.pressed = False

    def tick(self, dt):
        pass

    def draw(self, frame, s):
        pass


class Button(Widget):
    def __init__(self, x, y, w, h, label, on_click, style="button", size=16):
        super().__init__(x, y, w, h)
        self.label, self.on_click, self.style, self.size = label, on_click, style, size

    def release(self, x, y):
        if self.pressed and self.enabled and self.hit(x, y):
            self.on_click()
        self.pressed = False

    def draw(self, frame, s):
        x, y, w, h = self.rect
        k = 0.97 if self.pressed else 1.0
        g = shape(q(w * k * s), q(h * k * s), q(h * k * s / 2), self.style)
        g.draw(frame, (x + w / 2) * s - g.w / 2, (y + h / 2) * s - g.h / 2, lift=16 if self.hover else 0)
        blit_text(frame, self.label, (x + w / 2) * s, (y + h / 2) * s, "semibold", self.size * s,
                  TEXT if self.enabled else DIM, "mm")


class Segmented(Widget):
    """Choice of options; a glass pill slides (and stretches, like liquid) to the selected one."""

    INSET = 4

    def __init__(self, x, y, w, h, options, value, on_change):
        super().__init__(x, y, w, h)
        self.options, self.on_change = options, on_change
        self.index = [k for k, _ in options].index(value)
        self.pos, self.vel = float(self.index), 0.0

    @property
    def value(self):
        return self.options[self.index][0]

    def set(self, value):
        self.index = [k for k, _ in self.options].index(value)

    def press(self, x, y):
        rx, _, rw, _ = self.rect
        seg = (rw - 2 * self.INSET) / len(self.options)
        i = min(max(int((x - rx - self.INSET) // seg), 0), len(self.options) - 1)
        if i != self.index:
            self.index = i
            self.on_change(self.value)

    def tick(self, dt):
        # A slightly bouncy spring.
        k = 260.0
        acc = k * (self.index - self.pos) - 2 * math.sqrt(k) * 0.62 * self.vel
        self.vel += acc * dt
        self.pos += self.vel * dt
        if abs(self.index - self.pos) < 1e-3 and abs(self.vel) < 1e-3:
            self.pos, self.vel = float(self.index), 0.0

    def draw(self, frame, s):
        x, y, w, h = self.rect
        capsule(frame, x * s, y * s, w * s, h * s, (255, 255, 255), alpha=0.07)
        inset = self.INSET
        seg = (w - 2 * inset) / len(self.options)
        stretch = min(0.35, abs(self.vel) * 0.09)
        iw, ih = seg * (1 + stretch), (h - 2 * inset) * (1 - stretch * 0.3)
        cx, cy = x + inset + (self.pos + 0.5) * seg, y + h / 2
        g = shape(q(iw * s), q(ih * s), q(ih * s / 2), "pill")
        g.draw(frame, cx * s - g.w / 2, cy * s - g.h / 2, lift=10 if self.hover else 0)
        for i, (_key, label) in enumerate(self.options):
            blit_text(frame, label, (x + inset + (i + 0.5) * seg) * s, cy * s, "semibold", 15 * s,
                      TEXT if i == self.index else MUTED, "mm")


class Toggle(Widget):
    def __init__(self, x, y, value, on_change):
        super().__init__(x, y, 52, 30)
        self.value, self.on_change = value, on_change
        self.t = 1.0 if value else 0.0

    def set(self, value):
        self.value = value

    def release(self, x, y):
        if self.pressed and self.hit(x, y):
            self.value = not self.value
            self.on_change(self.value)
        self.pressed = False

    def tick(self, dt):
        target = 1.0 if self.value else 0.0
        step = dt * 6
        self.t = min(target, self.t + step) if self.t < target else max(target, self.t - step)

    def draw(self, frame, s):
        x, y, w, h = self.rect
        e = ease(self.t)
        track = tuple(a + (b - a) * e for a, b in zip((78, 84, 98), ACCENT))
        capsule(frame, x * s, y * s, w * s, h * s, track)
        kh = h - 6
        kw = kh * (1.3 if self.pressed else 1.0)   # the knob stretches while held
        kx = x + 3 + e * (w - 6 - kw)
        g = shape(q(kw * s), q(kh * s), q(kh * s / 2), "knob")
        g.draw(frame, kx * s, (y + 3) * s, tint_alpha=0.55 if self.pressed else 0.92)


class Slider(Widget):
    """Label, value and a track; the knob turns into a clear glass lens while dragged."""

    def __init__(self, x, y, w, label, lo, hi, value, fmt, on_change):
        super().__init__(x, y, w, 52)
        self.label, self.lo, self.hi, self.value = label, lo, hi, value
        self.fmt, self.on_change = fmt, on_change
        self.grow = 0.0

    def _track(self):
        x, y, w, _ = self.rect
        return x + 11, y + 36, w - 22

    def _set(self, x):
        tx, _, tl = self._track()
        k = min(max((x - tx) / tl, 0.0), 1.0)
        value = self.lo + k * (self.hi - self.lo)
        if value != self.value:
            self.value = value
            self.on_change(value)

    def press(self, x, y):
        self.pressed = True
        self._set(x)

    def drag(self, x, y):
        self._set(x)

    def tick(self, dt):
        target = 1.0 if self.pressed else 0.0
        step = dt * 8
        self.grow = min(target, self.grow + step) if self.grow < target else max(target, self.grow - step)

    def draw(self, frame, s):
        x, y, w, _ = self.rect
        blit_text(frame, self.label, x * s, (y + 10) * s, "regular", 14 * s, TEXT, "lm")
        blit_text(frame, self.fmt(self.value), (x + w) * s, (y + 10) * s, "regular", 14 * s, MUTED, "rm")
        tx, ty, tl = self._track()
        k = (self.value - self.lo) / (self.hi - self.lo)
        capsule(frame, tx * s, (ty - 3) * s, tl * s, 6 * s, (255, 255, 255), alpha=0.16)
        capsule(frame, tx * s, (ty - 3) * s, max(6, k * tl) * s, 6 * s, ACCENT)
        e = ease(self.grow)
        kh = 22 + 12 * e
        kw = kh * (1 + 0.3 * e)
        g = shape(q(kw * s), q(kh * s), q(kh * s / 2), "knob")
        g.draw(frame, (tx + k * tl) * s - g.w / 2, ty * s - g.h / 2, tint_alpha=0.92 - 0.8 * e)


class Stepper(Widget):
    """‹ value › for a small whole number (the camera)."""

    def __init__(self, x, y, value, lo, hi, on_change):
        super().__init__(x, y, 104, 32)
        self.value, self.lo, self.hi, self.on_change = value, lo, hi, on_change

    def press(self, x, y):
        rx, _, rw, _ = self.rect
        step = -1 if x < rx + rw / 3 else 1 if x > rx + rw * 2 / 3 else 0
        value = min(max(self.value + step, self.lo), self.hi)
        if value != self.value:
            self.value = value
            self.on_change(value)

    def draw(self, frame, s):
        x, y, w, h = self.rect
        capsule(frame, x * s, y * s, w * s, h * s, (255, 255, 255), alpha=0.10 if not self.hover else 0.16)
        cy = (y + h / 2) * s
        blit_text(frame, "‹", (x + 16) * s, cy, "semibold", 20 * s, MUTED if self.value > self.lo else DIM, "mm")
        blit_text(frame, str(self.value), (x + w / 2) * s, cy, "semibold", 15 * s, TEXT, "mm")
        blit_text(frame, "›", (x + w - 16) * s, cy, "semibold", 20 * s, MUTED if self.value < self.hi else DIM, "mm")
