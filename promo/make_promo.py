"""Renders the AirMouse promo video: 1920x1080, 30 fps, about 53 s, with music.

    python promo/make_promo.py                      -> promo/AirMouse_promo.mp4
    python promo/make_promo.py --stills 3,15,33     -> promo/still_3.png ... (to check frames)

Everything is generated in code. The Liquid Glass look comes from airmouse/glass.py;
the cursor in the hand scene is moved by the real gesture engine; the stabilization
chart uses the real filters; the app scene shows the real window from airmouse/ui.py.
"""

import argparse
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airmouse import settings as settings_module  # noqa: E402
from airmouse.face import FaceFrame  # noqa: E402
from airmouse.gestures import GestureEngine  # noqa: E402
from airmouse.glass import (  # noqa: E402
    STYLES, Glass, LiquidBackdrop, blend, blit_text, capsule, ease, rounded_rect_sdf, text_width,
)
from airmouse.settings import Settings  # noqa: E402

W, H, FPS = 1920, 1080, 30
TEXT = (245, 247, 250)
MUTED = (198, 204, 218)
ACCENT = (64, 140, 255)
GREEN = (94, 224, 122)
ORANGE = (255, 150, 80)
MODE_DOT = {"move": GREEN, "pending": (255, 204, 64), "pressed": (255, 204, 64), "drag": (255, 128, 84),
            "right": (200, 128, 255), "scroll": (84, 180, 255), "no_hand": (150, 155, 168)}

PROMO_STYLES = dict(STYLES)
PROMO_STYLES.update({
    "hero": dict(blur=10, refraction=1.3, dispersion=0.2, tint=(20, 22, 38), tint_alpha=0.32, saturation=1.4,
                 rim=1.2, sheen=0.12, shadow=0.35),
    "orb": dict(blur=0, refraction=2.4, dispersion=0.35, tint=(255, 255, 255), tint_alpha=0.05, saturation=1.5,
                rim=1.3, sheen=0.16, shadow=0.22),
    "caption": dict(blur=8, refraction=1.4, dispersion=0.2, tint=(18, 20, 30), tint_alpha=0.45, saturation=1.4,
                    rim=1.1, sheen=0.1, shadow=0.3),
})
_glass = {}


def glass(w, h, r, style):
    key = (int(round(w)), int(round(h)), int(round(r)), style)
    if key not in _glass:
        _glass[key] = Glass(*key[:3], **PROMO_STYLES[style])
    return _glass[key]


# -- small drawing helpers --------------------------------------------------

def lerp(a, b, k):
    return a + (b - a) * k


def spring(t, delay=0.0):
    """0 -> 1 with a small overshoot, like a released spring."""
    t -= delay
    return 0.0 if t <= 0 else 1 - math.exp(-5.5 * t) * math.cos(8 * t)


def text(frame, s, x, y, size, color=TEXT, weight="regular", anchor="mm", alpha=1.0):
    blit_text(frame, s, x, y, weight, size, color, anchor, alpha)


def faded(frame, alpha, draw):
    """Run draw(frame) at partial opacity."""
    if alpha <= 0.002:
        return
    if alpha >= 0.998:
        draw(frame)
        return
    layer = frame.copy()
    draw(layer)
    cv2.addWeighted(layer, alpha, frame, 1 - alpha, 0, dst=frame)


_masks = {}


def fill_round(frame, x, y, w, h, r, color, alpha=1.0):
    key = (int(round(w)), int(round(h)), int(round(r)))
    if key not in _masks:
        _masks[key] = np.clip(0.5 - rounded_rect_sdf(*key), 0, 1).astype(np.float32)
    m = _masks[key] * alpha if alpha < 1 else _masks[key]
    blend(frame, int(round(x)), int(round(y)), np.full((*m.shape, 3), color, np.uint8), 1 - m, m)


ARROW = np.array([(0, 0), (0, 25), (6, 19), (11, 30), (16, 28), (11, 17), (19, 17)], np.float32)


def cursor_arrow(frame, x, y, k=1.5):
    """White mouse pointer with a soft shadow, tip at (x, y)."""
    x0, y0 = int(x) - 10, int(y) - 10
    rw, rh = int(22 * k) + 26, int(32 * k) + 26
    shadow = np.zeros((rh, rw), np.uint8)
    cv2.fillPoly(shadow, [((ARROW * k + (x - x0 + 2, y - y0 + 4)) * 16).astype(np.int32)], 255, cv2.LINE_AA, 4)
    a = cv2.GaussianBlur(shadow.astype(np.float32) / 255, (0, 0), 3) * 0.45
    blend(frame, x0, y0, np.zeros((rh, rw, 3), np.uint8), 1 - a, a)
    poly = [((ARROW * k + (x, y)) * 16).astype(np.int32)]
    cv2.fillPoly(frame, poly, (255, 255, 255), cv2.LINE_AA, 4)
    cv2.polylines(frame, poly, True, (24, 26, 34), 2, cv2.LINE_AA, 4)


def ripple(frame, x, y, p, scale=1.0):
    if not 0 <= p < 1:
        return
    r = (10 + 46 * ease(p)) * scale
    layer = frame.copy()
    cv2.circle(layer, (int(x * 16), int(y * 16)), int(r * 16), (255, 255, 255), max(2, int(4 * scale)), cv2.LINE_AA, 4)
    cv2.addWeighted(layer, (1 - p) ** 1.4, frame, 1 - (1 - p) ** 1.4, 0, dst=frame)


def caption_track(frame, items, t, y=915):
    """items: [(t0, t1, text)]. The current text sits in a glass pill that resizes between texts."""
    for i, (t0, t1, s) in enumerate(items):
        if t0 <= t < t1:
            break
    else:
        return
    size = 36
    width = text_width(s, "semibold", size) + 96
    k = ease((t - t0) / 0.35)
    if i > 0 and abs(items[i - 1][1] - t0) < 1e-6:
        width = lerp(text_width(items[i - 1][2], "semibold", size) + 96, width, k)
    width = round(width / 8) * 8
    box_alpha = 1.0
    if i == 0:
        box_alpha = ease((t - t0) / 0.35)
    if i == len(items) - 1:
        box_alpha *= ease((t1 - t) / 0.35)
    faded(frame, box_alpha, lambda f: glass(width, 80, 40, "caption").draw(f, W / 2 - width / 2, y - 40))
    text(frame, s, W / 2, y, size, weight="semibold", alpha=k * ease((t1 - t) / 0.2))


