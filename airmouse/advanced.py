"""The «Подробнее» window: every number of tuning.py, by group, with a hint for each."""

import tkinter as tk
from tkinter import ttk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from . import tuning

MUTED = "#8a8a8a"
ACCENT_BUTTON = "Accent.TButton" if sv_ttk is not None else "TButton"


def format_value(param, value):
    if param.choices:
        return dict(param.choices).get(value, str(value))
    if param.unit == "×":
        return f"{value:.2f}×"
    if param.step >= 1:
        return f"{value:.0f} {param.unit}".strip()
    return f"{value:.2f} {param.unit}".strip()


def snap(param, value):
    """value on the slider's grid of steps."""
    steps = round((value - param.lo) / param.step)
    return round(min(max(param.lo + steps * param.step, param.lo), param.hi), 6)


class AdvancedSettings:
    def __init__(self, app):
        self.app, self.settings = app, app.settings
        root = app.root
        if sv_ttk is not None and not ttk.Style(root).theme_use().startswith("sun-valley"):
            sv_ttk.set_theme("dark")
        self.win = win = tk.Toplevel(root)
        win.title("Подробные настройки — AirMouse")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)
        outer = ttk.Frame(win, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, foreground=MUTED, justify="left", text=(
            "Всё применяется сразу. Настройки камеры перезапускают её сами.\n"
            "«По умолчанию» возвращает значения, с которыми AirMouse работает из коробки.")).pack(anchor="w")
        tabs = ttk.Notebook(outer)
        tabs.pack(fill="both", expand=True, pady=(12, 0))
        self.rows = {}
        for group in tuning.GROUPS:
            page = ttk.Frame(tabs, padding=(14, 10))
            tabs.add(page, text=group)
            for param in (p for p in tuning.PARAMS if p.group == group):
                self.rows[param.key] = self._row(page, param)
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(14, 0))
        ttk.Button(row, text="По умолчанию", command=self._reset).pack(side="left")
        ttk.Button(row, text="Готово", style=ACCENT_BUTTON, command=self.close).pack(side="right")
        win.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.focus_force()

    def alive(self):
        return bool(self.win.winfo_exists())

    def focus(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        self.win.destroy()

    # -- one parameter -------------------------------------------------------------

    def _row(self, parent, param):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 12))
        head = ttk.Frame(frame)
        head.pack(fill="x")
        ttk.Label(head, text=param.label).pack(side="left")
        value_label = ttk.Label(head, foreground=MUTED)
        value_label.pack(side="right")
        value = tuning.get(self.settings, param.key)
        if param.choices:
            names = [name for _v, name in param.choices]
            var = tk.StringVar(value=format_value(param, value))
            control = ttk.Combobox(frame, textvariable=var, values=names, state="readonly", width=44)
            control.bind("<<ComboboxSelected>>", lambda _e: self._chosen(param, var.get()))
            value_label.configure(text="")
        else:
            var = tk.DoubleVar(value=value)
            control = ttk.Scale(frame, from_=param.lo, to=param.hi, variable=var, length=440,
                                command=lambda _v: self._slid(param, var, value_label))
            control.bind("<ButtonRelease-1>", lambda _e: self._applied(param))
            value_label.configure(text=format_value(param, value))
        control.pack(fill="x", pady=(4, 0))
        if param.hint:
            ttk.Label(frame, text=param.hint, foreground=MUTED, wraplength=440, justify="left").pack(
                anchor="w", pady=(2, 0))
        return var, value_label

    def _slid(self, param, var, label):
        value = snap(param, var.get())
        label.configure(text=format_value(param, value))
        tuning.set_value(self.settings, param.key, value)
        self.app._schedule_save()

    def _chosen(self, param, name):
        value = next(v for v, label in param.choices if label == name)
        tuning.set_value(self.settings, param.key, value)
        self.app._schedule_save()
        self._applied(param)

    def _applied(self, param):
        """After a change that needs more than reading the new value: restart the camera, resize widgets."""
        if param.restart:
            self.app.restart_tracker()
        elif param.key == "widget_scale":
            self.app.onscreen.set_scale(self.app.scale() * tuning.get(self.settings, "widget_scale"))

    def _reset(self):
        restart = any(tuning.BY_KEY[key].restart for key in tuning.changed(self.settings))
        rescale = "widget_scale" in tuning.changed(self.settings)
        self.settings.advanced.clear()
        self.app._schedule_save()
        for key, (var, label) in self.rows.items():
            param = tuning.BY_KEY[key]
            if param.choices:
                var.set(format_value(param, param.default))
            else:
                var.set(param.default)
                label.configure(text=format_value(param, param.default))
        if restart:
            self.app.restart_tracker()
        if rescale:
            self.app.onscreen.set_scale(self.app.scale())
