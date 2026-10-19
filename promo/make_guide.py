"""Renders the AirMouse guide video: install, start, gestures, widgets, fine tuning. 1920x1080, 30 fps,
about 85 s, with music. Made for posting: everything is said in captions, sound is optional.

    python promo/make_guide.py                       -> promo/AirMouse_guide.mp4
    python promo/make_guide.py --stills 8,30,60      -> promo/guide_8.png ... (to check frames)

The look is «Природа»: fogged glass with condensation over a green, sunlit backdrop. As in
make_promo.py (whose helpers it uses), everything is generated in code: the hand scenes run
the real gesture engine, and the AirMouse windows and on-screen widgets are the real ones
(airmouse/ui.py, airmouse/onscreen.py), drawn into the video and never shown on the screen.
The «Подробнее» window is shown from screenshots of the real one in promo/guide/
(made by tools/capture_advanced.py).
"""

import argparse
import json
import math
import subprocess
import sys
import tempfile
import tkinter as tk
from collections import Counter, deque
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_promo as P  # noqa: E402  (also puts the project on sys.path)
from make_promo import (  # noqa: E402
    FPS, TEXT, W, app_icon, blend, capsule, caption_track, cursor_arrow, ease, faded, fill_round, glass, path,
    ripple, scene_title, spring, text, text_width,
)

from airmouse import bench, onscreen, overlay, widgets  # noqa: E402
from airmouse import settings as settings_module  # noqa: E402
from airmouse.app_base import MODE_DOT, MODE_TEXT  # noqa: E402
from airmouse.gestures import MOVE, GestureEngine, zone_rect  # noqa: E402
from airmouse.glass import STYLES, LiquidBackdrop, rounded_rect_sdf  # noqa: E402
from airmouse.settings import Settings  # noqa: E402
from airmouse.tracker import Tracker  # noqa: E402
from airmouse.ui import THEMES  # noqa: E402

# -- the «Природа» look -------------------------------------------------------

NATURE = THEMES["nature"]
GREEN = NATURE["accent"]
MUTED = (204, 222, 208)
P.MUTED, P.ACCENT = MUTED, GREEN          # the promo's helpers draw with these
P.PROMO_STYLES.update({
    "panel": STYLES["fog_panel"],
    "button": STYLES["fog_button"],
    "hero": dict(blur=16, refraction=1.2, dispersion=0.15, tint=(14, 34, 22), tint_alpha=0.38, saturation=1.15,
                 rim=1.1, sheen=0.12, shadow=0.35, haze=0.1, droplets=0.8),
    "caption": dict(blur=10, refraction=1.2, dispersion=0.15, tint=(12, 30, 20), tint_alpha=0.52, saturation=1.1,
                    rim=1.0, sheen=0.1, shadow=0.3, haze=0.06, droplets=0.35),
})
# What the camera sees behind the hand: a blurred room.
ROOM = dict(colors=((0.55, 0.47, 0.38), (0.32, 0.28, 0.26), (0.78, 0.68, 0.52), (0.22, 0.24, 0.27),
                    (0.62, 0.58, 0.50)), base=(0.10, 0.09, 0.08))
ICON = {"sun": "", "warning": "", "check": "", "pause": "", "admin": "",
        "shield": "", "folder": "", "monitor": "", "pointer": "", "play": "",
        "file": ""}
WINDOW_GLYPHS = ("", "", "")    # minimise, maximise, close
GUIDE = HERE / "guide"

settings_module.SETTINGS_DIR = Path(tempfile.gettempdir()) / "airmouse_guide"
settings_module.SETTINGS_FILE = settings_module.SETTINGS_DIR / "settings.json"
overlay.LayeredWindow.show = lambda self, *args: None      # the real widget windows never appear


# -- helpers ------------------------------------------------------------------

def step_title(frame, s, t):
    scene_title(frame, s, t, 92, 56)


def note(frame, number, s, x, y, t, start, w=760):
    """A numbered note in a glass pill that slides in at `start`."""
    a = ease((t - start) / 0.35)
    if a <= 0:
        return
    x += (1 - spring(t, start)) * 70

    def draw(f):
        glass(w, 80, 40, "button").draw(f, x, y - 40)
        capsule(f, x + 20, y - 20, 40, 40, GREEN)
        text(f, str(number), x + 40, y, 21, weight="bold")
        text(f, s, x + 80, y, 25, weight="semibold", anchor="lm")
    faded(frame, a, draw)


def chips(frame, labels, y, t, delay, size=28, steps=False):
    """A centred row of glass pills that pop in one after another (steps: with arrows between them)."""
    gap = 64 if steps else 20
    widths = [text_width(label, "semibold", size) + 64 for label in labels]
    x = W / 2 - (sum(widths) + gap * (len(widths) - 1)) / 2
    for i, (label, w) in enumerate(zip(labels, widths)):
        d = delay + 0.12 * i
        yy = y + (1 - spring(t, d)) * 90
        if steps and i:
            text(frame, "→", x - gap / 2, y, 30, MUTED, alpha=ease((t - d) / 0.35))

        def pill(f, x=x, yy=yy, w=w, label=label):
            glass(w, 64, 32, "button").draw(f, x, yy - 32)
            text(f, label, x + w / 2, yy, size, weight="semibold")
        faded(frame, ease((t - d) / 0.35), pill)
        x += w + gap


def ramp(spans, t, edge):
    """1 inside any (t0, t1) span, easing to 0 within `edge` seconds around it."""
    v = 0.0
    for t0, t1 in spans:
        inside = 1.0 if t0 <= t <= t1 else 1 - min(abs(t - t0), abs(t - t1)) / edge
        v = max(v, min(max(inside, 0.0), 1.0))
    return ease(v)


def pressed(t, at, length=0.12):
    return at <= t < at + length


_round = {}


def round_mask(w, h, r):
    key = (w, h, r)
    if key not in _round:
        _round[key] = np.clip(0.5 - rounded_rect_sdf(w, h, r), 0, 1).astype(np.float32)
    return _round[key]


def put_round(frame, image, x, y, r=16):
    """Paste an image with rounded corners."""
    h, w = image.shape[:2]
    m = round_mask(w, h, r)
    blend(frame, int(round(x)), int(round(y)), image, 1 - m, m)


