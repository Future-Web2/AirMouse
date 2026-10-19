"""On-screen widgets: small panels floating over all windows, worked by hand like everything else.

They show while AirMouse runs; a held thumbs up (or Ctrl+Alt+W) hides and shows
them. They never take the keyboard focus, so a button that presses Ctrl+C
copies in the program you were using. Drag a widget by its background to move it.

  status    the camera with the hand, what AirMouse sees, frames per second
  clock     time and date
  volume    drag or scroll to set the volume, tap the speaker to mute
  media     previous / play-pause / next track
  system    processor, memory and battery
  buttons   your own panel: buttons that press key combinations or open things

The cursor ring follows the cursor and shows the gesture in progress: it fills
as the fingers close (or the eyes stay shut) and flashes on a click.

Widget code runs in the Tk thread: mouse handlers from the window procedure
(where Tkinter must not be called), everything else from OnScreen's timer.
"""

import math
import time
from datetime import datetime

from . import system, tuning, winmouse
from .face import EYES_CLOSED, NO_FACE
from .gestures import DRAG, MOVE, NO_HAND, PENDING, PRESSED, RIGHT, SCROLL
from .overlay import Layer, LayeredWindow, cursor_pos

TEXT = (245, 247, 250)
MUTED = (170, 178, 192)
DIM = (112, 118, 132)
ACCENT = (64, 140, 255)
GREEN = (94, 224, 122)
YELLOW = (255, 204, 64)
ORANGE = (255, 128, 84)
PURPLE = (200, 128, 255)
BLUE = (84, 180, 255)
RED = (255, 98, 112)
GREY = (150, 155, 168)

ICON_PLAY, ICON_PREV, ICON_NEXT = "", "", ""
ICON_VOLUME, ICON_MUTE, ICON_SETTINGS = "", "", ""
ICON_UP, ICON_DOWN, ICON_PAUSE = "", "", ""

KINDS = ("status", "clock", "volume", "media", "system", "buttons")
NAMES = {
    "status": "AirMouse: камера и жест",
    "clock": "Часы",
    "volume": "Громкость",
    "media": "Музыка и видео",
    "system": "Нагрузка компьютера",
    "buttons": "Панель кнопок",
}
MAX_BUTTONS = 12
DEFAULT_BUTTONS = (
    ("Копировать", "keys", "ctrl+c"),
    ("Вставить", "keys", "ctrl+v"),
    ("Отменить", "keys", "ctrl+z"),
    ("Рабочий стол", "keys", "win+d"),
    ("Все окна", "keys", "win+tab"),
    ("Скриншот", "keys", "win+shift+s"),
    ("Голосовой ввод", "keys", "win+h"),
    ("Клавиатура", "open", "osk"),
)
DAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря")


def button_spec(label, do, value):
    return {"label": label, "do": do, "value": value}


def default_widgets():
    return [
        {"type": "status", "on": True},
        {"type": "volume", "on": True},
        {"type": "media", "on": True},
        {"type": "buttons", "on": True, "title": "Быстрые действия",
         "buttons": [button_spec(*b) for b in DEFAULT_BUTTONS]},
        {"type": "clock", "on": False},
        {"type": "system", "on": False},
    ]


def clean_specs(raw):
    """The widget list from the settings file, with anything malformed dropped, and every
    built-in widget present once (a new version may bring new ones). Empty: the defaults."""
    if not isinstance(raw, list) or not raw:
        return default_widgets()
    specs, seen = [], set()
    for item in raw:
        if not isinstance(item, dict) or item.get("type") not in KINDS:
            continue
        kind = item["type"]
        if kind != "buttons":
            if kind in seen:
                continue
            seen.add(kind)
        spec = {"type": kind, "on": bool(item.get("on", True))}
        for key in ("x", "y"):
            if isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool):
                spec[key] = int(item[key])
        if kind == "buttons":
            spec["title"] = str(item.get("title", ""))[:40]
            buttons = item.get("buttons") if isinstance(item.get("buttons"), list) else []
            spec["buttons"] = [button_spec(str(b.get("label", "")).strip()[:24] or "Кнопка", b["do"],
                                           str(b.get("value", ""))[:300])
                               for b in buttons if isinstance(b, dict) and b.get("do") in ("keys", "open")
                               ][:MAX_BUTTONS]
        specs.append(spec)
    for spec in default_widgets():
        if spec["type"] != "buttons" and spec["type"] not in seen:
            specs.append(spec)
    return specs


