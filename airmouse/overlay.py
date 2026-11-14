"""Windows that float over the desktop (on-screen widgets, the cursor ring), and their pictures.

LayeredWindow shows a picture with transparency over all windows and never takes the keyboard
focus; it is winoverlay.py on Windows and linuxwindows.py on Linux. Both take the same
premultiplied BGRA pictures and report the mouse the same way:

    LayeredWindow(click_through=False, on_mouse=None, hand_at=None)
        .show(bgra, x, y), .move(x, y), .hide(), .destroy(), .visible, .x, .y

Layer is the picture: colour and coverage in float32, painted with "over".
"""

import math
import sys
from functools import lru_cache

import cv2
import numpy as np

from .glass import LIGHT, _sprite, rounded_rect_sdf

if sys.platform == "win32":
    from .winoverlay import LayeredWindow, cursor_pos  # noqa: F401
else:
    from .linuxwindows import LayeredWindow, cursor_pos  # noqa: F401


# -- drawing ------------------------------------------------------------------------------

@lru_cache(maxsize=128)
def round_mask(w, h, r):
    """Coverage of a w x h rounded rectangle, anti-aliased."""
    return np.clip(0.5 - rounded_rect_sdf(w, h, r), 0, 1).astype(np.float32)


@lru_cache(maxsize=64)
def rim_light(w, h, r):
    """A thin bright edge, brighter where it faces the light (top left), as on the glass panels."""
    d = rounded_rect_sdf(w, h, r)
    gy, gx = np.gradient(d)
    length = np.hypot(gx, gy) + 1e-6
    facing = (gx / length) * LIGHT[0] + (gy / length) * LIGHT[1]
    line = np.clip(1.2 - np.maximum(-d, 0) / 1.3, 0, 1) * np.clip(0.5 - d, 0, 1)
    return (line * (0.25 + 0.75 * np.maximum(facing, 0) ** 2)).astype(np.float32)


@lru_cache(maxsize=64)
def soft_shadow(w, h, r, blur, offset):
    """(coverage, pad): a blurred copy of the shape, pad pixels larger on each side, moved down by offset."""
    pad = int(blur * 3 + offset + 2)
    d = rounded_rect_sdf(w, h, r, pad=pad)
    mask = np.clip(0.5 - d, 0, 1).astype(np.float32)
    shifted = np.zeros_like(mask)
    shifted[offset:] = mask[:-offset] if offset else mask
    return cv2.GaussianBlur(shifted, (0, 0), blur), pad


@lru_cache(maxsize=128)
def _solid(h, w, color):
    """An opaque BGRA image of one colour (read-only, shared)."""
    image = np.empty((h, w, 4), np.uint8)
    image[:] = (color[2], color[1], color[0], 255)
    image.flags.writeable = False
    return image


