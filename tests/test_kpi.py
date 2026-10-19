"""Cursor-quality KPIs of docs/KPI.md, checked on every run (simulated hand, real gesture engine)."""

import unittest

from airmouse import bench


class CursorKpiTest(unittest.TestCase):
    def test_still_hand_keeps_the_cursor_still(self):
        self.assertEqual(bench.still_hand(), {"moves_per_min": 0.0, "spread_px": 0.0})

    def test_still_hand_in_bad_light(self):
        self.assertLessEqual(bench.still_hand(sigma=1.5, common=1.0, fps=15)["spread_px"], 3.0)

    def test_lag(self):
        self.assertLessEqual(bench.lag_ms(300), 90)
        self.assertLessEqual(bench.lag_ms(1500), 55)

    def test_click_lands_where_the_cursor_stopped(self):
        result = bench.click_offset()
        self.assertEqual(result["clicks"], 1)
        self.assertLessEqual(result["offset_px"], 2.0)

    def test_every_pinch_is_one_click(self):
        self.assertEqual(bench.pinch_series(), {"pinches": 20, "left": 20, "right": 0, "scroll": 0})

    def test_double_click(self):
        self.assertTrue(bench.double_click()["same_pixel"])

    def test_no_false_actions(self):
        self.assertEqual(bench.false_actions(), 0)

    def test_tracking_glitch_is_ignored(self):
        self.assertLessEqual(bench.glitch(), 2.0)


if __name__ == "__main__":
    unittest.main()