def scene_title(frame, s, t, y=110, size=64):
    k = ease(t / 0.6)
    text(frame, s, W / 2, y + (1 - k) * 30, size, weight="bold", alpha=k)


ORBS = [(220, 210, 150, 60, 40, 0.5, 0.0), (1700, 260, 110, 50, 70, 0.6, 1.3), (300, 860, 120, 80, 40, 0.4, 2.1),
        (1610, 840, 190, 60, 50, 0.35, 3.0), (980, 130, 70, 120, 20, 0.7, 4.2), (1180, 960, 84, 90, 30, 0.55, 5.0)]


def orbs(frame, t):
    for x0, y0, d, ax, ay, sp, ph in ORBS:
        x = x0 + ax * math.sin(t * sp + ph)
        y = y0 + ay * math.cos(t * sp * 0.8 + ph)
        glass(d, d, d / 2, "orb").draw(frame, x - d / 2, y - d / 2)


def app_icon(size):
    img = Image.open(ROOT / "assets" / "airmouse.ico")
    img.size = max(img.ico.sizes())
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    a = np.asarray(img, np.float32)[..., 3] / 255
    return np.ascontiguousarray(np.asarray(img)[..., :3]), a


# -- synthetic hand (same geometry as the tests) ----------------------------

def hand(ox, oy, pose="open"):
    """21 landmarks in camera pixels; (ox, oy) is the middle knuckle; palm length 100 px."""
    mcp = {5: (ox - 50, oy + 5), 9: (ox, oy), 13: (ox + 50, oy + 5), 17: (ox + 95, oy + 15)}
    folded = {13, 17} if pose == "two" else set()
    pts = [None] * 21
    pts[0] = (ox, oy + 100, 0)
    for i, (mx, my) in mcp.items():
        for k, off in enumerate((0, -30, -15, 10) if i in folded else (0, -40, -65, -90)):
            pts[i + k] = (mx, my + off, 0)
    pts[1], pts[2], pts[3] = (ox - 60, oy + 80, 0), (ox - 85, oy + 55, 0), (ox - 100, oy + 30, 0)
    if pose == "left":
        pts[4] = (pts[8][0], pts[8][1] + 8, 0)
    elif pose == "right":
        pts[4] = ((pts[8][0] + pts[12][0]) / 2, pts[8][1] + 5, 0)
    else:
        pts[4] = (ox - 110, oy + 5, 0)
    return pts


HAND_LINES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
              (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17))


def draw_hand(frame, pts, x0, y0, k, dot=GREEN, thick=3):
    p = [((x0 + q[0] * k) * 16, (y0 + q[1] * k) * 16) for q in pts]
    for a, b in HAND_LINES:
        cv2.line(frame, (int(p[a][0]), int(p[a][1])), (int(p[b][0]), int(p[b][1])), (235, 240, 250), thick,
                 cv2.LINE_AA, 4)
    for q in p:
        cv2.circle(frame, (int(q[0]), int(q[1])), int(4.5 * 16), (255, 255, 255), -1, cv2.LINE_AA, 4)
    palm = [pts[i] for i in (0, 5, 9, 13, 17)]
    cx = x0 + sum(q[0] for q in palm) / 5 * k
    cy = y0 + sum(q[1] for q in palm) / 5 * k
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), int(12 * 16), dot, -1, cv2.LINE_AA, 4)
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), int(12 * 16), (255, 255, 255), 3, cv2.LINE_AA, 4)


def cam_for(sx, sy):
    """Camera position of the middle knuckle that puts the cursor at screen (sx, sy) (default settings)."""
    return (sx / 1919 * 0.6 + 0.2) * 640 - 19, (sy / 1079 * 0.45 + 0.325) * 480 - 25


def path(keys, t):
    """keys: [(time, x, y)]; eased movement between them."""
    if t <= keys[0][0]:
        return keys[0][1:]
    for (t0, x0, y0), (t1, x1, y1) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    return keys[-1][1:]


def at(spans, t, default=None):
    for t0, t1, v in spans:
        if t0 <= t < t1:
            return v
    return default


# -- a mock desktop the cursor works on ---------------------------------------

TILES = (("Документы", "", (66, 120, 235)), ("Фото", "", (226, 70, 140)),
         ("Музыка", "", (250, 140, 50)), ("Почта", "", (40, 165, 120)),
         ("Настройки", "", (120, 100, 235)), ("Папка", "", (232, 178, 40)))
TILE_CENTERS = ((480, 290), (960, 290), (1440, 290), (480, 560), (960, 560), (1440, 560))
LIST = (220, 735, 1480, 300)
ROWS = ("Отчёт за январь.docx", "Презентация проекта.pptx", "Фото с отпуска", "Бюджет 2026.xlsx", "Заметки.txt",
        "Музыка для работы", "Скриншоты", "AirMouse — промо.mp4", "Договор.pdf", "Идеи.md", "Резюме.docx",
        "Архив.zip")
SCREEN = (840, 160, 1020, 574)   # where the mock desktop sits in the video; 1920x1080 inside it


