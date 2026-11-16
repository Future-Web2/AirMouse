"""Renders the AirMouse commercial: 1920x1080, 30 fps, 60 s, with music. It sells and it instructs.

    python promo/make_ad.py                     -> promo/AirMouse_ad.mp4      (Russian)
    python promo/make_ad.py --lang en           -> promo/AirMouse_ad_en.mp4   (English)
    python promo/make_ad.py --stills 2,12,30    -> promo/ad_2.png ... (to check frames)

The script, cut to the beat (120 BPM: a bar is 2 s, every scene starts on a bar):

     0 s  hook      a question and the answer shown at once: a pinch in the air clicks
     4 s  problem   three situations where a mouse gets in the way
    10 s  product   the name and the promise, on the drop of the music
    14 s  3 steps   download and unzip, press Start, show your palm   (the instruction)
    26 s  gestures  the four gestures, on the real gesture engine
    36 s  more      widgets, the notebook, eyes and head, two hands   (a quick montage)
    46 s  proof     measured numbers, while the music holds back
    52 s  offer     free, the platforms, a QR code and the address

Everything is said in captions, so it works without sound. The look is the calm one of the
poster and the vertical video. As there, the hand scenes run the real gesture engine and the
window and widgets are AirMouse's own, drawn into the video and never shown on the screen.

When the product gets its own site, change CTA_URL below and render again.
"""

import argparse
import json
import math
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_guide as G  # noqa: E402  (also puts the project on sys.path; draws nothing on the screen)
import make_promo as P  # noqa: E402
import make_vertical as V  # noqa: E402  (calm colours for the mock desktop; the beat)
from make_carousel import face, qr, sample_drawing  # noqa: E402
from make_poster import ACCENT, BACKDROP, CYAN, REPO, SLATE, calm_look, hand_points, hand_sketch, ring  # noqa: E402
from make_promo import (  # noqa: E402
    MUTED, TEXT, blend, capsule, cursor_arrow, ease, faded, fill_round, glass, path, ripple, spring, text,
    text_width,
)

from airmouse import bench, i18n, onscreen  # noqa: E402
from airmouse import settings as settings_module  # noqa: E402
from airmouse.gestures import PENDING  # noqa: E402
from airmouse.glass import LiquidBackdrop  # noqa: E402
from airmouse.notebook import Notebook  # noqa: E402

W, H, FPS = 1920, 1080, 30
CTA_URL = REPO                      # where the last scene sends people
PUSH, FLASH, FADE = 0.3, 0.35, 0.4  # lengths of the transitions, seconds
DARK = (8, 14, 26)

# Fluent icons
I_HAND, I_SCREEN, I_HEALTH, I_LOCK, I_CHECK, I_SHIELD = "", "", "", "", "", ""

# -- the words, in Russian and English ------------------------------------------------------
# *word* is drawn in the accent colour.

STRINGS = {
    "hook1": ("Компьютер без мыши?", "A computer without a mouse?"),
    "hook2": ("*Да.* Просто рукой в воздухе.", "*Yes.* Just your hand in the air."),
    "pain_title": ("Знакомо?", "Sound familiar?"),
    "pain1": ("Руки заняты", "Hands are busy"),
    "pain1a": ("Готовите, чините, рисуете —", "Cooking, fixing, sketching —"),
    "pain1b": ("а надо нажать «дальше»", "and you need to click “next”"),
    "pain2": ("Мышь далеко", "Mouse out of reach"),
    "pain2a": ("Презентация, телевизор,", "A presentation, a TV,"),
    "pain2b": ("экран на стене", "a screen on the wall"),
    "pain3": ("Рука устаёт", "Hand gets tired"),
    "pain3a": ("Запястье болит, пальцы", "A sore wrist, shaky fingers,"),
    "pain3b": ("дрожат, клик мимо", "clicks that miss"),
    "pain_end": ("Мышь не всегда под рукой.", "A mouse is not always at hand."),
    "reveal": ("Веб-камера становится *мышью.*", "Your webcam becomes *the* *mouse.*"),
    "chips": (("Без датчиков", "Без перчаток", "Без установки"), ("No sensors", "No gloves", "No installer")),
    "steps": ("Начать — три шага", "Three steps to start"),
    "s1": ("Скачайте и распакуйте", "Download and unzip"),
    "s1a": ("Архив 83 МБ. Установка", "An 83 MB archive. No installer"),
    "s1b": ("и Python не нужны.", "and no Python needed."),
    "s2": ("Нажмите «Старт»", "Press “Start”"),
    "s2a": ("Камера включится,", "The camera turns on"),
    "s2b": ("и программа увидит руку.", "and AirMouse sees your hand."),
    "s3": ("Покажите ладонь", "Show your palm"),
    "s3a": ("Курсор пойдёт за рукой.", "The cursor follows your hand."),
    "s3b": ("Рамка в кадре — это весь экран.", "The frame in the picture is the screen."),
    "mb": ("83 МБ", "83 MB"),
    "loading": ("Загрузка…  {} из 83 МБ", "Downloading…  {} of 83 MB"),
    "loaded": ("Скачано", "Downloaded"),
    "downloads": ("Загрузки", "Downloads"),
    "app_kind": ("Приложение", "Application"),
    "no_install": ("Двойной щелчок — и программа работает", "Double-click, and it runs"),
    "camera": ("Камера", "Camera"),
    "screen": ("Экран", "Screen"),
    "checks": (("40–70 см от камеры", "Ладонь к камере", "Свет спереди"),
               ("40–70 cm away", "Palm to the camera", "Light from the front")),
    "g_title": ("Четыре жеста — и вы умеете всё", "Four gestures cover everything"),
    "gestures": (("Ладонь — курсор", "Щипок — клик", "Два пальца — прокрутка", "Сжать и вести — перенос"),
                 ("Palm — cursor", "Pinch — click", "Two fingers — scroll", "Pinch and move — drag")),
    "w_title": ("Виджеты прямо на экране", "Widgets right on the screen"),
    "w_cap": ("Палец вверх — и они под рукой", "Thumbs up, and they are at hand"),
    "n_title": ("Блокнот: рисуйте в воздухе", "Notebook: draw in the air"),
    "n_checks": (("Ручка, маркер, ластик", "Страницы сохраняются сами", "Копировать — и Ctrl+V"),
                 ("Pen, marker, eraser", "Pages save themselves", "Copy, then Ctrl+V")),
    "e_title": ("Руки заняты? Глазами и головой", "Hands busy? Use your eyes and head"),
    "e_cap": ("Долго моргнули — клик", "A long blink is a click"),
    "t_title": ("Две руки — ещё точнее", "Two hands, even more precise"),
    "t_cap": ("Развели руки — крупнее", "Move your hands apart to zoom in"),
    "p_title": ("Рука дрожит — *курсор* *нет*", "Your hand shakes. *The* *cursor* *doesn’t*"),
    "hand": ("Рука", "Hand"),
    "cursor": ("Курсор", "Cursor"),
    "tremor": ("дрожь руки", "hand tremor"),
    "cursor_low": ("курсор", "cursor"),
    "stat1": ("20 из 20", "20 of 20"),
    "stat1a": ("щипков — ровно 20 кликов", "pinches made exactly 20 clicks"),
    "stat2a": ("ложных кликов за минуту", "false clicks in a minute"),
    "stat3": ("Видео с камеры", "Camera video"),
    "stat3a": ("не покидает компьютер", "never leaves your computer"),
    "p_foot": ("До 60 кадров в секунду  ·  работает без интернета", "Up to 60 frames per second  ·  works offline"),
    "fps": ("30 кадр/с", "30 fps"),
    "cta": ("Попробуйте бесплатно", "Try it free"),
    "cta_os": ("Windows 10 и 11  ·  Linux", "Windows 10 & 11  ·  Linux"),
    "cta_need": ("Нужна только веб-камера", "All you need is a webcam"),
    "cta_qr": ("Наведите камеру телефона", "Point your phone camera"),
    "cta_link": ("Ссылка — в описании", "Link in the description"),
    "desktop": ("Рабочий стол", "Desktop"),
    "tiles": (("Документы", "Фото", "Музыка", "Почта", "Настройки", "Папка"),
              ("Documents", "Photos", "Music", "Mail", "Settings", "Folder")),
    "rows": (P.ROWS, ("January report.docx", "Project slides.pptx", "Holiday photos", "Budget 2026.xlsx",
                      "Notes.txt", "Music for work", "Screenshots", "AirMouse promo.mp4", "Contract.pdf",
                      "Ideas.md", "Resume.docx", "Archive.zip")),
}
LANG = "ru"


