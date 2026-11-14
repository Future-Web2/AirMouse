"""AirMouse: control the mouse on Windows and Linux with hand gestures in front of a webcam.

    python main.py              start the app
    python main.py --selftest   load the hand model once and exit (checks a build)
    python main.py --bench [report.json]   measure the KPIs of docs/KPI.md
"""

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


def main():
    if "--selftest" in sys.argv:
        from airmouse import ui, ui_classic  # noqa: F401  (checks the UI libraries load)
        from airmouse.tracker import selftest
        return selftest()
    if "--bench" in sys.argv:
        from airmouse import bench
        args = sys.argv[sys.argv.index("--bench") + 1:]
        return bench.run(args[0] if args else None)

    from airmouse import system
    if not system.single_instance():
        from airmouse import i18n
        from airmouse.settings import Settings
        i18n.set_language(Settings.load().language or i18n.system_language())
        system.show_message(i18n._("AirMouse уже запущен."))
        return 0

    from airmouse.settings import Settings
    system.enable_dpi_awareness()  # before any window exists
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
