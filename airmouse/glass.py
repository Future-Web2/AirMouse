"""Liquid Glass rendering: frosted, refracting glass shapes with lit edges.

Everything draws into RGB numpy images (uint8, H x W x 3) with OpenCV, so the
same code renders the app window and the promo video.

A glass shape is a rounded rectangle described by its signed distance field.
From it we get the anti-aliased mask; a bezel where the glass bends what is
behind it like a thick lens (with a little colour dispersion); a rim light
that is brighter on the side facing the light; a soft sheen; a drop shadow.
"""

import math
import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

LIGHT = (-0.55, -0.83)   # direction the light comes from: top left

STYLES = {
    # big panels with text on them: frosted and slightly dark, so text stays readable
    "panel": dict(blur=16, refraction=1.0, tint=(12, 14, 22), tint_alpha=0.5, saturation=1.4, rim=0.9, sheen=0.05,
                  shadow=0.3),
    # buttons: clearer glass that visibly bends what is behind
    "button": dict(blur=5, refraction=1.3, dispersion=0.15, tint=(255, 255, 255), tint_alpha=0.10,
                   saturation=1.4, rim=1.0, sheen=0.10),
    "accent": dict(blur=5, refraction=1.3, dispersion=0.15, tint=(40, 118, 255), tint_alpha=0.62,
                   saturation=1.3, rim=1.1, sheen=0.16),
    "danger": dict(blur=5, refraction=1.3, dispersion=0.15, tint=(235, 64, 90), tint_alpha=0.58,
                   saturation=1.3, rim=1.1, sheen=0.16),
    # the moving pill of a segmented control: almost clear, strong lens
    "pill": dict(blur=1.5, refraction=1.8, dispersion=0.3, tint=(255, 255, 255), tint_alpha=0.14,
                 saturation=1.5, rim=1.3, sheen=0.12),
    # switch and slider knobs: white at rest, a clear lens while dragged (tint_alpha set when drawing)
    "knob": dict(blur=0, refraction=2.2, dispersion=0.35, tint=(255, 255, 255), tint_alpha=0.92,
                 saturation=1.5, rim=1.2, sheen=0.10, shadow=0.35),
}


def rounded_rect_sdf(w, h, r, pad=0):
    """Signed distance (px) to a w x h rounded rectangle, on a (h + 2pad) x (w + 2pad) grid."""
    ys, xs = np.mgrid[0:h + 2 * pad, 0:w + 2 * pad].astype(np.float32)
    px = xs + 0.5 - pad - w / 2
    py = ys + 0.5 - pad - h / 2
    r = min(r, w / 2, h / 2)
    qx = np.abs(px) - (w / 2 - r)
    qy = np.abs(py) - (h / 2 - r)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside - r


def _crop(frame, x, y, w, h):
    """frame[y:y+h, x:x+w], extending the edge pixels where the box leaves the frame."""
    fh, fw = frame.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, fw), min(y + h, fh)
    if x0 >= x1 or y0 >= y1:
        return np.zeros((h, w, 3), np.uint8)
    part = frame[y0:y1, x0:x1]
    if (x0, y0, x1, y1) == (x, y, x + w, y + h):
        return part
    return cv2.copyMakeBorder(part, y0 - y, y + h - y1, x0 - x, x + w - x1, cv2.BORDER_REPLICATE)


