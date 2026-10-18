"""Full-screen gaze calibration: the user looks at dots and we learn where they look."""

import time
import tkinter as tk

from .face import GazeModel

BG = "#101114"
DOT = "#4f8ef7"
TEXT = "#e8e8e8"
MUTED = "#8a8f98"

GRID = (0.08, 0.5, 0.92)
ORDER = ((0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1), (0, 2), (1, 2), (2, 2))

# Seconds
INTRO_TIME = 2.5
HEAD_TIME = 6.0
SETTLE_TIME = 0.7    # the eyes need a moment to land on a new dot
COLLECT_TIME = 1.0
RESULT_TIME = 2.5

HEAD_TEXT = ("Смотрите на точку и медленно поворачивайте голову:\n"
             "влево — вправо, потом вверх — вниз")
DOT_TEXT = "Смотрите на точку. Голову держите ровно."


class GazeCalibration:
    """Shows the calibration and calls on_done(GazeModel or None) at the end."""

    def __init__(self, root, tracker, on_done):
        self.tracker = tracker
        self.on_done = on_done
        self.w, self.h = root.winfo_screenwidth(), root.winfo_screenheight()
        self.win = tk.Toplevel(root)
        self.win.geometry(f"{self.w}x{self.h}+0+0")
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG, cursor="none")
        self.canvas = tk.Canvas(self.win, bg=BG, highlightthickness=0, width=self.w, height=self.h)
        self.canvas.pack(fill="both", expand=True)
        self.win.bind("<Escape>", lambda _e: self._finish(None))
        self.win.focus_force()

        center = (self.w // 2, self.h // 2)
        dots = [(int(GRID[i] * self.w), int(GRID[j] * self.h)) for i, j in ORDER]
        # (kind, dot position, duration)
        self.steps = [("intro", center, INTRO_TIME), ("head", center, HEAD_TIME)]
        self.steps += [("dot", d, SETTLE_TIME + COLLECT_TIME) for d in dots]
        self.dot_count = len(dots)
        self.head_samples = []
        self.dot_samples = []
        self.target = None       # dot the user should look at now
        self._step = 0
        self._step_start = time.perf_counter()
        self._last_frame = None
        self._done = False
        self._tick()

    def _tick(self):
        if self._done:
            return
        now = time.perf_counter()
        kind, pos, duration = self.steps[self._step]
        elapsed = now - self._step_start
        if elapsed >= duration:
            self._step += 1
            self._step_start = now
            if self._step == len(self.steps):
                self._fit()
                return
            kind, pos, duration = self.steps[self._step]
            elapsed = 0.0
        self.target = pos
        self._collect(kind, pos, elapsed)
        self._draw(kind, pos, elapsed)
        self.win.after(15, self._tick)

    def _collect(self, kind, pos, elapsed):
        frame = self.tracker.face
        if frame is None or frame is self._last_frame:
            return
        self._last_frame = frame
        _t, face = frame
        if face is None or not face.eyes_open:
            return
        if kind == "head" and elapsed > 0.5:
            self.head_samples.append((face.gaze, face.head))
        elif kind == "dot" and elapsed > SETTLE_TIME:
            self.dot_samples.append((pos, face.gaze, face.head))

    def _draw(self, kind, pos, elapsed):
        c = self.canvas
        c.delete("all")
        x, y = pos
        if kind == "dot":
            k = min(elapsed / SETTLE_TIME, 1.0)
            r = 10 + 30 * (1 - k)            # ring shrinks onto the dot
            c.create_oval(x - r, y - r, x + r, y + r, outline=DOT, width=3)
            core = TEXT if elapsed > SETTLE_TIME else DOT
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=core, outline="")
            number = self._step - 1
            c.create_text(self.w // 2, int(self.h * 0.3), text=DOT_TEXT, fill=MUTED, font=("Segoe UI", 14))
            c.create_text(self.w // 2, int(self.h * 0.3) + 32, text=f"{number} / {self.dot_count}",
                          fill=MUTED, font=("Segoe UI", 12))
        else:
            c.create_oval(x - 10, y - 10, x + 10, y + 10, fill=DOT, outline="")
            if kind == "intro":
                text = "Калибровка взгляда\nСмотрите на точки, пока они не исчезнут. Esc — отмена."
            else:
                text = HEAD_TEXT
            c.create_text(x, int(self.h * 0.3), text=text, fill=TEXT, font=("Segoe UI", 18), justify="center")

    def _fit(self):
        model = GazeModel.fit(self.head_samples, self.dot_samples)
        c = self.canvas
        c.delete("all")
        if model is None:
            text = "Не получилось: глаза плохо видны.\nПроверьте освещение и попробуйте ещё раз."
        else:
            text = f"Готово!\nСредняя ошибка ≈ {model.error:.0f} px"
        c.create_text(self.w // 2, self.h // 2, text=text, fill=TEXT, font=("Segoe UI", 20), justify="center")
        self.target = None
        self.win.after(int(RESULT_TIME * 1000), lambda: self._finish(model))

    def _finish(self, model):
        if self._done:
            return
        self._done = True
        self.win.destroy()
        self.on_done(model)
