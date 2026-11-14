"""Windows that float over the desktop with smooth transparency on Windows (on-screen widgets, the
cursor ring); overlay.py picks this class on Windows (linuxwindows.py on Linux).

A LayeredWindow shows a premultiplied BGRA picture through UpdateLayeredWindow,
so its edges and shadows blend with whatever is behind. It never takes the
keyboard focus: clicking a widget leaves the active program active, so keys
the widget sends go to that program.

The window procedure runs inside Tk's event loop, where calling Tkinter is not
safe; mouse handlers must only change state and talk to Windows.
"""

import ctypes
from ctypes import wintypes

import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WS_POPUP = 0x80000000
WS_EX_TRANSPARENT, WS_EX_TOPMOST, WS_EX_TOOLWINDOW = 0x20, 0x8, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
ULW_ALPHA = 2
WM_SETCURSOR, WM_MOUSEACTIVATE = 0x20, 0x21
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL = 0x200, 0x201, 0x202, 0x20A
WM_CAPTURECHANGED, WM_MOUSELEAVE = 0x215, 0x2A3
MA_NOACTIVATE, HTCLIENT, TME_LEAVE = 3, 1, 2
IDC_ARROW, IDC_HAND = 32512, 32649


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("hwndTrack", wintypes.HWND),
                ("dwHoverTime", wintypes.DWORD)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.RegisterClassExW.argtypes = (ctypes.POINTER(WNDCLASSEXW),)
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID)
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.SetCapture.argtypes = (wintypes.HWND,)
user32.SetCapture.restype = wintypes.HWND
user32.GetCapture.restype = wintypes.HWND
user32.TrackMouseEvent.argtypes = (ctypes.POINTER(TRACKMOUSEEVENT),)
user32.LoadCursorW.argtypes = (wintypes.HINSTANCE, ctypes.c_void_p)
user32.LoadCursorW.restype = wintypes.HANDLE
user32.SetCursor.argtypes = (wintypes.HANDLE,)
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = LRESULT
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)

CLASS_NAME = "AirMouseOverlay"
_windows = {}     # hwnd -> LayeredWindow
_class = None


def _signed16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


@WNDPROC
def _window_proc(hwnd, msg, wparam, lparam):
    window = _windows.get(hwnd)
    if window is not None:
        try:
            result = window._message(msg, wparam, lparam)
        except Exception:  # never let an error escape into Windows' message loop
            result = None
        if result is not None:
            return result
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register_class():
    global _class
    if _class is None:
        instance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=_window_proc, hInstance=instance,
                         hCursor=user32.LoadCursorW(None, IDC_ARROW), lpszClassName=CLASS_NAME)
        user32.RegisterClassExW(ctypes.byref(wc))   # fails harmlessly if a previous window registered it
        _class = instance
    return _class


class LayeredWindow:
    """A borderless always-on-top window showing an RGBA picture.

    click_through: mouse goes to whatever is below (the cursor ring).
    on_mouse(kind, x, y, delta): "move", "down", "up", "leave", "wheel", "cancel"
    with x, y in window pixels. hand_at(x, y): True to show the hand cursor there.
    """

    def __init__(self, click_through=False, on_mouse=None, hand_at=None):
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if click_through:
            ex |= WS_EX_TRANSPARENT
        self.hwnd = user32.CreateWindowExW(ex, CLASS_NAME, "AirMouse", WS_POPUP, 0, 0, 1, 1,
                                           None, None, _register_class(), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _windows[self.hwnd] = self
        self.on_mouse, self.hand_at = on_mouse, hand_at
        self.x = self.y = self.w = self.h = 0
        self.visible = False
        self._dc = gdi32.CreateCompatibleDC(None)
        self._bitmap = None
        self._pixels = None
        self._tracking = False
        self._blend = BLENDFUNCTION(0, 0, 255, 1)   # AC_SRC_OVER, per-pixel alpha (premultiplied)

    def show(self, bgra, x, y):
        """Show a premultiplied BGRA picture (h, w, 4) with its top-left corner at screen (x, y)."""
        h, w = bgra.shape[:2]
        if (w, h) != (self.w, self.h):
            self._resize(w, h)
        np.copyto(self._pixels, bgra)
        self.x, self.y = int(x), int(y)
        user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(wintypes.POINT(self.x, self.y)),
                                   ctypes.byref(wintypes.SIZE(w, h)), self._dc, ctypes.byref(wintypes.POINT(0, 0)),
                                   0, ctypes.byref(self._blend), ULW_ALPHA)
        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True

    def move(self, x, y):
        """Move without redrawing."""
        self.x, self.y = int(x), int(y)
        user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(wintypes.POINT(self.x, self.y)), None, None,
                                   None, 0, None, 0)

    def hide(self):
        if self.visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def destroy(self):
        if self.hwnd:
            _windows.pop(self.hwnd, None)
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self._dc:
            gdi32.DeleteDC(self._dc)
            self._dc = None
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
            self._bitmap = None

    def _resize(self, w, h):
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                  biBitCount=32)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(self._dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        gdi32.SelectObject(self._dc, bitmap)
        if self._bitmap:
            gdi32.DeleteObject(self._bitmap)
        self._bitmap = bitmap
        self._pixels = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8)), (h, w, 4))
        self.w, self.h = w, h

    def _message(self, msg, wparam, lparam):
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE        # clicking does not take the focus from the active program
        if self.on_mouse is None:
            return None
        if msg == WM_SETCURSOR:
            if lparam & 0xFFFF == HTCLIENT and self.hand_at is not None:
                cx, cy = cursor_pos()
                hand = self.hand_at(cx - self.x, cy - self.y)
                user32.SetCursor(user32.LoadCursorW(None, IDC_HAND if hand else IDC_ARROW))
                return 1
            return None
        x, y = _signed16(lparam), _signed16(lparam >> 16)
        if msg == WM_MOUSEMOVE:
            if not self._tracking:
                user32.TrackMouseEvent(ctypes.byref(TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE,
                                                                    self.hwnd, 0)))
                self._tracking = True
            self.on_mouse("move", x, y, 0)
        elif msg == WM_LBUTTONDOWN:
            user32.SetCapture(self.hwnd)
            self.on_mouse("down", x, y, 0)
        elif msg == WM_LBUTTONUP:
            self.on_mouse("up", x, y, 0)
            if user32.GetCapture() == self.hwnd:
                user32.ReleaseCapture()   # sends WM_CAPTURECHANGED: after "up", so it cancels nothing
        elif msg == WM_MOUSELEAVE:
            self._tracking = False
            self.on_mouse("leave", 0, 0, 0)
        elif msg == WM_MOUSEWHEEL:   # its position is on the screen, not in the window
            self.on_mouse("wheel", x - self.x, y - self.y, _signed16(wparam >> 16))
        elif msg == WM_CAPTURECHANGED:
            self.on_mouse("cancel", 0, 0, 0)
        else:
            return None
        return 0
