"""AirMouse: control the Windows mouse with hand gestures in front of a webcam.

    python main.py              start the app
    python main.py --selftest   load the hand model once and exit (checks a build)
"""

import ctypes
import os
import sys
import traceback

os.environ.setdefault("GLOG_minloglevel", "2")  # keep MediaPipe's native logging quiet

# A windowed .exe has no console; libraries that print must not crash it.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from airmouse.settings import SETTINGS_DIR  # noqa: E402

ERROR_ALREADY_EXISTS = 183
_instance_mutex = None


def _first_instance():
    """True unless AirMouse is already running; the mutex lives as long as this process."""
    global _instance_mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _instance_mutex = kernel32.CreateMutexW(None, False, "Local\\AirMouse.SingleInstance")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def main():
    if "--selftest" in sys.argv:
        from airmouse import ui, ui_classic  # noqa: F401  (checks the UI libraries load)
        from airmouse.tracker import selftest
        return selftest()

    if not _first_instance():
        ctypes.windll.user32.MessageBoxW(None, "AirMouse уже запущен.", "AirMouse", 0x40)
        return 0

    from airmouse import winmouse
    from airmouse.settings import Settings
    winmouse.enable_dpi_awareness()  # before any window exists
    autostart = False
    while True:
        # Switching design closes the window; open it again in the new design,
        # with the camera running if it was.
        if Settings.load().design == "classic":
            from airmouse.ui_classic import App
        else:
            from airmouse.ui import App
        app = App(autostart=autostart)
        app.run()
        if app.next_design is None:
            return 0
        autostart = app.was_running


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        (SETTINGS_DIR / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
