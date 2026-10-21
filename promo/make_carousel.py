"""Renders the carousel: 8 slides 1440x1800 (4:5) to swipe through in Telegram, Instagram, VK.

    python promo/make_carousel.py            -> promo/carousel/AirMouse_01.jpg ... _08.jpg,
                                                AirMouse_carousel.pdf, overview.jpg
    python promo/make_carousel.py 3          -> only slide 3 (to check it)

The calm look of the poster (promo/make_poster.py): navy and teal glass, white text,
one light-blue accent, no red or violet. What is shown is real: the hand gestures are
the landmarks the gesture engine is tested with; the widgets, the notebook and the
«Подробнее» window are AirMouse's own (drawn off the screen); the stabilization chart
and the numbers come from the real filters, the KPIs and the tests.
The QR code needs `pip install segno`.
"""

import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_guide as G  # noqa: E402  (also puts the project on sys.path; draws nothing on the screen)
import make_promo as P  # noqa: E402
from make_poster import (  # noqa: E402
    ACCENT, CYAN, REPO, SLATE, H, W, backdrop, calm_look, hand_icon, hand_points, hand_sketch, head_icon, orbs,
    paste_layer, pinch_scene, u,
)
from make_promo import MUTED, TEXT, app_icon, blend, capsule, fill_round, glass, text, text_width  # noqa: E402

from airmouse import onscreen  # noqa: E402
from airmouse.gestures import MOVE  # noqa: E402
from airmouse.notebook import COLORS  # noqa: E402

OUT = HERE / "carousel"
TOTAL = 8
ICON_CHECK, ICON_UPDOWN, ICON_SIDES = "", "", ""
GRAPHITE, BLUE_INK, GREEN_INK, AMBER_INK = COLORS[0], COLORS[1], COLORS[3], COLORS[4]


# -- the frame every slide shares ---------------------------------------------------

def chrome(frame, n, logo=True):
    """Logo and page number on top; dots and «Листайте» at the bottom."""
    if logo:
        icon, a = app_icon(round(u(40)))
        blend(frame, round(u(56)), round(u(52)), icon, 1 - a, a)
        text(frame, "AirMouse", u(108), u(72), u(30), weight="semibold", anchor="lm")
    label = f"{n} / {TOTAL}"
    pw = text_width(label, "semibold", u(24)) + u(44)
    glass(pw, u(48), u(24), "button").draw(frame, W - u(56) - pw, u(48))
    text(frame, label, W - u(56) - pw / 2, u(72), u(24), weight="semibold")
    gap = u(24)
    x0 = W / 2 - (TOTAL - 1) * gap / 2
    for i in range(TOTAL):
        r = u(7) if i == n - 1 else u(5)
        capsule(frame, x0 + i * gap - r, u(1302) - r, 2 * r, 2 * r, (255, 255, 255), 1.0 if i == n - 1 else 0.4)
    if n < TOTAL:
        text(frame, "Листайте  →", W - u(60), u(1302), u(26), MUTED, "semibold", "rm")


def title(frame, s, sub=None, y=176):
    text(frame, s, W / 2, u(y), u(68), weight="bold")
    if sub:
        text(frame, sub, W / 2, u(y + 66), u(32), MUTED)


def bullets(frame, items, x, y, step=68, size=31):
    for i, s in enumerate(items):
        text(frame, ICON_CHECK, u(x), u(y + i * step), u(size), ACCENT, "icons")
        text(frame, s, u(x + 46), u(y + i * step), u(size), weight="semibold", anchor="lm")


def glass_row(frame, y, h, name, how, result, draw_icon):
    """A glass strip: a picture on the left, what to do, and what happens."""
    x, w = u(60), u(960)
    glass(w, u(h), u(36), "caption").draw(frame, x, u(y))
    cy = u(y + h / 2)
    draw_icon(frame, x + u(30), u(y), u(h))
    text(frame, name, x + u(200), cy - u(17), u(36), weight="bold", anchor="lm")
    text(frame, how, x + u(200), cy + u(24), u(25), MUTED, anchor="lm")
    text(frame, result, x + w - u(34), cy, u(36), ACCENT, "bold", "rm")


def small_hand(pose="open", pinch=0.0, mark=None):
    def draw(frame, x, y, h):
        k = (h - u(20)) / 205
        hand_sketch(frame, hand_points(pose, pinch), x + u(4), y + u(6), k, CYAN, width=max(2, round(2.2 * k)))
        if mark:
            text(frame, mark, x + u(136), y + h / 2, u(30), CYAN, "icons")
    return draw