def L(key):
    return STRINGS[key][0 if LANG == "ru" else 1]


def parts(s):
    """'a *b* c' -> [(word, colour)], the starred words in the accent colour."""
    return [(word.strip("*"), CYAN if word.startswith("*") else TEXT) for word in s.split()]


# -- helpers --------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def icon(size):
    return P.app_icon(size)


def kinetic(frame, words, cx, y, size, t, t0=0.0, step=0.09, weight="bold"):
    """A centred line whose words pop up one after another."""
    gap = size * 0.28
    widths = [text_width(s, weight, size) for s, _color in words]
    x = cx - (sum(widths) + gap * (len(words) - 1)) / 2
    for i, ((s, color), w) in enumerate(zip(words, widths)):
        d = t0 + i * step
        a = ease((t - d) / 0.2)
        if a > 0:
            text(frame, s, x, y + (1 - spring(t, d)) * size * 0.45, size, color, weight, "lm", a)
        x += w + gap


def mark(frame):
    """The small logo in the corner."""
    rgb, a = icon(40)
    blend(frame, 56, 46, rgb, 1 - a, a)
    text(frame, "AirMouse", 108, 66, 28, weight="semibold", anchor="lm")


def title(frame, s, t, y=96, size=56):
    kinetic(frame, parts(s), W / 2, y, size, t, 0.05, 0.06)


def lower(frame, s, t, t0, t1, y=972, size=40):
    """A glass pill with a line of text at the bottom, between t0 and t1."""
    if not t0 <= t < t1:
        return
    a = ease((t - t0) / 0.22) * ease((t1 - t) / 0.18)
    w = round((text_width(s, "semibold", size) + 96) / 2) * 2
    rise = (1 - spring(t, t0)) * 30

    def draw(f):
        glass(w, 92, 46, "caption").draw(f, W / 2 - w / 2, y - 46 + rise)
        text(f, s, W / 2, y + rise, size, weight="semibold")
    faded(frame, a, draw)


def camera_label(frame, x, y, label=None):
    capsule(frame, x + 24, y + 22, 12, 12, CYAN)
    text(frame, label or L("camera"), x + 46, y + 28, 17, MUTED, "semibold", "lm")


