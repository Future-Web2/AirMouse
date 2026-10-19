"""Put an RGB image straight into a window with GDI.

The Liquid Glass window is one image redrawn ~30 times a second. Handing it to
Tk as a photo image cost almost as much as drawing it (13 ms at 150% scale, the
image is converted and copied on the way); one SetDIBitsToDevice call is a
single copy.
"""

import ctypes
from ctypes import wintypes

import cv2
import numpy as np

_user32 = ctypes.WinDLL("user32")
_gdi32 = ctypes.WinDLL("gdi32")


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


_user32.GetDC.argtypes = (wintypes.HWND,)
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
_gdi32.SetDIBitsToDevice.argtypes = (
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
    wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
)

DIB_RGB_COLORS = 0


class Blitter:
    """Shows w x h RGB images in the window hwnd (a Tk widget with no background of its own)."""

    def __init__(self, hwnd, w, h):
        self.hwnd, self.w, self.h = hwnd, w, h
        self._bgra = np.zeros((h, w, 4), np.uint8)   # GDI wants BGR(A) rows; 32 bits keeps them aligned
        self._header = BITMAPINFOHEADER(
            biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h,   # negative: rows top to bottom
            biPlanes=1, biBitCount=32, biCompression=0,
        )
        self._shown = False

    def show(self, rgb, hdc=None):
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGRA, dst=self._bgra)
        self._shown = True
        self.repaint(hdc)

    def repaint(self, hdc=None):
        """Draw the last image again (after the window was covered), or into another device context."""
        if not self._shown:
            return
        dc = hdc or _user32.GetDC(self.hwnd)
        try:
            _gdi32.SetDIBitsToDevice(dc, 0, 0, self.w, self.h, 0, 0, 0, self.h, self._bgra.ctypes.data,
                                     ctypes.byref(self._header), DIB_RGB_COLORS)
        finally:
            if hdc is None:
                _user32.ReleaseDC(self.hwnd, dc)