def outline(frame, x, y, w, h, r, color, alpha=1.0, width=4):
    """A rounded ring just outside the rectangle (x, y, w, h)."""
    w, h, width = int(round(w)), int(round(h)), int(width)
    ow, oh = w + 2 * width, h + 2 * width
    ring = round_mask(ow, oh, r + width).copy()
    ring[width:width + h, width:width + w] -= round_mask(w, h, r)
    m = np.clip(ring, 0, 1) * alpha
    blend(frame, int(round(x)) - width, int(round(y)) - width, np.full((oh, ow, 3), color, np.uint8), 1 - m, m)


def paste_layer(frame, bgra, x, y, alpha=1.0):
    """Lay a widget picture (premultiplied BGRA, as the real widget windows get it) over an RGB frame."""
    h, w = bgra.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, frame.shape[1]), min(y + h, frame.shape[0])
    if x0 >= x1 or y0 >= y1 or alpha <= 0.01:
        return
    src = bgra[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32) * (alpha / 255.0)
    region = frame[y0:y1, x0:x1].astype(np.float32)
    region = region * (1 - src[..., 3:4]) + src[..., 2::-1] * 255.0
    frame[y0:y1, x0:x1] = np.clip(region, 0, 255).astype(np.uint8)


def caption_rgb(theme):
    """The title bar colour of a design (stored as 0x00BBGGRR for Windows)."""
    c = theme["caption"]
    return c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF


def draw_window(frame, image, x, y, title, bar, icon=None):
    """A window as Windows shows it: title bar, picture with rounded corners, soft shadow."""
    x, y = int(round(x)), int(round(y))
    ih, iw = image.shape[:2]
    glass(iw, ih + 36, 14, "caption").draw_shadow(frame, x, y - 36)
    fill_round(frame, x, y - 36, iw, ih + 36, 14, bar)
    tx = x + 16
    if icon is not None:
        blend(frame, x + 14, y - 29, icon[0], 1 - icon[1], icon[1])
        tx = x + 46
    text(frame, title, tx, y - 18, 15, MUTED, "regular", "lm")
    for j, glyph in enumerate(WINDOW_GLYPHS):
        text(frame, glyph, x + iw - 26 - (2 - j) * 46, y - 18, 12, MUTED, "icons")
    m = round_mask(iw, ih + 14, 14)[14:]
    blend(frame, x, y, image, 1 - m, m)


def zip_icon(f, x, y, w, h):
    fill_round(f, x, y, w, h, w * 0.16, (236, 190, 72))
    for k in range(4):
        fill_round(f, x + w / 2 - 3, y + 6 + k * h * 0.15, 6, h * 0.08, 1, (128, 90, 24), 0.85)


def folder_icon(f, x, y, w, h):
    fill_round(f, x, y, w * 0.46, h * 0.3, h * 0.1, (214, 150, 40))
    fill_round(f, x, y + h * 0.16, w, h * 0.84, h * 0.12, (248, 196, 72))


def cam_for_screen(sx, sy, sw, sh):
    """Camera position of hand()'s middle knuckle that puts the palm on screen point (sx, sy)."""
    x0, y0, x1, y1 = zone_rect(Settings(), 640, 480, sw, sh)
    return (x0 + sx / (sw - 1) * (x1 - x0)) * 640 - 19, (y0 + sy / (sh - 1) * (y1 - y0)) * 480 - 25


class Camera:
    """What the camera sees: a blurred room, with the hand drawn by AirMouse's own preview code."""

    def __init__(self):
        self.room = LiquidBackdrop(640, 480, seed=21, **ROOM)
        self.overlay = Tracker(Settings())
        self.overlay.kind = "hand"

    def frame(self, t, pts, mode=MOVE):
        bgr = np.ascontiguousarray(self.room.render(t * 0.6 + 4)[:, :, ::-1])
        self.overlay.mode = mode
        self.overlay._publish_preview(bgr, pts, 1920, 1080)
        return self.overlay.take_preview()


def moving_hand(t):
    """A hand resting comfortably in front of the camera."""
    return bench.hand(300 + 34 * math.sin(t * 1.3), 225 + 16 * math.cos(t * 1.1))


class _HiddenTk(tk.Tk):
    """The AirMouse windows are drawn into the video and never shown."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.withdraw()


def make_app(design, scale):
    """A real AirMouse window (airmouse/ui.py) in a design, at a scale, kept off the screen."""
    settings_module.SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    settings_module.SETTINGS_FILE.write_text(json.dumps({"design": design}), encoding="utf-8")
    from airmouse import ui
    real, tk.Tk = tk.Tk, _HiddenTk
    try:
        app = ui.App(scale=scale)
    finally:
        tk.Tk = real
    app._t0 = 0.0
    return app


def fake_tracker():
    """Stands in for the camera thread: the window only reads these."""
    return SimpleNamespace(kind="hand", mode=MOVE, fps=30.0, control_enabled=True, face=None, palm=None,
                           progress=0.0, error=None, events=deque(), widget_toggles=0, stats=Counter(),
                           take_preview=lambda: None, stop=lambda: None)


def render_app(app, now):
    widgets.set_theme(app.theme)       # the controls draw in the design of the window being drawn
    return app.render(now, 0.0)


def window_at(app, pos, lx, ly):
    """A point given in the window's own layout -> the video."""
    return pos[0] + lx * app.s, pos[1] + ly * app.s


def centre(rect):
    x, y, w, h = rect
    return x + w / 2, y + h / 2


def segment_centre(seg, i):
    x, y, w, h = seg.rect
    step = (w - 2 * seg.INSET) / len(seg.options)
    return x + seg.INSET + (i + 0.5) * step, y + h / 2


# -- scenes -------------------------------------------------------------------

class Intro:
    LENGTH = 4.6
    CHIPS = ("Установка", "Жесты", "Виджеты", "Глаза и голова", "Тонкая настройка")

    def __init__(self):
        self.icon = app_icon(120)
        self.clicks = []

    def __call__(self, frame, t):
        P.orbs(frame, t)
        off = (1 - spring(t, 0.1)) * 160
        faded(frame, ease(t / 0.5), lambda f: glass(1080, 470, 90, "hero").draw(f, 420, 280 + off))
        rgb, a = self.icon
        a = a * ease((t - 0.35) / 0.5)
        blend(frame, 900, int(310 + off), rgb, 1 - a, a)
        text(frame, "AirMouse", W / 2, 522 + off, 128, weight="bold", alpha=ease((t - 0.5) / 0.5))
        text(frame, "Как пользоваться: всё за полторы минуты", W / 2, 642 + off, 40, MUTED,
             alpha=ease((t - 0.9) / 0.5))
        chips(frame, self.CHIPS, 880, t, 1.5)


