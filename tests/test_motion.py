"""Cursor motion building blocks: the One Euro filter and the pointer (glide, leash, hold)."""

import math
import unittest

from airmouse.filters import OneEuroFilter2D
from airmouse.pointer import GLIDE_TIME, Pointer


class OneEuroTest(unittest.TestCase):
    def test_first_sample_passes_through(self):
        self.assertEqual(OneEuroFilter2D()(10.0, 20.0, 0.0), (10.0, 20.0))

    def test_converges_to_a_still_point(self):
        f = OneEuroFilter2D(min_cutoff=1.0, beta=0.0)
        f(0.0, 0.0, 0.0)
        for i in range(1, 120):
            x, y = f(100.0, 50.0, i / 30)
        self.assertAlmostEqual(x, 100.0, places=2)
        self.assertAlmostEqual(y, 50.0, places=2)

    def test_smooths_slow_shaking_more_than_fast_movement(self):
        f = OneEuroFilter2D(min_cutoff=1.0, beta=0.05)
        f(0.0, 0.0, 0.0)
        x, _ = f(10.0, 0.0, 1 / 30)
        slow = x / 10.0                    # share of a small step passed on at once
        g = OneEuroFilter2D(min_cutoff=1.0, beta=0.05)
        g(0.0, 0.0, 0.0)
        for i in range(1, 10):
            x, _ = g(100.0 * i, 0.0, i / 30)
        fast = 1 - (900.0 - x) / 100.0     # share of the last step passed on while moving fast
        self.assertGreater(fast, slow)

    def test_same_time_twice_keeps_the_value(self):
        f = OneEuroFilter2D()
        f(1.0, 1.0, 0.0)
        self.assertEqual(f(50.0, 50.0, 0.0), (1.0, 1.0))

    def test_reset(self):
        f = OneEuroFilter2D()
        f(1.0, 1.0, 0.0)
        f.reset()
        self.assertEqual(f(7.0, 8.0, 1.0), (7.0, 8.0))


class PointerTest(unittest.TestCase):
    def pointer(self, at=(500.0, 500.0)):
        p = Pointer(1920, 1080)
        p.start(at, at)
        p.follow(at, 0.0, 10.0, [])
        return p

    def test_shaking_inside_the_leash_does_not_move_the_cursor(self):
        p = self.pointer()
        actions = []
        for i in range(1, 30):
            p.follow((500 + 8 * math.sin(i), 500 + 8 * math.cos(i)), i / 30, 10.0, actions)
        self.assertEqual(actions, [])

    def test_the_leash_pulls_the_cursor_along(self):
        p = self.pointer()
        actions = []
        p.follow((530.0, 500.0), 1 / 30, 10.0, actions)
        self.assertEqual(actions, [("move", 520, 500)])

    def test_hold_pins_the_cursor(self):
        p = self.pointer()
        actions = []
        p.hold((500.0, 500.0), actions)
        p.follow((700.0, 500.0), 1 / 30, 10.0, actions)
        self.assertEqual(p.cursor, (500.0, 500.0))

    def test_release_glides_back_instead_of_jumping(self):
        p = self.pointer()
        p.hold((500.0, 500.0), [])
        p.release((700.0, 500.0))
        p.follow((700.0, 500.0), 1 / 30, 0.0, [])
        self.assertLess(p.cursor[0], 560)               # still close to where it was held
        for i in range(2, int(6 * GLIDE_TIME * 30)):
            p.follow((700.0, 500.0), i / 30, 0.0, [])
        self.assertGreater(p.cursor[0], 695)            # and then arrives

    def test_position_before(self):
        p = self.pointer()
        for i in range(1, 10):
            p.follow((500.0 + 20 * i, 500.0), i / 30, 0.0, [])
        self.assertAlmostEqual(p.position_before(4.5 / 30)[0], 580.0)

    def test_cursor_stays_on_screen(self):
        p = self.pointer()
        p.follow((5000.0, -300.0), 1 / 30, 0.0, [])
        self.assertEqual(p.cursor, (1919.0, 0.0))


if __name__ == "__main__":
    unittest.main()