# -- slides ---------------------------------------------------------------------------------

def slide_cover():
    frame = backdrop(9.0)
    orbs(frame, ((140, 180, 140), (960, 300, 100), (60, 920, 90)))
    icon, a = app_icon(round(u(104)))
    blend(frame, round(W / 2 - u(52)), round(u(126)), icon, 1 - a, a)
    text(frame, "AirMouse", W / 2, u(318), u(118), weight="bold")
    text(frame, "Управляйте компьютером рукой в воздухе", W / 2, u(398), u(38), MUTED)
    text(frame, "Нужна только веб-камера  ·  бесплатно", W / 2, u(452), u(29), TEXT, "semibold")
    x, y, w, h = u(80), u(512), u(920), u(560)
    glass(w, h, u(56), "hero").draw(frame, x, y)
    pinch_scene(frame, x, y, w, h)
    chip_w, chip_h, gap = 280, 96, 22
    cx = (1080 - (3 * chip_w + 2 * gap)) / 2
    cy = 1150
    for label, draw_icon in (("Рука", lambda f, ix, iy: hand_icon(f, ix, iy, u(64))),
                             ("Глаза", lambda f, ix, iy: P.eye(f, ix, iy, u(28), 1.0, (0.35, 0.0))),
                             ("Голова", lambda f, ix, iy: head_icon(f, ix, iy, u(26)))):
        glass(u(chip_w), u(chip_h), u(chip_h / 2), "caption").draw(frame, u(cx), u(cy - chip_h / 2))
        draw_icon(frame, u(cx + 70), u(cy))
        text(frame, label, u(cx + 120), u(cy), u(36), weight="bold", anchor="lm")
        cx += chip_w + gap
    chrome(frame, 1, logo=False)
    return frame


def slide_gestures():
    frame = backdrop(11.0)
    orbs(frame, ((1010, 250, 80),))
    title(frame, "Жесты рукой", "Как с мышью, только в воздухе")
    rows = (("Ладонь", "держите ладонь к камере", "Курсор", small_hand("open")),
            ("Щипок", "большой палец к указательному", "Клик", small_hand("open", 1.0)),
            ("Два пальца", "указательный и средний, вверх-вниз", "Прокрутка", small_hand("two", 0.0, ICON_UPDOWN)),
            ("Сжать и вести", "щипок, держать и двигать рукой", "Перетащить", small_hand("open", 1.0, ICON_SIDES)),
            ("Большой к двум", "к указательному и среднему", "Правый клик", small_hand("right", 1.0)),
            ("Палец вверх", "кулак, подержать полсекунды", "Виджеты", small_hand("thumb")))
    for i, (name, how, result, icon) in enumerate(rows):
        glass_row(frame, 300 + i * 150, 132, name, how, result, icon)
    text(frame, "Кольцо у курсора показывает, какой жест AirMouse видит", W / 2, u(1222), u(25), MUTED)
    chrome(frame, 2)
    return frame


def face(frame, cx, cy, r, left=True, right=True, mouth=0.0, brows=0.0, color=(240, 244, 252)):
    """A line face: eyes open or shut, the mouth open by `mouth`, brows raised by `brows` (0..1)."""
    t = max(2, round(r / 30))

    def ellipse(x, y, ax, ay, a0=0, a1=360, fill=None):
        centre, axes = (int(x * 16), int(y * 16)), (int(ax * 16), int(ay * 16))
        if fill is not None:
            cv2.ellipse(frame, centre, axes, 0, a0, a1, fill, -1, cv2.LINE_AA, 4)
        cv2.ellipse(frame, centre, axes, 0, a0, a1, color, t, cv2.LINE_AA, 4)

    ellipse(cx, cy, r * 0.78, r)
    for side, open_ in ((-1, left), (1, right)):
        ex, ey = cx + side * r * 0.3, cy - r * 0.17
        if not open_:
            ellipse(ex, ey + r * 0.02, r * 0.17, r * 0.07, 10, 170)
        elif r > u(80):
            P.eye(frame, ex, ey, r * 0.2, 1.0, (0.4, 0.0))
        else:
            ellipse(ex, ey, r * 0.15, r * 0.08, fill=(10, 16, 28))
            cv2.circle(frame, (int((ex + r * 0.03) * 16), int(ey * 16)), int(r * 0.05 * 16), color, -1, cv2.LINE_AA, 4)
        ellipse(ex, ey - r * (0.32 + 0.16 * brows), r * 0.2, r * 0.07, 200, 340)
    nose = np.array([(cx, cy - r * 0.05), (cx - r * 0.07, cy + r * 0.2), (cx + r * 0.05, cy + r * 0.22)])
    cv2.polylines(frame, [(nose * 16).astype(np.int32)], False, color, t, cv2.LINE_AA, 4)
    if mouth > 0.05:
        ellipse(cx, cy + r * 0.5, r * 0.2, r * (0.04 + 0.12 * mouth), fill=(10, 16, 28))
    else:
        ellipse(cx, cy + r * 0.44, r * 0.26, r * 0.1, 20, 160)