class Desktop:
    """State of the mock desktop, changed by mouse actions."""

    def __init__(self):
        self.tiles = list(TILE_CENTERS)
        self.scroll = self.scroll_to = 140.0
        self.ripples, self.flash, self.menu, self.drag = [], {}, None, None

    def tile_at(self, x, y):
        for i, (cx, cy) in enumerate(self.tiles):
            if abs(x - cx) < 160 and abs(y - cy) < 110:
                return i
        return None

    def act(self, action, t, cursor):
        kind = action[0]
        if kind == "click" and action[1] == "left":
            self.ripples.append((t, *cursor))
            i = self.tile_at(*cursor)
            if i is not None:
                self.flash[i] = t
            self.menu = None
        elif kind == "click" and action[1] == "right":
            self.ripples.append((t, *cursor))
            self.menu = (t, *cursor)
        elif kind == "down":
            self.ripples.append((t, *cursor))
            i = self.tile_at(*cursor)
            if i is not None:
                self.drag = (i, self.tiles[i][0] - cursor[0], self.tiles[i][1] - cursor[1])
        elif kind == "up":
            self.drag = None
        elif kind == "wheel":
            self.scroll_to = min(max(self.scroll_to - action[1] / 120 * 70, 0), len(ROWS) * 70 - LIST[3] + 20)

    def step(self, dt, cursor):
        self.scroll += (self.scroll_to - self.scroll) * (1 - math.exp(-dt / 0.12))
        if self.drag:
            i, dx, dy = self.drag
            self.tiles[i] = (cursor[0] + dx, cursor[1] + dy)

    def snapshot(self):
        return SimpleNamespace(tiles=list(self.tiles), scroll=self.scroll, ripples=list(self.ripples),
                               flash=dict(self.flash), menu=self.menu, drag=self.drag[0] if self.drag else None)


def draw_desktop(frame, snap, t, cursor=None, dots=()):
    x0, y0, w, h = SCREEN
    k = w / 1920
    glass(w, h, 34, "panel").draw(frame, x0, y0)
    sub = frame[y0:y0 + h, x0:x0 + w]
    for i, c in enumerate(((255, 95, 87), (255, 189, 46), (40, 201, 64))):
        capsule(sub, 22 + i * 20, 18, 11, 11, c)
    text(sub, "Рабочий стол", w / 2, 24, 15, MUTED, "semibold")

    order = [i for i in range(len(TILES)) if i != snap.drag] + ([snap.drag] if snap.drag is not None else [])
    for i in order:
        name, icon, color = TILES[i]
        cx, cy = snap.tiles[i]
        lift = 1.06 if i == snap.drag else 1.0
        flash = max(0.0, 1 - (t - snap.flash[i]) / 0.5) if i in snap.flash and t >= snap.flash[i] else 0.0
        col = tuple(min(255, int(c + (255 - c) * 0.45 * flash)) for c in color)
        tw, th = 300 * k * lift, 200 * k * lift
        if i == snap.drag:
            fill_round(sub, cx * k - tw / 2 + 4, cy * k - th / 2 + 8, tw, th, 22 * k, (0, 0, 0), 0.35)
        fill_round(sub, cx * k - tw / 2, cy * k - th / 2, tw, th, 22 * k, col, 0.92)
        text(sub, icon, cx * k, cy * k - 14 * k, 64 * k, TEXT, "icons")
        text(sub, name, cx * k, cy * k + 58 * k, 26 * k, TEXT, "semibold")

    lx, ly, lw, lh = (v * k for v in LIST)
    fill_round(sub, lx, ly, lw, lh, 22 * k, (255, 255, 255), 0.07)
    clip = sub[int(ly):int(ly + lh), int(lx):int(lx + lw)]
    first = int(snap.scroll // 70)
    for i in range(max(first - 1, 0), min(first + 6, len(ROWS))):
        ry = (i * 70 - snap.scroll + 35) * k
        text(clip, "", 40 * k, ry, 30 * k, MUTED, "icons")
        text(clip, ROWS[i], 80 * k, ry, 25 * k, TEXT, "regular", "lm")
        if i:
            capsule(clip, 30 * k, ry - 35 * k, lw - 60 * k, 1, (255, 255, 255), 0.08)

    for t0, rx, ry in snap.ripples:
        ripple(sub, rx * k, ry * k, (t - t0) / 0.6)
    for i, (dx, dy) in enumerate(dots):
        r = 9
        capsule(sub, dx * k - r, dy * k - r, 2 * r, 2 * r, (255, 255, 255) if i == len(dots) - 1 else ACCENT,
                1.0 if i == len(dots) - 1 else 0.5)
    if snap.menu is not None and t - snap.menu[0] < 1.6:
        mt, mx, my = snap.menu
        a = ease((t - mt) / 0.2) * ease((mt + 1.6 - t) / 0.2)

        def menu(f):
            glass(196, 136, 18, "caption").draw(f, mx * k + 8, my * k + 8)
            for j, item in enumerate(("Открыть", "Копировать", "Удалить")):
                text(f, item, mx * k + 30, my * k + 34 + j * 38, 17, (255, 120, 120) if j == 2 else TEXT, "regular",
                     "lm")
        faded(sub, a, menu)
    if cursor is not None:
        cursor_arrow(sub, cursor[0] * k, cursor[1] * k, 1.25)


# -- scenes (each draws onto a frame that already has the flowing backdrop) ----

class Intro:
    def __init__(self):
        self.icon = app_icon(120)

    def __call__(self, frame, t):
        orbs(frame, t)
        off = (1 - spring(t, 0.1)) * 160
        faded(frame, ease(t / 0.5), lambda f: glass(1080, 450, 90, "hero").draw(f, 420, 320 + off))
        rgb, a = self.icon
        a = a * ease((t - 0.35) / 0.5)
        blend(frame, 900, int(350 + off), rgb, 1 - a, a)
        text(frame, "AirMouse", W / 2, 560 + off, 136, weight="bold", alpha=ease((t - 0.5) / 0.5))
        text(frame, "Управляйте компьютером без мыши", W / 2, 680 + off, 40, MUTED, alpha=ease((t - 0.9) / 0.5))
        text(frame, "рукой  ·  взглядом  ·  поворотом головы", W / 2, 900, 32, TEXT, "semibold",
             alpha=ease((t - 1.8) / 0.6))


class Modes:
    CARDS = (("Рука", "жесты пальцами"), ("Глаза", "взгляд и моргание"), ("Голова", "поворот головы"))

    def __call__(self, frame, t):
        scene_title(frame, "Три способа управления", t, 170, 70)
        for i, (name, sub) in enumerate(self.CARDS):
            d = 0.25 + 0.2 * i
            cx, cy = 420 + 540 * i, 610 + (1 - spring(t, d)) * 140
            a = ease((t - d) / 0.4)

            def card(f, cx=cx, cy=cy, i=i, name=name, sub=sub):
                glass(440, 440, 48, "panel").draw(f, cx - 220, cy - 220)
                icon_y = cy - 60
                if i == 0:
                    draw_hand(f, hand(320, 240 + 10 * math.sin(t * 2)), cx - 320 * 0.9, icon_y - 250 * 0.9, 0.9)
                elif i == 1:
                    eye(f, cx, icon_y, 70, 1.0, (math.sin(t * 1.7), 0.15 * math.cos(t * 1.3)))
                else:
                    head_icon(f, cx, icon_y, math.sin(t * 1.4))
                text(f, name, cx, cy + 110, 50, weight="bold")
                text(f, sub, cx, cy + 165, 27, MUTED)
            faded(frame, a, card)


def eye(frame, cx, cy, w, openness, look):
    """A stylised eye: white, iris that looks around, lids that close."""
    h = 0.45 * w * openness
    if openness > 0.12:
        x0, y0 = int(cx - w - 4), int(cy - 0.5 * w - 4)
        region = frame[y0:y0 + int(w + 8), x0:x0 + int(2 * w + 8)]
        c = (int((cx - x0) * 16), int((cy - y0) * 16))
        axes = (int(w * 16), int(h * 16))
        mask = np.zeros(region.shape[:2], np.uint8)
        cv2.ellipse(mask, c, axes, 0, 0, 360, 255, -1, cv2.LINE_AA, 4)
        layer = region.copy()
        cv2.ellipse(layer, c, axes, 0, 0, 360, (236, 240, 248), -1, cv2.LINE_AA, 4)
        ic = (int(c[0] + look[0] * w * 0.42 * 16), int(c[1] + look[1] * h * 0.5 * 16))
        cv2.circle(layer, ic, int(w * 0.36 * 16), (60, 135, 255), -1, cv2.LINE_AA, 4)
        cv2.circle(layer, ic, int(w * 0.15 * 16), (14, 16, 28), -1, cv2.LINE_AA, 4)
        cv2.circle(layer, (ic[0] - int(w * 0.1 * 16), ic[1] - int(w * 0.1 * 16)), int(w * 0.06 * 16),
                   (255, 255, 255), -1, cv2.LINE_AA, 4)
        m = mask.astype(np.float32) / 255
        region[:] = cv2.blendLinear(layer, region, m, 1 - m)
        cv2.ellipse(frame, (int(cx * 16), int(cy * 16)), axes, 0, 0, 360, (250, 252, 255), 3, cv2.LINE_AA, 4)
    else:
        cv2.ellipse(frame, (int(cx * 16), int(cy * 16)), (int(w * 16), int(0.2 * w * 16)), 0, 10, 170,
                    (250, 252, 255), 4, cv2.LINE_AA, 4)


def head_icon(frame, cx, cy, turn):
    white = (240, 244, 252)
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), 92 * 16, white, 4, cv2.LINE_AA, 4)
    dx = turn * 26
    for ex in (-32, 32):
        cv2.circle(frame, (int((cx + ex + dx) * 16), int((cy - 18) * 16)), 9 * 16, white, -1, cv2.LINE_AA, 4)
    nose = np.array([(cx + dx * 1.4, cy - 4), (cx + dx * 1.4 - 10, cy + 22), (cx + dx * 1.4 + 6, cy + 22)])
    cv2.polylines(frame, [(nose * 16).astype(np.int32)], False, white, 3, cv2.LINE_AA, 4)
    cv2.ellipse(frame, (int((cx + dx) * 16), int((cy + 44) * 16)), (30 * 16, 12 * 16), 0, 10, 170, white, 3,
                cv2.LINE_AA, 4)


