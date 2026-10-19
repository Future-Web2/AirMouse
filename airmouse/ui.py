"""Main window in the Liquid Glass style.

The whole window is one image redrawn ~30 times a second: the live camera
(or a flowing colour backdrop while the camera is off) with glass panels and
widgets floating over it. See glass.py for the rendering, widgets.py for controls.
"""

import ctypes
import math
import time
import tkinter as tk

import cv2
import numpy as np

from . import tuning
from .app_base import CALIBRATE_TEXT, GESTURES, METERS, MODES, BaseApp, meter_value
from .blit import Blitter
from .glass import ICON_CAMERA, LiquidBackdrop, blit_text, capsule, shape
from .widgets import MUTED, TEXT, Button, Segmented, Slider, Stepper, Toggle, set_theme, style

W, H = 1120, 840                         # logical size of the window
SIDEBAR = (W - 16 - 376, 16, 376, H - 32)
STATUS = (16, 16, 310, 50)
WIDGETS_BUTTON = (338, 16, 150, 50)
ADVANCED_BUTTON = (500, 16, 160, 50)
SESSION = (16, 80, 310, 118)
CARD_W = 480
IDLE_FPS = 12     # window redraws per second while another window is active (in front: «Частота окна»)

# Two looks of the same window: clear liquid glass over violet light, and «Природа»,
# fogged glass with drops of condensation over a deep green, sunlit backdrop.
THEMES = {
    "glass": {"accent": (64, 140, 255), "track": (78, 84, 98), "styles": {}, "backdrop": {},
              "caption": 0x00160E0C},
    "nature": {"accent": (88, 200, 122), "track": (70, 92, 78),
               "styles": {kind: "fog_" + kind for kind in ("panel", "button", "accent", "danger", "pill", "knob")},
               "backdrop": {"colors": ((0.10, 0.42, 0.22), (0.36, 0.55, 0.16), (0.05, 0.46, 0.40),
                                       (0.55, 0.78, 0.30), (0.90, 0.78, 0.36)),
                            "base": (0.02, 0.05, 0.035), "glints": 1.0},
               "caption": 0x00182214,
               # the on-screen widgets cannot blur what is behind them: milky green with condensation
               "widgets": {"color": (34, 50, 40), "opacity": 0.84, "droplets": 0.9}},
}


