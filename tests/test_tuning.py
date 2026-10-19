"""«Подробнее»: the parameters, and that each one really changes what AirMouse does."""

import unittest

from airmouse import bench, tuning
from airmouse.bench import HandSim, cam_for
from airmouse.settings import Settings


def tuned(**values):
    settings = Settings()
    for key, value in values.items():
        tuning.set_value(settings, key, value)
    return settings


class ParamsTest(unittest.TestCase):
    def test_defaults_and_groups(self):
        settings = Settings()
        self.assertEqual(tuning.changed(settings), [])
        for param in tuning.PARAMS:
            self.assertIn(param.group, tuning.GROUPS)
            self.assertEqual(tuning.get(settings, param.key), param.default)
            if not param.choices:
                self.assertTrue(param.lo <= param.default <= param.hi, param.key)
        self.assertGreaterEqual(len(tuning.PARAMS), 20)

    def test_values_are_checked(self):
        settings = Settings()
        settings.advanced = {"camera_fps": 45, "deadzone": 99, "glide_ms": "fast", "pinch_confirm_ms": -5}
        self.assertEqual(tuning.get(settings, "camera_fps"), 30)        # not one of the choices
        self.assertEqual(tuning.get(settings, "deadzone"), 3.0)         # clamped
        self.assertEqual(tuning.get(settings, "glide_ms"), 150)         # not a number
        self.assertEqual(tuning.get(settings, "pinch_confirm_ms"), 0)
        self.assertEqual(tuning.seconds(Settings(), "post_click_ms"), 0.5)

    def test_only_changes_are_stored(self):
        settings = tuned(camera_fps=60, glide_ms=150)
        self.assertEqual(settings.advanced, {"camera_fps": 60.0})
        tuning.set_value(settings, "camera_fps", 30)
        self.assertEqual(settings.advanced, {})


class SixtyFramesTest(unittest.TestCase):
    """Confirmations are times, so 60 frames per second keeps the cursor KPIs of 30."""

    def test_pinches_at_60(self):
        self.assertEqual(bench.pinch_series(fps=60), {"pinches": 20, "left": 20, "right": 0, "scroll": 0,
                                                      "widgets": 0})

    def test_still_hand_and_shaking_at_60(self):
        self.assertEqual(bench.still_hand(fps=60)["moves_per_min"], 0.0)
        self.assertEqual(bench.false_actions(seconds=30, fps=60), 0)


class EffectTest(unittest.TestCase):
    def test_deadzone(self):
        loose = bench.still_hand(sigma=1.5, common=1.0, settings=tuned(deadzone=0.0))
        firm = bench.still_hand(sigma=1.5, common=1.0, settings=tuned(deadzone=2.0))
        self.assertGreater(loose["moves_per_min"], 100)
        self.assertEqual(firm["moves_per_min"], 0.0)

    def test_outlier_filter(self):
        self.assertLessEqual(bench.glitch(), 2.0)
        self.assertGreater(bench.glitch(settings=tuned(outlier_filter=0)), 5.0)

    def test_pinch_confirmation_time(self):
        def first_press(settings):
            sim = HandSim(sigma=0, common=0, settings=settings)
            ox, oy = cam_for(960, 540)
            sim.rest(30, ox, oy)
            start = sim.t
            sim.rest(15, ox, oy, pinch=1.0)
            return sim.engine._pinch_start - start
        self.assertLess(first_press(tuned(pinch_confirm_ms=0)), first_press(tuned(pinch_confirm_ms=200)))

    def test_thumbs_up_hold_time(self):
        def toggle_after(settings):
            sim = HandSim(sigma=0, common=0, settings=settings)
            ox, oy = cam_for(960, 540)
            sim.rest(30, ox, oy)
            start = sim.t
            sim.rest(60, ox, oy, pose="thumb")
            return next(t for t, action, _c in sim.events if action == ("widgets",)) - start
        self.assertAlmostEqual(toggle_after(Settings()), 0.53, delta=0.05)
        self.assertAlmostEqual(toggle_after(tuned(thumb_ms=1200)), 1.23, delta=0.05)


if __name__ == "__main__":
    unittest.main()