CAMERA = (60, 160, 740, 574)   # the "camera" panel next to the desktop


def camera_panel(frame, label="Камера"):
    x, y, w, h = CAMERA
    glass(w, h, 34, "panel").draw(frame, x, y)
    capsule(frame, x + 24, y + 22, 12, 12, (255, 70, 80))
    text(frame, label, x + 46, y + 28, 17, MUTED, "semibold", "lm")


class HandDemo:
    TITLE = "Режим «Рука»"
    LENGTH = 13.0
    KEYS = [(0.0, 960, 540), (0.4, 960, 540), (1.5, 480, 300), (2.6, 480, 300), (3.3, 900, 860), (3.9, 900, 860),
            (4.9, 900, 1000), (5.4, 900, 1000), (6.1, 960, 570), (6.6, 960, 570), (7.8, 1460, 860),
            (8.4, 1460, 860), (9.3, 1180, 420), (13.0, 1180, 420)]
    POSES = [(1.85, 2.0, "left"), (3.45, 5.15, "two"), (6.3, 8.05, "left"), (9.75, 9.92, "right")]
    CAPTIONS = [(0.0, 1.7, "Ладонь — двигает курсор"), (1.7, 3.3, "Щипок — клик"),
                (3.3, 5.6, "Два пальца — прокрутка"), (5.6, 9.3, "Сжать и вести — перетаскивание"),
                (9.3, 12.6, "Большой + два пальца — правый клик")]

    def __init__(self):
        """Run the real gesture engine on a scripted hand and keep what happened in each frame."""
        engine = GestureEngine(Settings(), 1920, 1080)
        rng = np.random.default_rng(4)
        desktop = Desktop()
        cursor = (960, 540)
        self.frames, self.clicks = [], []
        for i in range(-45, int(self.LENGTH * FPS) + 1):
            t = i / FPS
            ox, oy = cam_for(*path(self.KEYS, max(t, 0.0)))
            pts = hand(ox + rng.normal(0, 0.6), oy + rng.normal(0, 0.6), at(self.POSES, t, "open"))
            for action in engine.update(pts, 640, 480, 100 + t, cursor):
                if action[0] == "move":
                    cursor = action[1:]
                elif i >= 0:
                    desktop.act(action, t, cursor)
                    if action[0] in ("click", "down"):
                        self.clicks.append(t)
            if i >= 0:
                desktop.step(1 / FPS, cursor)
                self.frames.append(SimpleNamespace(pts=pts, cursor=cursor, mode=engine.mode,
                                                   desktop=desktop.snapshot()))

    def __call__(self, frame, t):
        rec = self.frames[min(int(t * FPS), len(self.frames) - 1)]
        scene_title(frame, self.TITLE, t, 92, 56)
        camera_panel(frame)
        x, y, w, h = CAMERA
        k = min(w / 640, (h - 40) / 480)
        ox, oy = x + (w - 640 * k) / 2, y + 40 + (h - 40 - 480 * k) / 2
        zx0, zy0 = ox + 0.2 * 640 * k, oy + 0.325 * 480 * k
        cv2.rectangle(frame, (int(zx0), int(zy0)), (int(zx0 + 0.6 * 640 * k), int(zy0 + 0.45 * 480 * k)),
                      (200, 205, 220), 1, cv2.LINE_AA)
        draw_hand(frame, rec.pts, ox, oy, k, MODE_DOT.get(rec.mode, GREEN))
        draw_desktop(frame, rec.desktop, t, rec.cursor)
        caption_track(frame, self.CAPTIONS, t)