class Glass:
    """One glass shape of a fixed size; draw it anywhere, any number of times."""

    def __init__(self, w, h, radius, *, blur=10.0, refraction=1.0, dispersion=0.0, tint=(255, 255, 255),
                 tint_alpha=0.1, saturation=1.3, rim=1.0, sheen=0.08, shadow=0.0):
        self.w, self.h = w, h = max(int(round(w)), 2), max(int(round(h)), 2)
        radius = min(radius, w / 2, h / 2)
        self.blur, self.tint, self.tint_alpha, self.saturation = blur, tint, tint_alpha, saturation

        d = rounded_rect_sdf(w, h, radius)
        self.mask = np.clip(0.5 - d, 0, 1).astype(np.float32)
        self.mask_inv = 1 - self.mask
        gy, gx = np.gradient(d)
        length = np.hypot(gx, gy) + 1e-6
        nx, ny = gx / length, gy / length          # outward normal
        depth = np.maximum(-d, 0)                  # distance inside from the edge

        # Bezel: near the edge sample the background further out, so the rim
        # shows what is beyond the edge squeezed inward, like a thick lens.
        bezel = max(min(radius * 0.9, min(w, h) * 0.45), 2.0)
        t = np.clip(1 - depth / bezel, 0, 1)
        disp = refraction * bezel * 0.55 * t ** 2.2
        dx, dy = nx * disp, ny * disp

        # Rim light: a crisp line plus a soft inner glow, brighter facing the light.
        facing = nx * LIGHT[0] + ny * LIGHT[1]
        light = 0.3 + 0.9 * np.maximum(facing, 0) ** 2 + 0.5 * np.maximum(-facing, 0) ** 2
        line = np.clip(1.2 - depth / 1.3, 0, 1)
        glow = np.clip(1 - depth / (bezel * 0.6), 0, 1) ** 3 * 0.22
        ys = np.arange(h, dtype=np.float32)[:, None] / h
        top_sheen = sheen * np.clip(1 - ys / 0.5, 0, 1) ** 2
        highlight = ((line * 0.75 + glow) * light * rim + top_sheen) * self.mask
        self._highlight = cv2.cvtColor(np.clip(highlight * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2RGB)

        # Where to sample the (downscaled, blurred) background for each output pixel.
        self.f = 4 if blur >= 8 else 2 if blur >= 3 else 1
        self.pad = int(math.ceil(disp.max() * (1 + dispersion) + 3 * blur + 2))
        cw = int(math.ceil((w + 2 * self.pad) / self.f) * self.f)
        ch = int(math.ceil((h + 2 * self.pad) / self.f) * self.f)
        self._crop_size = (cw, ch)
        ys_, xs_ = np.mgrid[0:h, 0:w].astype(np.float32)
        self._maps = []
        for k in ((1 - dispersion, 1.0, 1 + dispersion) if dispersion else (1.0,)):
            u = ((xs_ + self.pad + dx * k) + 0.5) / self.f - 0.5
            v = ((ys_ + self.pad + dy * k) + 0.5) / self.f - 0.5
            self._maps.append(cv2.convertMaps(u.astype(np.float32), v.astype(np.float32), cv2.CV_16SC2))

        self._tints = {}
        self.shadow = shadow
        if shadow:
            self._make_shadow(radius, opacity=shadow, blur=min(18.0, max(3.0, min(w, h) * 0.12)),
                              offset=min(10, max(2, h // 14)))

    def _make_shadow(self, radius, opacity, blur, offset):
        m = self.shadow_pad = int(blur * 3 + offset + 2)
        d = rounded_rect_sdf(self.w, self.h, radius, pad=m)
        mask = np.clip(0.5 - d, 0, 1).astype(np.float32)
        shifted = np.zeros_like(mask)
        shifted[offset:] = mask[:-offset]
        alpha = cv2.GaussianBlur(shifted, (0, 0), blur) * opacity
        self._shadow_keep = (1 - alpha).astype(np.float32)
        self._shadow_dark = alpha.astype(np.float32)
        self._black = np.zeros((*alpha.shape, 3), np.uint8)

    def draw_shadow(self, frame, x, y):
        if not self.shadow:
            return
        m = self.shadow_pad
        blend(frame, int(round(x)) - m, int(round(y)) - m, self._black, self._shadow_keep, self._shadow_dark)

    def draw(self, frame, x, y, lift=0.0, tint_alpha=None, tint=None):
        """Composite the glass onto frame with its top-left corner at (x, y)."""
        x, y = int(round(x)), int(round(y))
        fh, fw = frame.shape[:2]
        if x >= fw or y >= fh or x + self.w <= 0 or y + self.h <= 0:
            return
        if self.shadow:
            self.draw_shadow(frame, x, y)
        cw, ch = self._crop_size
        src = _crop(frame, x - self.pad, y - self.pad, cw, ch)
        if self.f > 1:
            src = cv2.resize(src, (cw // self.f, ch // self.f), interpolation=cv2.INTER_AREA)
        if self.blur > 0.5:
            src = cv2.GaussianBlur(src, (0, 0), self.blur / self.f)
        if len(self._maps) == 3:   # colour dispersion: red and blue bend a little differently
            channels = [cv2.extractChannel(cv2.remap(src, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE), c)
                        for c, (m1, m2) in enumerate(self._maps)]
            glass = cv2.merge(channels)
        else:
            glass = cv2.remap(src, *self._maps[0], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

        gray = cv2.cvtColor(cv2.cvtColor(glass, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
        glass = cv2.addWeighted(glass, self.saturation, gray, 1 - self.saturation, lift)
        ta = self.tint_alpha if tint_alpha is None else tint_alpha
        if ta > 0:
            glass = cv2.addWeighted(glass, 1 - ta, self._tint_image(tint or self.tint), ta, 0)
        glass = cv2.add(glass, self._highlight)
        blend(frame, x, y, glass, self.mask_inv, self.mask)

    def _tint_image(self, color):
        img = self._tints.get(color)
        if img is None:
            img = self._tints[color] = np.full((self.h, self.w, 3), color, np.uint8)
        return img


def blend(frame, x, y, image, keep, add):
    """frame = frame * keep + image * add over the part of image that lies inside frame."""
    fh, fw = frame.shape[:2]
    h, w = keep.shape
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, fw), min(y + h, fh)
    if x0 >= x1 or y0 >= y1:
        return
    sx, sy = x0 - x, y0 - y
    sl = (slice(sy, sy + y1 - y0), slice(sx, sx + x1 - x0))
    frame[y0:y1, x0:x1] = cv2.blendLinear(frame[y0:y1, x0:x1], image[sl], keep[sl], add[sl])


@lru_cache(maxsize=256)
def shape(w, h, r, style):
    """Cached glass shape; pass whole pixels (sizes are rounded by the callers)."""
    return Glass(w, h, r, **STYLES[style])


def q(v):
    """Round a size to an even number of pixels, so animated sizes reuse cached shapes."""
    return max(2, int(round(v / 2)) * 2)


# -- background -----------------------------------------------------------

class LiquidBackdrop:
    """Slowly flowing colour blobs on a dark base: the 'wallpaper' behind the glass."""

    COLORS = ((0.25, 0.43, 1.0), (0.66, 0.31, 1.0), (0.0, 0.78, 0.86), (1.0, 0.35, 0.63), (0.85, 0.3, 0.95))

    def __init__(self, w, h, seed=5, colors=None):
        self.w, self.h = w, h
        lw, lh = max(w // 8, 8), max(h // 8, 8)
        ys, xs = np.mgrid[0:lh, 0:lw].astype(np.float32)
        self.aspect = h / w
        self.xs, self.ys = xs / lw, ys / lh * self.aspect
        rng = np.random.default_rng(seed)
        self.blobs = [(np.array(c, np.float32), rng.uniform(0.12, 0.3), rng.uniform(0.1, 0.25),
                       rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0.16, 0.26))
                      for c in (colors or self.COLORS)]

    def render(self, t):
        color = np.zeros((*self.xs.shape, 3), np.float32)
        weight = np.full(self.xs.shape, 1e-4, np.float32)
        for c, sx, sy, px, py, r in self.blobs:
            cx = 0.5 + 0.42 * math.sin(t * sx + px)
            cy = (0.5 + 0.40 * math.cos(t * sy + py)) * self.aspect
            g = np.exp(-((self.xs - cx) ** 2 + (self.ys - cy) ** 2) / (2 * r * r))
            color += g[..., None] * c
            weight += g
        # Colours blend by weight (staying saturated where blobs overlap);
        # brightness grows with how much blob is there.
        glow = (1 - np.exp(-weight * 1.6))[..., None] * 0.92
        img = (0.035, 0.04, 0.08) * (1 - glow) + color / weight[..., None] * glow
        return cv2.resize((np.clip(img, 0, 1) * 255).astype(np.uint8), (self.w, self.h),
                          interpolation=cv2.INTER_CUBIC)


# -- text and flat shapes ---------------------------------------------------

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
FONT_FILES = {
    "regular": ("segoeui.ttf",),
    "semibold": ("seguisb.ttf",),
    "bold": ("segoeuib.ttf",),
    "icons": ("SegoeIcons.ttf", "segmdl2.ttf"),   # Windows 11 Fluent icons, Windows 10 MDL2 icons
}
ICON_CAMERA = ""


@lru_cache(maxsize=64)
def font(weight, size):
    for name in FONT_FILES[weight]:
        try:
            return ImageFont.truetype(str(FONT_DIR / name), size)
        except OSError:
            pass
    return ImageFont.load_default(size)


@lru_cache(maxsize=2048)
def _sprite(text, weight, size, color):
    f = font(weight, size)
    ascent, descent = f.getmetrics()
    w = int(math.ceil(f.getlength(text))) + 2
    h = ascent + descent + 2
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((1, 1), text, font=f, fill=255)
    a = np.asarray(img, np.float32) / 255
    return a, (1 - a).astype(np.float32), np.full((h, w, 3), color, np.uint8), ascent


def text_width(text, weight, size):
    return font(weight, int(round(size))).getlength(text)


def blit_text(frame, text, x, y, weight, size, color, anchor="lt", alpha=1.0):
    """Draw one line of text. anchor: l/m/r horizontally + t/m/b vertically ('m' centres the capitals)."""
    if not text or alpha <= 0:
        return
    size = int(round(size))
    a, inv, col, ascent = _sprite(text, weight, size, tuple(color))
    if alpha < 1:
        a = a * alpha
        inv = 1 - a
    h, w = a.shape
    hx = {"l": 0, "m": w / 2, "r": w}[anchor[0]]
    vy = {"t": 0, "m": 1 + ascent - 0.36 * size, "b": h}[anchor[1]]
    blend(frame, int(round(x - hx)), int(round(y - vy)), col, inv, a)


def capsule(frame, x, y, w, h, color, alpha=1.0):
    """Filled pill with round ends, anti-aliased, at fractional pixel coordinates."""
    fh, fw = frame.shape[:2]
    x0, y0 = max(int(math.floor(x)) - 1, 0), max(int(math.floor(y)) - 1, 0)
    x1, y1 = min(int(math.ceil(x + w)) + 1, fw), min(int(math.ceil(y + h)) + 1, fh)
    if x0 >= x1 or y0 >= y1:
        return
    region = frame[y0:y1, x0:x1]
    layer = region.copy()
    r = min(w, h) / 2
    S = 16  # 4 bits of sub-pixel precision
    cy = y + h / 2 - y0
    left, right = x + r - x0, x + w - r - x0
    color = tuple(int(c) for c in color)
    for cx in (left, right):
        cv2.circle(layer, (int(cx * S), int(cy * S)), int(r * S), color, -1, cv2.LINE_AA, 4)
    if right > left:
        cv2.rectangle(layer, (int(left * S), int((cy - r) * S)), (int(right * S), int((cy + r) * S)),
                      color, -1, cv2.LINE_AA, 4)
    if alpha >= 1:
        region[:] = layer
    else:
        cv2.addWeighted(layer, alpha, region, 1 - alpha, 0, dst=region)


def ease(t):
    """Smooth start and stop for 0..1."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)