CARD_W, CARD_H, CARD_Y = 540, 600, 200
CARD_X = (120, 690, 1260)


class Download:
    LENGTH = 8.6
    MENU = ("Открыть", "Извлечь все…", "Отправить", "Свойства")
    LABELS = ("Скачайте zip на странице Releases", "Распакуйте: «Извлечь все…»", "Запустите AirMouse.exe")

    def __init__(self):
        self.icon = app_icon(36)
        row = (CARD_X[0] + 270, CARD_Y + 222)
        zip_ = (CARD_X[1] + 270, CARD_Y + 202)
        self.menu_at = zip_
        extract = (zip_[0] + 145, zip_[1] + 10 + 8 + 44 + 22)
        exe = (CARD_X[2] + 270, CARD_Y + 190)
        self.keys = [(0.0, 960, 1010), (1.1, *row), (2.2, *row), (2.8, *zip_), (3.1, *zip_), (3.6, *extract),
                     (4.2, *extract), (5.1, *exe), (8.6, *exe)]
        self.clicks = [1.4, 2.9, 3.9, 5.3, 5.46]

    def __call__(self, frame, t):
        step_title(frame, "1. Скачайте и распакуйте", t)
        for i, (x, draw, label) in enumerate(zip(CARD_X, (self._releases, self._extract, self._run), self.LABELS)):
            d = 0.15 + 0.2 * i
            y = CARD_Y + (1 - spring(t, d)) * 120

            def card(f, x=x, y=y, draw=draw, i=i, label=label):
                glass(CARD_W, CARD_H, 36, "panel").draw(f, x, y)
                draw(f, x, y, t)
                capsule(f, x + 26, y + CARD_H - 72, 44, 44, GREEN)
                text(f, str(i + 1), x + 48, y + CARD_H - 50, 24, weight="bold")
                text(f, label, x + 86, y + CARD_H - 50, 22, weight="semibold", anchor="lm")
            faded(frame, ease((t - d) / 0.4), card)
        if 2.9 <= t < 3.95:
            mx, my = self.menu_at

            def menu(f):
                glass(260, 192, 18, "caption").draw(f, mx + 10, my + 10)
                for j, item in enumerate(self.MENU):
                    iy = my + 18 + 44 * j
                    if j == 1 and t >= 3.5:
                        fill_round(f, mx + 18, iy + 2, 244, 40, 10, GREEN, 0.4)
                    text(f, item, mx + 34, iy + 22, 18, TEXT, "semibold" if j == 1 else "regular", "lm")
            faded(frame, ease((t - 2.9) / 0.15) * ease((3.95 - t) / 0.1), menu)
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.5)

    def _releases(self, f, x, y, t):
        fill_round(f, x + 24, y + 24, 492, 44, 22, (255, 255, 255), 0.1)
        text(f, "github.com/Future-Web2/AirMouse/releases", x + 46, y + 46, 17, MUTED, anchor="lm")
        text(f, "AirMouse", x + 32, y + 116, 32, weight="bold", anchor="lm")
        fill_round(f, x + 192, y + 100, 92, 32, 16, GREEN, 0.95)
        text(f, "Latest", x + 238, y + 116, 16, weight="semibold")
        text(f, "Assets", x + 32, y + 170, 18, MUTED, "semibold", "lm")
        fill_round(f, x + 24, y + 190, 492, 64, 16, (255, 255, 255), 0.2 if 1.0 <= t < 2.5 else 0.08)
        zip_icon(f, x + 44, y + 202, 30, 40)
        text(f, "AirMouse-windows-x64.zip", x + 90, y + 222, 20, weight="semibold", anchor="lm")
        text(f, "83 МБ", x + 498, y + 222, 18, MUTED, anchor="rm")
        fill_round(f, x + 24, y + 262, 492, 56, 16, (255, 255, 255), 0.05)
        text(f, ICON["file"], x + 59, y + 290, 22, MUTED, "icons")
        text(f, "Source code (zip)", x + 90, y + 290, 18, MUTED, anchor="lm")
        if t >= 1.45:
            p = ease((t - 1.5) / 1.1)
            fill_round(f, x + 24, y + 372, 492, 12, 6, (255, 255, 255), 0.14)
            fill_round(f, x + 24, y + 372, max(12.0, 492 * p), 12, 6, GREEN)
            if p < 1:
                text(f, f"Загрузка…  {83 * p:.0f} из 83 МБ", x + 26, y + 346, 18, MUTED, anchor="lm")
            else:
                text(f, ICON["check"], x + 36, y + 346, 20, GREEN, "icons")
                text(f, "Скачано", x + 58, y + 346, 18, TEXT, "semibold", "lm")

    def _extract(self, f, x, y, t):
        text(f, ICON["folder"], x + 42, y + 46, 20, MUTED, "icons")
        text(f, "Загрузки", x + 64, y + 46, 18, MUTED, anchor="lm")
        k = ease((t - 3.95) / 0.45)            # the zip moves aside for the folder
        cx = x + 270 - 120 * k
        zip_icon(f, cx - 40, y + 150, 80, 104)
        text(f, "AirMouse-windows-x64.zip", cx, y + 290, 17, TEXT, "semibold")
        if t >= 3.95:
            s = spring(t, 3.95)
            if s > 0.05:
                folder_icon(f, x + 390 - 55 * s, y + 202 - 45 * s, 110 * s, 90 * s)
            text(f, "→", x + 282, y + 200, 40, MUTED, alpha=k)
            text(f, "AirMouse", x + 390, y + 290, 18, TEXT, "semibold", alpha=k)

    def _run(self, f, x, y, t):
        text(f, "Загрузки  ›  AirMouse", x + 32, y + 46, 18, MUTED, anchor="lm")
        fill_round(f, x + 24, y + 90, 492, 60, 14, (255, 255, 255), 0.05)
        folder_icon(f, x + 44, y + 106, 34, 28)
        text(f, "_internal", x + 94, y + 120, 19, TEXT, anchor="lm")
        chosen = t >= 5.3
        fill_round(f, x + 24, y + 160, 492, 60, 14, GREEN if chosen else (255, 255, 255),
                   0.4 if chosen else 0.16 if t >= 4.9 else 0.05)
        rgb, a = self.icon
        blend(f, int(x + 42), int(y + 172), rgb, 1 - a, a)
        text(f, "AirMouse.exe", x + 94, y + 190, 19, TEXT, "semibold", "lm")
        text(f, "Приложение", x + 498, y + 190, 16, MUTED, anchor="rm")

        def tip(g):
            fill_round(g, x + 24, y + 254, 492, 196, 18, (0, 0, 0), 0.22)
            text(g, ICON["shield"], x + 62, y + 296, 28, GREEN, "icons")
            text(g, "Windows предупредил?", x + 96, y + 296, 21, TEXT, "semibold", "lm")
            text(g, "Нажмите «Подробнее»,", x + 48, y + 348, 19, MUTED, anchor="lm")
            text(g, "затем «Выполнить в любом случае».", x + 48, y + 378, 19, MUTED, anchor="lm")
            text(g, "Python и установка не нужны.", x + 48, y + 420, 18, MUTED, anchor="lm")
        faded(f, ease((t - 6.0) / 0.4), tip)