class Stability:
    def __init__(self):
        engine = GestureEngine(Settings(), 1920, 1080)
        rng = np.random.default_rng(2)
        cursor = (960, 540)
        raw, cur, cur_y = [], [], []
        for i in range(-45, 150):   # a strong 6 Hz tremor plus tracking noise, in camera pixels
            t = i / FPS
            dx = 3.0 * math.sin(2 * math.pi * 6 * t) + rng.normal(0, 1.2)
            dy = 3.0 * math.cos(2 * math.pi * 5 * t) + rng.normal(0, 1.2)
            ox, oy = 301 + dx, 239 + dy
            for action in engine.update(hand(ox, oy), 640, 480, 50 + t, cursor):
                if action[0] == "move":
                    cursor = action[1:]
            if i >= 0:
                raw.append(((ox + 19) / 640 - 0.2) / 0.6 * 1919)
                cur.append(cursor[0])
                cur_y.append(cursor[1])
        self.raw, self.cur = np.array(raw), np.array(cur, float)
        self.raw_span = self.raw.max() - self.raw.min()
        self.cur_span = max(np.ptp(cur), np.ptp(cur_y))

    def __call__(self, frame, t):
        scene_title(frame, "Рука дрожит — курсор нет", t, 120, 66)
        px, py, pw, ph = 200, 230, 1520, 560
        glass(pw, ph, 40, "panel").draw(frame, px, py)
        x0, x1, cy = px + 60, px + 1060, py + ph / 2 + 20
        capsule(frame, x0, cy, x1 - x0, 1, (255, 255, 255), 0.15)
        for i, (label, color) in enumerate((("Рука (дрожь)", ORANGE), ("Курсор AirMouse", GREEN))):
            capsule(frame, x0 + i * 280, py + 44, 14, 14, color)
            text(frame, label, x0 + 26 + i * 280, py + 51, 22, MUTED, "semibold", "lm")
        p = ease((t - 0.4) / 3.2)
        n = max(2, int(len(self.raw) * p))
        mid = self.raw.mean()
        xs = np.linspace(x0, x1, len(self.raw))[:n]
        for series, color in ((self.raw, ORANGE), (self.cur, GREEN)):
            ys = cy + (series[:n] - mid) * 6
            pts = (np.stack([xs, ys], 1) * 16).astype(np.int32)
            cv2.polylines(frame, [pts], False, color, 4, cv2.LINE_AA, 4)
        sx = px + 1150
        text(frame, "Дрожь руки", sx, py + 150, 28, MUTED, "semibold", "lm")
        text(frame, f"{self.raw_span * p:.0f} px", sx, py + 225, 88, ORANGE, "bold", "lm")
        text(frame, "Курсор", sx, py + 330, 28, MUTED, "semibold", "lm")
        text(frame, f"{self.cur_span * p:.0f} px", sx, py + 405, 88, GREEN, "bold", "lm")
        text(frame, "Фильтр One Euro  ·  «поводок»  ·  курсор замирает на время клика", W / 2, 880, 30, TEXT,
             alpha=ease((t - 2.0) / 0.6))


