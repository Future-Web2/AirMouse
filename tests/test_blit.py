"""The window image goes to Windows unchanged: colour order, row order, every pixel."""

import ctypes
import unittest
from ctypes import wintypes

import numpy as np

from airmouse.blit import BITMAPINFOHEADER, Blitter

gdi32 = ctypes.WinDLL("gdi32")
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.GdiFlush.argtypes = ()


class BlitTest(unittest.TestCase):
    def test_image_arrives_unchanged(self):
        w, h = 70, 45
        rgb = np.random.default_rng(0).integers(0, 256, (h, w, 3), dtype=np.uint8)
        dc = gdi32.CreateCompatibleDC(None)
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                  biBitCount=32)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(dc, bitmap)
        try:
            Blitter(None, w, h).show(rgb, hdc=dc)
            gdi32.GdiFlush()
            bgra = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8)), (h, w, 4))
            np.testing.assert_array_equal(bgra[..., 2::-1], rgb)
        finally:
            gdi32.DeleteDC(dc)
            gdi32.DeleteObject(bitmap)

    def test_nothing_to_repaint_before_the_first_image(self):
        Blitter(None, 10, 10).repaint()   # must not draw (or fail) without an image


if __name__ == "__main__":
    unittest.main()