def slide_eyes():
    frame = backdrop(13.5)
    orbs(frame, ((1022, 262, 64),))
    title(frame, "Глаза и голова", "Когда руки заняты — смотрите и кивайте")
    x, y, w, h = u(60), u(300), u(960), u(420)
    glass(w, h, u(48), "panel").draw(frame, x, y)
    face(frame, x + u(230), y + h / 2, u(150), right=False, mouth=0.6, brows=0.4)
    sx, sy, sw, sh = x + u(470), y + u(60), u(440), u(300)
    fill_round(frame, sx, sy, sw, sh, u(20), (8, 14, 26), 0.85)
    for i in range(9):
        dx, dy = sx + u(50) + (i % 3) * (sw - u(100)) / 2, sy + u(50) + (i // 3) * (sh - u(100)) / 2
        capsule(frame, dx - u(9), dy - u(9), u(18), u(18), (255, 255, 255) if i == 4 else (59, 130, 246),
                1.0 if i == 4 else 0.6)
    P.cursor_arrow(frame, sx + sw / 2 + u(70), sy + sh / 2 + u(40), u(1.1))
    text(frame, "взгляд ведёт курсор, поворот головы доводит", sx + sw / 2, sy + sh + u(28), u(21), MUTED)
    rows = (("Долго моргнуть", "закрыть глаза на полсекунды", "Клик", dict(left=False, right=False)),
            ("Подмигнуть", "одним глазом", "Правый клик", dict(right=False)),
            ("Открыть рот", "держать и смотреть, куда тянуть", "Перетащить", dict(mouth=1.0)),
            ("Брови вверх", "и наклон головы вверх или вниз", "Прокрутка", dict(brows=1.0)))
    for i, (name, how, result, look) in enumerate(rows):
        def icon(f, ix, iy, ih, look=look):
            face(f, ix + u(80), iy + ih / 2, ih * 0.4, color=CYAN, **look)
        glass_row(frame, 760 + i * 124, 108, name, how, result, icon)
    chrome(frame, 3)
    return frame


def slide_widgets(camera):
    frame = backdrop(15.0)
    orbs(frame, ((1000, 300, 80),))
    title(frame, "Виджеты на экране", "Громкость, музыка и свои кнопки — тоже рукой")
    x, y, w, h = u(60), u(290), u(960), u(500)
    glass(w, h, u(48), "panel").draw(frame, x, y)
    env = G.WidgetEnv()
    env.s, env.look, env.accent = 1.3, {}, onscreen.ACCENT
    env.volume, env.frame = G.FakeVolume(0.64), camera
    widgets = {}
    for spec in onscreen.default_widgets():
        if spec["type"] in ("status", "volume", "media", "buttons"):
            widget = onscreen.WIDGET_CLASSES[spec["type"]](dict(spec, x=0, y=0), env)
            widget.tick(1.0)
            widgets[spec["type"]] = widget
    widgets["media"].hover, widgets["buttons"].hover = "play", "b0"

    def put(kind, px, py):
        widget = widgets[kind]
        paste_layer(frame, widget.render(1.0).bgra(), int(px - widget.m), int(py - widget.m))
        return py + widget.panel_size()[1]

    left, top = x + u(40), y + u(40)
    put("volume", left, put("status", left, top) + u(18))
    right_x = left + widgets["status"].panel_size()[0] + u(30)
    put("media", right_x, put("buttons", right_x, top) + u(18))
    tx = right_x + widgets["buttons"].panel_size()[0] + u(20)
    hand_sketch(frame, hand_points("thumb"), tx - u(10), y + u(70), u(1.15), CYAN, glow=(20, 70, 150))
    text(frame, "Палец вверх —", tx + u(115), y + u(360), u(26), weight="bold")
    text(frame, "показать", tx + u(115), y + u(396), u(26), MUTED)
    text(frame, "или скрыть", tx + u(115), y + u(428), u(26), MUTED)
    bullets(frame, ("Показать и скрыть: палец вверх или Ctrl+Alt+W",
                    "Свои кнопки: Ctrl+C, Win+D, программы и сайты",
                    "Не забирают фокус: клавиши уходят в вашу программу",
                    "Прямо на рабочем столе, а не в панели Win+W"), 80, 900, 84, 31)
    chrome(frame, 4)
    return frame


def sample_drawing(book):
    """A small drawing in calm colours, a little unsteady, as a hand in the air draws."""
    rng = np.random.default_rng(4)

    def line(points, tool, color, wobble=2.0):
        book.tool, book.color = tool, color
        pts = [(px + rng.normal(0, wobble), py + rng.normal(0, wobble)) for px, py in points]
        book.begin(pts[0])
        for p in pts[1:]:
            book.extend(p)
        book.end()

    def circle(cx, cy, r, n=48, start=0.0):
        return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n))
                for i in range(n + 1)]

    line([(80 + i * 30, 840 + 6 * math.sin(i / 3)) for i in range(48)], "marker", GREEN_INK, 1.5)
    line([(520, 840), (520, 560), (700, 420), (880, 560), (880, 840)], "pen", BLUE_INK)
    line([(520, 560), (880, 560)], "pen", BLUE_INK)
    line([(650, 840), (650, 700), (750, 700), (750, 840)], "pen", BLUE_INK)
    line([(580, 610), (640, 610), (640, 660), (580, 660), (580, 610)], "pen", GRAPHITE, 1.5)
    line(circle(1300, 230, 85), "marker", AMBER_INK)
    for a in range(0, 360, 30):
        r = math.radians(a)
        line([(1300 + 120 * math.cos(r), 230 + 120 * math.sin(r)), (1300 + 170 * math.cos(r), 230 + 170 * math.sin(r))],
             "pen", AMBER_INK, 1.5)
    line([(260, 840), (262, 640)], "marker", GRAPHITE, 1.5)
    for j in range(6):
        line(circle(262 + 30 * math.cos(j), 560 + 25 * math.sin(j * 2), 70 + 8 * j, 40, j), "marker", GREEN_INK, 3.0)
    for cx, r in ((1000, 60), (1080, 80), (1170, 55)):                 # a cloud
        line(circle(cx, 330, r, 40, 3.3)[:24], "pen", GRAPHITE, 1.2)
    # the stroke being drawn right now
    line([(1020 + i * 9, 930 - 30 * math.sin(i / 5)) for i in range(28)], "pen", BLUE_INK, 1.0)
    book.tool, book.color = "pen", BLUE_INK
    return 1020 + 27 * 9, 930 - 30 * math.sin(27 / 5)