def mock_tiles(frame, sx, sy, tw, th, gx, gy, lit=None):
    """Six calm tiles, 3 x 2; returns their centres."""
    centres = []
    for j, (_name, _glyph, color) in enumerate(P.TILES):
        bx, by = sx + (j % 3) * (tw + gx), sy + (j // 3) * (th + gy)
        col = tuple(min(255, c + 70) for c in color) if j == lit else color
        fill_round(frame, bx, by, tw, th, 22, col, 0.92)
        centres.append((bx + tw / 2, by + th / 2))
    return centres


class Env(G.WidgetEnv):
    """What the real widgets ask for, in the calm look."""

    def __init__(self, s):
        super().__init__()
        self.s, self.look, self.accent = s, {}, onscreen.ACCENT

    def status(self):
        return L("cursor"), CYAN, L("fps")


# -- scenes ---------------------------------------------------------------------------------

class Hook:
    """0 s. The question, and the answer shown at once: a pinch in the air clicks a tile."""

    LENGTH = 4.0
    CLICK = 1.75

    def __init__(self):
        self.clicks, self.whooshes = [self.CLICK], []

    def __call__(self, frame, t):
        text(frame, L("hook1"), W / 2, 150 + (1 - spring(t)) * 50, 96, weight="bold", alpha=ease(t / 0.3))
        x, y, w, h = 240, 260, 1440, 610
        clicked = t >= self.CLICK

        def stage(f):
            glass(w, h, 60, "hero").draw(f, x, y)
            pinch = 0.9 * ease((t - 0.7) / 0.9) * (1 - ease((t - 2.3) / 0.5))
            pts = hand_points("open", pinch)
            k, hx, hy = 2.5, x + 130, y + 60
            hand_sketch(f, pts, hx, hy, k, CYAN, glow=(20, 70, 150))
            for i in (4, 8):
                cv2.circle(f, (int((hx + pts[i][0] * k) * 16), int((hy + pts[i][1] * k) * 16)), 15 * 16, CYAN, -1,
                           cv2.LINE_AA, 4)
            sx, sy, sw, sh = x + 790, y + 115, 540, 380
            fill_round(f, sx, sy, sw, sh, 30, DARK, 0.85)
            for i in range(3):
                capsule(f, sx + 24 + i * 22, sy + 20, 12, 12, (100, 116, 139))
            lit = 4 if clicked and t < self.CLICK + 0.5 else None
            cx, cy = mock_tiles(f, sx + 30, sy + 62, 150, 130, 15, 20, lit)[4]
            if not clicked:
                ring(f, PENDING, min(pinch / 0.9, 0.95), cx, cy, 2.0)
            ripple(f, cx, cy, (t - self.CLICK) / 0.6, 2.0)
            cursor_arrow(f, cx, cy, 1.9)
        faded(frame, ease((t - 0.1) / 0.35), stage)
        kinetic(frame, parts(L("hook2")), W / 2, 968, 60, t, 2.05, 0.09)


class Problem:
    """4 s. Three situations where the mouse is the problem; one card per bar of the music."""

    LENGTH = 6.0
    CARDS = ((I_HAND, "pain1"), (I_SCREEN, "pain2"), (I_HEALTH, "pain3"))
    AT = (0.15, 2.0, 4.0)

    def __init__(self):
        self.clicks, self.whooshes = [], [a - 0.15 for a in self.AT[1:]]

    def __call__(self, frame, t):
        mark(frame)
        title(frame, L("pain_title"), t, 140, 76)
        for i, ((glyph, key), at) in enumerate(zip(self.CARDS, self.AT)):
            a = ease((t - at) / 0.3)
            if a <= 0:
                continue
            x, y = 120 + i * 580, 270 + (1 - spring(t, at)) * 120

            def card(f, x=x, y=y, glyph=glyph, key=key):
                glass(520, 470, 44, "panel").draw(f, x, y)
                fill_round(f, x + 195, y + 50, 130, 130, 65, ACCENT, 0.16)
                text(f, glyph, x + 260, y + 115, 66, CYAN, "icons")
                text(f, L(key), x + 260, y + 252, 46, weight="bold")
                text(f, L(key + "a"), x + 260, y + 334, 27, MUTED)
                text(f, L(key + "b"), x + 260, y + 376, 27, MUTED)
            faded(frame, a, card)
        kinetic(frame, parts(L("pain_end")), W / 2, 880, 52, t, 4.9, 0.08, "semibold")


class Reveal:
    """10 s. The product, on the drop."""

    LENGTH = 4.0

    def __init__(self):
        self.clicks, self.whooshes = [], []

    def __call__(self, frame, t):
        P.orbs(frame, t + 3)
        off = (1 - spring(t)) * 110
        rgb, a = icon(150)
        blend(frame, W // 2 - 75, int(200 + off), rgb, 1 - a * ease(t / 0.2), a * ease(t / 0.2))
        text(frame, "AirMouse", W / 2, 480 + off, 176, weight="bold", alpha=ease(t / 0.25))
        kinetic(frame, parts(L("reveal")), W / 2, 640, 60, t, 0.5, 0.1, "semibold")
        G.chips(frame, L("chips"), 850, t, 1.5, size=30)


def step_layout(frame, n, t, first=False):
    """What the three step scenes share: the heading, the 1-2-3 line and the words on the left."""
    mark(frame)
    title(frame, L("steps"), t if first else 10.0, 96, 54)
    for i in range(3):
        cx = W / 2 + (i - 1) * 120
        if i:
            capsule(frame, cx - 92, 172, 64, 4, ACCENT if i <= n else (255, 255, 255), 1.0 if i <= n else 0.25)
        on = i <= n
        capsule(frame, cx - 23, 151, 46, 46, ACCENT if on else (255, 255, 255), 1.0 if on else 0.16)
        if i < n:
            text(frame, I_CHECK, cx, 175, 22, DARK, "icons")
        else:
            text(frame, str(i + 1), cx, 174, 23, DARK if on else TEXT, "bold")
    k, dx = ease(t / 0.3), (spring(t) - 1) * 70
    text(frame, str(n + 1), 146 + dx, 410, 230, ACCENT, "bold", "lm", k)
    text(frame, L(f"s{n + 1}"), 150 + dx, 590, 56, weight="bold", anchor="lm", alpha=k)
    for j, key in enumerate("ab"):
        text(frame, L(f"s{n + 1}{key}"), 150, 672 + 46 * j, 32, MUTED, anchor="lm",
             alpha=ease((t - 0.25 - 0.1 * j) / 0.3))


class StepDownload:
    """14 s. Step 1: the zip from the Releases page, then the program in its folder."""

    LENGTH = 4.0
    X, Y, PW, PH = 920, 250, 880, 600

    def __init__(self):
        x, y = self.X, self.Y
        self.row, self.exe = (x + 440, y + 268), (x + 440, y + 236)
        self.keys = [(0.0, 1560, 1010), (0.7, *self.row), (2.35, *self.row), (2.95, *self.exe), (4.0, *self.exe)]
        self.clicks, self.whooshes = [0.9, 3.05, 3.2], []

    def __call__(self, frame, t):
        step_layout(frame, 0, t, first=True)
        x, y = self.X, self.Y + (1 - spring(t, 0.05)) * 80
        b = ease((t - 2.3) / 0.3)

        def panel(f):
            glass(self.PW, self.PH, 40, "panel").draw(f, x, y)
            faded(f, 1 - b, lambda g: self._releases(g, x, y, t))
            faded(f, b, lambda g: self._folder(g, x, y, t))
        faded(frame, ease(t / 0.3), panel)
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.6)

    def _releases(self, f, x, y, t):
        fill_round(f, x + 40, y + 36, 800, 52, 26, (255, 255, 255), 0.1)
        text(f, "github.com/Future-Web2/AirMouse/releases", x + 68, y + 62, 20, MUTED, anchor="lm")
        text(f, "AirMouse", x + 44, y + 150, 42, weight="bold", anchor="lm")
        fill_round(f, x + 260, y + 131, 104, 38, 19, ACCENT, 0.95)
        text(f, "Latest", x + 312, y + 150, 18, DARK, "semibold")
        text(f, "Assets", x + 44, y + 210, 20, MUTED, "semibold", "lm")
        fill_round(f, x + 40, y + 232, 800, 72, 18, (255, 255, 255), 0.2 if 0.6 <= t < 2.3 else 0.08)
        G.zip_icon(f, x + 62, y + 246, 34, 44)
        text(f, "AirMouse-windows-x64.zip", x + 116, y + 268, 24, weight="semibold", anchor="lm")
        text(f, L("mb"), x + 816, y + 268, 20, MUTED, anchor="rm")
        fill_round(f, x + 40, y + 316, 800, 64, 18, (255, 255, 255), 0.05)
        G.zip_icon(f, x + 64, y + 328, 30, 40)
        text(f, "AirMouse-linux-x64.tar.gz", x + 116, y + 348, 21, MUTED, anchor="lm")
        if t >= 0.95:
            p = ease((t - 1.0) / 1.1)
            fill_round(f, x + 40, y + 470, 800, 14, 7, (255, 255, 255), 0.14)
            fill_round(f, x + 40, y + 470, max(14.0, 800 * p), 14, 7, ACCENT)
            if p < 1:
                text(f, L("loading").format(f"{83 * p:.0f}"), x + 42, y + 436, 21, MUTED, anchor="lm")
            else:
                text(f, I_CHECK, x + 54, y + 436, 22, CYAN, "icons")
                text(f, L("loaded"), x + 78, y + 436, 21, TEXT, "semibold", "lm")

    def _folder(self, f, x, y, t):
        text(f, f"{L('downloads')}  ›  AirMouse", x + 44, y + 62, 22, MUTED, anchor="lm")
        fill_round(f, x + 40, y + 108, 800, 72, 18, (255, 255, 255), 0.05)
        G.folder_icon(f, x + 62, y + 128, 38, 32)
        text(f, "_internal", x + 120, y + 144, 22, TEXT, anchor="lm")
        chosen = t >= 3.05
        fill_round(f, x + 40, y + 196, 800, 80, 18, ACCENT if chosen else (255, 255, 255),
                   0.45 if chosen else 0.16 if t >= 2.8 else 0.05)
        rgb, a = icon(40)
        blend(f, int(x + 60), int(y + 216), rgb, 1 - a, a)
        text(f, "AirMouse.exe", x + 120, y + 236, 26, TEXT, "semibold", "lm")
        text(f, L("app_kind"), x + 816, y + 236, 19, MUTED, anchor="rm")
        k = ease((t - 3.3) / 0.3)
        text(f, I_SHIELD, x + 64, y + 360, 30, CYAN, "icons", alpha=k)
        text(f, L("no_install"), x + 100, y + 360, 25, TEXT, "semibold", "lm", k)


def make_window(scale):
    """A real AirMouse window (airmouse/ui.py) in the language of the video, kept off the screen."""
    settings_module.SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    settings_module.SETTINGS_FILE.write_text(json.dumps({"design": "glass", "language": LANG}), encoding="utf-8")
    from airmouse import ui
    real, G.tk.Tk = G.tk.Tk, G._HiddenTk
    try:
        app = ui.App(scale=scale)
    finally:
        G.tk.Tk = real
    app._t0 = 0.0
    app.backdrop = LiquidBackdrop(*app.size, **BACKDROP)      # calm colours while the camera is off
    return app


class StepStart:
    """18 s. Step 2: the real window; «Старт» turns the camera on."""

    LENGTH = 4.0
    SCALE = 0.82
    POS = (910, 270)
    CLICK = 1.3

    def __init__(self, camera):
        self.app = app = make_window(self.SCALE)
        self.camera = camera
        self.tracker = G.fake_tracker()
        start = G.window_at(app, self.POS, *G.centre(app.start_btn.rect))
        self.keys = [(0.0, 1500, 1010), (0.9, *start), (2.0, *start), (2.9, 1700, 990), (4.0, 1700, 990)]
        self.clicks, self.whooshes = [self.CLICK], []

    def __call__(self, frame, t):
        app = self.app
        step_layout(frame, 1, t)
        running = t >= self.CLICK + 0.12
        app.tracker = self.tracker if running else None
        app._show_running(running)
        app._has_frame = t >= self.CLICK + 0.6
        app._camera_bg = app._cover(self.camera.frame(t, G.moving_hand(t))) if app._has_frame else None
        app.start_btn.hover = 0.8 <= t < 2.0
        app.start_btn.pressed = G.pressed(t, self.CLICK)
        image = G.render_app(app, t + 3.0)
        y = self.POS[1] + (1 - spring(t, 0.05)) * 80
        faded(frame, ease(t / 0.3), lambda f: G.draw_window(f, image, self.POS[0], y, "AirMouse",
                                                           G.caption_rgb(app.theme), icon(22)))
        for c in self.clicks:
            ripple(frame, *path(self.keys, c), (t - c) / 0.6)
        cursor_arrow(frame, *path(self.keys, t), 1.6)


class StepHand:
    """22 s. Step 3: the palm in front of the camera moves the cursor on the screen."""

    LENGTH = 4.0
    PANEL, IMAGE = (870, 250, 660, 540), (890, 298, 620, 465)
    SCREEN_PANEL, SCREEN = (1556, 250, 300, 214), (1571, 292, 270, 152)
    TOUR = [(0.0, 960, 540), (0.5, 960, 540), (1.4, 300, 220), (1.9, 300, 220), (2.9, 1620, 330), (3.3, 1620, 330),
            (4.0, 1100, 700)]

    def __init__(self, camera):
        self.camera = camera
        self.wall = LiquidBackdrop(self.SCREEN[2], self.SCREEN[3], seed=12, **BACKDROP)
        self.clicks, self.whooshes = [], []

    def __call__(self, frame, t):
        step_layout(frame, 2, t)
        sx, sy = path(self.TOUR, t)
        pts = bench.hand(*P.cam_for(sx, sy))
        rise = (1 - spring(t, 0.05)) * 80

        def preview(f):
            x, y, w, h = self.PANEL
            glass(w, h, 30, "panel").draw(f, x, y + rise)
            camera_label(f, x, y + rise)
            ix, iy, iw, ih = self.IMAGE
            picture = cv2.resize(self.camera.frame(t, pts), (iw, ih), interpolation=cv2.INTER_LINEAR)
            G.put_round(f, picture, ix, iy + rise, 18)
            x, y, w, h = self.SCREEN_PANEL
            glass(w, h, 30, "panel").draw(f, x, y + rise)
            text(f, I_SCREEN, x + 30, y + 24 + rise, 16, MUTED, "icons")
            text(f, L("screen"), x + 52, y + 24 + rise, 17, MUTED, "semibold", "lm")
            ix, iy, iw, ih = self.SCREEN
            G.put_round(f, self.wall.render(t * 0.5 + 2), ix, iy + rise, 12)
            cursor_arrow(f, ix + sx / 1920 * iw, iy + rise + sy / 1080 * ih, 1.0)
        faded(frame, ease(t / 0.3), preview)
        for i, s in enumerate(L("checks")):
            k = ease((t - 0.7 - 0.5 * i) / 0.3)
            cy = 530 + 58 * i
            text(frame, I_CHECK, 1580 + (1 - k) * 30, cy, 24, CYAN, "icons", alpha=k)
            text(frame, s, 1612 + (1 - k) * 30, cy, 22, weight="semibold", anchor="lm", alpha=k)


class Gestures:
    """26 s. The four gestures on the real gesture engine; the pills below tick them off."""

    LENGTH = 10.0
    SPANS = ((0.0, 1.7), (1.7, 3.3), (3.3, 5.6), (5.6, 10.0))
    DEMO = 9.6                        # the demo's right click, which comes later, stays out

    def __init__(self):
        self.hand = P.HandDemo()
        self.clicks = [c for c in self.hand.clicks if c < self.DEMO]
        self.whooshes = []

    def __call__(self, frame, t):
        d = min(t, self.DEMO)
        rec = self.hand.frames[min(int(d * FPS), len(self.hand.frames) - 1)]
        mark(frame)
        title(frame, L("g_title"), t, 96, 54)
        x, y, w, h = P.CAMERA
        glass(w, h, 34, "panel").draw(frame, x, y)
        camera_label(frame, x, y)
        k = min(w / 640, (h - 40) / 480)
        ox, oy = x + (w - 640 * k) / 2, y + 40 + (h - 40 - 480 * k) / 2
        zx0, zy0, zx1, zy1 = G.zone_rect(G.Settings(), 640, 480, 16, 9)
        cv2.rectangle(frame, (int(ox + zx0 * 640 * k), int(oy + zy0 * 480 * k)),
                      (int(ox + zx1 * 640 * k), int(oy + zy1 * 480 * k)), (170, 190, 210), 2, cv2.LINE_AA)
        hand_sketch(frame, rec.pts, ox, oy, k, CYAN, width=3)
        P.SCREEN = (840, 160, 1020, 574)
        P.draw_desktop(frame, rec.desktop, d, rec.cursor)

        labels, size, gap = L("gestures"), 30, 20
        widths = [round((text_width(s, "semibold", size) + 104) / 2) * 2 for s in labels]
        px = W / 2 - (sum(widths) + gap * (len(widths) - 1)) / 2
        for i, (s, pw, (t0, t1)) in enumerate(zip(labels, widths, self.SPANS)):
            active, done = t0 <= t < t1, t >= t1
            lift = 10 * ease((t - t0) / 0.2) * (1 - ease((t - t1) / 0.2))

            def pill(f, px=px, pw=pw, s=s, i=i, active=active, done=done, lift=lift):
                glass(pw, 76, 38, "button").draw(f, px, 842 - lift)
                if active:
                    fill_round(f, px, 842 - lift, pw, 76, 38, ACCENT, 0.5)
                if done:
                    text(f, I_CHECK, px + 40, 880, 24, CYAN, "icons")
                else:
                    capsule(f, px + 22, 862 - lift, 36, 36, (255, 255, 255), 0.9 if active else 0.2)
                    text(f, str(i + 1), px + 40, 880 - lift, 20, DARK if active else TEXT, "bold")
                text(f, s, px + 72, 880 - lift, size, TEXT if active or done else MUTED, "semibold", "lm")
            faded(frame, ease((t - 0.15 - 0.08 * i) / 0.3), pill)
            px += pw + gap


class WidgetsScene:
    """36 s. Thumbs up: the real on-screen widgets appear; the volume is moved by hand."""

    LENGTH = 3.0
    SHOW, DRAG = 0.7, (1.5, 2.6)
    S = 1.6

    def __init__(self, camera):
        env = Env(self.S)
        env.volume, env.frame = G.FakeVolume(0.32), camera
        self.w = {}
        for spec in onscreen.default_widgets():
            if spec["type"] in ("status", "volume", "media", "buttons"):
                widget = onscreen.WIDGET_CLASSES[spec["type"]](dict(spec, x=0, y=0), env)
                widget.tick(1.0)
                self.w[spec["type"]] = widget
        size = {kind: w.panel_size() for kind, w in self.w.items()}
        left = 830 + (990 - size["status"][0] - 36 - size["buttons"][0]) // 2
        height = max(size["status"][1] + 24 + size["volume"][1], size["buttons"][1] + 24 + size["media"][1])
        top = 230 + (600 - height) // 2
        bx = left + size["status"][0] + 36
        self.pos = {"status": (left, top), "volume": (left, top + size["status"][1] + 24),
                    "buttons": (bx, top), "media": (bx, top + size["buttons"][1] + 24)}
        self.layers = {kind: w.render(1.0) for kind, w in self.w.items()}
        self.clicks, self.whooshes = [self.DRAG[0]], [self.SHOW - 0.1]

    def __call__(self, frame, t):
        mark(frame)
        title(frame, L("w_title"), t, 96, 54)
        x, y, w, h = 100, 230, 660, 600
        glass(w, h, 40, "panel").draw(frame, x, y)
        k = ease((t - 0.15) / 0.3)
        pts = [tuple(a + (b - a) * k for a, b in zip(p, q))
               for p, q in zip(hand_points("open"), hand_points("thumb"))]
        hand_sketch(frame, pts, x + 110, y + 90, 2.2, CYAN, glow=(20, 70, 150))
        volume = self.w["volume"]
        drag = ease((t - self.DRAG[0]) / (self.DRAG[1] - self.DRAG[0]))
        volume.level, volume.muted = 0.32 + 0.5 * drag, False
        volume.pressed = "slider" if self.DRAG[0] <= t < self.DRAG[1] else None
        self.layers["volume"] = volume.render(t)
        for i, kind in enumerate(("status", "buttons", "volume", "media")):
            a = ease((t - self.SHOW - 0.07 * i) / 0.25)
            px, py = self.pos[kind]
            widget = self.w[kind]
            G.paste_layer(frame, self.layers[kind].bgra(), int(px - widget.m), int(py - widget.m + (1 - a) * 30), a)
        if t >= self.DRAG[0] - 0.4:
            vx, vy = self.pos["volume"]
            x0, x1 = volume.TRACK
            cursor_arrow(frame, vx + (x0 + volume.level * (x1 - x0)) * volume.s, vy + 36 * volume.s, 1.6)
        lower(frame, L("w_cap"), t, 0.2, self.LENGTH)


class NotebookScene:
    """39 s. The notebook: a drawing appears stroke by stroke, the cursor at the pen."""

    LENGTH = 3.0
    S = 1.4

    def __init__(self):
        env = Env(self.S)
        self.widget = onscreen.NotebookWidget({"type": "notebook", "on": True, "x": 0, "y": 0}, env)
        recorder = Notebook()
        sample_drawing(recorder)
        self.strokes = [(step.tool, step.color, step.points) for step in recorder.page.steps]
        self.total = sum(len(points) for _tool, _color, points in self.strokes)
        self.size = self.widget.panel_size()
        self.clicks, self.whooshes = [], []

    def _draw_until(self, n):
        book = self.widget.book = Notebook()
        self.widget.env.notebook = book
        tip = None
        for tool, color, points in self.strokes:
            if n <= 0:
                break
            book.tool, book.color = tool, color
            book.begin(points[0])
            for p in points[1:n]:
                book.extend(p)
            book.end()
            tip = points[min(n, len(points)) - 1]
            n -= len(points)
        book.tool, book.color = "pen", self.strokes[1][1]
        return tip

    def __call__(self, frame, t):
        mark(frame)
        title(frame, L("n_title"), t, 96, 54)
        tip = self._draw_until(int(self.total * ease((t - 0.15) / 2.3)))
        widget = self.widget
        pw, ph = self.size
        x, y = 110, 190 + (700 - ph) // 2
        G.paste_layer(frame, widget.render(t).bgra(), x - widget.m, y - widget.m, ease(t / 0.25))
        if tip is not None:
            px, py, paper_w, paper_h = widget.paper()
            cursor_arrow(frame, x + (px + tip[0] / 1600 * paper_w) * self.S,
                         y + (py + tip[1] / 1000 * paper_h) * self.S, 1.6)
        tx = x + pw + 70
        for i, s in enumerate(L("n_checks")):
            k = ease((t - 0.5 - 0.4 * i) / 0.3)
            yy = 440 + i * 96
            text(frame, I_CHECK, tx + (1 - k) * 30, yy, 38, CYAN, "icons", alpha=k)
            text(frame, s, tx + 54 + (1 - k) * 30, yy, 38, weight="semibold", anchor="lm", alpha=k)


class EyesScene:
    """42 s. No hands: the eyes take the cursor to a tile, a long blink clicks it."""

    LENGTH = 2.0
    BLINK, CLICK = (1.0, 1.4), 1.4

    def __init__(self):
        self.clicks, self.whooshes = [self.CLICK], []

    def __call__(self, frame, t):
        mark(frame)
        title(frame, L("e_title"), t, 96, 54)
        glass(560, 600, 40, "panel").draw(frame, 200, 220)
        shut = self.BLINK[0] <= t < self.BLINK[1]
        face(frame, 480, 520, 200, left=not shut, right=not shut)
        sx, sy, sw, sh = 880, 250, 840, 540
        glass(sw, sh, 34, "panel").draw(frame, sx, sy)
        clicked = t >= self.CLICK
        centres = mock_tiles(frame, sx + 60, sy + 90, 220, 170, 30, 40, 4 if clicked else None)
        k = ease((t - 0.15) / 0.75)
        cx = centres[0][0] + (centres[4][0] - centres[0][0]) * k
        cy = centres[0][1] + (centres[4][1] - centres[0][1]) * k
        if shut:
            ring(frame, PENDING, (t - self.BLINK[0]) / (self.BLINK[1] - self.BLINK[0]), cx, cy, 2.0)
        ripple(frame, cx, cy, (t - self.CLICK) / 0.6, 2.0)
        cursor_arrow(frame, cx, cy, 1.9)
        lower(frame, L("e_cap"), t, 0.2, self.LENGTH)


class TwoHands:
    """44 s. Both hands: moving them apart zooms the page between them."""

    LENGTH = 2.0

    def __init__(self):
        self.clicks, self.whooshes = [], []

    def __call__(self, frame, t):
        mark(frame)
        title(frame, L("t_title"), t, 96, 54)
        glass(1320, 600, 40, "panel").draw(frame, 300, 220)
        k = ease((t - 0.3) / 1.2)
        zoom = 1 + 0.5 * k
        pw, ph = 250 * zoom, 320 * zoom
        px, py = W / 2 - pw / 2, 520 - ph / 2
        fill_round(frame, px, py, pw, ph, 14 * zoom, (236, 242, 250), 0.96)
        for i, part in enumerate((0.8, 0.62, 0.7, 0.45)):
            capsule(frame, px + 24 * zoom, py + (36 + 26 * i) * zoom, (pw - 48 * zoom) * part, 8 * zoom,
                    (100, 116, 139), 0.9)
        fill_round(frame, px + 24 * zoom, py + 160 * zoom, pw - 48 * zoom, 120 * zoom, 10 * zoom, ACCENT, 0.85)
        text(frame, f"{round(100 * zoom / 5) * 5}%", W / 2, py + 220 * zoom, 44 * zoom, DARK, "bold")
        size, apart = 1.55, 250 + 150 * k
        for left in (False, True):
            pts = bench.hand(112, 96, 0.0, "two", left=left)
            box = 224 * size
            hx = W / 2 + apart if left else W / 2 - apart - box
            hand_sketch(frame, pts, hx, 400, size, CYAN, glow=(20, 70, 150))
        lower(frame, L("t_cap"), t, 0.2, self.LENGTH)


class Proof:
    """46 s. The measured numbers; the music holds back so they can be read."""

    LENGTH = 6.0

    def __init__(self):
        self.st = P.Stability()
        self.clicks, self.whooshes = [], []

    def __call__(self, frame, t):
        mark(frame)
        kinetic(frame, parts(L("p_title")), W / 2, 110, 64, t, 0.05, 0.08)
        x, y, w, h = 100, 210, 1010, 560
        glass(w, h, 40, "panel").draw(frame, x, y)
        st = self.st
        p = ease((t - 0.3) / 2.4)
        n = max(2, int(len(st.raw) * p))
        xs = np.linspace(x + 50, x + w - 50, len(st.raw))[:n]
        mid, cy = st.raw.mean(), y + 220
        for series, color, width in ((st.raw, SLATE, 4), (st.cur, CYAN, 5)):
            pts = (np.stack([xs, cy + (series[:n] - mid) * 4.6], 1) * 16).astype(np.int32)
            cv2.polylines(frame, [pts], False, color, width, cv2.LINE_AA, 4)
        for i, (label, color) in enumerate(((L("hand"), SLATE), (L("cursor"), CYAN))):
            capsule(frame, x + 46 + i * 190, y + 34, 16, 16, color)
            text(frame, label, x + 74 + i * 190, y + 42, 24, MUTED, "semibold", "lm")
        q = ease((t - 0.6) / 1.8)
        by = y + 448
        text(frame, f"{st.raw_span * q:.0f} px", x + w / 2 - 250, by, 92, SLATE, "bold")
        text(frame, "→", x + w / 2, by, 70, MUTED)
        text(frame, f"{st.cur_span * q:.0f} px", x + w / 2 + 250, by, 92, CYAN, "bold")
        text(frame, L("tremor"), x + w / 2 - 250, by + 68, 26, MUTED)
        text(frame, L("cursor_low"), x + w / 2 + 250, by + 68, 26, MUTED)

        tiles = ((L("stat1"), None, L("stat1a")), ("0", None, L("stat2a")), (L("stat3"), I_LOCK, L("stat3a")))
        for i, (big, glyph, small) in enumerate(tiles):
            at = 1.4 + 0.45 * i
            tx, ty = 1150 + (1 - spring(t, at)) * 80, 210 + i * 192

            def tile(f, tx=tx, ty=ty, big=big, glyph=glyph, small=small):
                glass(670, 176, 40, "caption").draw(f, tx, ty)
                if glyph:
                    text(f, glyph, tx + 76, ty + 88, 54, CYAN, "icons")
                    text(f, big, tx + 140, ty + 64, 38, weight="bold", anchor="lm")
                    text(f, small, tx + 140, ty + 116, 27, MUTED, anchor="lm")
                else:
                    text(f, big, tx + 40, ty + 72, 72, CYAN, "bold", "lm")
                    text(f, small, tx + 40, ty + 136, 27, MUTED, anchor="lm")
            faded(frame, ease((t - at) / 0.3), tile)
        text(frame, L("p_foot"), W / 2, 880, 32, TEXT, "semibold", alpha=ease((t - 3.0) / 0.4))


class Offer:
    """52 s. What to do now."""

    LENGTH = 8.0

    def __init__(self):
        self.clicks, self.whooshes = [], []

    def __call__(self, frame, t):
        P.orbs(frame, t + 20)
        cx = 610
        off = (1 - spring(t)) * 100
        rgb, a = icon(150)
        blend(frame, cx - 75, int(170 + off), rgb, 1 - a * ease(t / 0.2), a * ease(t / 0.2))
        text(frame, "AirMouse", cx, 440 + off, 160, weight="bold", alpha=ease(t / 0.25))
        kinetic(frame, [(s, CYAN) for s in L("cta").split()], cx, 572, 64, t, 0.4, 0.1)
        text(frame, L("cta_os"), cx, 664, 38, TEXT, "semibold", alpha=ease((t - 0.8) / 0.4))
        text(frame, L("cta_need"), cx, 722, 32, MUTED, alpha=ease((t - 1.0) / 0.4))
        pw = round((text_width(CTA_URL, "semibold", 36) + 96) / 2) * 2
        k = ease((t - 1.3) / 0.4)
        faded(frame, k, lambda f: glass(pw, 92, 46, "button").draw(f, cx - pw / 2, 818))
        text(frame, CTA_URL, cx, 864, 36, weight="semibold", alpha=k)
        text(frame, L("cta_link"), cx, 950, 28, MUTED, alpha=ease((t - 1.7) / 0.4))

        size, qx = 440, 1250
        qy = 250 + (1 - spring(t, 0.7)) * 90

        def card(f):
            glass(size + 80, size + 150, 50, "panel").draw(f, qx - 40, qy - 40)
            qr(f, "https://" + CTA_URL, qx, qy, size)
            text(f, L("cta_qr"), qx + size / 2, qy + size + 56, 30, MUTED)
        faded(frame, ease((t - 0.7) / 0.4), card)


# -- timeline -------------------------------------------------------------------------------

def build_timeline(lang="ru"):
    """[(start, end, scene, how it comes in)], the length, the click times and the whoosh times."""
    global LANG
    LANG = lang
    i18n.set_language(lang)
    calm_look()
    P.TILES = tuple((name, glyph, color) for name, (_old, glyph, color) in zip(L("tiles"), P.TILES))
    P.ROWS, P.DESKTOP_TITLE = L("rows"), L("desktop")
    camera = G.Camera()
    thumb = camera.frame(1.0, bench.hand(300, 230, pose="thumb"))
    parts_ = [(Hook(), "cut"), (Problem(), "push"), (Reveal(), "flash"), (StepDownload(), "push"),
              (StepStart(camera), "push"), (StepHand(camera), "push"), (Gestures(), "push"),
              (WidgetsScene(thumb), "push"), (NotebookScene(), "push"), (EyesScene(), "push"), (TwoHands(), "push"),
              (Proof(), "fade"), (Offer(), "flash")]
    scenes, start = [], 0.0
    for scene, how in parts_:
        scenes.append((start, start + scene.LENGTH, scene, how))
        start += scene.LENGTH
    clicks = [s + c for s, _e, scene, _how in scenes for c in scene.clicks]
    whooshes = [s + c for s, _e, scene, _how in scenes for c in scene.whooshes]
    whooshes += [s - 0.2 for s, _e, _scene, how in scenes if how == "push"]
    return scenes, start, clicks, sorted(whooshes)


_vignette = {}


def vignette(frame):
    """Darken the corners of the backdrop a little, so the eye stays in the middle."""
    h, w = frame.shape[:2]
    if (w, h) not in _vignette:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.hypot((xs - w / 2) / (w / 2), (ys - h / 2) / (h / 2))
        m = 1 - 0.38 * np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6
        _vignette[(w, h)] = cv2.merge([(m * 255).astype(np.uint8)] * 3)
    return cv2.multiply(frame, _vignette[(w, h)], scale=1 / 255)


def render_frame(scenes, duration, backdrop, t):
    base = vignette(backdrop.render(t * 0.9))
    i = max(j for j, (start, *_rest) in enumerate(scenes) if start <= t)
    start, _end, scene, how = scenes[i]
    local = t - start
    out = base.copy()
    scene(out, local)
    if i and how == "push" and local < PUSH:
        # the old scene leaves to the left as the new one comes in from the right, with motion blur
        p_start, p_end, previous, _how = scenes[i - 1]
        old = base.copy()
        previous(old, p_end - p_start - 1 / FPS)
        e = ease(local / PUSH)
        shift = int(round(e * W))
        mixed = np.empty_like(out)
        mixed[:, :W - shift] = old[:, shift:]
        mixed[:, W - shift:] = out[:, :shift]
        blur = int(90 * math.sin(math.pi * local / PUSH)) | 1
        out = cv2.blur(mixed, (blur, 1)) if blur > 1 else mixed
    elif i and how == "fade" and local < FADE:
        p_start, p_end, previous, _how = scenes[i - 1]
        old = base.copy()
        previous(old, p_end - p_start - 1 / FPS)
        k = ease(local / FADE)
        out = cv2.addWeighted(old, 1 - k, out, k, 0)
    elif how == "flash" and local < FLASH:
        glow = (1 - local / FLASH) ** 2 * 0.75
        out = cv2.addWeighted(out, 1.0, np.full_like(out, 255), glow, 0)
    fade = ease(t / 0.15) * ease((duration - t) / 0.9)
    return out if fade >= 1 else cv2.convertScaleAbs(out, alpha=fade)


# -- main -----------------------------------------------------------------------------------

def make_music(wav, scenes, duration, whooshes, clicks):
    """The beat of the vertical video, arranged for this script: the drop when the product is
    named, a quieter stretch under the numbers, the full groove back for the offer."""
    start = {type(scene).__name__: s for s, _e, scene, _how in scenes}
    V.DROP = start["Reveal"]
    V.BREAK = (start["Proof"], start["Offer"])
    V.make_beat(wav, duration, whooshes, clicks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?")
    parser.add_argument("--lang", choices=("ru", "en"), default="ru")
    parser.add_argument("--stills", help="comma-separated seconds; saves PNGs instead of the video")
    parser.add_argument("--music", help="only write the music to this .wav")
    args = parser.parse_args()
    out = Path(args.out) if args.out else HERE / ("AirMouse_ad.mp4" if args.lang == "ru" else "AirMouse_ad_en.mp4")
    cv2.setNumThreads(0)

    scenes, duration, clicks, whooshes = build_timeline(args.lang)
    if args.music:
        make_music(args.music, scenes, duration, whooshes, clicks)
        print("saved", args.music)
        return
    backdrop = LiquidBackdrop(W, H, seed=8, **BACKDROP)
    if args.stills:
        for s in args.stills.split(","):
            still = out.parent / f"ad_{s}.png"
            Image.fromarray(render_frame(scenes, duration, backdrop, float(s))).save(still)
            print("saved", still)
        return

    import imageio_ffmpeg
    wav = Path(tempfile.gettempdir()) / "airmouse_ad_music.wav"
    make_music(wav, scenes, duration, whooshes, clicks)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(duration * FPS)
    for i in range(total):
        proc.stdin.write(render_frame(scenes, duration, backdrop, i / FPS).tobytes())
        if i % 150 == 0:
            print(f"frame {i}/{total}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("saved", out)


if __name__ == "__main__":
    main()