class StartScene:
    """The real window: «Старт» turns the camera on."""

    LENGTH = 6.6
    SCALE = 0.8
    POS = (150, 236)
    CLICK = 2.0
    NOTES = ((0.5, "Выберите режим: Рука, Глаза или Голова"), (2.0, "Нажмите «Старт» — включится камера"),
             (3.4, "Поднимите ладонь — курсор пойдёт за ней"), (4.7, "Ctrl+Alt+M — пауза, «Стоп» — выключить"))

    def __init__(self, camera):
        self.app = make_app("nature", self.SCALE)
        self.camera = camera
        self.icon = app_icon(22)
        self.tracker = fake_tracker()
        app = self.app
        hand_mode = window_at(app, self.POS, *segment_centre(app.segmented, 0))
        start = window_at(app, self.POS, *centre(app.start_btn.rect))
        self.keys = [(0.0, 1000, 1010), (0.8, *hand_mode), (1.4, *hand_mode), (1.85, *start), (2.7, *start),
                     (3.6, 1560, 960), (6.6, 1560, 960)]
        self.clicks = [self.CLICK]

    def __call__(self, frame, t):
        app = self.app
        step_title(frame, "2. Нажмите «Старт»", t)
        running = t >= self.CLICK + 0.12
        app.tracker = self.tracker if running else None
        app._show_running(running)
        app._has_frame = t >= self.CLICK + 0.9
        app._camera_bg = app._cover(self.camera.frame(t, moving_hand(t))) if app._has_frame else None
        app.segmented.hover = 0.6 <= t < 1.6
        app.start_btn.hover = 1.7 <= t < 2.6
        app.start_btn.pressed = pressed(t, self.CLICK)
        image = render_app(app, t + 3.0)
        y = self.POS[1] + (1 - spring(t, 0.05)) * 80
        faded(frame, ease(t / 0.4), lambda f: draw_window(f, image, self.POS[0], y, "AirMouse",
                                                         caption_rgb(app.theme), self.icon))
        for i, (start, s) in enumerate(self.NOTES):
            note(frame, i + 1, s, 1110, 330 + 120 * i, t, start, 740)
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.5)


class HandPlacement:
    """Where the hand goes: the frame on the preview is the whole screen."""

    LENGTH = 7.0
    PANEL, IMAGE = (100, 180, 780, 650), (120, 236, 740, 555)
    SCREEN_PANEL, SCREEN = (1000, 180, 600, 380), (1020, 226, 560, 315)
    TOUR = [(0.0, 960, 540), (0.8, 960, 540), (1.8, 160, 130), (2.5, 160, 130), (3.5, 1760, 140), (4.1, 1760, 140),
            (5.1, 1680, 950), (5.7, 1680, 950), (6.8, 960, 540)]
    CHECKS = ((0.5, "40–70 см от камеры"), (1.5, "Ладонь смотрит в камеру"), (2.5, "Свет спереди, не из окна сзади"),
              (3.5, "Рамка на превью — это весь экран"), (4.5, "«Центр зоны по руке» — рамка к руке"))

    def __init__(self, camera):
        self.camera = camera
        self.wall = LiquidBackdrop(self.SCREEN[2], self.SCREEN[3], seed=12, **NATURE["backdrop"])
        self.clicks = []

    def __call__(self, frame, t):
        step_title(frame, "3. Как держать руку", t)
        sx, sy = path(self.TOUR, t)
        pts = bench.hand(*P.cam_for(sx, sy))
        x, y, w, h = self.PANEL
        a = ease(t / 0.4)

        def preview(f):
            glass(w, h, 30, "panel").draw(f, x, y)
            capsule(f, x + 24, y + 22, 12, 12, (255, 70, 80))
            text(f, "Превью камеры в окне AirMouse", x + 46, y + 28, 17, MUTED, "semibold", "lm")
            ix, iy, iw, ih = self.IMAGE
            picture = cv2.resize(self.camera.frame(t, pts), (iw, ih), interpolation=cv2.INTER_LINEAR)
            put_round(f, picture, ix, iy, 18)
        faded(frame, a, preview)

        x, y, w, h = self.SCREEN_PANEL

        def screen(f):
            glass(w, h, 30, "panel").draw(f, x, y)
            text(f, ICON["monitor"], x + 30, y + 26, 16, MUTED, "icons")
            text(f, "Экран", x + 50, y + 26, 17, MUTED, "semibold", "lm")
            ix, iy, iw, ih = self.SCREEN
            put_round(f, self.wall.render(t * 0.5 + 2), ix, iy, 12)
            cursor_arrow(f, ix + sx / 1920 * iw, iy + sy / 1080 * ih, 1.0)
        faded(frame, ease((t - 0.2) / 0.4), screen)

        for i, (start, s) in enumerate(self.CHECKS):
            k = ease((t - start) / 0.35)
            cy = 628 + 62 * i
            dx = (1 - k) * 40
            text(frame, ICON["check"], 1022 + dx, cy, 30, GREEN, "icons", alpha=k)
            text(frame, s, 1062 + dx, cy, 28, weight="semibold", anchor="lm", alpha=k)


class Gestures(P.HandDemo):
    TITLE = "4. Жесты рукой"
    CAPTIONS = [(0.0, 1.7, "Ладонь — двигает курсор"), (1.7, 3.3, "Щипок большим и указательным — клик"),
                (3.3, 5.6, "Два пальца вверх или вниз — прокрутка"),
                (5.6, 9.3, "Сжать, держать и вести — перетаскивание"),
                (9.3, 12.6, "Большой к двум пальцам — правый клик")]


