"""Renders the poster: promo/AirMouse_poster.png, 1440x1800 (4:5, shows large in the feed).

    python promo/make_poster.py

A calm look: deep navy and teal glass, white text, one light-blue accent, no red or
violet. promo/make_carousel.py makes the 8-slide version in the same look.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_promo as P  # noqa: E402
from make_promo import MUTED, ROOT, TEXT, app_icon, blend, eye, fill_round, glass, text, text_width  # noqa: E402

from airmouse import bench, onscreen  # noqa: E402
from airmouse.gestures import PENDING  # noqa: E402
from airmouse.glass import LiquidBackdrop  # noqa: E402

S = 4 / 3                    # layout below is in 1080x1350 units, drawn at 1440x1800
W, H = round(1080 * S), round(1350 * S)
REPO = "github.com/Future-Web2/AirMouse"
# Deep navy, blue and teal light behind the glass.
BACKDROP = dict(colors=((0.06, 0.16, 0.36), (0.10, 0.32, 0.62), (0.04, 0.40, 0.48), (0.22, 0.36, 0.50),
                        (0.12, 0.52, 0.66)), base=(0.02, 0.04, 0.09))
ACCENT = (125, 200, 255)     # the one accent colour
CYAN = (56, 189, 248)
SLATE = (148, 163, 184)
ICON_MONITOR, ICON_PEN = "", ""


def u(v):
    return v * S


def calm_look():
    """Glass without rainbow edges and with a navy tint, for the posters."""
    P.PROMO_STYLES.update({
        "orb": dict(blur=0, refraction=2.4, dispersion=0.0, tint=(255, 255, 255), tint_alpha=0.05, saturation=1.1,
                    rim=1.3, sheen=0.16, shadow=0.22),
        "hero": dict(blur=12, refraction=1.2, dispersion=0.0, tint=(10, 18, 34), tint_alpha=0.4, saturation=1.1,
                     rim=1.1, sheen=0.12, shadow=0.35),
        "caption": dict(blur=8, refraction=1.3, dispersion=0.0, tint=(12, 20, 34), tint_alpha=0.5, saturation=1.1,
                        rim=1.0, sheen=0.1, shadow=0.3),
        "button": dict(P.PROMO_STYLES["button"], dispersion=0.0),
        "panel": dict(P.PROMO_STYLES["panel"], dispersion=0.0),
    })


def backdrop(t, seed=8):
    return LiquidBackdrop(W, H, seed=seed, **BACKDROP).render(t)


def orbs(frame, spots):
    for cx, cy, d in spots:
        glass(u(d), u(d), u(d / 2), "orb").draw(frame, u(cx - d / 2), u(cy - d / 2))


def hand_icon(frame, cx, cy, size):
    """Small line drawing of an open hand."""
    k = size / 200
    pts = {0: (0, 100)}
    for i, (mx, my) in {5: (-50, 5), 9: (0, 0), 13: (50, 5), 17: (95, 15)}.items():
        for j, off in enumerate((0, -40, -65, -90)):
            pts[i + j] = (mx, my + off)
    pts.update({1: (-60, 80), 2: (-85, 55), 3: (-100, 30), 4: (-110, 5)})
    lines = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
             (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17))
    ox, oy = cx - 0 * k, cy - 5 * k
    p = {i: (int((ox + x * k) * 16), int((oy + y * k) * 16)) for i, (x, y) in pts.items()}
    for a, b in lines:
        cv2.line(frame, p[a], p[b], (245, 248, 255), max(2, int(size / 40)), cv2.LINE_AA, 4)


def head_icon(frame, cx, cy, r):
    white = (245, 248, 255)
    t = max(2, int(r / 12))
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), int(r * 16), white, t, cv2.LINE_AA, 4)
    for ex in (-0.35, 0.35):
        cv2.circle(frame, (int((cx + ex * r + 0.15 * r) * 16), int((cy - 0.2 * r) * 16)), int(r * 0.1 * 16), white,
                   -1, cv2.LINE_AA, 4)
    cv2.ellipse(frame, (int((cx + 0.12 * r) * 16), int((cy + 0.38 * r) * 16)), (int(0.35 * r * 16), int(0.14 * r * 16)),
                0, 10, 170, white, t, cv2.LINE_AA, 4)


def hand_sketch(frame, pts, x0, y0, k, dot=CYAN, glow=None, width=None):
    """The 21 hand points as AirMouse sees them: white bones, joints, the palm centre."""
    p = [((x0 + q[0] * k) * 16, (y0 + q[1] * k) * 16) for q in pts]
    width = width or max(2, round(2.6 * k))
    if glow is not None:                          # a soft glow under the bones
        layer = np.zeros_like(frame)
        for a, b in P.HAND_LINES:
            cv2.line(layer, tuple(map(int, p[a])), tuple(map(int, p[b])), glow, width * 4, cv2.LINE_AA, 4)
        cv2.add(frame, cv2.GaussianBlur(layer, (0, 0), width * 3), dst=frame)
    for a, b in P.HAND_LINES:
        cv2.line(frame, tuple(map(int, p[a])), tuple(map(int, p[b])), (238, 242, 250), width, cv2.LINE_AA, 4)
    for q in p:
        cv2.circle(frame, (int(q[0]), int(q[1])), int(max(3.0, 3.6 * k) * 16), (255, 255, 255), -1, cv2.LINE_AA, 4)
    palm = [pts[i] for i in (0, 5, 9, 13, 17)]
    cx, cy = x0 + sum(q[0] for q in palm) / 5 * k, y0 + sum(q[1] for q in palm) / 5 * k
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), int(9 * k * 16), dot, -1, cv2.LINE_AA, 4)
    cv2.circle(frame, (int(cx * 16), int(cy * 16)), int(9 * k * 16), (255, 255, 255), max(2, round(2 * k)),
               cv2.LINE_AA, 4)


def hand_points(pose="open", pinch=0.0):
    """bench.hand, moved so its box starts near (0, 0): about 205 x 200 points."""
    return bench.hand(112, 96, pinch, pose)


def paste_layer(frame, bgra, x, y):
    """Lay a premultiplied BGRA picture (what AirMouse's own overlay windows show) over the frame."""
    h, w = bgra.shape[:2]
    src = bgra.astype(np.float32) / 255
    region = frame[y:y + h, x:x + w].astype(np.float32)
    frame[y:y + h, x:x + w] = np.clip(region * (1 - src[..., 3:4]) + src[..., 2::-1] * 255, 0, 255).astype(np.uint8)


def ring(frame, mode, progress, cx, cy, s):
    """The real cursor ring (onscreen.CursorRing) around (cx, cy)."""
    r = onscreen.CursorRing(s)
    paste_layer(frame, r.render(r.state(mode, progress, 0.0)).bgra(), int(cx - r.size / 2), int(cy - r.size / 2))


def pinch_scene(frame, x, y, w, h):
    """The hand pinching on the left, a screen with the cursor about to click on the right."""
    k = h / 270
    pts = hand_points("open", 0.82)
    hand_sketch(frame, pts, x + w * 0.04, y + h * 0.12, k, CYAN, glow=(20, 70, 150))
    for i in (4, 8):
        cv2.circle(frame, (int((x + w * 0.04 + pts[i][0] * k) * 16), int((y + h * 0.12 + pts[i][1] * k) * 16)),
                   int(h * 0.02 * 16), CYAN, -1, cv2.LINE_AA, 4)
    sx, sy, sw, sh = x + w * 0.555, y + h * 0.15, w * 0.4, h * 0.46
    fill_round(frame, sx, sy, sw, sh, h * 0.04, (8, 14, 26), 0.85)
    for i in range(3):
        P.capsule(frame, sx + h * 0.03 + i * h * 0.03, sy + h * 0.028, h * 0.018, h * 0.018, (100, 116, 139))
    colors = ((37, 99, 235), (14, 165, 233), (20, 184, 166), (71, 85, 105), (59, 130, 246), (6, 182, 212))
    for j, col in enumerate(colors):
        fill_round(frame, sx + sw * (0.08 + 0.3 * (j % 3)), sy + sh * (0.22 + 0.36 * (j // 3)), sw * 0.24,
                   sh * 0.26, h * 0.025, col, 0.9)
    cx, cy = sx + sw * 0.5, sy + sh * 0.71
    ring(frame, PENDING, 0.72, cx, cy, h / 330)
    P.cursor_arrow(frame, cx, cy, h / 420)
    tx = sx + sw / 2
    text(frame, "Щипок — это клик", tx, y + h * 0.75, h * 0.071, weight="bold")
    text(frame, "кольцо у курсора заполняется,", tx, y + h * 0.84, h * 0.047, MUTED)
    text(frame, "пока пальцы сходятся", tx, y + h * 0.9, h * 0.047, MUTED)


def feature(frame, x, y, w, h, draw_icon, title, sub):
    glass(w, h, u(30), "caption").draw(frame, x, y)
    draw_icon(frame, x + u(62), y + h / 2)
    text(frame, title, x + u(120), y + h / 2 - u(17), u(31), weight="bold", anchor="lm")
    text(frame, sub, x + u(120), y + h / 2 + u(21), u(23), MUTED, anchor="lm")


def main():
    calm_look()
    frame = backdrop(9.0)
    orbs(frame, ((140, 170, 140), (960, 130, 100), (1020, 640, 70)))

    icon, a = app_icon(round(u(96)))
    blend(frame, round(W / 2 - u(48)), round(u(60)), icon, 1 - a, a)
    text(frame, "AirMouse", W / 2, u(236), u(112), weight="bold")
    text(frame, "Управляйте компьютером рукой в воздухе", W / 2, u(314), u(36), MUTED)
    text(frame, "Нужна только веб-камера  ·  бесплатно  ·  Windows 10 и 11", W / 2, u(366), u(27), TEXT,
         "semibold")

    x, y, w, h = u(80), u(420), u(920), u(480)
    glass(w, h, u(52), "hero").draw(frame, x, y)
    pinch_scene(frame, x, y, w, h)

    tiles = ((lambda f, ix, iy: hand_icon(f, ix, iy, u(62)), "Жесты рукой", "клик, прокрутка, перенос"),
             (lambda f, ix, iy: eye(f, ix, iy, u(30), 1.0, (0.3, 0.0)), "Глаза и голова", "когда руки заняты"),
             (lambda f, ix, iy: text(f, ICON_MONITOR, ix, iy, u(44), ACCENT, "icons"), "Виджеты на экране",
              "громкость и свои кнопки"),
             (lambda f, ix, iy: text(f, ICON_PEN, ix, iy, u(44), ACCENT, "icons"), "Блокнот",
              "рисуйте рукой, как в Paint"))
    for i, (draw_icon, title, sub) in enumerate(tiles):
        feature(frame, u(80 + (i % 2) * 470), u(936 + (i // 2) * 138), u(450), u(122), draw_icon, title, sub)

    pill_w = text_width(REPO, "semibold", u(28)) + u(70)
    glass(pill_w, u(62), u(31), "button").draw(frame, W / 2 - pill_w / 2, u(1252))
    text(frame, REPO, W / 2, u(1283), u(28), weight="semibold")

    out = ROOT / "promo" / "AirMouse_poster.png"
    Image.fromarray(frame).save(out, optimize=True)
    print("saved", out)


if __name__ == "__main__":
    main()
