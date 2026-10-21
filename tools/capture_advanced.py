r"""Screenshots of the «Подробнее» window for the guide video (promo/make_guide.py).

    .venv\Scripts\python.exe tools\capture_advanced.py      -> promo/guide/advanced_*.png, advanced.json

The windows never appear: they are fully transparent and never activated, and the
keyboard focus goes straight back to where it was. The camera stays off. The JSON keeps
where the tabs and the frame-rate box are, so the video can point at them.
"""

import ctypes
import json
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "promo" / "guide"

user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = (wintypes.HWND,)
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD)
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x80
PW_CLIENTONLY, PW_RENDERFULLCONTENT = 1, 2
FOREGROUND = user32.GetForegroundWindow()


def quiet(window):
    """Fully transparent and never activated."""
    window.withdraw()
    window.attributes("-alpha", 0.0)
    wrapper = user32.GetParent(window.winfo_id())
    style = user32.GetWindowLongPtrW(wrapper, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(wrapper, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    window.deiconify()


class QuietTk(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        quiet(self)


class QuietToplevel(tk.Toplevel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        quiet(self)

    def focus_force(self):
        pass


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def capture(window, name):
    """Save the client area of a window, drawn by Windows even though it is transparent."""
    window.update()
    wrapper = user32.GetParent(window.winfo_id())
    rect = wintypes.RECT()
    user32.GetClientRect(wrapper, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    dc = gdi32.CreateCompatibleDC(None)
    info = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(dc, bitmap)
    user32.PrintWindow(wrapper, dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
    image = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8)), (h, w, 4)).copy()
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    cv2.imwrite(str(OUT / name), image[..., :3])
    print("saved", OUT / name, f"{w}x{h}")
    return w, h


def give_focus_back():
    if user32.GetForegroundWindow() != FOREGROUND:
        user32.SetForegroundWindow(FOREGROUND)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def main():
    from airmouse import overlay, settings, tuning, winmouse

    settings.SETTINGS_DIR = Path(tempfile.mkdtemp())
    settings.SETTINGS_FILE = settings.SETTINGS_DIR / "settings.json"
    settings.SETTINGS_FILE.write_text('{"design": "nature"}', encoding="utf-8")
    winmouse.enable_dpi_awareness()
    overlay.LayeredWindow.show = lambda self, *args: None        # no widgets on the screen
    tk.Tk, tk.Toplevel = QuietTk, QuietToplevel

    from airmouse import ui
    from airmouse.advanced import format_value

    OUT.mkdir(parents=True, exist_ok=True)
    app = ui.App()

    def pump(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.root.update()
            give_focus_back()
            time.sleep(0.01)

    pump(0.5)
    app.open_advanced()
    win = app._advanced.win
    pump(1.0)

    notebook = next(w for w in descendants(win) if isinstance(w, ttk.Notebook))
    fps_box = next(w for w in descendants(win) if isinstance(w, ttk.Combobox))   # the first parameter
    x0, y0 = win.winfo_rootx(), win.winfo_rooty()

    def rect(widget):
        return [widget.winfo_rootx() - x0, widget.winfo_rooty() - y0, widget.winfo_width(), widget.winfo_height()]

    # Where each tab is: ask the notebook which tab is under points along its top edge.
    nx, ny, nw, _nh = rect(notebook)
    tabs = []
    for y in range(4, 40, 2):
        spans = []
        for x in range(nw):
            try:
                index = notebook.index(f"@{x},{y}")
            except tk.TclError:
                continue
            if spans and spans[-1][0] == index:
                spans[-1][2] = x
            else:
                spans.append([index, x, x])
        if len(spans) == len(tuning.GROUPS):
            tabs = [[nx + a, ny + y, b - a + 1] for _index, a, b in spans]
            break

    w, h = capture(win, "advanced_camera.png")
    param = tuning.BY_KEY["camera_fps"]
    variable = fps_box.cget("textvariable")
    app.root.setvar(variable, format_value(param, 60))      # only shown: the setting is not changed
    pump(0.3)
    capture(win, "advanced_camera60.png")
    app.root.setvar(variable, format_value(param, param.default))
    for index, name in ((1, "cursor"), (2, "clicks"), (len(tuning.GROUPS) - 1, "access")):
        notebook.select(index)
        pump(0.4)
        capture(win, f"advanced_{name}.png")

    meta = {"size": [w, h], "camera_fps": rect(fps_box), "tabs": tabs}
    (OUT / "advanced.json").write_text(json.dumps(meta), encoding="utf-8")
    print(meta)
    app._advanced.close()
    app._on_close()
    give_focus_back()


if __name__ == "__main__":
    main()