class FakeVolume:
    """The volume widget's sound device: it only remembers the level (the real volume is not touched)."""

    def __init__(self, level):
        self._level, self._muted = level, False

    def level(self):
        return self._level

    def muted(self):
        return self._muted

    def set_level(self, level):
        self._level = level

    def set_muted(self, muted):
        self._muted = muted


class WidgetEnv:
    """What the widgets ask OnScreen for, answered by the scene."""

    def __init__(self):
        self.s = 1.0
        self.accent, self.look = GREEN, NATURE["widgets"]
        self.volume = FakeVolume(0.3)
        self.frame, self.frame_id = None, 0
        self.mode, self.pointer = MOVE, (0, 0)

    def status(self):
        return MODE_TEXT.get(self.mode, ""), MODE_DOT.get(self.mode, GREEN), "30 кадр/с"

    def camera_on(self):
        return True

    def cursor(self):
        return self.pointer

    def request(self, item):
        pass

    def changed(self):
        pass

    def place(self, widget):
        pass

    def clamp(self, widget, x, y):
        return x, y


class WidgetsDemo:
    """The real on-screen widgets on a mock screen, worked by the real gesture engine."""

    LENGTH = 10.6
    DESK = (560, 170, 1280, 720)        # the mock screen; its pixels are the widgets' pixels
    CAMERA = (60, 236, 460, 410)
    KEYS_PANEL = (60, 676, 460, 150)
    REST = (330, 250)
    THUMB = (0.7, 2.0)                  # thumbs up held
    PINCHES = ((4.45, 6.6), (8.35, 8.5))
    HOTKEY = (2.9, 3.6)                 # Ctrl+Alt+W: hide, then show again
    CAPTIONS = [(0.0, 2.6, "Палец вверх — показать или скрыть виджеты"), (2.6, 4.4, "Или Ctrl+Alt+W с клавиатуры"),
                (4.4, 7.0, "Щипок на ползунке и вести — громкость"),
                (7.0, 9.0, "Кнопки: Копировать, Win+D, свои команды"),
                (9.0, 10.6, "Виджеты AirMouse — на экране, а не в Win+W")]

    def __init__(self, camera):
        self.camera = camera
        self.env = env = WidgetEnv()
        specs = [dict(spec) for spec in onscreen.default_widgets() if spec["on"]]
        self.widgets = [onscreen.WIDGET_CLASSES[spec["type"]](spec, env) for spec in specs]
        self.kind = {w.spec["type"]: w for w in self.widgets}
        self._arrange()
        self.ring = onscreen.CursorRing(1.0)
        self.wall = LiquidBackdrop(1280, 720, seed=8, **NATURE["backdrop"])
        self.video = LiquidBackdrop(568, 300, seed=4, colors=((0.95, 0.62, 0.30), (0.20, 0.45, 0.30),
                                                              (0.55, 0.75, 0.90), (0.95, 0.85, 0.55)),
                                    base=(0.05, 0.08, 0.10))
        self.mask = round_mask(1280, 720, 14)
        self._simulate()

    def _arrange(self):
        """As OnScreen.arrange: a column along the right edge, then the next one to its left."""
        sw, sh = self.DESK[2:]
        margin, gap = 24, 12
        x_right, y, column_w = sw - margin, margin, 0
        for w in self.widgets:
            pw, ph = w.panel_size()
            if y + ph > sh - margin and y > margin:
                x_right -= column_w + gap
                y, column_w = margin, 0
            w.spec["x"], w.spec["y"] = x_right - pw, y
            y += ph + gap
            column_w = max(column_w, pw)

    # the mouse, as the widget windows get it
    def _target(self, x, y):
        for w in reversed(self.widgets):
            pw, ph = w.panel_size()
            if w.spec["x"] <= x < w.spec["x"] + pw and w.spec["y"] <= y < w.spec["y"] + ph:
                return w
        return None

    def _route(self, kind, x, y, visible):
        def local(w):
            return x - w.spec["x"] + w.m, y - w.spec["y"] + w.m

        if self._captured is not None:
            w = self._captured
            w.mouse(kind, *local(w), 0)
            if kind == "up":
                self._captured = None
            return
        target = self._target(x, y) if visible else None
        if target is not self._hovered:
            if self._hovered is not None:
                self._hovered.mouse("leave", 0, 0, 0)
            self._hovered = target
        if target is None or kind == "up":
            return
        if kind == "click":
            target.mouse("down", *local(target), 0)
            target.mouse("up", *local(target), 0)
        else:
            target.mouse(kind, *local(target), 0)
            if kind == "down":
                self._captured = target

    def _visible(self, t):
        visible, since = False, -1e9
        for et, on in self.toggles:
            if et <= t:
                visible, since = on, et
        return visible, since

    def _simulate(self):
        """Run the gesture engine on the scripted hand once and keep what each frame shows."""
        sw, sh = self.DESK[2:]
        engine = GestureEngine(Settings(), sw, sh)
        rng = np.random.default_rng(6)
        volume, buttons = self.kind["volume"], self.kind["buttons"]
        volume._read()
        knob = (volume.spec["x"] + volume.TRACK[0], volume.spec["y"] + 36)
        span = volume.TRACK[1] - volume.TRACK[0]
        copy = (buttons.spec["x"] + 78, buttons.spec["y"] + 64)        # «Копировать»
        keys = [(0.0, *self.REST), (2.4, *self.REST), (3.9, knob[0] + 0.3 * span, knob[1]),
                (4.85, knob[0] + 0.3 * span, knob[1]), (6.0, knob[0] + 0.86 * span, knob[1]),
                (6.9, knob[0] + 0.86 * span, knob[1]), (8.1, *copy), (self.LENGTH, *copy)]
        self._captured = self._hovered = None
        self.toggles, self.frames, self.clicks, self.click_at = [], [], [], []
        cursor = self.REST
        for i in range(-30, int(self.LENGTH * FPS) + 1):
            t = i / FPS
            ox, oy = cam_for_screen(*path(keys, max(t, 0.0)), sw, sh)
            thumb = self.THUMB[0] <= t < self.THUMB[1]
            pts = bench.hand(ox, oy, pose="thumb") if thumb else bench.hand(ox, oy, ramp(self.PINCHES, t, 0.1))
            pts = bench.noisy(pts, rng, 0.5, 0.4)
            visible = self._visible(t)[0]
            flash = buttons._flash
            for action in engine.update(pts, 640, 480, 100 + t, cursor):
                kind = action[0]
                if kind == "move":
                    cursor = action[1:]
                    self.env.pointer = cursor
                    self._route("move", *cursor, visible)
                elif kind == "widgets":
                    self.toggles.append((t, not visible))
                elif kind in ("down", "up", "click"):
                    self._route(kind, *cursor, visible)
                    self.ring.event(action, t)
                    if kind != "up" and i >= 0:
                        self.clicks.append(t)
                        self.click_at.append((t, *cursor))
            if buttons._flash is not None and buttons._flash is not flash:     # just clicked: time it in video time
                buttons._flash = (buttons._flash[0], t + 0.3)
            elif buttons._flash is not None and t >= buttons._flash[1]:
                buttons._flash = None
            if any(abs(t - k) < 1e-6 for k in self.HOTKEY):
                self.toggles.append((t, not self._visible(t)[0]))
            if i >= 0:
                self.frames.append(SimpleNamespace(
                    pts=pts, cursor=cursor, mode=engine.mode, ring=self.ring.state(engine.mode, engine.pinch, t),
                    states=[(w.hover, w.pressed) for w in self.widgets], volume=volume.level,
                    flash=buttons._flash[0] if buttons._flash else None))

    def __call__(self, frame, t):
        rec = self.frames[min(int(round(t * FPS)), len(self.frames) - 1)]
        step_title(frame, "5. Виджеты на экране", t)
        self._camera_panel(frame, rec, t)
        self._keys_panel(frame, t)

        desk = self.wall.render(t * 0.5 + 3)
        self._player(desk, t)
        desk[672:] = (desk[672:] * 0.25 + np.array((14, 20, 16)) * 0.75).astype(np.uint8)   # taskbar
        for i, color in enumerate(((88, 200, 122), (66, 140, 235), (236, 190, 72), (226, 90, 120), (150, 120, 235))):
            fill_round(desk, 548 + 40 * i, 680, 32, 32, 8, color, 0.95)
        text(desk, "12:30", 1256, 696, 15, TEXT, anchor="rm")

        env = self.env
        env.mode = rec.mode
        env.frame = self.camera.frame(t, rec.pts, rec.mode)
        volume, buttons = self.kind["volume"], self.kind["buttons"]
        volume.level, volume.muted = rec.volume, False
        buttons._flash = (rec.flash, math.inf) if rec.flash is not None else None
        visible, since = self._visible(t)
        for i, (w, (hover, down)) in enumerate(zip(self.widgets, rec.states)):
            k = ease((t - since - 0.06 * i) / 0.3)
            a = k if visible else 1 - k
            if a <= 0.01:
                continue
            w.hover, w.pressed = hover, down
            if isinstance(w, onscreen.StatusWidget):
                w._shown = (None, None)
            layer = w.render(t)
            paste_layer(desk, layer.bgra(), int(w.spec["x"] - w.m), int(w.spec["y"] - w.m + (1 - a) * 18), a)
        for c, cx, cy in self.click_at:
            ripple(desk, cx, cy, (t - c) / 0.6)
        cx, cy = rec.cursor
        ring = self.ring.render(rec.ring)
        paste_layer(desk, ring.bgra(), int(cx - self.ring.size / 2), int(cy - self.ring.size / 2))
        cursor_arrow(desk, cx, cy, 1.25)

        x, y, w, h = self.DESK
        glass(w + 28, h + 28, 28, "panel").draw(frame, x - 14, y - 14)
        blend(frame, x, y, desk, 1 - self.mask, self.mask)
        caption_track(frame, self.CAPTIONS, t, 978)

    def _camera_panel(self, frame, rec, t):
        x, y, w, h = self.CAMERA
        glass(w, h, 30, "panel").draw(frame, x, y)
        capsule(frame, x + 24, y + 22, 12, 12, (255, 70, 80))
        text(frame, "Камера", x + 46, y + 28, 17, MUTED, "semibold", "lm")
        k = 0.62
        ox, oy = x + (w - 640 * k) / 2, y + 60
        zx0, zy0, zx1, zy1 = zone_rect(Settings(), 640, 480, 16, 9)
        cv2.rectangle(frame, (int(ox + zx0 * 640 * k), int(oy + zy0 * 480 * k)),
                      (int(ox + zx1 * 640 * k), int(oy + zy1 * 480 * k)), (200, 215, 205), 1, cv2.LINE_AA)
        P.draw_hand(frame, rec.pts, ox, oy, k, P.MODE_DOT.get(rec.mode, GREEN))

    def _keys_panel(self, frame, t):
        x, y, w, h = self.KEYS_PANEL
        glass(w, h, 30, "panel").draw(frame, x, y)
        text(frame, "Или с клавиатуры", x + 24, y + 30, 17, MUTED, "semibold", "lm")
        kx = x + 24
        down = any(k <= t < k + 0.3 for k in self.HOTKEY)
        for i, (label, kw) in enumerate((("Ctrl", 112), ("Alt", 96), ("W", 76))):
            if i:
                text(frame, "+", kx + 14, y + 96, 26, MUTED)
                kx += 28
            fill_round(frame, kx, y + 66 + (3 if down else 0), kw, 60, 14, GREEN if down else (255, 255, 255),
                       0.75 if down else 0.14)
            text(frame, label, kx + kw / 2, y + 96 + (3 if down else 0), 24, weight="semibold")
            kx += kw

    def _player(self, desk, t):
        x, y, w, h = 40, 56, 600, 420
        fill_round(desk, x, y, w, h, 16, (16, 22, 18), 0.92)
        text(desk, "Видео — Природа.mp4", x + 20, y + 24, 15, MUTED, anchor="lm")
        put_round(desk, self.video.render(t * 0.8), x + 16, y + 46, 10)
        capsule(desk, x + 64, y + h - 40, w - 100, 6, (255, 255, 255), 0.25)
        capsule(desk, x + 64, y + h - 40, (w - 100) * (0.3 + 0.01 * t), 6, GREEN)
        text(desk, ICON["play"], x + 34, y + h - 37, 18, TEXT, "icons")


