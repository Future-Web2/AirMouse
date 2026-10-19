"""Windows that float over the desktop with smooth transparency (on-screen widgets, the cursor ring).

A LayeredWindow shows a premultiplied BGRA picture through UpdateLayeredWindow,
so its edges and shadows blend with whatever is behind. It never takes the
keyboard focus: clicking a widget leaves the active program active, so keys
the widget sends go to that program.

The window procedure runs inside Tk's event loop, where calling Tkinter is not
safe; mouse handlers must only change state and talk to Windows.

Layer is the picture: colour and coverage in float32, painted with "over".
"""

import ctypes
import math
from ctypes import wintypes
from functools import lru_cache

import cv2
import numpy as np

from .glass import LIGHT, _sprite, rounded_rect_sdf

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


# -- drawing ------------------------------------------------------------------------------

@lru_cache(maxsize=128)
def round_mask(w, h, r):
    """Coverage of a w x h rounded rectangle, anti-aliased."""
    return np.clip(0.5 - rounded_rect_sdf(w, h, r), 0, 1).astype(np.float32)


@lru_cache(maxsize=64)
def rim_light(w, h, r):
    """A thin bright edge, brighter where it faces the light (top left), as on the glass panels."""
    d = rounded_rect_sdf(w, h, r)
    gy, gx = np.gradient(d)
    length = np.hypot(gx, gy) + 1e-6
    facing = (gx / length) * LIGHT[0] + (gy / length) * LIGHT[1]
    line = np.clip(1.2 - np.maximum(-d, 0) / 1.3, 0, 1) * np.clip(0.5 - d, 0, 1)
    return (line * (0.25 + 0.75 * np.maximum(facing, 0) ** 2)).astype(np.float32)


@lru_cache(maxsize=64)
def soft_shadow(w, h, r, blur, offset):
    """(coverage, pad): a blurred copy of the shape, pad pixels larger on each side, moved down by offset."""
    pad = int(blur * 3 + offset + 2)
    d = rounded_rect_sdf(w, h, r, pad=pad)
    mask = np.clip(0.5 - d, 0, 1).astype(np.float32)
    shifted = np.zeros_like(mask)
    shifted[offset:] = mask[:-offset] if offset else mask
    return cv2.GaussianBlur(shifted, (0, 0), blur), pad


@lru_cache(maxsize=128)
def _solid(h, w, color):
    """An opaque BGRA image of one colour (read-only, shared)."""
    image = np.empty((h, w, 4), np.uint8)
    image[:] = (color[2], color[1], color[0], 255)
    image.flags.writeable = False
    return image