class Layer:
    """A picture with transparency, kept as premultiplied BGRA (what UpdateLayeredWindow takes).

    Everything is painted "over" what is there: dst = colour * a + dst * (1 - a),
    alpha included, with a = coverage x opacity; one OpenCV call per paint.
    """

    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.pixels = np.zeros((self.h, self.w, 4), np.uint8)

    def copy(self):
        other = Layer.__new__(Layer)
        other.w, other.h, other.pixels = self.w, self.h, self.pixels.copy()
        return other

    @property
    def alpha(self):
        """Coverage 0..1 (for checks; drawing never needs it)."""
        return self.pixels[..., 3].astype(np.float32) * np.float32(1 / 255)

    def paint(self, x, y, coverage, color, opacity=1.0):
        """Lay colour over the picture where coverage (h, w; 0..1) says, at (x, y).

        color: (r, g, b) 0..255, or an RGB uint8 image the size of coverage.
        """
        x, y = int(round(x)), int(round(y))
        h, w = coverage.shape
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, self.w), min(y + h, self.h)
        if x0 >= x1 or y0 >= y1 or opacity <= 0:
            return
        sl = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
        a = coverage[sl] if opacity >= 1 else coverage[sl] * np.float32(opacity)
        if isinstance(color, np.ndarray):
            source = cv2.cvtColor(np.ascontiguousarray(color[sl]), cv2.COLOR_RGB2BGRA)
        else:
            source = _solid(y1 - y0, x1 - x0, tuple(int(c) for c in color))
        region = self.pixels[y0:y1, x0:x1]
        cv2.blendLinear(region, source, 1 - a, a, dst=region)

    def bgra(self):
        """The picture as premultiplied BGRA (h, w, 4), ready for LayeredWindow.show."""
        return self.pixels

    # -- shapes ---------------------------------------------------------------------------

    def round_rect(self, x, y, w, h, r, color, opacity=1.0):
        w, h = int(round(w)), int(round(h))
        if w > 0 and h > 0:
            self.paint(x, y, round_mask(w, h, int(round(r))), color, opacity)

    def panel(self, x, y, w, h, r, color=(16, 18, 28), opacity=0.86, shadow=0.35, rim=0.55, blur=5.0, offset=3):
        """The background of a widget: dark frosted glass with a lit edge and a soft shadow.

        The shadow reaches about 3 x blur + offset pixels beyond the panel; leave that much room.
        """
        x, y, w, h, r = (int(round(v)) for v in (x, y, w, h, r))
        if shadow:
            coverage, pad = soft_shadow(w, h, r, float(blur), int(round(offset)))
            self.paint(x - pad, y - pad, coverage, (0, 0, 0), shadow)
        self.paint(x, y, round_mask(w, h, r), color, opacity)
        if rim:
            self.paint(x, y, rim_light(w, h, r), (255, 255, 255), rim)

    def text(self, text, x, y, size, color, weight="regular", anchor="lt", opacity=1.0, max_width=None):
        """One line of text; anchor as in glass.blit_text. Too long for max_width: shortened with «…»."""
        if not text:
            return 0
        size = int(round(size))
        coverage, _inv, _col, ascent = _sprite(text, weight, size, tuple(color))
        if max_width is not None and coverage.shape[1] > max_width:
            while len(text) > 1 and coverage.shape[1] > max_width:
                text = text[:-1]
                coverage, _inv, _col, ascent = _sprite(text.rstrip() + "…", weight, size, tuple(color))
        h, w = coverage.shape
        hx = {"l": 0, "m": w / 2, "r": w}[anchor[0]]
        vy = {"t": 0, "m": 1 + ascent - 0.36 * size, "b": h}[anchor[1]]
        self.paint(x - hx, y - vy, coverage, color, opacity)
        return w

    def icon(self, glyph, cx, cy, size, color, opacity=1.0):
        """A Segoe Fluent Icons glyph centred at (cx, cy)."""
        size = int(round(size))
        coverage, _inv, _col, _ascent = _sprite(glyph, "icons", size, tuple(color))
        h, w = coverage.shape
        self.paint(cx - w / 2, cy - h / 2, coverage, color, opacity)

    def image(self, rgb, x, y, w, h, r=0):
        """An RGB image scaled into the box, with rounded corners."""
        w, h = int(round(w)), int(round(h))
        if w <= 0 or h <= 0:
            return
        scaled = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        self.paint(x, y, round_mask(w, h, int(round(r))), scaled)

    def _shape(self, x0, y0, x1, y1, draw):
        """Coverage drawn by draw(mask, ox, oy) with OpenCV in the box (sub-pixel: coordinates x16)."""
        x0, y0 = int(math.floor(x0)) - 2, int(math.floor(y0)) - 2
        x1, y1 = int(math.ceil(x1)) + 2, int(math.ceil(y1)) + 2
        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        draw(mask, x0, y0)
        return x0, y0, mask.astype(np.float32) * np.float32(1 / 255)

    def circle(self, cx, cy, r, color, opacity=1.0):
        x, y, coverage = self._shape(cx - r, cy - r, cx + r, cy + r, lambda m, ox, oy: cv2.circle(
            m, (int((cx - ox) * 16), int((cy - oy) * 16)), int(r * 16), 255, -1, cv2.LINE_AA, 4))
        self.paint(x, y, coverage, color, opacity)

    def arc(self, cx, cy, r, width, color, opacity=1.0, start=0.0, extent=360.0):
        """A ring of the given line width; start and extent in degrees, clockwise from the top."""
        if extent <= 0:
            return
        o = r + width

        def draw(m, ox, oy):
            centre = (int((cx - ox) * 16), int((cy - oy) * 16))
            cv2.ellipse(m, centre, (int(r * 16), int(r * 16)), -90, start, start + min(extent, 360.0), 255,
                        max(1, int(round(width))), cv2.LINE_AA, 4)
        x, y, coverage = self._shape(cx - o, cy - o, cx + o, cy + o, draw)
        self.paint(x, y, coverage, color, opacity)

    def capsule(self, x, y, w, h, color, opacity=1.0):
        """A filled pill (a rounded bar), at fractional coordinates."""
        r = min(w, h) / 2

        def draw(m, ox, oy):
            for cx in (x + r, x + w - r):
                cv2.circle(m, (int((cx - ox) * 16), int((y + r - oy) * 16)), int(r * 16), 255, -1, cv2.LINE_AA, 4)
            if w > 2 * r:
                cv2.rectangle(m, (int((x + r - ox) * 16), int((y - oy) * 16)),
                              (int((x + w - r - ox) * 16), int((y + h - oy) * 16)), 255, -1, cv2.LINE_AA, 4)
        px, py, coverage = self._shape(x, y, x + w, y + h, draw)
        self.paint(px, py, coverage, color, opacity)

    def polyline(self, points, color, width=2.0, opacity=1.0):
        """A smooth line through (x, y) points."""
        if len(points) < 2:
            return
        xs, ys = [p[0] for p in points], [p[1] for p in points]

        def draw(m, ox, oy):
            pts = np.array([[(px - ox) * 16, (py - oy) * 16] for px, py in points], np.int32)
            cv2.polylines(m, [pts], False, 255, max(1, int(round(width))), cv2.LINE_AA, 4)
        x, y, coverage = self._shape(min(xs) - width, min(ys) - width, max(xs) + width, max(ys) + width, draw)
        self.paint(x, y, coverage, color, opacity)