class Eyes(P.EyesDemo):
    TITLE = "6. Глаза и голова: без рук"
    CAPTIONS = [(0.0, 2.3, "Сначала калибровка: смотрите на 9 точек"),
                (2.3, 4.4, "Взгляд ведёт курсор, поворот головы доводит"),
                (4.4, 5.9, "Долго моргнуть — клик"), (5.9, 8.0, "Подмигнуть — правый клик"),
                (8.0, 10.7, "Открыть рот — перетаскивание")]


class AdvancedScene:
    """«Подробнее»: the real window (screenshots), 60 frames a second, the tabs."""

    LENGTH = 10.0
    SCALE = 0.62
    APP_POS = (150, 330)
    K = 1.15                                # the dialog picture, enlarged a little for the video
    SHOTS = ("camera", "camera60", "cursor", "clicks")
    SWITCH = (3.5, 5.6, 7.5)                # the picture changes to the next shot
    NOTES = ((0.4, "«Подробнее» — 23 параметра в 6 вкладках"), (3.4, "60 кадр/с — курсор точнее и отзывчивее"),
             (5.8, "Курсор, клики, жесты, пороги лица"), (7.8, "«По умолчанию» вернёт всё как было"))

    def __init__(self, camera):
        self.app = make_app("nature", self.SCALE)
        self.camera = camera
        self.icon = app_icon(22)
        self.tracker = fake_tracker()
        self.shots = [cv2.cvtColor(cv2.imread(str(GUIDE / f"advanced_{name}.png")), cv2.COLOR_BGR2RGB)
                      for name in self.SHOTS]
        meta = json.loads((GUIDE / "advanced.json").read_text(encoding="utf-8"))
        h, w = self.shots[0].shape[:2]
        self.shots = [cv2.resize(s, (round(w * self.K), round(h * self.K)), interpolation=cv2.INTER_CUBIC)
                      for s in self.shots]
        aw, ah = self.app.size
        self.pos = (self.APP_POS[0] + (aw - w * self.K) / 2, self.APP_POS[1] + (ah - h * self.K) / 3)
        self.box = [v * self.K for v in meta["camera_fps"]]
        bx, by = self.pos
        box = (bx + self.box[0] + self.box[2] / 2, by + self.box[1] + self.box[3] / 2)
        self.option = (box[0] - 60, by + self.box[1] + self.box[3] + 6 + 1.5 * 34 * self.K)
        tabs = [(bx + (tx + tw / 2) * self.K, by + (ty + 18) * self.K) for tx, ty, tw in meta["tabs"]]
        button = window_at(self.app, self.APP_POS, *centre(self.app.advanced_btn.rect))
        reset = (bx + 75 * self.K, by + (h - 32) * self.K)
        self.keys = [(0.0, 1100, 1010), (1.0, *button), (1.5, *button), (2.5, *box), (3.0, *box), (3.3, *self.option),
                     (3.6, *self.option), (5.1, *tabs[1]), (6.9, *tabs[1]), (7.4, *tabs[2]), (8.0, *tabs[2]),
                     (8.9, *reset), (10.0, *reset)]
        self.clicks = [1.2, 2.9, 3.45, 5.5, 7.4]

    def __call__(self, frame, t):
        app = self.app
        step_title(frame, "7. «Подробнее»: точная настройка", t)
        app.tracker, app._has_frame = self.tracker, True
        app._show_running(True)
        app._camera_bg = app._cover(self.camera.frame(t, moving_hand(t)))
        app.advanced_btn.hover = 0.9 <= t < 1.5
        app.advanced_btn.pressed = pressed(t, 1.2)
        image = render_app(app, t + 9.0)
        faded(frame, ease(t / 0.4), lambda f: draw_window(f, image, *self.APP_POS, "AirMouse",
                                                         caption_rgb(app.theme), self.icon))
        if t >= 1.35:
            self._dialog(frame, t)
        for i, (start, s) in enumerate(self.NOTES):
            note(frame, i + 1, s, 1000, 330 + 120 * i, t, start, 800)
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.5)

    def _dialog(self, frame, t):
        n = sum(t >= s for s in self.SWITCH)
        shot = self.shots[n]
        if n and t - self.SWITCH[n - 1] < 0.15:
            k = ease((t - self.SWITCH[n - 1]) / 0.15)
            shot = cv2.addWeighted(self.shots[n - 1], 1 - k, shot, k, 0)
        bx, by = self.pos
        y = by + (1 - spring(t, 1.35)) * 40

        def dialog(f):
            draw_window(f, shot, bx, y, "Подробные настройки — AirMouse", (32, 32, 32))
            x0, y0, w, h = self.box
            if 3.5 <= t < 5.4:
                outline(f, bx + x0, y + y0, w, h, 6, GREEN, 0.9 * ease((t - 3.5) / 0.2) * ease((5.4 - t) / 0.3))
            if 2.95 <= t < 3.5:                  # the open list of the box
                lx, ly = bx + x0, y + y0 + h + 4
                fill_round(f, lx, ly, w, 2 * 34 * self.K + 8, 8, (44, 44, 44))
                for j, label in enumerate(("30 кадр/с", "60 кадр/с — точнее и быстрее")):
                    iy = ly + 4 + j * 34 * self.K
                    if j == 1 and t >= 3.3:
                        fill_round(f, lx + 4, iy, w - 8, 34 * self.K, 6, (64, 64, 64))
                    text(f, label, lx + 14, iy + 17 * self.K, 15 * self.K, TEXT, anchor="lm")
        faded(frame, ease((t - 1.35) / 0.25), dialog)