class Layer:
    """A picture with transparency, kept as premultiplied BGRA (what UpdateLayeredWindow takes).

    Everything is painted "over" what is there: dst = colour * a + dst * (1 - a),
    alpha included, with a = coverage x opacity; one OpenCV call per paint.
    """

    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.pixels = np.zeros((self.h, self.w, 4), np.uint8)

    def copy(self):
        other = Layer.__new__(Layer)
        other.w, other.h, other.pixels = self.w, self.h, self.pixels.copy()
        return other

    @property
    def alpha(self):
        """Coverage 0..1 (for checks; drawing never needs it)."""
        return self.pixels[..., 3].astype(np.float32) * np.float32(1 / 255)

    def paint(self, x, y, coverage, color, opacity=1.0):
        """Lay colour over the picture where coverage (h, w; 0..1) says, at (x, y).

        color: (r, g, b) 0..255, or an RGB uint8 image the size of coverage.
        """
        x, y = int(round(x)), int(round(y))
        h, w = coverage.shape
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, self.w), min(y + h, self.h)
        if x0 >= x1 or y0 >= y1 or opacity <= 0:
            return
        sl = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
        a = coverage[sl] if opacity >= 1 else coverage[sl] * np.float32(opacity)
        if isinstance(color, np.ndarray):
            source = cv2.cvtColor(np.ascontiguousarray(color[sl]), cv2.COLOR_RGB2BGRA)
        else:
            source = _solid(y1 - y0, x1 - x0, tuple(int(c) for c in color))
        region = self.pixels[y0:y1, x0:x1]
        cv2.blendLinear(region, source, 1 - a, a, dst=region)

    def bgra(self):
        """The picture as premultiplied BGRA (h, w, 4), ready for LayeredWindow.show."""
        return self.pixels

    # -- shapes ---------------------------------------------------------------------------

    def round_rect(self, x, y, w, h, r, color, opacity=1.0):
        w, h = int(round(w)), int(round(h))
        if w > 0 and h > 0:
            self.paint(x, y, round_mask(w, h, int(round(r))), color, opacity)

    def panel(self, x, y, w, h, r, color=(16, 18, 28), opacity=0.86, shadow=0.35, rim=0.55, blur=5.0, offset=3):
        """The background of a widget: dark frosted glass with a lit edge and a soft shadow.

        The shadow reaches about 3 x blur + offset pixels beyond the panel; leave that much room.
        """
        x, y, w, h, r = (int(round(v)) for v in (x, y, w, h, r))
        if shadow:
            coverage, pad = soft_shadow(w, h, r, float(blur), int(round(offset)))
            self.paint(x - pad, y - pad, coverage, (0, 0, 0), shadow)
        self.paint(x, y, round_mask(w, h, r), color, opacity)
        if rim:
            self.paint(x, y, rim_light(w, h, r), (255, 255, 255), rim)

    def text(self, text, x, y, size, color, weight="regular", anchor="lt", opacity=1.0, max_width=None):
        """One line of text; anchor as in glass.blit_text. Too long for max_width: shortened with «…»."""
        if not text:
            return 0
        size = int(round(size))
        coverage, _inv, _col, ascent = _sprite(text, weight, size, tuple(color))
        if max_width is not None and coverage.shape[1] > max_width:
            while len(text) > 1 and coverage.shape[1] > max_width:
                text = text[:-1]
                coverage, _inv, _col, ascent = _sprite(text.rstrip() + "…", weight, size, tuple(color))
        h, w = coverage.shape
        hx = {"l": 0, "m": w / 2, "r": w}[anchor[0]]
        vy = {"t": 0, "m": 1 + ascent - 0.36 * size, "b": h}[anchor[1]]
        self.paint(x - hx, y - vy, coverage, color, opacity)
        return w

    def icon(self, glyph, cx, cy, size, color, opacity=1.0):
        """A Segoe Fluent Icons glyph centred at (cx, cy)."""
        size = int(round(size))
        coverage, _inv, _col, _ascent = _sprite(glyph, "icons", size, tuple(color))
        h, w = coverage.shape
        self.paint(cx - w / 2, cy - h / 2, coverage, color, opacity)

    def image(self, rgb, x, y, w, h, r=0):
        """An RGB image scaled into the box, with rounded corners."""
        w, h = int(round(w)), int(round(h))
        if w <= 0 or h <= 0:
            return
        scaled = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        self.paint(x, y, round_mask(w, h, int(round(r))), scaled)

    def _shape(self, x0, y0, x1, y1, draw):
        """Coverage drawn by draw(mask, ox, oy) with OpenCV in the box (sub-pixel: coordinates x16)."""
        x0, y0 = int(math.floor(x0)) - 2, int(math.floor(y0)) - 2
        x1, y1 = int(math.ceil(x1)) + 2, int(math.ceil(y1)) + 2
        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        draw(mask, x0, y0)
        return x0, y0, mask.astype(np.float32) * np.float32(1 / 255)

    def circle(self, cx, cy, r, color, opacity=1.0):
        x, y, coverage = self._shape(cx - r, cy - r, cx + r, cy + r, lambda m, ox, oy: cv2.circle(
            m, (int((cx - ox) * 16), int((cy - oy) * 16)), int(r * 16), 255, -1, cv2.LINE_AA, 4))
        self.paint(x, y, coverage, color, opacity)

    def arc(self, cx, cy, r, width, color, opacity=1.0, start=0.0, extent=360.0):
        """A ring of the given line width; start and extent in degrees, clockwise from the top."""
        if extent <= 0:
            return
        o = r + width

        def draw(m, ox, oy):
            centre = (int((cx - ox) * 16), int((cy - oy) * 16))
            cv2.ellipse(m, centre, (int(r * 16), int(r * 16)), -90, start, start + min(extent, 360.0), 255,
                        max(1, int(round(width))), cv2.LINE_AA, 4)
        x, y, coverage = self._shape(cx - o, cy - o, cx + o, cy + o, draw)
        self.paint(x, y, coverage, color, opacity)

    def capsule(self, x, y, w, h, color, opacity=1.0):
        """A filled pill (a rounded bar), at fractional coordinates."""
        r = min(w, h) / 2

        def draw(m, ox, oy):
            for cx in (x + r, x + w - r):
                cv2.circle(m, (int((cx - ox) * 16), int((y + r - oy) * 16)), int(r * 16), 255, -1, cv2.LINE_AA, 4)
            if w > 2 * r:
                cv2.rectangle(m, (int((x + r - ox) * 16), int((y - oy) * 16)),
                              (int((x + w - r - ox) * 16), int((y + h - oy) * 16)), 255, -1, cv2.LINE_AA, 4)
        px, py, coverage = self._shape(x, y, x + w, y + h, draw)
        self.paint(px, py, coverage, color, opacity)

    def polyline(self, points, color, width=2.0, opacity=1.0):
        """A smooth line through (x, y) points."""
        if len(points) < 2:
            return
        xs, ys = [p[0] for p in points], [p[1] for p in points]

        def draw(m, ox, oy):
            pts = np.array([[(px - ox) * 16, (py - oy) * 16] for px, py in points], np.int32)
            cv2.polylines(m, [pts], False, 255, max(1, int(round(width))), cv2.LINE_AA, 4)
        x, y, coverage = self._shape(min(xs) - width, min(ys) - width, max(xs) + width, max(ys) + width, draw)
        self.paint(x, y, coverage, color, opacity)
