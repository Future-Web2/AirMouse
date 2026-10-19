"""Floating windows and the RGBA picture they show.

The windows made here show fully transparent pictures far off-screen, so the
user sees nothing; mouse messages are sent to them directly.
"""

import ctypes
import unittest
from ctypes import wintypes

import numpy as np

from airmouse import overlay
from airmouse.overlay import Layer, LayeredWindow

user32 = ctypes.WinDLL("user32")
user32.IsWindow.argtypes = (wintypes.HWND,)


def lparam(x, y):
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


class LayerTest(unittest.TestCase):
    def test_paint_is_over_with_premultiplied_colour(self):
        layer = Layer(4, 3)
        full = np.ones((3, 4), np.float32)
        layer.paint(0, 0, full, (255, 0, 0), 0.5)
        np.testing.assert_allclose(layer.bgra()[1, 1], (0, 0, 128, 128), atol=1)    # blue, green, red, alpha
        layer.paint(0, 0, full, (0, 0, 255), 0.5)
        np.testing.assert_allclose(layer.bgra()[1, 1], (128, 0, 64, 191), atol=1)
        self.assertAlmostEqual(float(layer.alpha[1, 1]), 0.75, delta=0.01)

    def test_image_paint(self):
        layer = Layer(3, 2)
        image = np.zeros((2, 3, 3), np.uint8)
        image[..., 0] = 200                                   # red, as an RGB image
        layer.paint(0, 0, np.ones((2, 3), np.float32), image)
        np.testing.assert_array_equal(layer.bgra()[0, 0], (0, 0, 200, 255))

    def test_paint_clips_at_the_edges(self):
        layer = Layer(5, 5)
        layer.paint(-2, 3, np.ones((4, 4), np.float32), (255, 255, 255))
        self.assertEqual(int((layer.alpha > 0).sum()), 2 * 2)

    def test_text_and_shortening(self):
        layer = Layer(400, 60)
        width = layer.text("Голосовой ввод и ещё очень длинная надпись", 0, 30, 16, (255, 255, 255),
                           anchor="lm", max_width=120)
        self.assertLessEqual(width, 120)
        self.assertGreater(float(layer.alpha.max()), 0.9)

    def test_panel_is_opaque_inside_and_fades_outside(self):
        layer = Layer(200, 140)
        layer.panel(30, 30, 140, 80, 16, blur=5, offset=3)
        self.assertGreater(float(layer.alpha[70, 100]), 0.8)
        self.assertLess(float(layer.alpha[0, 0]), 0.01)      # the shadow is gone by the border

    def test_shapes(self):
        layer = Layer(80, 80)
        layer.arc(40, 40, 20, 3, (255, 200, 0), extent=180)
        right, left = layer.alpha[:, 41:].sum(), layer.alpha[:, :39].sum()
        self.assertGreater(right, 10 * max(left, 1e-3))      # half a ring: clockwise from the top
        layer.circle(10, 10, 4, (255, 255, 255))
        layer.capsule(5, 60, 60, 8, (255, 255, 255))
        layer.polyline([(5, 70), (40, 75), (75, 70)], (255, 0, 0))
        self.assertGreater(float(layer.alpha[10, 10]), 0.9)


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.window = LayeredWindow(on_mouse=lambda *args: self.calls.append(args), hand_at=lambda x, y: True)
        self.window.show(np.zeros((30, 40, 4), np.uint8), -9000, -9000)   # transparent and far away

    def tearDown(self):
        self.window.destroy()

    def send(self, msg, wparam=0, lp=0):
        return overlay.user32.SendMessageW(self.window.hwnd, msg, wparam, lp)

    def test_style_never_takes_the_focus(self):
        ex = overlay.user32.GetWindowLongW(self.window.hwnd, -20)
        for flag in (overlay.WS_EX_LAYERED, overlay.WS_EX_TOPMOST, overlay.WS_EX_TOOLWINDOW,
                     overlay.WS_EX_NOACTIVATE):
            self.assertTrue(ex & flag)
        self.assertFalse(ex & overlay.WS_EX_TRANSPARENT)
        self.assertEqual(self.send(overlay.WM_MOUSEACTIVATE), overlay.MA_NOACTIVATE)
        self.assertTrue(self.window.visible)

    def test_mouse_messages(self):
        self.send(overlay.WM_MOUSEMOVE, 0, lparam(5, 6))
        self.send(overlay.WM_LBUTTONDOWN, 1, lparam(10, 12))
        self.send(overlay.WM_LBUTTONUP, 0, lparam(11, 13))
        self.send(overlay.WM_MOUSEWHEEL, (-120 & 0xFFFF) << 16, lparam(-9000 + 7, -9000 + 8))
        kinds = [c[0] for c in self.calls]
        self.assertEqual(kinds[:4], ["move", "down", "up", "cancel"])   # releasing the capture comes after "up"
        self.assertEqual(self.calls[1][1:3], (10, 12))
        self.assertEqual(self.calls[-1], ("wheel", 7, 8, -120))

    def test_resize_and_move(self):
        self.window.show(np.zeros((50, 60, 4), np.uint8), -9100, -9100)
        self.assertEqual((self.window.w, self.window.h), (60, 50))
        self.window.move(-9200, -9150)
        self.assertEqual((self.window.x, self.window.y), (-9200, -9150))
        self.window.hide()
        self.assertFalse(overlay.user32.IsWindowVisible(self.window.hwnd))


class ClickThroughTest(unittest.TestCase):
    def test_click_through_window(self):
        window = LayeredWindow(click_through=True)
        try:
            ex = overlay.user32.GetWindowLongW(window.hwnd, -20)
            self.assertTrue(ex & overlay.WS_EX_TRANSPARENT)
        finally:
            hwnd = window.hwnd
            window.destroy()
        self.assertNotIn(hwnd, overlay._windows)
        self.assertFalse(user32.IsWindow(hwnd))


if __name__ == "__main__":
    unittest.main()