def slide_notebook():
    frame = backdrop(17.0)
    orbs(frame, ((90, 300, 80),))
    title(frame, "Блокнот: рисуйте рукой", "Как Paint: щипок — и ведите руку")
    env = G.WidgetEnv()
    s = 1.75
    env.s, env.look, env.accent = s, {}, onscreen.ACCENT
    widget = onscreen.NotebookWidget({"type": "notebook", "on": True, "x": 0, "y": 0}, env)
    end = sample_drawing(widget.book)
    pw, _ph = widget.panel_size()
    x, y = round((W - pw) / 2), round(u(290))
    paste_layer(frame, widget.render(1.0).bgra(), x - widget.m, y - widget.m)
    px, py, paper_w, paper_h = widget.paper()
    P.cursor_arrow(frame, x + (px + end[0] / 1600 * paper_w) * s, y + (py + end[1] / 1000 * paper_h) * s, u(1.15))
    bullets(frame, ("Ручка, маркер, ластик и пять цветов",
                    "Страницы сохраняются сами",
                    "Копировать — и Ctrl+V в чат или документ",
                    "Открыть: Ctrl+Alt+N или карандаш на мини-панели"), 80, 978, 66, 30)
    chrome(frame, 5)
    return frame


def slide_precision(stability):
    frame = backdrop(19.0)
    orbs(frame, ((1010, 120, 70),))
    title(frame, "Рука дрожит — курсор нет", "Фильтр One Euro и «поводок» гасят дрожь")
    x, y, w, h = u(60), u(290), u(960), u(420)
    glass(w, h, u(44), "panel").draw(frame, x, y)
    x0, x1, cy = x + u(40), x + u(600), y + h / 2 + u(20)
    for i, (label, color) in enumerate((("Рука", SLATE), ("Курсор", CYAN))):
        capsule(frame, x0 + i * u(170), y + u(40), u(14), u(14), color)
        text(frame, label, x0 + u(24) + i * u(170), y + u(47), u(24), MUTED, "semibold", "lm")
    capsule(frame, x0, cy, x1 - x0, 1, (255, 255, 255), 0.15)
    mid = stability.raw.mean()
    xs = np.linspace(x0, x1, len(stability.raw))
    for series, color in ((stability.raw, SLATE), (stability.cur, CYAN)):
        pts = (np.stack([xs, cy + (series - mid) * u(4.5)], 1) * 16).astype(np.int32)
        cv2.polylines(frame, [pts], False, color, max(3, round(u(3.5))), cv2.LINE_AA, 4)
    sx = x + u(650)
    text(frame, "Дрожь руки", sx, y + u(110), u(26), MUTED, "semibold", "lm")
    text(frame, f"{stability.raw_span:.0f} px", sx, y + u(170), u(70), SLATE, "bold", "lm")
    text(frame, "Курсор", sx, y + u(260), u(26), MUTED, "semibold", "lm")
    text(frame, f"{stability.cur_span:.0f} px", sx, y + u(320), u(70), CYAN, "bold", "lm")
    tiles = (("20 из 20", "щипков — ровно 20 кликов"), ("0", "ложных кликов за минуту дрожи"),
             ("172", "автотеста при каждом изменении"), ("Офлайн", "камера обрабатывается на компьютере"))
    for i, (big, small) in enumerate(tiles):
        tx, ty = u(60 + (i % 2) * 490), u(750 + (i // 2) * 236)
        glass(u(470), u(216), u(40), "caption").draw(frame, tx, ty)
        text(frame, big, tx + u(235), ty + u(88), u(66), weight="bold")
        text(frame, small, tx + u(235), ty + u(160), u(25), MUTED)
    text(frame, "Числа — из замеров и автотестов AirMouse", W / 2, u(1236), u(23), MUTED)
    chrome(frame, 6)
    return frame


def slide_tuning():
    frame = backdrop(21.0)
    title(frame, "Тонкая настройка", "29 параметров: больше или меньше — как вам удобно")
    shot = cv2.cvtColor(cv2.imread(str(G.GUIDE / "advanced_camera60.png")), cv2.COLOR_BGR2RGB)
    k = u(560) / shot.shape[1]
    shot = cv2.resize(shot, (round(shot.shape[1] * k), round(shot.shape[0] * k)), interpolation=cv2.INTER_AREA)
    x, y = round(u(60)), round(u(330))
    G.draw_window(frame, shot, x, y, "Подробные настройки — AirMouse", (32, 32, 32))
    bx, by, bw, bh = (v * k for v in G.json.loads((G.GUIDE / "advanced.json").read_text(encoding="utf-8"))["camera_fps"])
    G.outline(frame, x + bx, y + by, bw, bh, 8, ACCENT, 0.95, 5)
    cards = (("60 кадр/с", "курсор точнее и отзывчивее"), ("Мёртвая зона", "гасит мелкую дрожь"),
             ("Щипок", "сколько держать до клика"), ("Доступность", "вторая рука, клик задержкой"),
             ("По умолчанию", "вернуть всё как было"))
    cx = u(660)
    for i, (head, sub) in enumerate(cards):
        cy = u(300 + i * 148)
        glass(u(360), u(132), u(32), "caption").draw(frame, cx, cy)
        text(frame, head, cx + u(28), cy + u(50), u(32), ACCENT if i == 0 else TEXT, "bold", "lm")
        text(frame, sub, cx + u(28), cy + u(92), u(22), MUTED, anchor="lm")
    labels = ("Стекло", "Природа", "Классика")
    widths = [text_width(s, "semibold", u(28)) + u(56) for s in labels]
    lead = "Дизайн окна:"
    lx = W / 2 - (text_width(lead, "regular", u(28)) + u(20) + sum(widths) + u(14) * (len(widths) - 1)) / 2
    text(frame, lead, lx, u(1150), u(28), MUTED, anchor="lm")
    lx += text_width(lead, "regular", u(28)) + u(20)
    for s, pw in zip(labels, widths):
        glass(pw, u(56), u(28), "button").draw(frame, lx, u(1122))
        text(frame, s, lx + pw / 2, u(1150), u(28), weight="semibold")
        lx += pw + u(14)
    text(frame, "Всё применяется сразу, без перезапуска", W / 2, u(1228), u(23), MUTED)
    chrome(frame, 7)
    return frame


def qr(frame, data, x, y, size):
    """A QR code (segno) drawn as crisp squares on a white rounded card."""
    import segno
    matrix = np.array([list(row) for row in segno.make(data, error="m").matrix], np.uint8)
    n = matrix.shape[0] + 8                                  # with the quiet zone
    cell = size / n
    fill_round(frame, x, y, size, size, size * 0.06, (255, 255, 255))
    for r, c in zip(*np.nonzero(matrix)):
        x0, y0 = x + (c + 4) * cell, y + (r + 4) * cell
        cv2.rectangle(frame, (int(round(x0)), int(round(y0))), (int(round(x0 + cell)) - 1, int(round(y0 + cell)) - 1),
                      (12, 18, 30), -1)


def slide_download():
    frame = backdrop(23.0)
    orbs(frame, ((70, 980, 90), (1015, 1020, 70)))
    title(frame, "Попробуйте бесплатно", "Windows 10 и 11  ·  нужна только веб-камера")
    steps = (("Скачайте", "AirMouse-windows-x64.zip на GitHub"), ("Распакуйте", "архив целиком: «Извлечь все…»"),
             ("Запустите", "AirMouse.exe и нажмите «Старт»"))
    for i, (head, rest) in enumerate(steps):
        y = u(310 + i * 128)
        glass(u(960), u(108), u(54), "caption").draw(frame, u(60), y)
        capsule(frame, u(84), y + u(24), u(60), u(60), (37, 99, 235))
        text(frame, str(i + 1), u(114), y + u(54), u(30), weight="bold")
        text(frame, head, u(170), y + u(54), u(34), weight="bold", anchor="lm")
        text(frame, rest, u(170) + text_width(head, "bold", u(34)) + u(16), y + u(54), u(28), MUTED, anchor="lm")
    size = u(330)
    cx = W / 2
    glass(size + u(60), size + u(120), u(44), "panel").draw(frame, cx - size / 2 - u(30), u(700))
    qr(frame, "https://" + REPO, cx - size / 2, u(730), size)
    text(frame, "Наведите камеру телефона", cx, u(1100), u(26), MUTED)
    pw = text_width(REPO, "semibold", u(30)) + u(70)
    glass(pw, u(70), u(35), "button").draw(frame, cx - pw / 2, u(1150))
    text(frame, REPO, cx, u(1185), u(30), weight="semibold")
    text(frame, "Python не нужен  ·  видео-гайд и инструкция — в репозитории", cx, u(1248), u(23), MUTED)
    chrome(frame, 8)
    return frame


# -- main --------------------------------------------------------------------------------

def build(only=None):
    calm_look()
    camera = G.Camera().frame(1.0, G.bench.hand(300, 230))
    makers = (slide_cover, slide_gestures, slide_eyes, lambda: slide_widgets(camera), slide_notebook,
              lambda: slide_precision(P.Stability()), slide_tuning, slide_download)
    return {i + 1: make() for i, make in enumerate(makers) if only is None or i + 1 == only}


def main():
    cv2.setNumThreads(0)
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    OUT.mkdir(exist_ok=True)
    slides = build(only)
    images = []
    for n, frame in slides.items():
        image = Image.fromarray(frame)
        path = OUT / f"AirMouse_{n:02d}.jpg"
        image.save(path, quality=93, subsampling=0, optimize=True)
        images.append(image)
        print("saved", path)
    if only is None:
        images[0].save(OUT / "AirMouse_carousel.pdf", save_all=True, append_images=images[1:], resolution=144)
        thumb_w, gap = 360, 24
        thumb_h = round(thumb_w * H / W)
        sheet = Image.new("RGB", (4 * thumb_w + 5 * gap, 2 * thumb_h + 3 * gap), (8, 14, 26))
        for i, image in enumerate(images):
            sheet.paste(image.resize((thumb_w, thumb_h), Image.LANCZOS),
                        (gap + (i % 4) * (thumb_w + gap), gap + (i // 4) * (thumb_h + gap)))
        sheet.save(OUT / "overview.jpg", quality=90)
        print("saved", OUT / "AirMouse_carousel.pdf", OUT / "overview.jpg")


if __name__ == "__main__":
    main()