def _style_title_bar(window, color=0x00160E0C):
    """Dark title bar in the colour of the window (color: 0x00BBGGRR)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dwm = ctypes.windll.dwmapi
        for attribute, value in ((20, 1), (35, color), (34, color)):  # dark mode, caption, border
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))
    except (AttributeError, OSError):
        pass


def _pct(v):
    return f"{v * 100:.0f}%"


class App(BaseApp):
    def __init__(self, autostart=False, scale=None):
        """scale: display scale; normally taken from Windows (the promo video passes its own)."""
        super().__init__(autostart)
        self.theme = THEMES["nature" if self.settings.design == "nature" else "glass"]
        set_theme(self.theme)
        self._camera_bg = None
        self._captured = None
        # Display scale (100%, 125%, 150%, ...), rounded so odd DPI values do not blur the image.
        self.s = s = scale or max(round(self.root.winfo_fpixels("1i") / 96.0 * 4) / 4, 1.0)
        self.size = (round(W * s), round(H * s))
        # The window image is drawn straight into this frame (see blit.py);
        # with no background Tk never paints over it.
        self.view = tk.Frame(self.root, width=self.size[0], height=self.size[1], background="",
                             highlightthickness=0, bd=0)
        self.view.pack()
        self.view.bind("<Motion>", self._on_motion)
        self.view.bind("<Leave>", lambda _e: self._set_hover(None))
        self.view.bind("<ButtonPress-1>", self._on_press)
        self.view.bind("<B1-Motion>", self._on_drag)
        self.view.bind("<ButtonRelease-1>", self._on_release)
        self.view.bind("<Expose>", lambda _e: self.blitter.repaint())
        self._image = np.zeros((self.size[1], self.size[0], 3), np.uint8)   # the window, redrawn every frame
        self._cover_image = np.zeros_like(self._image)                     # the camera, scaled to the window

        self.backdrop = LiquidBackdrop(*self.size, **self.theme["backdrop"])
        self._build()
        self._apply_mode()
        self.root.update_idletasks()
        self.blitter = Blitter(self.view.winfo_id(), *self.size)
        _style_title_bar(self.root, self.theme["caption"])
        self._t0 = self._last = time.perf_counter()
        self.after(1, self._tick)
        self._ready()

    # -- layout -----------------------------------------------------------

    def _build(self):
        st = self.settings
        x0 = SIDEBAR[0] + 24
        cw = SIDEBAR[2] - 48

        def setter(attr):
            def apply(value):
                # The tracker thread reads the same Settings object, so changes apply live.
                setattr(st, attr, value)
                self._schedule_save()
            return apply

        self.segmented = Segmented(x0, 120, cw, 44, MODES, st.mode, self._on_mode)
        self.start_btn = Button(x0, 180, cw, 52, "Старт", self._toggle_start, style="accent", size=17)
        self.control_toggle = Toggle(x0 + cw - 52, 254, True, self._set_control)
        self.camera_stepper = Stepper(x0 + cw - 104, 344, st.camera_index, 0, 4, self._on_camera)
        self.sliders = [
            Slider(x0, 388, cw, "Стабилизация", 0.0, 1.0, st.smoothing, _pct, setter("smoothing")),
            Slider(x0, 442, cw, "Скорость курсора", 0.0, 1.0, st.cursor_speed, _pct, setter("cursor_speed")),
            None,  # mode dependent, see _apply_mode
            Slider(x0, 550, cw, "Скорость прокрутки", 0.5, 6.0, st.scroll_speed, lambda v: f"{v:.1f}×",
                   setter("scroll_speed")),
        ]
        self.pinch_slider = Slider(x0, 496, cw, "Чувствительность клика", 0.15, 0.45, st.pinch_threshold,
                                   lambda v: _pct((v - 0.15) / 0.30), setter("pinch_threshold"))
        self.blink_slider = Slider(x0, 496, cw, "Моргание для клика", 0.25, 0.8, st.blink_time,
                                   lambda v: f"{v:.2f} с", setter("blink_time"))
        self.invert_toggle = Toggle(x0 + cw - 52, 616, st.invert_scroll, setter("invert_scroll"))
        self.top_toggle = Toggle(x0 + cw - 52, 656, st.always_on_top, self._set_always_on_top)
        # Switching design reopens the window; let the pill slide first.
        self.design = Segmented(x0 + cw - 264, 693, 264, 36,
                                (("glass", "Стекло"), ("nature", "Природа"), ("classic", "Классика")),
                                st.design, lambda d: self.after(250, self._switch_design, d))
        self.calibrate_btn = Button(x0, 746, cw, 44, "", self._calibrate, size=15)
        self.widgets_btn = Button(*WIDGETS_BUTTON, "Виджеты", self.open_widget_editor, size=15)
        self.advanced_btn = Button(*ADVANCED_BUTTON, "Подробнее", self.open_advanced, size=15)

    def _widgets(self):
        return [self.segmented, self.start_btn, self.control_toggle, self.camera_stepper, *self.sliders,
                self.invert_toggle, self.top_toggle, self.design, self.calibrate_btn, self.widgets_btn,
                self.advanced_btn]

    def scale(self):
        return self.s

    # -- hooks ------------------------------------------------------------

    def _apply_mode(self):
        mode = self.settings.mode
        self.sliders[2] = self.pinch_slider if mode == "hand" else self.blink_slider
        self.calibrate_btn.label = CALIBRATE_TEXT[mode]

    def _show_running(self, running):
        self.start_btn.label, self.start_btn.style = ("Стоп", "danger") if running else ("Старт", "accent")
        if not running:
            self._camera_bg = None

    def _show_control(self, on):
        self.control_toggle.set(on)

    def _set_calibrate_button(self, label, enabled):
        self.calibrate_btn.label, self.calibrate_btn.enabled = label, enabled

    def _on_frame(self, frame):
        self._camera_bg = self._cover(frame)

    # -- drawing ----------------------------------------------------------

    def render(self, now, dt):
        """Draw the whole window into a new RGB image."""
        s = self.s
        for widget in self._widgets():
            widget.tick(dt)
        frame = self._image
        if self._camera_bg is not None:
            np.copyto(frame, self._camera_bg)
        else:
            self.backdrop.render(now - self._t0, out=frame)

        self._panel(frame, SIDEBAR, 32)
        self._draw_status(frame)
        if self.tracker is not None and self.session.started is not None:
            self._draw_session(frame, now)
        gestures = GESTURES[self.settings.mode]
        card_h = 52 + 24 * len(gestures)
        card_y = H - 16 - card_h
        self._draw_gestures(frame, gestures, card_y, card_h)
        if self.settings.mode != "hand":
            self._draw_meters(frame, card_y - 12 - 92)
        if self._camera_bg is None:
            self._draw_placeholder(frame)
        self._draw_sidebar(frame)
        for widget in self._widgets():
            widget.draw(frame, s)
        return frame

    def _panel(self, frame, rect, radius):
        x, y, w, h = rect
        s = self.s
        shape(round(w * s), round(h * s), round(radius * s), style("panel")).draw(frame, x * s, y * s)

    def _text(self, frame, text, x, y, size, color=TEXT, weight="regular", anchor="lm"):
        blit_text(frame, text, x * self.s, y * self.s, weight, size * self.s, color, anchor)

    def _draw_sidebar(self, frame):
        x0, _, sw, _ = SIDEBAR
        x0 += 24
        right = SIDEBAR[0] + sw - 24
        self._text(frame, "AirMouse", x0, 58, 32, weight="bold")
        self._text(frame, "Мышь, которой управляете вы", x0, 94, 14, MUTED)
        self._text(frame, "Управлять мышью", x0, 262, 15)
        self._text(frame, "Ctrl+Alt+M — пауза", x0, 283, 12, MUTED)
        capsule(frame, x0 * self.s, 314 * self.s, (right - x0) * self.s, 1 * self.s, (255, 255, 255), alpha=0.14)
        self._text(frame, "НАСТРОЙКИ", x0, 334, 11, MUTED, "semibold")
        self._text(frame, "Камера", x0, 360, 14)
        self._text(frame, "Обратная прокрутка", x0, 631, 14)
        self._text(frame, "Поверх всех окон", x0, 671, 14)
        self._text(frame, "Дизайн", x0, 711, 14)
        self._text(frame, self.calibration_info(), x0, 806, 12, MUTED)

    def _draw_status(self, frame):
        text, color, fps = self._status()
        x, y, w, h = STATUS
        self._panel(frame, STATUS, 25)
        cy = y + h / 2
        capsule(frame, (x + 20) * self.s, (cy - 6) * self.s, 12 * self.s, 12 * self.s, color)
        self._text(frame, text, x + 42, cy, 16, weight="semibold")
        self._text(frame, fps, x + w - 20, cy, 13, MUTED, anchor="rm")

    def _draw_session(self, frame, now):
        """This run: how long, frame rate over the last minute, processor use, clicks and scrolling."""
        s = self.s
        x, y, w, h = SESSION
        self._panel(frame, SESSION, 26)
        duration, fps, cpu, actions = self.session.summary(self.tracker, now)
        self._text(frame, "СЕАНС", x + 22, y + 24, 11, MUTED, "semibold")
        self._text(frame, duration, x + w - 22, y + 24, 12, MUTED, anchor="rm")
        values = list(self.session.fps)
        if len(values) > 1:
            top = max(30.0, max(values))
            x0, x1, y0, y1 = x + 22, x + 186, y + 42, y + 74
            step = (x1 - x0) / (self.session.fps.maxlen - 1)
            start = x1 - step * (len(values) - 1)
            line = np.array([[(start + i * step) * s * 16, (y1 - (y1 - y0) * v / top) * s * 16]
                             for i, v in enumerate(values)], np.int32)
            cv2.polylines(frame, [line], False, self.theme["accent"], max(1, round(2 * s)), cv2.LINE_AA, 4)
        self._text(frame, fps, x + w - 22, y + 50, 14, weight="semibold", anchor="rm")
        self._text(frame, cpu, x + w - 22, y + 70, 12, MUTED, anchor="rm")
        self._text(frame, actions, x + 22, y + 98, 12, MUTED)

    def _draw_gestures(self, frame, gestures, y, h):
        self._panel(frame, (16, y, CARD_W, h), 26)
        self._text(frame, "ЖЕСТЫ", 40, y + 26, 11, MUTED, "semibold")
        for i, (gesture, action) in enumerate(gestures):
            ry = y + 54 + 24 * i
            self._text(frame, gesture, 40, ry, 13, weight="semibold")
            self._text(frame, action, 252, ry, 13, MUTED)

    def _draw_meters(self, frame, y):
        s = self.s
        self._panel(frame, (16, y, CARD_W, 92), 26)
        self._text(frame, "ЛИЦО", 40, y + 26, 11, MUTED, "semibold")
        face = self.face()
        for i, (label, key) in enumerate(METERS):
            col, row = i % 2, i // 2
            lx, ly = 40 + col * 224, y + 52 + row * 24
            self._text(frame, label, lx, ly, 13)
            value = meter_value(face, key) if face is not None else 0.0
            bx = lx + 98
            capsule(frame, bx * s, (ly - 3) * s, 100 * s, 6 * s, (255, 255, 255), alpha=0.16)
            if value > 0.02:
                capsule(frame, bx * s, (ly - 3) * s, max(6, 100 * value) * s, 6 * s, self.theme["accent"])

    def _draw_placeholder(self, frame):
        cx, cy = SIDEBAR[0] / 2, H / 2 - 30
        w, h = 360, 156
        self._panel(frame, (cx - w / 2, cy - h / 2, w, h), 32)
        starting = self.tracker is not None
        self._text(frame, ICON_CAMERA, cx, cy - 32, 30, weight="icons", anchor="mm")
        title = "Включаю камеру…" if starting else "Камера выключена"
        hint = "Это займёт пару секунд" if starting else "Нажмите «Старт»"
        self._text(frame, title, cx, cy + 14, 21, weight="semibold", anchor="mm")
        self._text(frame, hint, cx, cy + 44, 14, MUTED, anchor="mm")

    # -- input ------------------------------------------------------------

    def _widget_at(self, x, y):
        for widget in self._widgets():
            if widget.hit(x, y):
                return widget
        return None

    def _set_hover(self, widget):
        for w in self._widgets():
            w.hover = w is widget
        self.view.configure(cursor="hand2" if widget is not None and widget.enabled else "")

    def _on_motion(self, event):
        if self._captured is None:
            self._set_hover(self._widget_at(event.x / self.s, event.y / self.s))

    def _on_press(self, event):
        x, y = event.x / self.s, event.y / self.s
        widget = self._widget_at(x, y)
        if widget is not None and widget.enabled:
            self._captured = widget
            widget.press(x, y)

    def _on_drag(self, event):
        if self._captured is not None:
            self._captured.drag(event.x / self.s, event.y / self.s)

    def _on_release(self, event):
        if self._captured is not None:
            widget, self._captured = self._captured, None
            widget.release(event.x / self.s, event.y / self.s)

    # -- main loop --------------------------------------------------------

    def _tick(self):
        start = time.perf_counter()
        dt = min(start - self._last, 0.1)
        self._last = start
        self._poll()
        if self.next_design is not None:
            return  # the window is closing for a design switch
        if self.root.state() != "iconic":
            self.blitter.show(self.render(start, dt))
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        in_front = ctypes.windll.user32.GetForegroundWindow() == hwnd
        spent = time.perf_counter() - start
        fps = tuning.get(self.settings, "window_fps") if in_front else IDLE_FPS
        self.after(max(1, int((1 / fps - spent) * 1000)), self._tick)

    def _cover(self, frame):
        """Scale the camera image to fill the window, cropping the overflow, slightly dimmed."""
        fh, fw = frame.shape[:2]
        tw, th = self.size
        k = max(tw / fw, th / fh)
        rw, rh = math.ceil(fw * k), math.ceil(fh * k)
        dim = cv2.convertScaleAbs(frame, alpha=0.9)   # on the small image: same result, a fraction of the work
        if (rw, rh) == (tw, th):   # the usual case: a 4:3 camera fills the 4:3 window exactly
            return cv2.resize(dim, (tw, th), dst=self._cover_image, interpolation=cv2.INTER_LINEAR)
        big = cv2.resize(dim, (rw, rh), interpolation=cv2.INTER_LINEAR)
        x, y = (rw - tw) // 2, (rh - th) // 2
        np.copyto(self._cover_image, big[y:y + th, x:x + tw])
        return self._cover_image