class DesignScene:
    """The design row: «Стекло» -> «Природа», the window changes like a drop spreading."""

    LENGTH = 7.0
    SCALE = 0.8
    POS = (150, 236)
    CLICK = 1.3
    NOTES = ((0.3, "Дизайн → «Природа»"), (2.4, "Запотевшее стекло и капли конденсата"),
             (3.4, "Зелёный фон с солнечными бликами"), (4.4, "Виджеты на экране — тоже в каплях"),
             (5.4, "Есть ещё «Стекло» и «Классика»"))

    def __init__(self):
        self.before, self.after = make_app("glass", self.SCALE), make_app("nature", self.SCALE)
        for app in (self.before, self.after):
            app.design.on_change = lambda value: None        # the real one reopens the window
        self.icon = app_icon(22)
        self.spot = [v * self.SCALE for v in segment_centre(self.before.design, 1)]
        self.keys = [(0.0, 1100, 1010), (1.0, *window_at(self.before, self.POS, *segment_centre(self.before.design, 1))),
                     (2.4, *window_at(self.before, self.POS, *segment_centre(self.before.design, 1))),
                     (3.4, 1560, 980), (7.0, 1560, 980)]
        self.clicks = [self.CLICK]
        w, h = self.before.size
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.dist = np.hypot(xx - self.spot[0], yy - self.spot[1])
        self.reach = float(self.dist.max())
        self.n = None

    def _advance(self, t):
        """Move the design switch's liquid pill to time t (it is a spring, so frame by frame)."""
        target = round(t * FPS)
        seg = self.before.design
        if self.n is None or target < self.n:
            seg.index, seg.pos, seg.vel = 0, 0.0, 0.0
            self.n = -1
        while self.n < target:
            self.n += 1
            if self.n == round(self.CLICK * FPS):
                seg.press(*segment_centre(seg, 1))
            seg.tick(1 / FPS)

    def __call__(self, frame, t):
        step_title(frame, "8. Новый дизайн «Природа»", t)
        self._advance(t)
        self.before.design.hover = 0.9 <= t < 1.8
        before = render_app(self.before, t + 2.0).copy()
        k = ease((t - self.CLICK - 0.35) / 1.0)
        if k > 0:
            after = render_app(self.after, t + 2.0)
            m = np.clip((k * self.reach - self.dist) / 40 + 0.5, 0, 1)[..., None]
            image = (before * (1 - m) + after * m).astype(np.uint8)
        else:
            image = before
        bar = tuple(int(a + (b - a) * k) for a, b in zip(caption_rgb(self.before.theme), caption_rgb(self.after.theme)))
        y = self.POS[1] + (1 - spring(t, 0.05)) * 80
        faded(frame, ease(t / 0.4), lambda f: draw_window(f, image, self.POS[0], y, "AirMouse", bar, self.icon))
        for i, (start, s) in enumerate(self.NOTES):
            note(frame, i + 1, s, 1110, 300 + 112 * i, t, start, 740)
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.5)


