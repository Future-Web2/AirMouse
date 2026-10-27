r"""Screenshots for the README and the guide, in Russian and in English.

    .venv\Scripts\python.exe tools\screenshots.py      -> docs/*.png (Russian), docs/en/*.png (English)

Nothing appears on the screen and the camera stays off. The Liquid Glass window draws
itself into a picture, over a drawn camera picture with a simulated pair of hands (the
pointer hand open, the other in an «L»: the precise cursor). The on-screen widgets draw
into pictures put together on a backdrop. The ttk windows are fully transparent and
copied with PrintWindow, as in capture_advanced.py.
"""

import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import capture_advanced as quiet  # noqa: E402  (transparent windows, PrintWindow)

from airmouse import bench, i18n, overlay, settings, winmouse  # noqa: E402
from airmouse.glass import LiquidBackdrop, blit_text  # noqa: E402

DOCS = ROOT / "docs"
WIDGETS_TITLE = {
    "ru": ("Рабочий стол: виджеты висят поверх всех окон", "Палец вверх или Ctrl+Alt+W — показать / скрыть"),
    "en": ("Desktop: widgets float above all windows", "Thumbs up or Ctrl+Alt+W: show / hide"),
}


def out(language, name):
    folder = DOCS if language == "ru" else DOCS / "en"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def fresh_settings(**values):
    """A settings file of its own in a temporary folder (never the user's)."""
    import json
    settings.SETTINGS_DIR = Path(tempfile.mkdtemp())
    settings.SETTINGS_FILE = settings.SETTINGS_DIR / "settings.json"
    settings.SETTINGS_FILE.write_text(json.dumps(values), encoding="utf-8")


def camera_picture(mode="precise"):
    """A camera picture (a soft backdrop) with the pointer hand open and the other in an «L», drawn as
    the tracker draws them; RGB 640 x 480."""
    from airmouse.settings import Settings
    from airmouse.tracker import Tracker
    trk = Tracker(Settings(mode="hand"))
    trk.mode = mode
    backdrop = LiquidBackdrop(640, 480, seed=11).render(0.8)
    frame = cv2.cvtColor(cv2.convertScaleAbs(backdrop, alpha=0.75), cv2.COLOR_RGB2BGR)
    pointer = bench.hand(330, 150)
    second = bench.hand(140, 175, pose="l", left=True)
    trk._publish_preview(frame, pointer, 1920, 1080, second)
    return trk.take_preview()


def fake_tracker(mode="precise"):
    return SimpleNamespace(fps=30.0, mode=mode, kind="hand", control_enabled=True, error=None, palm=None,
                           face=None, progress=0.0, stats=Counter(), events=[], widget_toggles=0, pause_toggles=0,
                           dwell=None, take_preview=lambda: None, stop=lambda: None)


def glass(language, design="glass"):
    fresh_settings(design=design, language=language)
    from airmouse import ui
    app = ui.App(scale=1.0)
    app._on_frame(camera_picture())
    app.tracker, app._has_frame = fake_tracker(), True
    app._show_running(True)
    picture = app.render(time.perf_counter(), 1.0)
    for _ in range(30):                           # the pills slide into place
        picture = app.render(time.perf_counter(), 0.05)
    name = "screenshot_glass.png" if design == "glass" else "screenshot_nature.png"
    cv2.imwrite(str(out(language, name)), cv2.cvtColor(picture, cv2.COLOR_RGB2BGR))
    app.tracker = None
    app._on_close()


def classic(language):
    fresh_settings(design="classic", language=language)
    from airmouse import ui_classic
    app = ui_classic.App()
    app._show_running(True)
    app._on_frame(camera_picture())
    app.mode_var.set(i18n._("Точный курсор"))
    app.fps_var.set(i18n._("{:.0f} кадр/с").format(30))
    app.root.update()
    quiet.capture(app.root, out(language, "screenshot_classic.png"))
    app._on_close()


def advanced(language):
    fresh_settings(design="glass", language=language)
    from airmouse import tuning, ui
    from tkinter import ttk
    app = ui.App(scale=1.0)
    app.open_advanced()
    win = app._advanced.win
    win.update()
    tabs = next(w for w in quiet.descendants(win) if isinstance(w, ttk.Notebook))
    for group, name in (("Камера", "screenshot_advanced.png"), ("Две руки", "screenshot_twohands.png"),
                        ("Доступность", "screenshot_accessibility.png")):
        tabs.select(tuning.GROUPS.index(group))
        win.update()
        time.sleep(0.2)
        quiet.capture(win, out(language, name))
    app._advanced.close()
    app._on_close()


def paste(picture, layer, x, y):
    """A widget's picture (premultiplied BGRA) laid over an RGB picture at (x, y)."""
    pixels = layer.bgra()
    h, w = pixels.shape[:2]
    region = picture[y:y + h, x:x + w].astype(np.float32)
    alpha = pixels[..., 3:4].astype(np.float32) / 255
    color = pixels[..., 2::-1].astype(np.float32)          # BGR -> RGB
    picture[y:y + h, x:x + w] = np.clip(color + region * (1 - alpha), 0, 255).astype(np.uint8)


class ShownVolume:
    """A volume to show (the real one is only read, and may well be off)."""

    def level(self):
        return 0.62

    def muted(self):
        return False


class ShownLoad:
    def cpu(self):
        return 18.0

    def memory(self):
        return 54.0

    def battery(self):
        return 82.0, False


def widgets(language):
    from airmouse import onscreen
    from airmouse.twohands import PRECISE
    env = bench._WidgetEnv(1.0)
    env.volume, env.load = ShownVolume(), ShownLoad()
    env.frame = camera_picture()
    env.status = lambda: (i18n._("Точный курсор"), (90, 220, 230), i18n._("{:.0f} кадр/с").format(30))
    env.dwell_state = lambda: ("double", False)
    picture = cv2.convertScaleAbs(LiquidBackdrop(1280, 720, seed=4).render(2.0), alpha=0.8)
    title, hint = WIDGETS_TITLE[language]
    blit_text(picture, title, 40, 48, "semibold", 22, (245, 247, 250), "lm")
    blit_text(picture, hint, 40, 80, "regular", 15, (220, 226, 236), "lm")
    specs = {spec["type"]: spec for spec in onscreen.default_widgets()}
    places = {"volume": (584, 2), "media": (584, 94), "buttons": (584, 190), "status": (878, 2),
              "dwell": (18, 420), "clock": (18, 560), "system": (420, 548)}
    for kind, (x, y) in places.items():
        widget = onscreen.WIDGET_CLASSES[kind](dict(specs[kind], x=x, y=y), env)
        widget.tick(time.perf_counter())
        paste(picture, widget.render(time.perf_counter()), x, y)
    ring = onscreen.CursorRing(1.0)
    paste(picture, ring.render(ring.state(PRECISE, 0.55, 0.0)), 850 - ring.size // 2, 330 - ring.size // 2)
    cv2.imwrite(str(out(language, "screenshot_widgets.png")), cv2.cvtColor(picture, cv2.COLOR_RGB2BGR))


def main():
    winmouse.enable_dpi_awareness()
    overlay.LayeredWindow.show = lambda self, *args: None        # no widgets on the screen
    import tkinter as tk
    tk.Tk, tk.Toplevel = quiet.QuietTk, quiet.QuietToplevel
    for language in ("ru", "en"):
        i18n.set_language(language)
        glass(language)
        glass(language, "nature")
        classic(language)
        advanced(language)
        widgets(language)
        print("done:", language)
    quiet.give_focus_back()


if __name__ == "__main__":
    main()
