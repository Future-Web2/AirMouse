"""The window for choosing on-screen widgets and making your own panels of buttons."""

import tkinter as tk
from tkinter import messagebox, ttk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from . import system
from .onscreen import MAX_BUTTONS, NAMES, button_spec

MUTED = "#8a8a8a"
ERROR = "#ff6470"
ACCENT_BUTTON = "Accent.TButton" if sv_ttk is not None else "TButton"
ACTIONS = (("keys", "Нажать клавиши"), ("open", "Открыть программу, файл или сайт"))
VALUE_LABELS = {"keys": "Клавиши", "open": "Что открыть"}
HINTS = {
    "keys": "Например: ctrl+c, win+d, alt+tab, ctrl+shift+esc, f5, playpause, volumeup",
    "open": "Например: notepad, calc, osk, https://youtube.com или путь к файлу",
}


def _center(window, parent):
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class WidgetEditor:
    def __init__(self, app):
        self.app, self.settings, self.onscreen = app, app.settings, app.onscreen
        root = app.root
        if sv_ttk is not None and not ttk.Style(root).theme_use().startswith("sun-valley"):
            sv_ttk.set_theme("dark")   # the Liquid Glass window has no ttk theme of its own
        self.win = win = tk.Toplevel(root)
        win.title("Виджеты на экране — AirMouse")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)

        outer = ttk.Frame(win, padding=18)
        outer.pack(fill="both", expand=True)
        self.on_var = tk.BooleanVar(value=self.settings.widgets_on)
        self.ring_var = tk.BooleanVar(value=self.settings.cursor_ring)
        ttk.Checkbutton(outer, text="Показывать виджеты, пока AirMouse управляет мышью", variable=self.on_var,
                        command=self._switches).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(outer, foreground=MUTED, justify="left", text=(
            "Показать или скрыть: подержите большой палец вверх или нажмите Ctrl+Alt+W.\n"
            "Блокнот для рисования открывают Ctrl+Alt+N и карандаш на мини-панели AirMouse.\n"
            "Виджеты не забирают фокус: их кнопки нажимают клавиши в той программе, где вы работаете.\n"
            "Чтобы передвинуть виджет, потяните его за фон (щипок, подержать и вести).")).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        ttk.Checkbutton(outer, text="Кольцо у курсора: показывает щипок, клик и прокрутку", variable=self.ring_var,
                        command=self._switches).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))

        left = ttk.LabelFrame(outer, text="Виджеты", padding=10)
        left.grid(row=3, column=0, sticky="nsew")
        self.list = ttk.Treeview(left, columns=("name", "shown"), show="headings", height=9, selectmode="browse")
        self.list.heading("name", text="Виджет")
        self.list.heading("shown", text="На экране")
        self.list.column("name", width=250)
        self.list.column("shown", width=90, anchor="center")
        self.list.pack(fill="both", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda _e: self._show_panel())
        self.list.bind("<Double-1>", lambda _e: self._toggle_widget())
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Показать / скрыть", command=self._toggle_widget).pack(side="left")
        ttk.Button(row, text="Расставить заново", command=self._arrange).pack(side="right")
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Новая панель кнопок", command=self._add_panel).pack(side="left")
        self.remove_btn = ttk.Button(row, text="Удалить панель", command=self._remove_panel)
        self.remove_btn.pack(side="right")

        right = ttk.LabelFrame(outer, text="Панель кнопок", padding=10)
        right.grid(row=3, column=1, sticky="nsew", padx=(14, 0))
        self.title_var = tk.StringVar()
        ttk.Label(right, text="Название").pack(anchor="w")
        self.title_entry = ttk.Entry(right, textvariable=self.title_var, width=36)
        self.title_entry.pack(fill="x", pady=(2, 10))
        self.title_var.trace_add("write", lambda *_a: self._rename())
        self.buttons = ttk.Treeview(right, columns=("label", "action"), show="headings", height=7,
                                    selectmode="browse")
        self.buttons.heading("label", text="Кнопка")
        self.buttons.heading("action", text="Что делает")
        self.buttons.column("label", width=130)
        self.buttons.column("action", width=190)
        self.buttons.pack(fill="both", expand=True)
        self.buttons.bind("<Double-1>", lambda _e: self._edit_button())
        row = ttk.Frame(right)
        row.pack(fill="x", pady=(10, 0))
        self.panel_controls = [self.title_entry, self.buttons]
        for text, command in (("Добавить", self._add_button), ("Изменить", self._edit_button),
                              ("Удалить", self._remove_button), ("▲", lambda: self._move_button(-1)),
                              ("▼", lambda: self._move_button(1))):
            button = ttk.Button(row, text=text, command=command, width=3 if len(text) == 1 else None)
            button.pack(side="left", padx=(0, 6))
            self.panel_controls.append(button)
        self.panel_hint = ttk.Label(right, foreground=MUTED, text="Выберите слева панель кнопок.")
        self.panel_hint.pack(anchor="w", pady=(8, 0))

        ttk.Button(outer, text="Готово", style=ACCENT_BUTTON, command=self.close).grid(
            row=4, column=1, sticky="e", pady=(16, 0))
        self._fill_list()
        _center(win, root)
        win.focus_force()

    # -- window -----------------------------------------------------------------

    def alive(self):
        return bool(self.win.winfo_exists())

    def focus(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        self.win.destroy()

    def _changed(self, rebuild=False):
        if rebuild:
            self.onscreen.rebuild()
        else:
            self.onscreen.refresh()
        self.app._schedule_save()

    # -- the widget list --------------------------------------------------------

    @property
    def specs(self):
        return self.settings.widgets

    def _name(self, spec):
        if spec["type"] == "buttons":
            return f"{NAMES['buttons']}: {spec.get('title') or 'без названия'}"
        return NAMES[spec["type"]]

    def _fill_list(self, select=None):
        self.list.delete(*self.list.get_children())
        for i, spec in enumerate(self.specs):
            self.list.insert("", "end", iid=str(i), values=(self._name(spec), "да" if spec["on"] else "—"))
        if select is not None and 0 <= select < len(self.specs):
            self.list.selection_set(str(select))
            self.list.see(str(select))
        self._show_panel()

    def _selected(self):
        selection = self.list.selection()
        return int(selection[0]) if selection else None

    def _switches(self):
        self.settings.widgets_on = self.on_var.get()
        self.settings.cursor_ring = self.ring_var.get()
        self.app._schedule_save()

    def _toggle_widget(self):
        index = self._selected()
        if index is None:
            return
        self.specs[index]["on"] = not self.specs[index]["on"]
        self._fill_list(index)
        self._changed()

    def _arrange(self):
        self.onscreen.arrange()
        self._changed()

    def _add_panel(self):
        self.specs.append({"type": "buttons", "on": True, "title": "Мои кнопки", "buttons": []})
        self._changed(rebuild=True)
        self._fill_list(len(self.specs) - 1)
        self.title_entry.focus_set()
        self.title_entry.select_range(0, "end")

    def _remove_panel(self):
        index = self._selected()
        if index is None or self.specs[index]["type"] != "buttons":
            return
        if not messagebox.askyesno("AirMouse", f"Удалить «{self._name(self.specs[index])}»?", parent=self.win):
            return
        del self.specs[index]
        self._changed(rebuild=True)
        self._fill_list(min(index, len(self.specs) - 1))

    # -- the selected panel of buttons -----------------------------------------------

    def _panel(self):
        index = self._selected()
        if index is not None and self.specs[index]["type"] == "buttons":
            return self.specs[index]
        return None

    def _show_panel(self, select=None):
        panel = self._panel()
        state = "normal" if panel is not None else "disabled"
        for control in self.panel_controls:
            if isinstance(control, ttk.Treeview):
                continue
            control.configure(state=state)
        self.remove_btn.configure(state=state)
        self.buttons.delete(*self.buttons.get_children())
        self._loading = True
        self.title_var.set(panel.get("title", "") if panel else "")
        self._loading = False
        if panel is None:
            self.panel_hint.configure(text="Выберите слева панель кнопок или создайте новую.")
            return
        for i, button in enumerate(panel["buttons"]):
            what = button["value"] if button["do"] == "keys" else f"открыть {button['value']}"
            self.buttons.insert("", "end", iid=str(i), values=(button["label"], what))
        if select is not None and 0 <= select < len(panel["buttons"]):
            self.buttons.selection_set(str(select))
        left = MAX_BUTTONS - len(panel["buttons"])
        self.panel_hint.configure(text=f"Можно добавить ещё {left}." if left else "Кнопок уже максимум.")

    def _rename(self):
        panel = self._panel()
        if panel is None or getattr(self, "_loading", False):
            return
        panel["title"] = self.title_var.get()[:40]
        index = self._selected()
        self.list.item(str(index), values=(self._name(panel), "да" if panel["on"] else "—"))
        self._changed()

    def _selected_button(self):
        selection = self.buttons.selection()
        return int(selection[0]) if selection else None

    def _add_button(self):
        panel = self._panel()
        if panel is None or len(panel["buttons"]) >= MAX_BUTTONS:
            return

        def done(button):
            panel["buttons"].append(button)
            self._show_panel(len(panel["buttons"]) - 1)
            self._changed()
        ButtonDialog(self.win, None, done)

    def _edit_button(self):
        panel, index = self._panel(), self._selected_button()
        if panel is None or index is None:
            return

        def done(button):
            panel["buttons"][index] = button
            self._show_panel(index)
            self._changed()
        ButtonDialog(self.win, panel["buttons"][index], done)

    def _remove_button(self):
        panel, index = self._panel(), self._selected_button()
        if panel is None or index is None:
            return
        del panel["buttons"][index]
        self._show_panel(min(index, len(panel["buttons"]) - 1))
        self._changed()

    def _move_button(self, step):
        panel, index = self._panel(), self._selected_button()
        if panel is None or index is None or not 0 <= index + step < len(panel["buttons"]):
            return
        items = panel["buttons"]
        items[index], items[index + step] = items[index + step], items[index]
        self._show_panel(index + step)
        self._changed()


class ButtonDialog:
    """Asks for a button: its label and what it does. Calls on_ok(button) when saved."""

    def __init__(self, parent, button, on_ok):
        self.on_ok = on_ok
        self.win = win = tk.Toplevel(parent)
        win.title("Кнопка")
        win.resizable(False, False)
        win.transient(parent)
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill="both", expand=True)
        button = button or button_spec("", "keys", "")
        self.label_var = tk.StringVar(value=button["label"])
        self.value_var = tk.StringVar(value=button["value"])
        names = dict(ACTIONS)
        self.action_var = tk.StringVar(value=names[button["do"]])

        ttk.Label(frame, text="Надпись на кнопке").pack(anchor="w")
        label_entry = ttk.Entry(frame, textvariable=self.label_var, width=42)
        label_entry.pack(fill="x", pady=(2, 10))
        ttk.Label(frame, text="Что делает").pack(anchor="w")
        action = ttk.Combobox(frame, textvariable=self.action_var, values=[n for _k, n in ACTIONS], state="readonly")
        action.pack(fill="x", pady=(2, 10))
        action.bind("<<ComboboxSelected>>", lambda _e: self._update_hint())
        self.value_label = ttk.Label(frame)
        self.value_label.pack(anchor="w")
        ttk.Entry(frame, textvariable=self.value_var, width=42).pack(fill="x", pady=(2, 4))
        self.hint = ttk.Label(frame, foreground=MUTED, wraplength=360, justify="left")
        self.hint.pack(anchor="w")
        self.error = ttk.Label(frame, foreground=ERROR, wraplength=360, justify="left")
        self.error.pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Сохранить", style=ACCENT_BUTTON, command=self._save).pack(side="right")
        ttk.Button(row, text="Отмена", command=win.destroy).pack(side="right", padx=(0, 8))
        win.bind("<Return>", lambda _e: self._save())
        win.bind("<Escape>", lambda _e: win.destroy())
        self._update_hint()
        _center(win, parent)
        win.grab_set()
        label_entry.focus_set()

    def _do(self):
        return next(key for key, name in ACTIONS if name == self.action_var.get())

    def _update_hint(self):
        do = self._do()
        self.value_label.configure(text=VALUE_LABELS[do])
        self.hint.configure(text=HINTS[do])

    def _save(self):
        label = self.label_var.get().strip()
        if not label:
            self.error.configure(text="Напишите надпись для кнопки.")
            return
        button = button_spec(label[:24], self._do(), self.value_var.get().strip())
        problem = system.check_action(button)
        if problem:
            self.error.configure(text=problem)
            return
        self.win.destroy()
        self.on_ok(button)
