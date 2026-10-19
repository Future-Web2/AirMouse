"""Behaviour shared by both window designs: tracking, modes, calibration, hotkeys, settings,
the on-screen widgets and the session numbers.

A design (ui.py for Liquid Glass, ui_classic.py for the classic look) subclasses
BaseApp, builds its window in __init__ and implements the hooks at the bottom.
"""

import time
import tkinter as tk
from collections import deque
from tkinter import messagebox

import cv2

from . import resource_path, system, tuning, winmouse
from .calibration import GazeCalibration
from .face import EYES_CLOSED, NO_FACE
from .gestures import DRAG, MOVE, NO_HAND, PENDING, PRESSED, RIGHT, SCROLL
from .onscreen import OnScreen
from .settings import Settings
from .tracker import Tracker, preload

DESIGNS = (("glass", "Liquid Glass"), ("nature", "Природа (запотевшее стекло)"), ("classic", "Классический"))
MODES = (("hand", "Рука"), ("gaze", "Глаза"), ("head", "Голова"))

MODE_TEXT = {
    NO_HAND: "Рука не видна",
    NO_FACE: "Лицо не видно",
    MOVE: "Курсор",
    PENDING: "Клик",
    PRESSED: "Кнопка нажата",
    EYES_CLOSED: "Глаза закрыты",
    DRAG: "Перетаскивание",
    RIGHT: "Правый клик",
    SCROLL: "Прокрутка",
}
GREY = (150, 155, 168)
YELLOW = (255, 204, 64)
MODE_DOT = {
    NO_HAND: GREY, NO_FACE: GREY, MOVE: (94, 224, 122), PENDING: YELLOW, PRESSED: YELLOW,
    EYES_CLOSED: YELLOW, DRAG: (255, 128, 84), RIGHT: (200, 128, 255), SCROLL: (84, 180, 255),
}

FACE_CLICKS = (
    ("Долго моргнуть", "левый клик, дважды — двойной"),
    ("Подмигнуть", "правый клик"),
    ("Открыть рот", "зажать кнопку (перетаскивание)"),
    ("Брови вверх + наклон", "прокрутка"),
)
GESTURES = {
    "hand": (
        ("Ладонь", "двигает курсор"),
        ("Большой + указательный", "левый клик, дважды — двойной"),
        ("Сжать, держать и вести", "перетаскивание"),
        ("Большой + два пальца", "правый клик"),
        ("Два пальца вверх / вниз", "прокрутка"),
        ("Большой палец вверх", "показать / скрыть виджеты"),
    ),
    "gaze": (
        ("Взгляд", "переносит курсор, куда смотрите"),
        ("Лёгкий поворот головы", "точно доводит курсор"),
    ) + FACE_CLICKS,
    "head": (("Поворот головы", "двигает курсор"),) + FACE_CLICKS,
}
METERS = (("Левый глаз", 0), ("Правый глаз", 1), ("Рот", "jaw"), ("Брови", "brow"))

CALIBRATE_TEXT = {
    "hand": "Центр зоны по руке",
    "gaze": "Калибровка взгляда",
    "head": "Центр по положению головы",
}
COUNTDOWN_TEXT = {
    "hand": "Держите руку удобно… {}",
    "head": "Смотрите в центр экрана… {}",
}
CALIBRATE_DELAY = 3  # seconds to get into a comfortable position
PRELOAD_DELAY = 1500  # ms after the window appears: load MediaPipe in the background


def meter_value(face, key):
    return face.blink[key] if isinstance(key, int) else getattr(face, key)


class Session:
    """Numbers for the «Сеанс» card: frame rate over the last minute, processor use, what was done."""

    def __init__(self):
        self.fps = deque(maxlen=120)   # a sample every half second
        self.cpu = 0.0
        self.started = None
        self._load = system.ProcessLoad()
        self._next = self._next_cpu = 0.0

    def sample(self, tracker, now):
        if tracker is None:
            self.started = None
            self.fps.clear()
            return
        if self.started is None:
            self.started = now
            self._load.cpu()
        if now >= self._next:
            self._next = now + 0.5
            self.fps.append(tracker.fps)
        if now >= self._next_cpu:
            self._next_cpu = now + 1.0
            self.cpu = self._load.cpu()

    def summary(self, tracker, now):
        """(duration "мм:сс", "кадр/с", processor text, actions text) for a running tracker."""
        seconds = max(int(now - self.started), 0) if self.started is not None else 0
        stats = tracker.stats
        return (f"{seconds // 60:02d}:{seconds % 60:02d}", f"{tracker.fps:.0f} кадр/с", f"процессор {self.cpu:.0f}%",
                f"клики {stats['left']}  ·  правые {stats['right']}  ·  прокрутка {stats['wheel']}")