class EyesDemo:
    TITLE = "Режим «Глаза»"
    LENGTH = 11.0
    DOTS = [(150, 120), (960, 120), (1770, 120), (1770, 540), (960, 540), (150, 540), (150, 960), (960, 960),
            (1770, 960)]
    CAPTIONS = [(0.0, 2.3, "Калибровка: посмотрите на 9 точек"), (2.3, 4.4, "Взгляд — переносит курсор"),
                (4.4, 5.9, "Долго моргнуть — клик"), (5.9, 8.0, "Подмигнуть — правый клик"),
                (8.0, 10.7, "Открыть рот — перетаскивание")]

    def __init__(self):
        desktop = Desktop()
        cursor = (960, 540)
        rng = np.random.default_rng(9)
        self.frames, self.clicks = [], []
        events = {round(5.2 * FPS): ("click", "left"), round(7.2 * FPS): ("click", "right"),
                  round(8.7 * FPS): ("down", "left"), round(10.2 * FPS): ("up", "left")}
        for i in range(int(self.LENGTH * FPS) + 1):
            t = i / FPS
            gaze = self.gaze(t)
            if t >= 2.2:
                follow = 1 - math.exp(-(1 / FPS) / 0.07)
                cursor = (cursor[0] + (gaze[0] - cursor[0]) * follow + rng.normal(0, 0.8),
                          cursor[1] + (gaze[1] - cursor[1]) * follow + rng.normal(0, 0.8))
            if i in events:
                desktop.act(events[i], t, cursor)
                self.clicks.append(t)
            desktop.step(1 / FPS, cursor)
            self.frames.append(SimpleNamespace(gaze=gaze, cursor=cursor if t >= 2.2 else None,
                                               desktop=desktop.snapshot()))

    def gaze(self, t):
        if t < 2.2:
            return self.DOTS[min(int(max(t - 0.2, 0) / 0.22), 8)]
        if t < 5.9:
            return (960, 300)
        if t < 8.0:
            return (700, 880)
        if t < 8.9:
            return (480, 570)
        return path([(8.9, 480, 570), (9.9, 1350, 870)], t)

    def __call__(self, frame, t):
        rec = self.frames[min(int(t * FPS), len(self.frames) - 1)]
        scene_title(frame, self.TITLE, t, 92, 56)
        camera_panel(frame)
        x, y, w, h = CAMERA
        cx, cy = x + w / 2, y + h / 2 + 24
        blink = ease(min((t - 4.6) / 0.12, (5.2 - t) / 0.12)) if 4.6 <= t <= 5.2 else 0.0
        wink = ease(min((t - 6.8) / 0.12, (7.2 - t) / 0.12)) if 6.8 <= t <= 7.2 else 0.0
        mouth = ease(min((t - 8.6) / 0.2, (10.2 - t) / 0.2)) if 8.6 <= t <= 10.2 else 0.0
        look = ((rec.gaze[0] - 960) / 960, (rec.gaze[1] - 540) / 540)
        white = (235, 240, 250)
        S = 16
        cv2.ellipse(frame, (int(cx * S), int((cy + 10) * S)), (170 * S, 220 * S), 0, 0, 360, white, 3, cv2.LINE_AA, 4)
        for a in range(0, 360, 12):
            r = math.radians(a)
            px, py = cx + 170 * math.cos(r), cy + 10 + 220 * math.sin(r)
            cv2.circle(frame, (int(px * S), int(py * S)), int(3 * S), (255, 255, 255), -1, cv2.LINE_AA, 4)
        for side, extra in ((-1, 0.0), (1, wink)):
            ex = cx + side * 68
            eye(frame, ex, cy - 40, 46, max(0.0, 1 - max(blink, extra)), look)
            cv2.ellipse(frame, (int(ex * S), int((cy - 92) * S)), (44 * S, 12 * S), 0, 200, 340, white, 4,
                        cv2.LINE_AA, 4)
        nose = np.array([(cx, cy - 10), (cx - 14, cy + 44), (cx + 8, cy + 48)])
        cv2.polylines(frame, [(nose * S).astype(np.int32)], False, white, 3, cv2.LINE_AA, 4)
        if mouth > 0.05:
            cv2.ellipse(frame, (int(cx * S), int((cy + 110) * S)), (int(40 * S), int((8 + 34 * mouth) * S)), 0, 0,
                        360, (20, 22, 34), -1, cv2.LINE_AA, 4)
            cv2.ellipse(frame, (int(cx * S), int((cy + 110) * S)), (int(40 * S), int((8 + 34 * mouth) * S)), 0, 0,
                        360, white, 3, cv2.LINE_AA, 4)
        else:
            cv2.ellipse(frame, (int(cx * S), int((cy + 104) * S)), (50 * S, 16 * S), 0, 20, 160, white, 3,
                        cv2.LINE_AA, 4)
        dots = self.DOTS[:min(int(max(t - 0.2, 0) / 0.22) + 1, 9)] if t < 2.2 else ()
        draw_desktop(frame, rec.desktop, t, rec.cursor, dots)
        caption_track(frame, self.CAPTIONS, t)