class Tips:
    LENGTH = 7.6
    TIPS = ((ICON["sun"], "Темно — 15 кадр/с", "Включите свет перед собой"),
            (ICON["pointer"], "Курсор дрожит", "«Стабилизация» правее"),
            (ICON["warning"], "Клики сами по себе", "«Чувствительность клика» левее"),
            (ICON["pause"], "Пауза", "Ctrl+Alt+M"),
            (ICON["monitor"], "Виджеты", "Палец вверх или Ctrl+Alt+W"),
            (ICON["admin"], "Диспетчер задач", "AirMouse — от имени администратора"))

    def __init__(self):
        self.clicks = []

    def __call__(self, frame, t):
        step_title(frame, "Советы", t)
        for i, (icon, title, body) in enumerate(self.TIPS):
            d = 0.2 + 0.15 * i
            x, y = CARD_X[i % 3], 220 + 290 * (i // 3) + (1 - spring(t, d)) * 100

            def card(f, x=x, y=y, icon=icon, title=title, body=body):
                glass(CARD_W, 250, 36, "panel").draw(f, x, y)
                text(f, icon, x + 62, y + 62, 40, GREEN, "icons")
                text(f, title, x + 40, y + 136, 32, weight="bold", anchor="lm")
                text(f, body, x + 40, y + 190, 24, MUTED, anchor="lm")
            faded(frame, ease((t - d) / 0.4), card)
        text(frame, "Полный гайд с картинками — docs/GUIDE.md на GitHub", W / 2, 860, 30, MUTED,
             alpha=ease((t - 2.4) / 0.5))


class Outro:
    LENGTH = 5.5

    def __init__(self):
        self.icon = app_icon(110)
        self.clicks = []

    def __call__(self, frame, t):
        P.orbs(frame, t + 20)
        off = (1 - spring(t, 0.1)) * 140
        faded(frame, ease(t / 0.5), lambda f: glass(1180, 560, 90, "hero").draw(f, 370, 170 + off))
        rgb, a = self.icon
        a = a * ease((t - 0.3) / 0.5)
        blend(frame, 905, int(205 + off), rgb, 1 - a, a)
        text(frame, "AirMouse", W / 2, 400 + off, 140, weight="bold", alpha=ease((t - 0.3) / 0.5))
        text(frame, "Бесплатно для Windows 10 и 11 — нужна только веб-камера", W / 2, 508 + off, 34, MUTED,
             alpha=ease((t - 0.6) / 0.5))
        link = "github.com/Future-Web2/AirMouse"
        lw = text_width(link, "semibold", 36) + 90

        def pill(f):
            glass(lw, 84, 42, "button").draw(f, W / 2 - lw / 2, 600 + off)
            text(f, link, W / 2, 642 + off, 36, weight="semibold")
        faded(frame, ease((t - 0.9) / 0.4), pill)
        chips(frame, ("Releases", "AirMouse-windows-x64.zip", "AirMouse.exe"), 860, t, 1.3, steps=True)


# -- timeline ----------------------------------------------------------------

def build_timeline():
    camera = Camera()
    parts = [Intro(), Download(), StartScene(camera), HandPlacement(camera), Gestures(), WidgetsDemo(camera),
             Eyes(), AdvancedScene(camera), DesignScene(), Tips(), Outro()]
    scenes, end = [], 0.0
    for scene in parts:
        start = max(end - P.XFADE, 0.0)
        end = start + scene.LENGTH
        scenes.append((start, end, scene))
    clicks = [start + c for start, _end, scene in scenes for c in scene.clicks]
    return scenes, end, clicks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(HERE / "AirMouse_guide.mp4"))
    parser.add_argument("--stills", help="comma-separated seconds; saves PNGs instead of the video")
    args = parser.parse_args()
    cv2.setNumThreads(0)

    scenes, duration, clicks = build_timeline()
    backdrop = LiquidBackdrop(W, P.H, seed=5, **NATURE["backdrop"])
    if args.stills:
        for s in args.stills.split(","):
            out = Path(args.out).parent / f"guide_{s}.png"
            Image.fromarray(P.render_frame(scenes, duration, backdrop, float(s))).save(out)
            print("saved", out)
        return

    import imageio_ffmpeg
    wav = Path(tempfile.gettempdir()) / "airmouse_guide_music.wav"
    whooshes = [start - 0.35 for start, *_ in scenes[1:]]
    P.make_music(wav, duration, whooshes, clicks, arp_from=4.0, pulse=(24.4, 80.0))
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{P.H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(duration * FPS)
    for i in range(total):
        proc.stdin.write(P.render_frame(scenes, duration, backdrop, i / FPS).tobytes())
        if i % 150 == 0:
            print(f"frame {i}/{total}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("saved", args.out)


if __name__ == "__main__":
    main()
