"""Renders the vertical video for Reels, Shorts and TikTok: 1080x1920 (9:16), 30 fps, 36 s, with music.

    python promo/make_vertical.py                    -> promo/AirMouse_vertical.mp4
    python promo/make_vertical.py --stills 2,8,16    -> promo/vertical_2.png ... (to check frames)

The calm look of the poster and the carousel: navy and teal glass, white text, one
light-blue accent, no red or violet. The hand scene runs the real gesture engine (as in
make_promo.py); the widgets and the notebook are AirMouse's own, drawn off the screen.

The music is made here too: an original beat at 120 BPM (pluck chords Am–F–C–G, kick,
claps, hats, sub bass with sidechain, a riser into the drop as the demo starts), so the
video can be posted anywhere without rights problems. To use a trending sound instead,
add it in the Reels / TikTok / Shorts editor and turn the original sound down.
"""

import argparse
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_guide as G  # noqa: E402  (also puts the project on sys.path; draws nothing on the screen)
import make_promo as P  # noqa: E402
from make_carousel import qr, sample_drawing  # noqa: E402
from make_poster import (  # noqa: E402
    ACCENT, BACKDROP, CYAN, REPO, SLATE, calm_look, hand_points, hand_sketch, paste_layer, ring,
)
from make_promo import MUTED, TEXT, app_icon, blend, capsule, ease, faded, fill_round, glass, spring, text  # noqa: E402
from make_promo import text_width  # noqa: E402

from airmouse import onscreen  # noqa: E402
from airmouse.glass import LiquidBackdrop  # noqa: E402
from airmouse.gestures import PENDING  # noqa: E402
from airmouse.notebook import Notebook  # noqa: E402

W, H, FPS = 1080, 1920, 30
XFADE = 0.4
# Calm colours for the promo's mock desktop and the hand's palm dot.
P.TILES = (("Документы", P.TILES[0][1], (37, 99, 235)), ("Фото", P.TILES[1][1], (14, 165, 233)),
           ("Музыка", P.TILES[2][1], (20, 184, 166)), ("Почта", P.TILES[3][1], (71, 85, 105)),
           ("Настройки", P.TILES[4][1], (59, 130, 246)), ("Папка", P.TILES[5][1], (6, 182, 212)))
P.MODE_DOT = {mode: CYAN for mode in P.MODE_DOT}
P.ACCENT = ACCENT


# -- helpers ------------------------------------------------------------------------

def title(frame, s, t, y=170, size=66):
    k = ease(t / 0.4)
    text(frame, s, W / 2, y + (1 - k) * 30, size, weight="bold", alpha=k)


def caption(frame, s, t, t0, t1, y=1720, size=46):
    """A glass pill with a line of text, faded in and out between t0 and t1."""
    if not t0 <= t < t1:
        return
    a = ease((t - t0) / 0.25) * ease((t1 - t) / 0.2)
    w = text_width(s, "semibold", size) + 100
    rise = (1 - spring(t, t0)) * 40

    def draw(f):
        glass(w, 112, 56, "caption").draw(f, W / 2 - w / 2, y - 56 + rise)
        text(f, s, W / 2, y + rise, size, weight="semibold")
    faded(frame, a, draw)


def mark(frame):
    """The small logo in the corner."""
    icon, a = app_icon(44)
    blend(frame, 54, 54, icon, 1 - a, a)
    text(frame, "AirMouse", 112, 76, 32, weight="semibold", anchor="lm")


# -- scenes -----------------------------------------------------------------------------