class BaseApp:
    def __init__(self, autostart=False):
        """autostart: start the camera right away (after switching design while it was on)."""
        # Window image operations are small; spreading each over all cores
        # costs far more in thread hand-offs than it saves.
        cv2.setNumThreads(0)
        self.settings = Settings.load()
        if self.settings.mode not in CALIBRATE_TEXT:
            self.settings.mode = "hand"
        self.tracker = None
        self.control = True
        self.next_design = None    # set when the user switches design; main() then opens that window
        self.was_running = False
        self._autostart = autostart
        self._has_frame = False
        self._calibration = None
        self._needs_calibration = False
        self._save_job = None
        self._jobs = set()
        self._hotkey_was_down = False
        self._widgets_key_was_down = False
        self._calibrate_left = 0
        self.session = Session()
        self.onscreen = None       # the on-screen widgets, created once the window exists
        self._editor = self._advanced = None

        self.root = tk.Tk()
        self.root.title("AirMouse")
        self.root.resizable(False, False)
        icon = resource_path("assets/airmouse.ico")
        if icon.exists():
            self.root.iconbitmap(default=str(icon))

    def _ready(self):
        """Call at the end of the subclass __init__, once the window is built."""
        self.root.attributes("-topmost", self.settings.always_on_top)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.onscreen = OnScreen(self, self.scale() * tuning.get(self.settings, "widget_scale"))
        if self._autostart:
            self._start()
        else:
            self.after(PRELOAD_DELAY, preload)

    def scale(self):
        """Display scale (1.0 at 100%), in quarter steps."""
        return max(round(self.root.winfo_fpixels("1i") / 96.0 * 4) / 4, 1.0)

    def open_widget_editor(self):
        from .widget_editor import WidgetEditor
        if self._editor is not None and self._editor.alive():
            self._editor.focus()
        else:
            self._editor = WidgetEditor(self)

    def open_advanced(self):
        from .advanced import AdvancedSettings
        if self._advanced is not None and self._advanced.alive():
            self._advanced.focus()
        else:
            self._advanced = AdvancedSettings(self)

    def restart_tracker(self):
        """Start the camera again with new camera settings (if it is on)."""
        if self.tracker is not None:
            self._stop()
            self._start()

    def run(self):
        self.root.mainloop()

    def after(self, ms, fn, *args):
        """root.after that is cancelled when the window closes (so nothing fires into a destroyed window)."""
        holder = []

        def run():
            self._jobs.discard(holder[0])
            fn(*args)
        holder.append(self.root.after(ms, run))
        self._jobs.add(holder[0])

    # -- actions ----------------------------------------------------------

    def _toggle_start(self):
        if self.tracker is not None:
            self._stop()
        else:
            self._start()

    def _start(self):
        self.tracker = Tracker(self.settings)
        self.tracker.control_enabled = self.control
        self.tracker.start()
        self._needs_calibration = self.settings.mode == "gaze" and not self.settings.gaze_model
        self._show_running(True)

    def _stop(self):
        if self._calibration is not None:
            self._calibration._finish(None)
        if self.tracker is not None:
            self.tracker.stop()
            self.tracker = None
        self._has_frame = False
        self._show_running(False)

    def _on_mode(self, mode):
        if mode == self.settings.mode:
            return
        self.settings.mode = mode
        self._schedule_save()
        self._apply_mode()
        if self.tracker is not None:
            self._stop()
            self._start()

    def _set_control(self, on):
        self.control = on
        if self.tracker is not None and self._calibration is None:
            self.tracker.control_enabled = on

    def _on_camera(self, index):
        self.settings.camera_index = index
        self._schedule_save()
        if self.tracker is not None:
            self._stop()
            self._start()

    def _set_always_on_top(self, on):
        self.settings.always_on_top = on
        self.root.attributes("-topmost", on)
        self._schedule_save()

    def _switch_design(self, design):
        if design == self.settings.design:
            return
        self.settings.design = design
        self.next_design = design
        self.was_running = self.tracker is not None
        self._on_close()

    def _calibrate(self):
        if self.tracker is None:
            messagebox.showinfo("AirMouse", "Сначала нажмите «Старт».", parent=self.root)
            return
        if self.settings.mode == "gaze":
            self._open_gaze_calibration()
            return
        self._calibrate_left = CALIBRATE_DELAY
        self._calibrate_step()

    def _calibrate_step(self):
        mode = self.settings.mode
        if self.tracker is None or mode == "gaze":
            self._set_calibrate_button(CALIBRATE_TEXT[mode], True)
            return
        if self._calibrate_left > 0:
            self._set_calibrate_button(COUNTDOWN_TEXT[mode].format(self._calibrate_left), False)
            self._calibrate_left -= 1
            self.after(1000, self._calibrate_step)
            return
        self._set_calibrate_button(CALIBRATE_TEXT[mode], True)
        if mode == "head":
            self.tracker.recenter()
            return
        palm = self.tracker.palm
        if palm is None:
            messagebox.showinfo("AirMouse", "Рука не видна. Поднимите руку перед камерой и попробуйте ещё раз.",
                                parent=self.root)
            return
        self.settings.zone_center_x = min(max(palm[0], 0.2), 0.8)
        self.settings.zone_center_y = min(max(palm[1], 0.2), 0.8)
        self._schedule_save()

    def _open_gaze_calibration(self):
        if self._calibration is not None:
            return
        self._needs_calibration = False
        self.tracker.control_enabled = False   # no clicks from blinking at the dots
        self._calibration = GazeCalibration(self.root, self.tracker, self._calibration_done)

    def _calibration_done(self, model):
        self._calibration = None
        if self.tracker is not None:
            self.tracker.control_enabled = self.control
        if model is not None:
            self.settings.gaze_model = model.data
            self._schedule_save()
        self._apply_mode()

    def calibration_info(self):
        if self.settings.mode != "gaze":
            return ""
        if self.settings.gaze_model:
            return f"Точность взгляда ≈ {self.settings.gaze_model['error']:.0f} px"
        return "Калибровки ещё нет"

    # -- polling (call every frame from the design's timer) ----------------

    def _poll(self):
        ctrl_alt = winmouse.key_down(winmouse.VK_CONTROL) and winmouse.key_down(winmouse.VK_MENU)
        down = ctrl_alt and winmouse.key_down(ord("M"))
        if down and not self._hotkey_was_down:
            self._set_control(not self.control)
            self._show_control(self.control)
        self._hotkey_was_down = down
        down = ctrl_alt and winmouse.key_down(ord("W"))
        if down and not self._widgets_key_was_down and self.onscreen is not None:
            self.onscreen.toggle()
        self._widgets_key_was_down = down

        tracker = self.tracker
        self.session.sample(tracker if self._has_frame else None, time.perf_counter())
        if tracker is None:
            return
        if tracker.error:
            error = tracker.error
            self._stop()
            messagebox.showerror("AirMouse", error, parent=self.root)
            return
        frame = tracker.take_preview()
        if frame is not None:
            self._has_frame = True
            self._on_frame(frame)
            if self.onscreen is not None:
                self.onscreen.on_frame(frame)
        if self._needs_calibration and tracker.face and tracker.face[1] is not None:
            self._open_gaze_calibration()

    def _status(self):
        """(text, dot colour, fps text) for the status line."""
        tracker = self.tracker
        if tracker is None:
            return "Остановлено", GREY, ""
        fps = f"{tracker.fps:.0f} кадр/с" if self._has_frame else ""
        if self._calibration is not None:
            return "Калибровка…", YELLOW, fps
        if not self._has_frame:
            return "Запуск…", GREY, fps
        if tracker.kind == "gaze" and not self.settings.gaze_model:
            return "Нужна калибровка взгляда", YELLOW, fps
        if not tracker.control_enabled:
            return "Пауза", GREY, fps
        return MODE_TEXT.get(tracker.mode, ""), MODE_DOT.get(tracker.mode, GREY), fps

    def face(self):
        """Newest FaceFrame (face modes), or None."""
        tracker = self.tracker
        return tracker.face[1] if tracker is not None and tracker.face else None

    # -- settings ---------------------------------------------------------

    def _schedule_save(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._save)

    def _save(self):
        self._save_job = None
        try:
            self.settings.save()
        except OSError:
            pass

    def _on_close(self):
        self._stop()
        if self.onscreen is not None:
            self.onscreen.close()
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        for job in self._jobs:
            self.root.after_cancel(job)
        self._save()
        self.root.destroy()

    # -- hooks for the design ----------------------------------------------

    def _apply_mode(self):
        """Show the controls and help for self.settings.mode."""

    def _show_running(self, running):
        """Camera started or stopped."""

    def _show_control(self, on):
        """Mouse control was switched by the hotkey."""

    def _set_calibrate_button(self, label, enabled):
        pass

    def _on_frame(self, frame):
        """New camera frame (RGB, with the hand / face drawn on it)."""
