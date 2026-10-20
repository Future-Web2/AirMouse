"""Renders the Telegram poster: promo/AirMouse_poster.png, 1440x1800 (4:5, shows large in the feed).

    python promo/make_poster.py

Same Liquid Glass look as the app and the promo video; the window in the middle
is the real app window (rendered through airmouse/ui.py, never shown on the screen).
promo/make_carousel.py makes the 8-slide version in the same look.
"""

import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_promo import (  # noqa: E402
    MUTED, ROOT, TEXT, app_icon, blend, eye, fill_round, glass, rounded_rect_sdf, text, text_width,
)
from airmouse.glass import LiquidBackdrop  # noqa: E402

S = 4 / 3                    # layout below is in 1080x1350 units, drawn at 1440x1800
W, H = round(1080 * S), round(1350 * S)
REPO = "github.com/Future-Web2/AirMouse"


def u(v):
    return v * S


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


def app_window(frame, x, y, w):
    """The real app window (hand mode, camera on), scaled to width w, with a title bar and a shadow.
    It is drawn off the screen (make_guide.make_app): no window appears."""
    from make_guide import fake_tracker, make_app, render_app

    from airmouse import bench
    from airmouse.settings import Settings
    from airmouse.tracker import Tracker
    app = make_app("glass", 1.1)
    camera = LiquidBackdrop(640, 480, seed=11).render(2.78)
    overlay = Tracker(Settings())
    overlay.kind, overlay.mode = "hand", "move"
    overlay._publish_preview(np.ascontiguousarray(camera[:, :, ::-1]), bench.hand(328, 241), 1920, 1080)
    app.tracker, app._has_frame = fake_tracker(), True
    app._show_running(True)
    app._camera_bg = app._cover(overlay.take_preview())
    img = render_app(app, 3.0).copy()
    app.onscreen.close()
    app.root.destroy()
    h = round(img.shape[0] * w / img.shape[1])
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    bar = round(u(32))
    glass(w, h + bar, u(16), "caption").draw_shadow(frame, x, y)
    fill_round(frame, x, y, w, h + bar, u(16), (14, 16, 24))
    icon, a = app_icon(round(u(18)))
    blend(frame, round(x + u(14)), round(y + u(7)), icon, 1 - a, a)
    text(frame, "AirMouse", x + u(42), y + bar / 2, u(14), MUTED, "regular", "lm")
    for j, glyph in enumerate(("", "", "")):
        text(frame, glyph, x + w - u(24) - (2 - j) * u(40), y + bar / 2, u(11), MUTED, "icons")
    mask = np.clip(0.5 - rounded_rect_sdf(w, h + round(u(16)), u(16)), 0, 1).astype(np.float32)[round(u(16)):]
    blend(frame, x, y + bar, img, 1 - mask, mask)
    return y + bar + h


def main():
    frame = LiquidBackdrop(W, H, seed=8).render(9.0)
    for cx, cy, d in ((150, 170, 170), (960, 120, 120), (1000, 560, 90), (70, 760, 110)):
        glass(u(d), u(d), u(d / 2), "orb").draw(frame, u(cx - d / 2), u(cy - d / 2))

    icon, a = app_icon(round(u(104)))
    blend(frame, round(W / 2 - u(52)), round(u(56)), icon, 1 - a, a)
    text(frame, "AirMouse", W / 2, u(232), u(118), weight="bold")
    text(frame, "Управляйте компьютером без мыши", W / 2, u(312), u(38), MUTED)
    text(frame, "рукой  ·  взглядом  ·  поворотом головы", W / 2, u(362), u(28), TEXT, "semibold")

    bottom = app_window(frame, round(u(80)), round(u(420)), round(u(920)))

    # Three modes: glass chips over the bottom edge of the window
    chip_w, chip_h, gap = 280, 96, 22
    x = (1080 - (3 * chip_w + 2 * gap)) / 2
    cy = bottom / S + 22
    for label, draw_icon in (("Рука", lambda f, ix, iy: hand_icon(f, ix, iy, u(64))),
                             ("Глаза", lambda f, ix, iy: eye(f, ix, iy, u(28), 1.0, (0.35, 0.0))),
                             ("Голова", lambda f, ix, iy: head_icon(f, ix, iy, u(26)))):
        glass(u(chip_w), u(chip_h), u(chip_h / 2), "caption").draw(frame, u(x), u(cy - chip_h / 2))
        draw_icon(frame, u(x + 70), u(cy))
        text(frame, label, u(x + 120), u(cy), u(36), weight="bold", anchor="lm")
        x += chip_w + gap

    text(frame, "Щипок — клик   ·   Виджеты на экране   ·   Блокнот", W / 2, u(1248), u(27), TEXT, "semibold")
    pill_w = text_width(REPO, "semibold", u(26)) + u(64)
    glass(pill_w, u(58), u(29), "button").draw(frame, W / 2 - pill_w / 2, u(1296) - u(29))
    text(frame, REPO, W / 2, u(1296), u(26), weight="semibold")

    out = ROOT / "promo" / "AirMouse_poster.png"
    Image.fromarray(frame).save(out, optimize=True)
    print("saved", out)


if __name__ == "__main__":
    main()