# -- widgets ----------------------------------------------------------------------------

class Widget:
    """A panel that draws itself and answers the mouse. Layout is in logical pixels (x env.s)."""

    width, height = 200, 80

    def __init__(self, spec, env):
        self.spec, self.env, self.s = spec, env, env.s
        self.m = round(22 * self.s)            # transparent border around the panel, room for its shadow
        self.hover = self.pressed = None
        self.dirty = True
        self._drag = None
        self._base = None

    # geometry
    def logical_size(self):
        return self.width, self.height

    def panel_size(self):
        w, h = self.logical_size()
        return round(w * self.s), round(h * self.s)

    def window_size(self):
        w, h = self.panel_size()
        return w + 2 * self.m, h + 2 * self.m

    def at(self, x, y):
        """Logical panel coordinates -> pixels in the widget's picture."""
        return self.m + x * self.s, self.m + y * self.s

    def parts(self):
        """Clickable parts: [(name, (x, y, w, h))] in logical panel coordinates."""
        return []

    def part_at(self, x, y):
        lx, ly = (x - self.m) / self.s, (y - self.m) / self.s
        for name, (px, py, pw, ph) in self.parts():
            if px <= lx <= px + pw and py <= ly <= py + ph:
                return name
        return None

    # mouse (called from the window procedure: never call Tkinter in here)
    def mouse(self, kind, x, y, delta):
        if kind == "move":
            if self._drag is not None:
                self._follow_drag()
            elif self.pressed is not None:
                self.on_drag(self.pressed, (x - self.m) / self.s, (y - self.m) / self.s)
            else:
                self._set_hover(self.part_at(x, y))
        elif kind == "down":
            part = self.part_at(x, y)
            if part is None:
                cx, cy = self.env.cursor()
                self._drag = (cx, cy, self.spec["x"], self.spec["y"])
            else:
                self.pressed = part
                self.dirty = True
                self.on_press(part, (x - self.m) / self.s, (y - self.m) / self.s)
        elif kind == "up":
            if self._drag is not None:
                self._follow_drag()
                self._drag = None
                self.env.changed()
            elif self.pressed is not None:
                part, self.pressed = self.pressed, None
                self.dirty = True
                if self.part_at(x, y) == part:
                    self.on_click(part)
        elif kind == "wheel":
            self.on_wheel(self.part_at(x, y), delta)
        elif kind in ("leave", "cancel"):
            if kind == "cancel":
                self._drag = None
                if self.pressed is not None:
                    self.pressed = None
                    self.dirty = True
            self._set_hover(None)

    def _set_hover(self, part):
        if part != self.hover:
            self.hover = part
            self.dirty = True

    def _follow_drag(self):
        cx, cy, sx, sy = self._drag
        nx, ny = self.env.cursor()
        self.spec["x"], self.spec["y"] = self.env.clamp(self, sx + nx - cx, sy + ny - cy)
        self.env.place(self)

    def on_press(self, part, x, y):
        pass

    def on_drag(self, part, x, y):
        pass

    def on_click(self, part):
        pass

    def on_wheel(self, part, delta):
        pass

    # drawing
    def tick(self, now):
        """Called often from the timer: update state, set self.dirty when the picture changes."""

    def render(self, now):
        w, h = self.window_size()
        if self._base is None or (self._base.w, self._base.h) != (w, h):
            base = Layer(w, h)
            pw, ph = self.panel_size()
            base.panel(self.m, self.m, pw, ph, 18 * self.s, blur=5 * self.s, offset=3 * self.s)
            self.draw_static(base)
            self._base = base
        layer = self._base.copy()
        self.draw(layer, now)
        return layer

    def draw_static(self, layer):
        """What never changes (drawn once onto the cached background)."""

    def draw(self, layer, now):
        pass

    def button(self, layer, name, x, y, w, h, radius=12):
        """A soft button background that lights up under the cursor and while pressed."""
        lift = 0.24 if self.pressed == name else 0.15 if self.hover == name else 0.07
        px, py = self.at(x, y)
        layer.round_rect(px, py, w * self.s, h * self.s, radius * self.s, (255, 255, 255), lift)

    def text(self, layer, text, x, y, size, color=TEXT, weight="regular", anchor="lm", **kwargs):
        px, py = self.at(x, y)
        return layer.text(text, px, py, size * self.s, color, weight, anchor, **kwargs)