class AppShowcase:
    """The real window (airmouse/ui.py) driven by a scripted mouse pointer."""

    SCALE = 1.0
    POS = (400, 196)
    DRAG = (4.5, 6.2)   # the stabilization slider is dragged between these times

    def __init__(self):
        settings_module.SETTINGS_DIR = Path(tempfile.gettempdir()) / "airmouse_promo"
        settings_module.SETTINGS_FILE = settings_module.SETTINGS_DIR / "settings.json"
        if settings_module.SETTINGS_FILE.exists():
            settings_module.SETTINGS_FILE.unlink()
        from airmouse import ui
        from airmouse.tracker import Tracker
        self.ui, self.Tracker = ui, Tracker
        self.camera = LiquidBackdrop(640, 480, seed=11)
        self.icon = app_icon(22)
        self._reset()

    def _reset(self):
        if getattr(self, "app", None) is not None:
            self.app.root.destroy()
        app = self.app = self.ui.App(scale=self.SCALE)
        app.root.withdraw()
        app.settings.gaze_model = {"error": 9.0}
        self.fake = SimpleNamespace(kind="hand", mode="move", fps=30.0, control_enabled=True, face=None, palm=None)
        app.tracker = self.fake
        app._has_frame = True
        app.start_btn.label, app.start_btn.style = "Стоп", "danger"

        def on_mode(mode):
            app.settings.mode = mode
            app._apply_mode()
            self.fake.kind = mode

        app.segmented.on_change = on_mode
        self.overlay = self.Tracker(app.settings)
        self.t = -1.0
        self.events = self._schedule()

    def _targets(self):
        """Where the pointer goes, taken from the real widget positions."""
        seg = self.app.segmented
        sx, sy, sw, sh = seg.rect
        step = (sw - 2 * seg.INSET) / 3
        segment = [(sx + seg.INSET + (i + 0.5) * step, sy + sh / 2) for i in range(3)]
        tx, ty, tl = self.app.sliders[0]._track()
        knob = lambda v: (tx + v * tl, ty)  # noqa: E731
        bx, by, bw, bh = self.app.invert_toggle.rect
        sbx, sby, sbw, sbh = self.app.start_btn.rect
        return segment, knob, (bx + bw / 2, by + bh / 2), (sbx + sbw / 2, sby + sbh / 2)

    def _schedule(self):
        segment, knob, toggle, _ = self._targets()
        seg, sl, tg = self.app.segmented, self.app.sliders[0], self.app.invert_toggle
        ev = []
        for when, i in ((0.9, 1), (2.1, 2), (3.3, 0)):   # Глаза, Голова, Рука
            ev += [(when, "press", seg, *segment[i]), (when + 0.05, "release", seg, *segment[i])]
        t0, t1 = self.DRAG
        ev.append((t0, "press", sl, *knob(0.7)))
        for i in range(1, 25):
            k = i / 24
            ev.append((t0 + (t1 - t0) * k, "drag", sl, *knob(0.7 + 0.22 * math.sin(math.pi * k) + 0.1 * k)))
        ev.append((t1, "release", sl, *knob(0.8)))
        ev += [(7.0, "press", tg, *toggle), (7.08, "release", tg, *toggle)]
        return ev

    def _pointer(self, t):
        segment, knob, toggle, start = self._targets()
        t0, t1 = self.DRAG
        sl = self.app.sliders[0]
        if t0 <= t <= t1:
            return knob((sl.value - sl.lo) / (sl.hi - sl.lo))
        keys = [(0.0, 560, 470), (0.75, *segment[1]), (1.6, *segment[1]), (2.0, *segment[2]), (2.8, *segment[2]),
                (3.2, *segment[0]), (3.9, *segment[0]), (t0 - 0.05, *knob(0.7))]
        if t > t1:
            keys = [(t1, *knob(0.8)), (6.8, *toggle), (7.4, *toggle), (8.0, *start)]
        return path(keys, t)

    def __call__(self, frame, t):
        if t < self.t:
            self._reset()
        app = self.app
        while self.t < t:
            self.t = self.t + 1 / FPS if self.t >= 0 else 0.0
            for et, kind, widget, x, y in self.events:
                if self.t - 1 / FPS < et <= self.t:
                    getattr(widget, kind)(x, y)
            mode = app.settings.mode
            cam = self.camera.render(self.t * 1.3 + 2)
            if mode == "hand":
                pts = hand(300 + 30 * math.sin(self.t * 1.6), 230 + 15 * math.cos(self.t * 1.2))
                self.overlay.kind = "hand"
                self.overlay.mode = "move"
                self.overlay._publish_preview(np.ascontiguousarray(cam[:, :, ::-1]), pts, 1920, 1080)
                cam = self.overlay.take_preview()
                self.fake.mode = "move"
            else:
                self.fake.face = (self.t, FaceFrame(gaze=(0.5, 0), head=(0, 0.5),
                                                    blink=(0.15 + 0.1 * math.sin(self.t * 3), 0.12),
                                                    jaw=0.25 + 0.2 * math.sin(self.t * 2), brow=0.3))
            app._camera_bg = app._cover(cam)
            hover = app.invert_toggle if 6.6 < self.t < 7.4 else app.start_btn if self.t > 7.6 else None
            for wdg in app._widgets():
                wdg.hover = wdg is hover
            self.image = app.render(self.t + 5, 1 / FPS)

        scene_title(frame, "Интерфейс Liquid Glass", t, 92, 56)
        x, y = self.POS
        ih, iw = self.image.shape[:2]
        glass(iw, ih + 36, 14, "caption").draw_shadow(frame, x, y - 36)
        fill_round(frame, x, y - 36, iw, ih + 36, 14, (14, 16, 24))
        blend(frame, x + 14, y - 29, self.icon[0], 1 - self.icon[1], self.icon[1])
        text(frame, "AirMouse", x + 46, y - 18, 15, MUTED, "regular", "lm")
        for j, glyph in enumerate(("", "", "")):
            text(frame, glyph, x + iw - 26 - (2 - j) * 46, y - 18, 12, MUTED, "icons")
        mask = np.clip(0.5 - rounded_rect_sdf(iw, ih + 14, 14), 0, 1).astype(np.float32)[14:]
        blend(frame, x, y, self.image, 1 - mask, mask)
        px, py = self._pointer(t)
        cursor_arrow(frame, x + px * self.SCALE, y + py * self.SCALE, 1.5)

    @property
    def clicks(self):
        return [et for et, kind, *_ in self._schedule() if kind == "press"]


class Outro:
    BADGES = ("MediaPipe", "One Euro Filter", "Python", "Windows 11")

    def __call__(self, frame, t):
        orbs(frame, t + 20)
        off = (1 - spring(t, 0.1)) * 140
        faded(frame, ease(t / 0.5), lambda f: glass(1180, 470, 90, "hero").draw(f, 370, 230 + off))
        text(frame, "AirMouse", W / 2, 420 + off, 150, weight="bold", alpha=ease((t - 0.3) / 0.5))
        text(frame, "Мышь, которой управляете вы", W / 2, 548 + off, 44, MUTED, alpha=ease((t - 0.6) / 0.5))
        text(frame, "Нужна только веб-камера", W / 2, 620 + off, 30, TEXT, "semibold", alpha=ease((t - 0.9) / 0.5))
        widths = [text_width(b, "semibold", 28) + 64 for b in self.BADGES]
        x = W / 2 - (sum(widths) + 24 * (len(widths) - 1)) / 2
        for i, (badge, w) in enumerate(zip(self.BADGES, widths)):
            d = 1.0 + 0.15 * i
            y = 830 + (1 - spring(t, d)) * 90

            def pill(f, x=x, y=y, w=w, badge=badge):
                glass(w, 66, 33, "button").draw(f, x, y - 33)
                text(f, badge, x + w / 2, y, 28, weight="semibold")
            faded(frame, ease((t - d) / 0.35), pill)
            x += w + 24


# -- timeline ----------------------------------------------------------------

XFADE = 0.6


def build_timeline():
    hand_demo, eyes_demo, app_demo = HandDemo(), EyesDemo(), AppShowcase()
    scenes = [(0.0, 6.0, Intro()), (5.4, 11.0, Modes()), (10.4, 23.4, hand_demo), (22.8, 29.8, Stability()),
              (29.2, 40.2, eyes_demo), (39.6, 47.6, app_demo), (47.0, 53.0, Outro())]
    clicks = ([10.4 + c for c in hand_demo.clicks] + [29.2 + c for c in eyes_demo.clicks]
              + [39.6 + c for c in app_demo.clicks])
    return scenes, 53.0, clicks