class Hook:
    LENGTH = 4.2
    CLICK = 1.75

    def __init__(self):
        self.clicks = [self.CLICK]

    def __call__(self, frame, t):
        k1, k2 = ease(t / 0.35), ease((t - 0.35) / 0.35)
        text(frame, "Компьютер без мыши?", W / 2, 300 + (1 - spring(t)) * 50, 86, weight="bold", alpha=k1)
        text(frame, "Просто рукой в воздухе", W / 2, 410, 54, MUTED, alpha=k2)
        x, y, w, h = 60, 520, 960, 1060
        faded(frame, ease((t - 0.15) / 0.4), lambda f: glass(w, h, 60, "hero").draw(f, x, y))
        pinch = ease((t - 0.7) / 0.9)
        pts = hand_points("open", 0.85 * pinch)
        k = 2.6
        hand_sketch(frame, pts, x + 210, y + 60, k, CYAN, glow=(20, 70, 150))
        for i in (4, 8):
            cv2.circle(frame, (int((x + 210 + pts[i][0] * k) * 16), int((y + 60 + pts[i][1] * k) * 16)), int(16 * 16),
                       CYAN, -1, cv2.LINE_AA, 4)
        sx, sy, sw, sh = x + 130, y + 640, 700, 340
        fill_round(frame, sx, sy, sw, sh, 30, (8, 14, 26), 0.85)
        colors = ((37, 99, 235), (14, 165, 233), (20, 184, 166), (71, 85, 105), (59, 130, 246), (6, 182, 212))
        clicked = t >= self.CLICK
        for j, col in enumerate(colors):
            bx, by = sx + 50 + (j % 3) * 210, sy + 50 + (j // 3) * 130
            lit = clicked and j == 4 and t < self.CLICK + 0.5
            fill_round(frame, bx, by, 180, 110, 22, tuple(min(255, c + 70) for c in col) if lit else col, 0.92)
        cx, cy = sx + 50 + 210 + 90, sy + 50 + 130 + 55
        if not clicked:
            ring(frame, PENDING, min(pinch, 0.95), cx, cy, 2.2)
        P.ripple(frame, cx, cy, (t - self.CLICK) / 0.6, 2.2)
        P.cursor_arrow(frame, cx, cy, 2.0)
        text(frame, "Щипок — клик", W / 2, y + h + 110, 64, weight="bold", alpha=ease((t - self.CLICK) / 0.3))


class Demo:
    """The real gesture engine moving the cursor over a mock desktop (from the promo)."""

    LENGTH = 9.6
    CAMERA = (60, 250, 960, 740)
    SCREEN = (60, 1040, 960, 540)
    CAPTIONS = ((0.0, 1.7, "Ладонь — курсор"), (1.7, 3.3, "Щипок — клик"), (3.3, 5.6, "Два пальца — прокрутка"),
                (5.6, 9.6, "Сжать и вести — перетащить"))

    def __init__(self):
        self.hand = P.HandDemo()
        self.clicks = [c for c in self.hand.clicks if c < self.LENGTH]

    def __call__(self, frame, t):
        rec = self.hand.frames[min(int(t * FPS), len(self.hand.frames) - 1)]
        mark(frame)
        title(frame, "Как это работает", t, 175, 62)
        x, y, w, h = self.CAMERA
        glass(w, h, 40, "panel").draw(frame, x, y)
        capsule(frame, x + 28, y + 26, 14, 14, CYAN)
        text(frame, "Камера", x + 54, y + 33, 24, MUTED, "semibold", "lm")
        k = (w - 60) / 640
        ox, oy = x + 30, y + 50
        zx0, zy0, zx1, zy1 = G.zone_rect(G.Settings(), 640, 480, 16, 9)
        cv2.rectangle(frame, (int(ox + zx0 * 640 * k), int(oy + zy0 * 480 * k)),
                      (int(ox + zx1 * 640 * k), int(oy + zy1 * 480 * k)), (170, 190, 210), 2, cv2.LINE_AA)
        hand_sketch(frame, rec.pts, ox, oy, k, CYAN, width=4)
        P.SCREEN = self.SCREEN
        P.draw_desktop(frame, rec.desktop, t, rec.cursor)
        for t0, t1, s in self.CAPTIONS:
            caption(frame, s, t, t0, t1)


class Widgets:
    """The real on-screen widgets popping up on a thumbs up; the volume moved by hand."""

    LENGTH = 7.2
    SHOW, DRAG = 1.1, (3.3, 5.2)

    def __init__(self, camera):
        self.env = env = G.WidgetEnv()
        env.s, env.look, env.accent = 1.65, {}, onscreen.ACCENT
        env.volume, env.frame = G.FakeVolume(0.32), camera
        self.w = {}
        for spec in onscreen.default_widgets():
            if spec["type"] in ("status", "volume", "media", "buttons"):
                widget = onscreen.WIDGET_CLASSES[spec["type"]](dict(spec, x=0, y=0), env)
                widget.tick(1.0)
                self.w[spec["type"]] = widget
        sw, bw = self.w["status"].panel_size(), self.w["buttons"].panel_size()
        left = (W - sw[0] - 40 - bw[0]) // 2
        self.pos = {"status": (left, 820), "volume": (left, 820 + sw[1] + 26)}
        bx = left + sw[0] + 40
        self.pos.update({"buttons": (bx, 820), "media": (bx, 820 + self.w["buttons"].panel_size()[1] + 26)})
        self.layers = {kind: w.render(1.0) for kind, w in self.w.items()}
        self.clicks = [self.DRAG[0]]

    def __call__(self, frame, t):
        mark(frame)
        title(frame, "Виджеты на экране", t, 175, 62)
        x, y, w, h = 60, 250, 960, 520
        glass(w, h, 40, "panel").draw(frame, x, y)
        blend_k = ease((t - 0.3) / 0.35)
        open_pts, thumb_pts = hand_points("open"), hand_points("thumb")
        pts = [tuple(a + (b - a) * blend_k for a, b in zip(p, q)) for p, q in zip(open_pts, thumb_pts)]
        hand_sketch(frame, pts, x + 330, y + 40, 2.1, CYAN, glow=(20, 70, 150))
        volume = self.w["volume"]
        drag = ease((t - self.DRAG[0]) / (self.DRAG[1] - self.DRAG[0]))
        volume.level, volume.muted = 0.32 + 0.5 * drag, False
        volume.pressed = "slider" if self.DRAG[0] <= t < self.DRAG[1] else None
        self.layers["volume"] = volume.render(t)
        for i, kind in enumerate(("status", "buttons", "volume", "media")):
            a = ease((t - self.SHOW - 0.08 * i) / 0.3)
            px, py = self.pos[kind]
            widget = self.w[kind]
            G.paste_layer(frame, self.layers[kind].bgra(), int(px - widget.m), int(py - widget.m + (1 - a) * 30), a)
        if t >= self.DRAG[0] - 0.6:
            vx, vy = self.pos["volume"]
            x0, x1 = volume.TRACK
            cx = vx + (x0 + volume.level * (x1 - x0)) * volume.s
            cy = vy + 36 * volume.s
            P.cursor_arrow(frame, cx, cy, 1.6)
        caption(frame, "Палец вверх — виджеты", t, 0.2, 3.1)
        caption(frame, "Громкость, музыка, кнопки — рукой", t, 3.1, self.LENGTH)


class Drawing:
    """The notebook: a drawing appears stroke by stroke, the cursor at the pen."""

    LENGTH = 6.4
    S = 1.6

    def __init__(self):
        self.env = env = G.WidgetEnv()
        env.s, env.look, env.accent = self.S, {}, onscreen.ACCENT
        self.widget = onscreen.NotebookWidget({"type": "notebook", "on": True, "x": 0, "y": 0}, env)
        recorder = Notebook()
        sample_drawing(recorder)
        self.strokes = [(step.tool, step.color, step.points) for step in recorder.page.steps]
        self.total = sum(len(points) for _tool, _color, points in self.strokes)
        self.clicks = []

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
        title(frame, "Блокнот: рисуйте рукой", t, 175, 62)
        tip = self._draw_until(int(self.total * ease((t - 0.3) / 4.8)))
        widget = self.widget
        pw, _ph = widget.panel_size()
        x, y = round((W - pw) / 2), 290
        a = ease(t / 0.3)
        G.paste_layer(frame, widget.render(t).bgra(), x - widget.m, y - widget.m, a)
        if tip is not None:
            px, py, paper_w, paper_h = widget.paper()
            P.cursor_arrow(frame, x + (px + tip[0] / 1600 * paper_w) * self.S,
                           y + (py + tip[1] / 1000 * paper_h) * self.S, 1.6)
        for i, s in enumerate(("Ручка, маркер, ластик", "Страницы сохраняются сами", "Копировать — и Ctrl+V")):
            k = ease((t - 0.8 - 0.5 * i) / 0.35)
            yy = 1190 + i * 96
            text(frame, G.ICON["check"], 110 + (1 - k) * 30, yy, 44, ACCENT, "icons", alpha=k)
            text(frame, s, 160 + (1 - k) * 30, yy, 46, weight="semibold", anchor="lm", alpha=k)
        caption(frame, "Как Paint — только рукой", t, 0.4, self.LENGTH)


class Precision:
    LENGTH = 4.4

    def __init__(self):
        self.st = P.Stability()
        self.clicks = []

    def __call__(self, frame, t):
        mark(frame)
        title(frame, "Рука дрожит —", t, 190, 74)
        text(frame, "курсор нет", W / 2, 290, 74, CYAN, "bold", alpha=ease((t - 0.25) / 0.4))
        x, y, w, h = 60, 390, 960, 520
        glass(w, h, 40, "panel").draw(frame, x, y)
        st = self.st
        p = ease((t - 0.2) / 2.2)
        n = max(2, int(len(st.raw) * p))
        xs = np.linspace(x + 40, x + w - 40, len(st.raw))[:n]
        mid, cy = st.raw.mean(), y + h / 2
        for series, color in ((st.raw, SLATE), (st.cur, CYAN)):
            pts = (np.stack([xs, cy + (series[:n] - mid) * 6.5], 1) * 16).astype(np.int32)
            cv2.polylines(frame, [pts], False, color, 5, cv2.LINE_AA, 4)
        for i, (label, color) in enumerate((("Рука", SLATE), ("Курсор", CYAN))):
            capsule(frame, x + 40 + i * 200, y + 36, 16, 16, color)
            text(frame, label, x + 68 + i * 200, y + 44, 28, MUTED, "semibold", "lm")
        q = ease((t - 0.6) / 1.6)
        text(frame, f"{st.raw_span * q:.0f} px", 330, 1060, 110, SLATE, "bold")
        text(frame, "→", W / 2 + 10, 1060, 90, MUTED)
        text(frame, f"{st.cur_span * q:.0f} px", 760, 1060, 110, CYAN, "bold")
        text(frame, "дрожь руки            курсор", W / 2, 1150, 34, MUTED)
        for i, (big, small) in enumerate((("20 из 20", "щипков — ровно 20 кликов"), ("0", "ложных кликов"))):
            k = ease((t - 1.6 - 0.3 * i) / 0.35)
            tx, ty = 60 + i * 490, 1260 + (1 - k) * 40

            def tile(f, tx=tx, ty=ty, big=big, small=small):
                glass(470, 240, 40, "caption").draw(f, tx, ty)
                text(f, big, tx + 235, ty + 100, 76, weight="bold")
                text(f, small, tx + 235, ty + 180, 30, MUTED)
            faded(frame, k, tile)


class Outro:
    LENGTH = 6.2

    def __init__(self):
        self.icon = app_icon(170)
        self.clicks = []

    def __call__(self, frame, t):
        for ox, oy, d in ((150, 330, 150), (930, 260, 110), (90, 1180, 100), (990, 1300, 80)):
            glass(d, d, d / 2, "orb").draw(frame, ox - d / 2, oy - d / 2)
        rgb, a = self.icon
        a = a * ease(t / 0.4)
        off = (1 - spring(t, 0.05)) * 80
        blend(frame, int(W / 2 - 85), int(220 + off), rgb, 1 - a, a)
        text(frame, "AirMouse", W / 2, 520 + off, 140, weight="bold", alpha=ease((t - 0.15) / 0.4))
        text(frame, "Бесплатно  ·  Windows 10 и 11", W / 2, 630, 46, MUTED, alpha=ease((t - 0.4) / 0.4))
        text(frame, "Нужна только веб-камера", W / 2, 700, 42, TEXT, "semibold", alpha=ease((t - 0.6) / 0.4))
        size = 420
        k = ease((t - 0.8) / 0.4)

        def card(f):
            glass(size + 80, size + 150, 50, "panel").draw(f, W / 2 - size / 2 - 40, 790)
            qr(f, "https://" + REPO, W / 2 - size / 2, 830, size)
            text(f, "Наведите камеру телефона", W / 2, 1300, 32, MUTED)
        faded(frame, k, card)
        pw = text_width(REPO, "semibold", 40) + 90
        faded(frame, ease((t - 1.2) / 0.4), lambda f: glass(pw, 100, 50, "button").draw(f, W / 2 - pw / 2, 1420))
        text(frame, REPO, W / 2, 1470, 40, weight="semibold", alpha=ease((t - 1.2) / 0.4))
        text(frame, "Ссылка — в описании", W / 2, 1580, 38, MUTED, alpha=ease((t - 1.6) / 0.4))


# -- timeline ----------------------------------------------------------------------------

def build_timeline():
    calm_look()
    camera = G.Camera().frame(1.0, G.bench.hand(300, 230, pose="thumb"))
    parts = [(0.0, Hook()), (3.8, Demo()), (13.0, Widgets(camera)), (19.8, Drawing()), (25.8, Precision()),
             (29.8, Outro())]
    scenes = [(start, start + scene.LENGTH, scene) for start, scene in parts]
    duration = scenes[-1][1]
    clicks = [start + c for start, _end, scene in scenes for c in scene.clicks]
    return scenes, duration, clicks


def render_frame(scenes, duration, backdrop, t):
    """As make_promo.render_frame, with quicker cross-fades and no slow fade-in: a reel must open at once."""
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
    fade = ease(t / 0.15) * ease((duration - t) / 0.8)
    return out if fade >= 1 else cv2.convertScaleAbs(out, alpha=fade)


# -- music ---------------------------------------------------------------------------------

SR = 44100
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
CHORDS = ((57, 60, 64, 67, 71), (53, 57, 60, 64, 69), (48, 55, 60, 62, 64), (55, 59, 62, 64, 67))   # Am9 F C G6
DROP = 4.0                     # the beat comes in as the demo starts
BREAK = (26.0, 30.0)           # lighter while the numbers are shown


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def pluck(n_samples, f, bright=1.0, decay=4.0):
    """A plucked synth note: harmonics that fade faster the higher they are (like a closing filter)."""
    tt = np.arange(n_samples) / SR
    out = np.zeros(n_samples)
    for k in range(1, 9):
        if f * k > 12000:
            break
        out += (1 / k) * np.exp(-tt * (decay + 9 * k / bright)) * np.sin(2 * np.pi * f * k * tt + 0.3 * k)
    return out * np.clip(tt / 0.004, 0, 1)


def place(track, start, sound, gain=1.0):
    a = int(start * SR)
    if a >= len(track):
        return
    b = min(len(track), a + len(sound))
    track[a:b] += gain * sound[:b - a]


def highpass(x):
    return np.diff(np.diff(x, prepend=0), prepend=0)


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same")


def make_beat(path, duration, whooshes, clicks):
    """An original modern beat (120 BPM, Am–F–C–G): pluck chords with sidechain, kick, claps, hats,
    sub bass, an arpeggio, a riser and an impact into the drop; soft ticks on clicks."""
    n = int(duration * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    drums, keys, bass, fx = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    bars = int(math.ceil(duration / BAR))

    def full(at):
        return DROP <= at < duration - 1.0 and not BREAK[0] <= at < BREAK[1]

    kick_len = int(0.35 * SR)
    kt = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * np.cumsum(45 + 85 * np.exp(-kt * 28)) / SR) * np.exp(-kt * 7)
    kick += 0.3 * np.exp(-kt * 300) * rng.normal(size=kick_len)
    clap_len = int(0.25 * SR)
    ct = np.arange(clap_len) / SR
    clap_env = sum(np.exp(-np.maximum(ct - d, 0) * 40) * (ct >= d) for d in (0.0, 0.011, 0.022))
    clap = smooth(highpass(rng.normal(size=clap_len)), 3) * clap_env * np.exp(-ct * 9)
    hat_len = int(0.06 * SR)
    hat = highpass(rng.normal(size=hat_len)) * np.exp(-np.arange(hat_len) / SR * 70)
    open_len = int(0.22 * SR)
    open_hat = highpass(rng.normal(size=open_len)) * np.exp(-np.arange(open_len) / SR * 14)
    hat, open_hat = smooth(hat, 2), smooth(open_hat, 2)            # take the harsh top off
    for sound in (clap, hat, open_hat):
        sound /= np.max(np.abs(sound))

    duck = np.ones(n)                                  # sidechain: everything but the kick dips on each kick
    for b in range(bars):
        start = b * BAR
        chord = CHORDS[b % 4]
        for beat in range(4):
            at = start + beat * BEAT
            if full(at):
                place(drums, at, kick, 1.0)
                a = int(at * SR)
                m = min(n, a + int(0.25 * SR))
                duck[a:m] = np.minimum(duck[a:m], 1 - 0.65 * np.exp(-np.arange(m - a) / SR * 14))
                if beat in (1, 3):
                    place(drums, at, clap, 0.42)
                place(drums, at + BEAT / 2, open_hat, 0.09)
            if full(at) or (BREAK[0] <= at < BREAK[1]):
                for s16 in range(4):
                    place(drums, at + s16 * BEAT / 4, hat, 0.055 if s16 % 2 else 0.03)
        # pluck chord stabs on a syncopated 16th pattern; softer and darker before the drop
        for step in (0, 3, 6, 10, 12):
            at = start + step * BEAT / 4
            if at >= duration - 0.5:
                continue
            lit = full(at) or BREAK[0] <= at < BREAK[1]
            for note in chord:
                place(keys, at, pluck(int(0.6 * SR), hz(note), bright=1.0 if lit else 0.35), 0.11 if lit else 0.08)
        # arpeggio an octave up in the second half of the groove
        if 12.0 <= start < duration - 2 and not BREAK[0] <= start < BREAK[1]:
            pattern = (0, 2, 4, 2, 1, 3, 4, 3)
            for i in range(16):
                at = start + i * BEAT / 4
                note = chord[pattern[i % 8]] + 12
                place(keys, at, pluck(int(0.3 * SR), hz(note), bright=1.6, decay=10), 0.05)
        # sub bass: the root, eighth notes
        root = hz(chord[0] - 24)
        for i in range(8):
            at = start + i * BEAT / 2
            if full(at):
                ln = int(BEAT / 2 * SR)
                bt = np.arange(ln) / SR
                note = np.tanh(1.6 * np.sin(2 * np.pi * root * bt)) * np.clip(bt / 0.01, 0, 1) * np.clip(
                    (BEAT / 2 - bt) / 0.02, 0, 1)
                place(bass, at, note, 0.32)

    # pads before the drop and in the break
    for start, end in ((0.0, DROP), BREAK):
        for b in range(int(start / BAR), int(math.ceil(end / BAR))):
            chord = CHORDS[b % 4]
            a, z = int(b * BAR * SR), min(n, int((b + 1) * BAR * SR + 0.3 * SR))
            tt = t[a:z] - b * BAR
            env = np.clip(tt / 0.5, 0, 1) * np.clip((BAR + 0.3 - tt) / 0.6, 0, 1)
            for note in chord:
                f = hz(note)
                keys[a:z] += 0.03 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2.003 * f * tt))

    # riser and snare roll into the drop (and out of the break), impact on the drop
    for end in (DROP, BREAK[1]):
        a, z = int((end - BAR) * SR), int(end * SR)
        ramp = np.linspace(0, 1, z - a) ** 2
        noise = rng.normal(size=z - a)
        fx[a:z] += 0.10 * ramp * (smooth(noise, 9) * (1 - ramp) + highpass(noise) * 0.4 * ramp)
        sweep = np.cumsum(200 + 1400 * ramp) / SR
        fx[a:z] += 0.035 * ramp * np.sin(2 * np.pi * sweep)
        for i, step in enumerate(np.concatenate([np.arange(0, BAR / 2, BEAT / 2), np.arange(BAR / 2, BAR, BEAT / 4)])):
            place(drums, end - BAR + step, clap, 0.06 + 0.24 * step / BAR)
        it = np.arange(int(1.2 * SR)) / SR
        place(fx, end, np.sin(2 * np.pi * 50 * it) * np.exp(-it * 3) * 0.45 + 0.08 * smooth(
            rng.normal(size=len(it)), 5) * np.exp(-it * 6))
    for st in whooshes:
        a, z = max(0, int(st * SR)), min(n, int((st + 0.6) * SR))
        fx[a:z] += 0.05 * smooth(rng.normal(size=z - a), 30) * np.hanning(z - a)
    for st in clicks:
        a, z = int(st * SR), min(n, int((st + 0.04) * SR))
        tt = t[a:z] - st
        fx[a:z] += 0.08 * np.exp(-tt * 160) * np.sin(2 * np.pi * 2200 * tt)

    # a little room on the keys
    ir_t = np.arange(int(1.4 * SR)) / SR
    ir = rng.normal(size=len(ir_t)) * np.exp(-ir_t / 0.35)
    nfft = 1 << int(np.ceil(np.log2(n + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(keys, nfft) * np.fft.rfft(ir, nfft), nfft)[:n]
    keys = keys + 0.25 * wet * (np.std(keys) / (np.std(wet) + 1e-9))

    mix = drums + duck * (keys + bass) + fx
    mix *= np.clip(t / 0.05, 0, 1) * np.clip((duration - t) / 1.6, 0, 1)
    mix = np.tanh(1.3 * mix / (np.max(np.abs(mix)) + 1e-9)) / np.tanh(1.3)       # gentle glue
    mix *= 0.92 / np.max(np.abs(mix))
    left = mix
    right = 0.85 * mix + 0.15 * np.roll(duck * keys / (np.max(np.abs(keys)) + 1e-9) * 0.3, int(0.012 * SR))
    stereo = (np.stack([left, right], 1) * 32767).clip(-32767, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())


# -- main ----------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(HERE / "AirMouse_vertical.mp4"))
    parser.add_argument("--stills", help="comma-separated seconds; saves PNGs instead of the video")
    parser.add_argument("--music", help="only write the music to this .wav")
    args = parser.parse_args()
    cv2.setNumThreads(0)

    scenes, duration, clicks = build_timeline()
    whooshes = [start - 0.25 for start, *_ in scenes[1:]]
    if args.music:
        make_beat(args.music, duration, whooshes, clicks)
        print("saved", args.music)
        return
    backdrop = LiquidBackdrop(W, H, seed=8, **BACKDROP)
    if args.stills:
        for s in args.stills.split(","):
            out = Path(args.out).parent / f"vertical_{s}.png"
            Image.fromarray(render_frame(scenes, duration, backdrop, float(s))).save(out)
            print("saved", out)
        return

    import imageio_ffmpeg
    wav = Path(tempfile.gettempdir()) / "airmouse_vertical_music.wav"
    make_beat(wav, duration, whooshes, clicks)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
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