class StatusWidget(Widget):
    width, height = 280, 262
    PREVIEW = (16, 46, 248, 186)
    FPS = 15        # the preview here needs no more

    def __init__(self, spec, env):
        super().__init__(spec, env)
        self._shown = (None, None)
        self._drawn = 0.0

    def parts(self):
        return [("settings", (238, 8, 30, 30))]

    def on_click(self, part):
        self.env.request(("editor",))

    def tick(self, now):
        state = (self.env.status(), self.env.frame_id)
        if state != self._shown and now - self._drawn >= 1 / self.FPS:
            self._shown = state
            self.dirty = True

    def draw_static(self, layer):
        self.text(layer, "Ctrl+Alt+M — пауза   ·   палец вверх — скрыть", 140, 246, 11, DIM, anchor="mm")

    def draw(self, layer, now):
        self._drawn = now
        (text, color, fps), _frame_id = self._shown if self._shown[0] else (self.env.status(), 0)
        cx, cy = self.at(24, 23)
        layer.circle(cx, cy, 5.5 * self.s, color)
        self.text(layer, text, 38, 23, 15, weight="semibold", max_width=150 * self.s)
        self.text(layer, fps, 230, 23, 12, MUTED, anchor="rm")
        self.button(layer, "settings", 238, 8, 30, 30, radius=10)
        layer.icon(ICON_SETTINGS, *self.at(253, 23), 14 * self.s, MUTED)
        x, y, w, h = self.PREVIEW
        px, py = self.at(x, y)
        frame = self.env.frame if self.env.camera_on() else None
        if frame is not None:
            fh, fw = frame.shape[:2]
            if fw * h > fh * w:              # a wide camera picture: show its middle
                keep = fh * w // h
                frame = frame[:, (fw - keep) // 2:(fw - keep) // 2 + keep]
            layer.image(frame, px, py, w * self.s, h * self.s, 12 * self.s)
        else:
            layer.round_rect(px, py, w * self.s, h * self.s, 12 * self.s, (0, 0, 0), 0.35)
            text = "Камера включается…" if self.env.camera_on() else "Камера выключена"
            self.text(layer, text, x + w / 2, y + h / 2, 13, MUTED, anchor="mm")


class ClockWidget(Widget):
    width, height = 224, 92

    def __init__(self, spec, env):
        super().__init__(spec, env)
        self._minute = None

    def tick(self, now):
        minute = datetime.now().strftime("%Y%m%d%H%M")
        if minute != self._minute:
            self._minute = minute
            self.dirty = True

    def draw(self, layer, now):
        moment = datetime.now()
        self.text(layer, moment.strftime("%H:%M"), 20, 38, 38, weight="bold")
        self.text(layer, f"{DAYS[moment.weekday()]}, {moment.day} {MONTHS[moment.month - 1]}", 21, 72, 13, MUTED)


class VolumeWidget(Widget):
    width, height = 284, 72
    TRACK = (78, 210)      # logical x of the slider ends
    POLL = 0.5             # seconds between asking Windows (the volume can change elsewhere)

    def __init__(self, spec, env):
        super().__init__(spec, env)
        self.level = self.muted = None
        self._polled = -1.0

    def parts(self):
        return [("mute", (12, 12, 48, 48)), ("slider", (68, 14, 152, 44))]

    def _read(self):
        level, muted = self.env.volume.level(), self.env.volume.muted()
        if (level, muted) != (self.level, self.muted):
            self.level, self.muted = level, muted
            self.dirty = True

    def tick(self, now):
        if now - self._polled >= self.POLL and self.pressed is None:
            self._polled = now
            self._read()

    def _set(self, level):
        if self.level is None:
            return
        level = min(max(level, 0.0), 1.0)
        self.env.volume.set_level(level)
        if self.muted and level > 0:
            self.env.volume.set_muted(False)
            self.muted = False
        self.level = level
        self.dirty = True

    def _from_x(self, x):
        x0, x1 = self.TRACK
        return (x - x0) / (x1 - x0)

    def on_press(self, part, x, y):
        if part == "slider":
            self._set(self._from_x(x))

    def on_drag(self, part, x, y):
        if part == "slider":
            self._set(self._from_x(x))

    def on_click(self, part):
        if part == "mute" and self.level is not None:
            self.muted = not self.muted
            self.env.volume.set_muted(self.muted)
            self.dirty = True

    def on_wheel(self, part, delta):
        if self.level is not None:
            self._set(self.level + delta / 120 * 0.04)   # 4% a notch; AirMouse sends quarter notches

    def draw(self, layer, now):
        self.button(layer, "mute", 12, 12, 48, 48, radius=14)
        silent = self.muted or not self.level
        layer.icon(ICON_MUTE if silent else ICON_VOLUME, *self.at(36, 36), 18 * self.s, MUTED if silent else TEXT)
        if self.level is None:
            self.text(layer, "Нет звукового устройства", 72, 36, 13, MUTED)
            return
        x0, x1 = self.TRACK
        tx, ty = self.at(x0, 33)
        length = (x1 - x0) * self.s
        layer.capsule(tx, ty, length, 6 * self.s, (255, 255, 255), 0.16)
        filled = max(6 * self.s, self.level * length)
        layer.capsule(tx, ty, filled, 6 * self.s, DIM if self.muted else ACCENT)
        knob = 9 if self.pressed == "slider" else 8 if self.hover == "slider" else 7
        layer.circle(tx + self.level * length, ty + 3 * self.s, knob * self.s, (255, 255, 255))
        self.text(layer, f"{round(self.level * 100)}%", 266, 36, 15, MUTED if self.muted else TEXT,
                  weight="semibold", anchor="rm")


class MediaWidget(Widget):
    width, height = 232, 76
    KEYS = (("prev", 52, ICON_PREV, "prevtrack"), ("play", 116, ICON_PLAY, "playpause"),
            ("next", 180, ICON_NEXT, "nexttrack"))

    def parts(self):
        return [(name, (x - 28, 10, 56, 56)) for name, x, _icon, _key in self.KEYS]

    def on_click(self, part):
        for name, _x, _icon, key in self.KEYS:
            if name == part:
                self.env.request(("keys", key))

    def draw(self, layer, now):
        for name, x, icon, _key in self.KEYS:
            cx, cy = self.at(x, 38)
            lift = 0.26 if self.pressed == name else 0.16 if self.hover == name else 0.08
            r = 26 if name == "play" else 22
            layer.circle(cx, cy, r * self.s, (255, 255, 255), lift)
            layer.icon(icon, cx, cy, (20 if name == "play" else 16) * self.s, TEXT)


class SystemWidget(Widget):
    width = 252
    ROWS = (("cpu", "Процессор"), ("memory", "Память"), ("battery", "Батарея"))

    def __init__(self, spec, env):
        super().__init__(spec, env)
        self.values = {}
        self._polled = -1.0
        self.env.load.cpu()   # starts the measurement

    def logical_size(self):
        return self.width, 88 if self.env.load.battery() is None else 120

    def tick(self, now):
        if now - self._polled >= 1.0:
            self._polled = now
            battery = self.env.load.battery()
            values = {"cpu": self.env.load.cpu(), "memory": self.env.load.memory()}
            if battery is not None:
                values["battery"] = battery[0]
                values["charging"] = battery[1]
            if values != self.values:
                self.values = values
                self.dirty = True

    def draw(self, layer, now):
        y = 28
        for key, label in self.ROWS:
            if key not in self.values:
                continue
            value = self.values[key]
            if key == "battery" and self.values.get("charging"):
                label = "Заряжается"
            self.text(layer, label, 18, y, 13)
            bx, by = self.at(110, y - 3)
            length = 84 * self.s
            layer.capsule(bx, by, length, 6 * self.s, (255, 255, 255), 0.16)
            high = value >= 85 if key != "battery" else value <= 15
            layer.capsule(bx, by, max(6 * self.s, length * value / 100), 6 * self.s, RED if high else ACCENT)
            self.text(layer, f"{value:.0f}%", 236, y, 13, MUTED, anchor="rm")
            y += 32


class ButtonsWidget(Widget):
    COLUMNS, BUTTON_W, BUTTON_H, GAP, PAD = 2, 124, 44, 8, 16
    ERROR_TIME = 3.0

    def __init__(self, spec, env):
        super().__init__(spec, env)
        self.error = None          # (text, until)
        self._flash = None         # (index, until): the button just used

    def _top(self):
        return self.PAD + (26 if self.spec.get("title") else 0)

    def logical_size(self):
        n = max(len(self.spec.get("buttons", [])), 1)
        rows = math.ceil(n / self.COLUMNS)
        w = 2 * self.PAD + self.COLUMNS * self.BUTTON_W + (self.COLUMNS - 1) * self.GAP
        return w, self._top() + rows * self.BUTTON_H + (rows - 1) * self.GAP + self.PAD + (22 if self.error else 0)

    def parts(self):
        top = self._top()
        return [(f"b{i}", (self.PAD + (i % self.COLUMNS) * (self.BUTTON_W + self.GAP),
                           top + (i // self.COLUMNS) * (self.BUTTON_H + self.GAP), self.BUTTON_W, self.BUTTON_H))
                for i in range(len(self.spec.get("buttons", [])))]

    def on_click(self, part):
        index = int(part[1:])
        self._flash = (index, time.perf_counter() + 0.25)
        self.env.request(("action", self.spec["buttons"][index], self))

    def show_error(self, text):
        """Called by OnScreen after running an action (None: it worked)."""
        if text:
            self.error = (text, time.perf_counter() + self.ERROR_TIME)
            self._base = None   # the panel grows by a line
        self.dirty = True

    def tick(self, now):
        if self.error and now >= self.error[1]:
            self.error = None
            self._base = None
            self.dirty = True
        if self._flash and now >= self._flash[1]:
            self._flash = None
            self.dirty = True

    def draw_static(self, layer):
        if self.spec.get("title"):
            self.text(layer, self.spec["title"].upper(), self.PAD + 2, 26, 11, MUTED, "semibold")

    def draw(self, layer, now):
        buttons = self.spec.get("buttons", [])
        if not buttons:
            self.text(layer, "Добавьте кнопки в настройках", self.PAD + 2, self._top() + 22, 12, MUTED)
        for (name, (x, y, w, h)), button in zip(self.parts(), buttons):
            flash = self._flash is not None and name == f"b{self._flash[0]}"
            px, py = self.at(x, y)
            if flash:
                layer.round_rect(px, py, w * self.s, h * self.s, 12 * self.s, ACCENT, 0.85)
            else:
                self.button(layer, name, x, y, w, h)
            self.text(layer, button["label"], x + w / 2, y + h / 2, 13, TEXT, "semibold", "mm",
                      max_width=(w - 14) * self.s)
        if self.error:
            _w, h = self.logical_size()
            self.text(layer, self.error[0], self.PAD + 2, h - self.PAD - 4, 12, RED, max_width=250 * self.s)


WIDGET_CLASSES = {"status": StatusWidget, "clock": ClockWidget, "volume": VolumeWidget, "media": MediaWidget,
                  "system": SystemWidget, "buttons": ButtonsWidget}


# -- cursor ring --------------------------------------------------------------------------

class CursorRing:
    """The ring drawn around the cursor while AirMouse moves it."""

    SIZE = 76            # logical size of its window
    RADIUS = 21
    FLASH = 0.35         # seconds a click flash lasts

    COLORS = {MOVE: (255, 255, 255), PENDING: YELLOW, PRESSED: YELLOW, EYES_CLOSED: YELLOW, DRAG: ORANGE,
              RIGHT: PURPLE, SCROLL: BLUE}

    def __init__(self, s):
        self.s = s
        self.size = round(self.SIZE * s)
        self._flash = None     # (colour, start)
        self._wheel = None     # (direction, start)

    def event(self, action, now):
        kind = action[0]
        if kind in ("click", "down"):
            self._flash = (PURPLE if action[1] == "right" else GREEN, now)
        elif kind == "wheel":
            self._wheel = (1 if action[1] > 0 else -1, now)

    def state(self, mode, progress, now):
        """Everything the picture depends on, rounded so that equal pictures compare equal."""
        flash = None
        if self._flash and now - self._flash[1] < self.FLASH:
            flash = (self._flash[0], round((now - self._flash[1]) / self.FLASH, 1))
        wheel = self._wheel[0] if self._wheel and now - self._wheel[1] < 0.25 else 0
        if mode not in (MOVE, PENDING, EYES_CLOSED):
            progress = 0.0
        return mode, round(progress, 2) if progress > 0.03 else 0.0, flash, wheel

    def render(self, state):
        mode, progress, flash, wheel = state
        s, c = self.s, self.size / 2
        layer = Layer(self.size, self.size)
        color = self.COLORS.get(mode, GREY)
        r = self.RADIUS * s
        strong = mode in (PRESSED, DRAG, RIGHT, SCROLL, PENDING)
        width = (3.2 if strong else 1.6) * s
        layer.arc(c, c, r, width + 2 * s, (0, 0, 0), 0.3)      # a dark halo keeps it visible on white
        layer.arc(c, c, r, width, color, 0.95 if strong else 0.7)
        if progress:
            layer.arc(c, c, r, 3.6 * s, YELLOW, 0.95, extent=360 * progress)
        if mode == SCROLL:
            for direction, glyph, dy in ((1, ICON_UP, -1), (-1, ICON_DOWN, 1)):
                layer.icon(glyph, c, c + dy * (r + 9 * s), 12 * s, BLUE, 1.0 if wheel == direction else 0.55)
        if flash:
            flash_color, phase = flash
            layer.arc(c, c, r + 10 * s * phase, 3 * s, flash_color, 0.9 * (1 - phase))
        return layer


# -- the manager ---------------------------------------------------------------------------

class OnScreen:
    """Owns the widget windows and the cursor ring, and drives them from the app's timer."""

    def __init__(self, app, scale):
        self.app, self.settings, self.s = app, app.settings, scale
        self.volume, self.load = system.Volume(), system.SystemLoad()
        self.frame, self.frame_id = None, 0
        self.items = []                  # [widget, window]
        self.ring = CursorRing(scale)
        self._ring_window = None
        self._ring_state = None
        self._requests = []
        self._tracker = None
        self._toggles = 0
        self._event = 0
        self._save = False
        self._closed = False
        self.settings.widgets = clean_specs(self.settings.widgets)
        self.rebuild()
        self.app.after(200, self._tick)

    # what widgets use
    def cursor(self):
        return cursor_pos()

    def request(self, item):
        self._requests.append(item)

    def changed(self):
        self._save = True

    def status(self):
        return self.app._status()

    def camera_on(self):
        return self.app.tracker is not None

    def place(self, widget):
        for w, window in self.items:
            if w is widget and window.visible:
                window.move(widget.spec["x"] - widget.m, widget.spec["y"] - widget.m)

    def clamp(self, widget, x, y):
        """Keep at least part of the panel on some screen."""
        left, top, width, height = (winmouse.user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        w, h = widget.panel_size()
        keep = round(60 * self.s)
        return (int(min(max(x, left - w + keep), left + width - keep)),
                int(min(max(y, top), top + height - keep)))

    # the app's side
    def on_frame(self, frame):
        self.frame = frame
        self.frame_id += 1

    def toggle(self):
        self.settings.widgets_on = not self.settings.widgets_on
        self._save = True

    def rebuild(self):
        """Recreate the widgets from settings.widgets (after the editor changed them)."""
        for _widget, window in self.items:
            window.destroy()
        self.items = []
        for spec in self.settings.widgets:
            widget = WIDGET_CLASSES[spec["type"]](spec, self)
            window = LayeredWindow(on_mouse=widget.mouse, hand_at=lambda x, y, w=widget: w.part_at(x, y) is not None)
            self.items.append([widget, window])
            if "x" in spec and "y" in spec:   # the screens may have changed since it was placed
                spec["x"], spec["y"] = self.clamp(widget, spec["x"], spec["y"])
        self.arrange(only_new=True)

    def set_scale(self, s):
        """Draw the widgets and the cursor ring at another size («Размер виджетов»)."""
        self.s = s
        self.ring = CursorRing(s)
        self._ring_state = None
        if self._ring_window is not None:
            self._ring_window.destroy()
            self._ring_window = None
        self.rebuild()

    def refresh(self):
        """Redraw every widget (after an edit that keeps the same widgets, e.g. a renamed button)."""
        for widget, _window in self.items:
            widget._base = None
            widget.dirty = True

    def arrange(self, only_new=False):
        """Put widgets in a column along the right edge of the main screen (only_new: those without a place)."""
        sw, sh = winmouse.screen_size()
        margin, gap = round(24 * self.s), round(12 * self.s)
        x_right, y = sw - margin, margin
        column_w = 0
        for widget, _window in self.items:
            if only_new and "x" in widget.spec and "y" in widget.spec:
                continue
            w, h = widget.panel_size()
            if y + h > sh - margin and y > margin:      # next column to the left
                x_right -= column_w + gap
                y, column_w = margin, 0
            widget.spec["x"], widget.spec["y"] = x_right - w, y
            y += h + gap
            column_w = max(column_w, w)
            widget.dirty = True
        self._save = True

    def close(self):
        self._closed = True
        for _widget, window in self.items:
            window.destroy()
        self.items = []
        if self._ring_window is not None:
            self._ring_window.destroy()
            self._ring_window = None

    # the timer
    def _tick(self):
        if self._closed:
            return
        delay = 100
        try:
            delay = self._update(time.perf_counter())
        finally:
            if not self._closed:
                self.app.after(delay, self._tick)

    def _update(self, now):
        """One timer tick. Returns the ms until the next: often while the ring follows the cursor
        or a widget is being used, less often while widgets just sit there, rarely otherwise."""
        tracker = self.app.tracker
        running = tracker is not None and self.app._has_frame
        if tracker is not self._tracker:          # a new run: start counting its gestures afresh
            self._tracker = tracker
            self._toggles = tracker.widget_toggles if tracker is not None else 0
            self._event = 0
        if tracker is not None and tracker.widget_toggles != self._toggles:
            if (tracker.widget_toggles - self._toggles) % 2:
                self.toggle()
            self._toggles = tracker.widget_toggles

        always = tuning.get(self.settings, "widgets_always")
        show = (running or always) and self.settings.widgets_on
        first = 1   # widgets drawn for the first time this tick: tens of ms each, so one per tick
        for widget, window in self.items:
            if show and widget.spec["on"]:
                widget.tick(now)
                if widget.dirty or not window.visible:
                    if widget._base is None:
                        if not first:
                            continue
                        first -= 1
                    widget.dirty = False
                    window.show(widget.render(now).bgra(), widget.spec["x"] - widget.m, widget.spec["y"] - widget.m)
            else:
                window.hide()

        ring = self._update_ring(now, tracker, running)
        self._run_requests()
        if self._save:
            self._save = False
            self.app._schedule_save()
        in_use = any(w.pressed is not None or w._drag is not None for w, _window in self.items)
        if ring or in_use:
            return 16
        return 33 if show else 100

    def _update_ring(self, now, tracker, running):
        visible = running and self.settings.cursor_ring and tracker.mode not in (NO_HAND, NO_FACE)
        if not visible:
            if self._ring_window is not None:
                self._ring_window.hide()
            return False
        if self._ring_window is None:
            self._ring_window = LayeredWindow(click_through=True)
        for number, _t, action in list(tracker.events):
            if number > self._event:
                self._event = number
                self.ring.event(action, now)
        state = self.ring.state(tracker.mode, tracker.progress, now)
        cx, cy = cursor_pos()
        x, y = cx - self.ring.size // 2, cy - self.ring.size // 2
        window = self._ring_window
        if state != self._ring_state or not window.visible:
            self._ring_state = state
            window.show(self.ring.render(state).bgra(), x, y)
        elif (x, y) != (window.x, window.y):
            window.move(x, y)
        return True

    def _run_requests(self):
        requests, self._requests = self._requests, []
        for item in requests:
            if item[0] == "action":
                _kind, action, widget = item
                widget.show_error(system.run_action(action))
            elif item[0] == "keys":
                system.press_keys(item[1])
            elif item[0] == "editor":
                self.app.open_widget_editor()