def render_frame(scenes, duration, backdrop, t):
    base = backdrop.render(t * 0.9)
    layers = []
    for start, end, scene in scenes:
        if start <= t < end:
            f = base.copy()
            scene(f, t - start)
            k = (ease((t - start) / XFADE) if start > 0 else 1.0) * (ease((end - t) / XFADE) if end < duration else 1.0)
            layers.append((f, k))
    if not layers:
        out = base
    elif len(layers) == 1:
        out = layers[0][0]
    else:
        (a, _), (b, kb) = layers[0], layers[-1]
        out = cv2.addWeighted(a, 1 - kb, b, kb, 0)
    fade = ease(t / 0.8) * ease((duration - t) / 1.2)
    if fade < 1:
        out = cv2.convertScaleAbs(out, alpha=fade)
    return out


# -- music -------------------------------------------------------------------

def make_music(path, duration, whooshes, clicks, sr=44100, arp_from=5.4, pulse=(10.4, 47.0)):
    """Ambient pad + soft arpeggio (from arp_from) + gentle pulse (during pulse), whooshes on scene changes,
    ticks on clicks."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    music = np.zeros(n)
    rng = np.random.default_rng(7)

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    chords = ((57, 60, 64, 67, 71), (53, 57, 60, 64, 67), (48, 55, 59, 64), (55, 59, 62, 64))
    bar = 4.0
    for k in range(int(math.ceil(duration / bar)) + 1):
        start = k * bar
        notes = chords[k % len(chords)]
        a, b = max(0, int((start - 0.3) * sr)), min(n, int((start + bar + 2.0) * sr))
        if a >= b:
            continue
        tt = t[a:b] - start
        env = np.clip((tt + 0.3) / 1.5, 0, 1) ** 2 * np.clip((bar + 2.0 - tt) / 2.3, 0, 1)
        for m in notes:
            f = hz(m)
            v = sum(np.sin(2 * np.pi * f * (1 + d) * tt + ph) for d, ph in ((-0.0025, 0.3), (0, 1.1), (0.0025, 2.0)))
            music[a:b] += 0.06 * env * (v / 3 + 0.15 * np.sin(2 * np.pi * 2 * f * tt))
        music[a:b] += 0.1 * env * np.sin(2 * np.pi * hz(notes[0] - 12) * tt)

    pattern = (0, 2, 1, 3, 2, 4, 3, 1)
    for j, st in enumerate(np.arange(arp_from, duration - 3.0, 0.25)):
        notes = chords[int(st // bar) % len(chords)]
        f = hz(notes[pattern[j % 8] % len(notes)] + 12)
        a, b = int(st * sr), min(n, int((st + 1.2) * sr))
        tt = t[a:b] - st
        env = np.exp(-tt * 5) * np.clip(tt / 0.004, 0, 1)
        music[a:b] += 0.03 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) * np.exp(-tt * 8))

    for st in np.arange(*pulse, 1.0):   # soft pulse while the demos run
        a, b = int(st * sr), min(n, int((st + 0.35) * sr))
        tt = t[a:b] - st
        f = 52 + 40 * np.exp(-tt * 30)
        music[a:b] += 0.12 * np.exp(-tt * 9) * np.sin(2 * np.pi * np.cumsum(f) / sr)

    # Reverb: convolution with decaying noise
    ir_t = np.arange(int(2.2 * sr)) / sr
    ir = rng.normal(size=len(ir_t)) * np.exp(-ir_t / 0.55)
    nfft = 1 << int(np.ceil(np.log2(n + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(music, nfft) * np.fft.rfft(ir, nfft), nfft)[:n]
    music = music + 0.3 * wet * (np.std(music) / (np.std(wet) + 1e-9))

    fx = np.zeros(n)
    for st in whooshes:
        a, b = max(0, int(st * sr)), min(n, int((st + 1.0) * sr))
        noise = np.convolve(rng.normal(size=b - a), np.hanning(40) / 20, mode="same")
        fx[a:b] += 0.05 * noise * np.hanning(b - a)
    for st in clicks:
        a, b = int(st * sr), min(n, int((st + 0.05) * sr))
        tt = t[a:b] - st
        fx[a:b] += 0.12 * np.exp(-tt * 140) * np.sin(2 * np.pi * 1900 * tt) + 0.1 * np.exp(-tt * 60) * np.sin(
            2 * np.pi * 180 * tt)

    out = music + fx
    out *= np.clip(t / 1.0, 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    out /= np.max(np.abs(out)) / 0.89
    right = np.roll(out, int(0.011 * sr))   # a little width
    stereo = (np.stack([out, right], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


# -- main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(ROOT / "promo" / "AirMouse_promo.mp4"))
    parser.add_argument("--stills", help="comma-separated seconds; saves PNGs instead of the video")
    args = parser.parse_args()
    cv2.setNumThreads(0)

    scenes, duration, clicks = build_timeline()
    backdrop = LiquidBackdrop(W, H, seed=5)
    if args.stills:
        for s in args.stills.split(","):
            path_ = Path(args.out).parent / f"still_{s}.png"
            Image.fromarray(render_frame(scenes, duration, backdrop, float(s))).save(path_)
            print("saved", path_)
        return

    import imageio_ffmpeg
    wav = Path(tempfile.gettempdir()) / "airmouse_promo_music.wav"
    whooshes = [start - 0.35 for start, *_ in scenes[1:]]
    make_music(wav, duration, whooshes, clicks)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(duration * FPS)
    for i in range(total):
        proc.stdin.write(render_frame(scenes, duration, backdrop, i / FPS).tobytes())
        if i % 150 == 0:
            print(f"frame {i}/{total}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("saved", args.out)


if __name__ == "__main__":
    main()
