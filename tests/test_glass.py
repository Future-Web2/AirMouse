"""Liquid Glass rendering: the faster drawing must look the same as the straightforward one."""

import unittest

import cv2
import numpy as np

from airmouse import glass
from airmouse.glass import STYLES, Glass, LiquidBackdrop


def reference_draw(g, frame, x, y, lift=0.0, tint_alpha=None, tint=None):
    """Glass.draw as AirMouse 1.0.0 did it: every step at full size, the whole shadow blended."""
    if g.shadow:
        m = g.shadow_pad
        glass.blend(frame, x - m, y - m, g._black, g._shadow_keep, g._shadow_dark)
    cw, ch = g._crop_size
    src = glass._crop(frame, x - g.pad, y - g.pad, cw, ch)
    if g.f > 1:
        src = cv2.resize(src, (cw // g.f, ch // g.f), interpolation=cv2.INTER_AREA)
    if g.blur > 0.5:
        src = cv2.GaussianBlur(src, (0, 0), g.blur / g.f)
    if len(g._maps) == 3:
        out = cv2.merge([cv2.extractChannel(cv2.remap(src, m1, m2, cv2.INTER_LINEAR,
                                                      borderMode=cv2.BORDER_REPLICATE), c)
                         for c, (m1, m2) in enumerate(g._maps)])
    else:
        out = cv2.remap(src, *g._maps[0], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gray = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    out = cv2.addWeighted(out, g.saturation, gray, 1 - g.saturation, lift)
    ta = g.tint_alpha if tint_alpha is None else tint_alpha
    if ta > 0:
        out = cv2.addWeighted(out, 1 - ta, np.full((g.h, g.w, 3), tint or g.tint, np.uint8), ta, 0)
    out = cv2.add(out, g._highlight)
    glass.blend(frame, x, y, out, g.mask_inv, g.mask)


def background(w=900, h=700):
    """Soft colour blobs with sharp detail on top, like a camera image."""
    img = LiquidBackdrop(w, h, seed=3).render(1.7)
    rng = np.random.default_rng(1)
    for _ in range(60):
        p1 = tuple(int(v) for v in rng.integers(0, (w, h)))
        p2 = tuple(int(v) for v in rng.integers(0, (w, h)))
        cv2.line(img, p1, p2, tuple(int(c) for c in rng.integers(0, 256, 3)), 2, cv2.LINE_AA)
    return img


class GlassMatchesReferenceTest(unittest.TestCase):
    def check(self, w, h, r, style, x, y, **draw_args):
        g = Glass(w, h, r, **STYLES[style])
        expected, actual = background(), background()
        reference_draw(g, expected, x, y, **draw_args)
        g.draw(actual, x, y, **draw_args)
        d = np.abs(expected.astype(int) - actual.astype(int)).max(axis=2)
        self.assertLessEqual(d.max(), 10, f"{style} {w}x{h} at {x},{y}")
        self.assertLess(d.mean(), 1.0, f"{style} {w}x{h} at {x},{y}")

    def test_big_panel_with_shadow(self):
        self.check(560, 600, 48, "panel", 300, 40)

    def test_panel_partly_outside_the_frame(self):
        self.check(560, 600, 48, "panel", 500, -60)

    def test_button_with_colour_dispersion(self):
        self.check(330, 78, 39, "accent", 100, 300, lift=16)

    def test_knob_while_dragged(self):
        self.check(44, 34, 17, "knob", 420, 500, tint_alpha=0.3)

    def test_pill(self):
        self.check(160, 54, 27, "pill", 600, 620)


class SplitTest(unittest.TestCase):
    def test_solid_parts_and_corners_cover_the_shape_once(self):
        g = Glass(400, 300, 40, **STYLES["panel"])
        cover = np.zeros((g.h, g.w), int)
        for y0, y1, x0, x1 in g._solid:
            self.assertTrue((g.mask[y0:y1, x0:x1] == 1).all())
            cover[y0:y1, x0:x1] += 1
        for y0, y1, x0, x1 in g._corners:
            cover[y0:y1, x0:x1] += 1
        self.assertTrue((cover == 1).all())

    def test_small_shapes_are_blended_whole(self):
        g = Glass(40, 30, 15, **STYLES["knob"])
        self.assertIsNone(g._solid)


class BlendTest(unittest.TestCase):
    def test_clips_at_the_frame_edges(self):
        frame = np.zeros((20, 20, 3), np.uint8)
        image = np.full((10, 10, 3), 200, np.uint8)
        keep = np.zeros((10, 10), np.float32)
        glass.blend(frame, -5, 15, image, keep, 1 - keep)
        self.assertEqual(int(frame.sum()), 200 * 3 * 5 * 5)
        self.assertTrue((frame[15:, :5] == 200).all())


class BackdropTest(unittest.TestCase):
    def test_draws_into_the_given_image(self):
        backdrop = LiquidBackdrop(320, 240)
        out = np.zeros((240, 320, 3), np.uint8)
        self.assertIs(backdrop.render(2.0, out=out), out)
        self.assertGreater(out.mean(), 10)


if __name__ == "__main__":
    unittest.main()
