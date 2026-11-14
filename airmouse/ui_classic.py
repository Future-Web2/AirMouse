"""Classic main window: standard Tkinter widgets with the Sun Valley theme (Windows 11 look)."""

import ctypes
import time
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from . import system, tuning
from .app_base import CALIBRATE_TEXT, DESIGNS, METERS, MODES, BaseApp, gesture_rows, meter_value, translated
from .i18n import LANGUAGE_LABEL, LANGUAGES, _

PREVIEW_W, PREVIEW_H = 480, 360
PREVIEW_BG = "#1b1b1b"
MUTED = "#8a8a8a"


def _dark_title_bar(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


class App(BaseApp):
    def __init__(self, autostart=False):
        super().__init__(autostart)
        dark = system.dark_theme()
        if sv_ttk is not None:
            sv_ttk.set_theme("dark" if dark else "light")
        self._build()
        self._apply_mode()
        self.root.update_idletasks()
        if dark:
            _dark_title_bar(self.root)
        self.after(33, self._tick)
        self._ready()

    # -- layout -----------------------------------------------------------

    def _build(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        # Left: camera preview, status, face meters and gesture help
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="n")
        self.canvas = tk.Canvas(left, width=PREVIEW_W, height=PREVIEW_H, bg=PREVIEW_BG, highlightthickness=0)
        self.canvas.pack()
        self.photo = ImageTk.PhotoImage(Image.new("RGB", (PREVIEW_W, PREVIEW_H), PREVIEW_BG))
        self.canvas_image = self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas_text = self.canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2, fill="#a0a0a0", font=("Segoe UI", 12), justify="center")
        self._show_placeholder(_("Камера выключена\nНажмите «Старт»"))

        status = ttk.Frame(left)
        status.pack(fill="x", pady=(10, 0))
        self.mode_var = tk.StringVar(value=_("Остановлено"))
        ttk.Label(status, textvariable=self.mode_var, font=("Segoe UI", 13, "bold")).pack(side="left")
        self.fps_var = tk.StringVar()
        ttk.Label(status, textvariable=self.fps_var, foreground=MUTED).pack(side="right")

        # This run: frame rate over the last minute (a line), processor use, what was done.
        self.session_slot = ttk.Frame(left)
        self.session_slot.pack(fill="x")
        self.session_box = ttk.LabelFrame(self.session_slot, text=_("Сеанс"), padding=(12, 6))
        self.session_chart = tk.Canvas(self.session_box, width=PREVIEW_W - 26, height=30, highlightthickness=0,
                                       bg=PREVIEW_BG)
        self.session_chart.pack(fill="x")
        self.session_line = self.session_chart.create_line(0, 0, 0, 0, fill="#408cff", width=2, smooth=True)
        self.session_top = tk.StringVar()
        self.session_bottom = tk.StringVar()
        ttk.Label(self.session_box, textvariable=self.session_top).pack(anchor="w", pady=(6, 0))
        ttk.Label(self.session_box, textvariable=self.session_bottom, foreground=MUTED).pack(anchor="w")

        self.meter_slot = ttk.Frame(left)
        self.meter_slot.pack(fill="x")
        self.face_box = ttk.LabelFrame(self.meter_slot, text=_("Лицо"), padding=(12, 6))
        self.meters = {}
        for i, (title, key) in enumerate(METERS):
            row, col = divmod(i, 2)
            ttk.Label(self.face_box, text=_(title)).grid(row=row, column=col * 2, sticky="w", pady=2,
                                                         padx=(0 if col == 0 else 16, 8))
            bar = ttk.Progressbar(self.face_box, maximum=1.0, length=120)
            bar.grid(row=row, column=col * 2 + 1, sticky="w")
            self.meters[key] = bar

        self.gestures_box = ttk.LabelFrame(left, text=_("Жесты"), padding=(12, 6))
        self.gestures_box.pack(fill="x", pady=(12, 0))

        # Right: mode, controls and settings
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="n", padx=(24, 0))
        ttk.Label(right, text="AirMouse", font=("Segoe UI Variable Display", 24, "bold")).pack(anchor="w")
        ttk.Label(right, text=_("Мышь, которой управляете вы"), foreground=MUTED).pack(anchor="w", pady=(0, 12))

        modes = ttk.Frame(right)
        modes.pack(fill="x", pady=(0, 12))
        self.mode_choice = tk.StringVar(value=self.settings.mode)
        for i, (key, title) in enumerate(translated(MODES)):
            modes.columnconfigure(i, weight=1, uniform="mode")
            ttk.Radiobutton(modes, text=title, value=key, variable=self.mode_choice, style="Toggle.TButton",
                            command=lambda: self._on_mode(self.mode_choice.get())).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))

        self.start_btn = ttk.Button(right, text=_("Старт"), style="Accent.TButton", command=self._toggle_start)
        self.start_btn.pack(fill="x", ipady=4)

        self.control_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(right, text=_("Управлять мышью   Ctrl+Alt+M"), variable=self.control_var,
                        style="Switch.TCheckbutton",
                        command=lambda: self._set_control(self.control_var.get())).pack(anchor="w", pady=(12, 0))

        box = ttk.LabelFrame(right, text=_("Настройки"), padding=(12, 8))
        box.pack(fill="x", pady=(16, 0))

        camera_row = ttk.Frame(box)
        camera_row.pack(fill="x")
        ttk.Label(camera_row, text=_("Камера")).pack(side="left")
        self.camera_var = tk.StringVar(value=str(self.settings.camera_index))
        camera = ttk.Combobox(camera_row, textvariable=self.camera_var, values=[str(i) for i in range(5)],
                              width=4, state="readonly")
        camera.pack(side="right")
        camera.bind("<<ComboboxSelected>>", lambda _e: self._on_camera(int(self.camera_var.get())))

        self._slider(box, _("Стабилизация"), "smoothing", 0.0, 1.0, lambda v: f"{v * 100:.0f}%")
        self._slider(box, _("Скорость курсора"), "cursor_speed", 0.0, 1.0, lambda v: f"{v * 100:.0f}%")
        click_slot = ttk.Frame(box)
        click_slot.pack(fill="x")
        self.pinch_row = self._slider(click_slot, _("Чувствительность клика"), "pinch_threshold", 0.15, 0.45,
                                      lambda v: f"{(v - 0.15) / 0.30 * 100:.0f}%")
        self.blink_row = self._slider(click_slot, _("Моргание для клика"), "blink_time", 0.25, 0.8,
                                      lambda v: _("{:.2f} с").format(v))
        self._slider(box, _("Скорость прокрутки"), "scroll_speed", 0.5, 6.0, lambda v: f"{v:.1f}×")
        self._check(box, _("Обратная прокрутка"), "invert_scroll")
        self._check(box, _("Поверх всех окон"), "always_on_top", self._set_always_on_top)
        self.widgets_var = self._check(box, _("Виджеты на экране (палец вверх, Ctrl+Alt+W)"), "widgets_on")
        self._check(box, _("Кольцо у курсора"), "cursor_ring")
        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(10, 0))
        buttons.columnconfigure((0, 1, 2), weight=1, uniform="more")
        ttk.Button(buttons, text=_("Виджеты…"), command=self.open_widget_editor).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(buttons, text=_("Блокнот"), command=self.toggle_notebook).grid(row=0, column=1, sticky="ew",
                                                                               padx=(0, 4))
        ttk.Button(buttons, text=_("Подробнее…"), command=self.open_advanced).grid(row=0, column=2, sticky="ew")

        designs = translated(DESIGNS)
        self.design_var = self._choice(box, _("Дизайн"), designs, self.settings.design, 26,
                                       lambda key: self._switch_design(key))
        self._choice(box, LANGUAGE_LABEL, LANGUAGES, self.settings.language, 12,
                     lambda key: self._switch_language(key))

        self.calibrate_btn = ttk.Button(box, command=self._calibrate)
        self.calibrate_btn.pack(fill="x", pady=(12, 2))
        self.calib_info = tk.StringVar()
        ttk.Label(box, textvariable=self.calib_info, foreground=MUTED).pack(anchor="w")

    def _slider(self, parent, title, attr, lo, hi, fmt):
        var = tk.DoubleVar(value=getattr(self.settings, attr))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        head = ttk.Frame(row)
        head.pack(fill="x", pady=(10, 0))
        ttk.Label(head, text=title).pack(side="left")
        value = ttk.Label(head, text=fmt(var.get()), foreground=MUTED)
        value.pack(side="right")

        def changed(_=None):
            # The tracker thread reads the same Settings object, so changes apply live.
            setattr(self.settings, attr, var.get())
            value.configure(text=fmt(var.get()))
            self._schedule_save()

        ttk.Scale(row, from_=lo, to=hi, variable=var, command=changed).pack(fill="x")
        return row

    def _choice(self, parent, title, options, value, width, on_choose):
        """A row with a drop-down list of ((key, name), ...); on_choose(key) when another is picked."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=title).pack(side="left")
        names = dict(options)
        var = tk.StringVar(value=names[value])
        box = ttk.Combobox(row, textvariable=var, values=list(names.values()), width=width, state="readonly")
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: on_choose(next(k for k, v in options if v == var.get())))
        return var

    def _check(self, parent, title, attr, on_change=None):
        var = tk.BooleanVar(value=getattr(self.settings, attr))

        def changed():
            if on_change is not None:
                on_change(var.get())
            else:
                setattr(self.settings, attr, var.get())
                self._schedule_save()

        ttk.Checkbutton(parent, text=title, variable=var, command=changed).pack(anchor="w", pady=(8, 0))
        return var

    def _show_placeholder(self, text):
        self.canvas.itemconfigure(self.canvas_image, state="hidden")
        self.canvas.itemconfigure(self.canvas_text, text=text, state="normal")

    # -- hooks ------------------------------------------------------------

    def _apply_mode(self):
        mode = self.settings.mode
        for child in self.gestures_box.winfo_children():
            child.destroy()
        for row, (gesture, action) in enumerate(gesture_rows(mode, self.settings)):
            ttk.Label(self.gestures_box, text=gesture, font=("Segoe UI", 10, "bold")).grid(
                row=row, column=0, sticky="w", pady=1)
            ttk.Label(self.gestures_box, text=action).grid(row=row, column=1, sticky="w", padx=(14, 0), pady=1)
        if mode != "hand":
            self.face_box.pack(fill="x", pady=(12, 0))
            self.pinch_row.pack_forget()
            self.blink_row.pack(fill="x")
        else:
            self.face_box.pack_forget()
            self.blink_row.pack_forget()
            self.pinch_row.pack(fill="x")
        self.calibrate_btn.configure(text=_(CALIBRATE_TEXT[mode]))
        self.calib_info.set(self.calibration_info())

    def _show_running(self, running):
        self.start_btn.configure(text=_("Стоп") if running else _("Старт"),
                                 style="TButton" if running else "Accent.TButton")
        self._show_placeholder(_("Включаю камеру…") if running else _("Камера выключена\nНажмите «Старт»"))
        if not running:
            self.mode_var.set(_("Остановлено"))
            self.fps_var.set("")
            for bar in self.meters.values():
                bar.configure(value=0)
            self.session_box.pack_forget()

    def _show_control(self, on):
        self.control_var.set(on)

    def _set_calibrate_button(self, label, enabled):
        self.calibrate_btn.configure(text=label, state="normal" if enabled else "disabled")

    def _on_frame(self, frame):
        fh, fw = frame.shape[:2]
        if fw * PREVIEW_H > fh * PREVIEW_W:      # a wide camera picture: show its middle
            keep = fh * PREVIEW_W // PREVIEW_H
            frame = frame[:, (fw - keep) // 2:(fw - keep) // 2 + keep]
        small = cv2.resize(frame, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_AREA)
        self.photo.paste(Image.fromarray(small))
        self.canvas.itemconfigure(self.canvas_image, state="normal")
        self.canvas.itemconfigure(self.canvas_text, state="hidden")

    # -- main loop --------------------------------------------------------

    def _tick(self):
        self._poll()
        if self.next_design is not None:
            return  # the window is closing for a design switch
        if self.tracker is not None:
            text, _color, fps = self._status()
            self.mode_var.set(text)
            self.fps_var.set(fps)
            face = self.face()
            for key, bar in self.meters.items():
                bar.configure(value=meter_value(face, key) if face is not None else 0.0)
            self._show_session()
        if self.widgets_var.get() != self.settings.widgets_on:   # the thumbs up / Ctrl+Alt+W toggle it too
            self.widgets_var.set(self.settings.widgets_on)
        self.after(int(1000 / tuning.get(self.settings, "window_fps")), self._tick)

    def _show_session(self):
        if self.session.started is None:
            return
        if not self.session_box.winfo_ismapped():
            self.session_box.pack(fill="x", pady=(12, 0))
        duration, fps, cpu, actions = self.session.summary(self.tracker, time.perf_counter())
        self.session_top.set(f"{duration}   ·   {fps}   ·   {cpu}")
        self.session_bottom.set(actions)
        values = list(self.session.fps)
        w, h = int(self.session_chart["width"]), int(self.session_chart["height"])
        if len(values) > 1:
            top = max(30.0, max(values))
            step = (w - 4) / (self.session.fps.maxlen - 1)
            start = w - 2 - step * (len(values) - 1)
            coords = []
            for i, v in enumerate(values):
                coords += [start + i * step, h - 3 - (h - 6) * v / top]
            self.session_chart.coords(self.session_line, *coords)
