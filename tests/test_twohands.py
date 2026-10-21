"""Two hands (a pointer hand and a hand of buttons), two-hand gestures and the dwell click (twohands.py)."""

import unittest

from airmouse import bench, tuning
from airmouse.bench import LEFT_REST, RIGHT_REST, TwoHandSim, cam_for, hand
from airmouse.gestures import HandFeatures
from airmouse.settings import Settings
from airmouse.twohands import HandControl


def tuned(**values):
    settings = Settings()
    for key, value in values.items():
        tuning.set_value(settings, key, value)
    return settings


RIGHT = dict(ox=RIGHT_REST[0], oy=RIGHT_REST[1])
LEFT = dict(ox=LEFT_REST[0], oy=LEFT_REST[1])


def pinch(sim, right, left, hold=5, pose="open"):
    """A pinch of the left (button) hand while the right one stays as given."""
    for p in (0.4, 0.8, 1.0):
        sim.step(right, dict(left, pinch=p, pose=pose))
    sim.rest(hold, right, dict(left, pinch=1.0, pose=pose))
    for p in (0.6, 0.2, 0.0):
        sim.step(right, dict(left, pinch=p, pose=pose))


class SplitTest(unittest.TestCase):
    def test_which_hand_is_which(self):
        right, left = hand(*RIGHT_REST), hand(*LEFT_REST, left=True)
        control = HandControl(Settings(), 1920, 1080)
        self.assertEqual(control.split([left, right]), (right, left))           # right hand: cursor
        self.assertEqual(control.split([right, left]), (right, left))
        self.assertEqual(control.split([left]), (left, None))                   # one hand: always the cursor
        self.assertEqual(control.split([]), (None, None))
        self.assertEqual(HandControl(tuned(pointer_hand=0), 1920, 1080).split([right, left]), (left, right))
        self.assertEqual(HandControl(tuned(mirror=0), 1920, 1080).split([right, left]), (left, right))
        self.assertEqual(HandControl(tuned(two_hands=0), 1920, 1080).split([left, right]), (left, None))

    def test_a_left_hand_reads_like_a_right_one(self):
        r, l = HandFeatures(hand(200, 200, 1.0)), HandFeatures(hand(200, 200, 1.0, left=True))
        self.assertAlmostEqual(r.pinch_index, l.pinch_index)
        self.assertTrue(HandFeatures(hand(200, 200, pose="thumb_down")).thumb_down)
        self.assertFalse(HandFeatures(hand(200, 200, pose="thumb")).thumb_down)
        self.assertTrue(HandFeatures(hand(200, 200)).open)


class ButtonHandTest(unittest.TestCase):
    def test_clicks_without_moving_the_cursor(self):
        result = bench.second_hand_clicks()
        self.assertEqual((result["down"], result["up"], result["other"]), (20, 20, 0))
        self.assertLessEqual(result["cursor_moved_px"], 3.0)

    def test_drag_while_the_pointer_hand_moves(self):
        sim = TwoHandSim(1)
        sim.rest(40, RIGHT, LEFT)
        for p in (0.4, 0.8, 1.0):
            sim.step(RIGHT, dict(LEFT, pinch=p))
        start = sim.cursor
        for i in range(1, 31):                                 # the pointer hand moves, the button stays down
            sim.step(dict(RIGHT, ox=RIGHT_REST[0] + 2 * i), dict(LEFT, pinch=1.0))
        for p in (0.6, 0.2, 0.0):
            sim.step(dict(RIGHT, ox=RIGHT_REST[0] + 60), dict(LEFT, pinch=p))
        self.assertEqual(sim.actions(), [("down", "left"), ("up", "left")])
        self.assertGreater(sim.cursor[0] - start[0], 200)

    def test_right_click_scroll_and_windows(self):
        sim = TwoHandSim(2)
        sim.rest(40, RIGHT, LEFT)
        pinch(sim, RIGHT, LEFT, pose="right")
        sim.rest(20, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [("click", "right")])
        sim.events.clear()
        sim.rest(10, RIGHT, dict(LEFT, pose="two"))
        for i in range(1, 21):                                 # two fingers, hand up: scroll up
            sim.step(RIGHT, dict(LEFT, oy=LEFT_REST[1] - 3 * i, pose="two"))
        wheel = [a[1] for a in sim.actions() if a[0] == "wheel"]
        self.assertTrue(wheel and all(w > 0 for w in wheel))
        self.assertEqual([a for a in sim.actions() if a[0] != "wheel"], [])
        sim.events.clear()
        sim.rest(20, RIGHT, LEFT)
        sim.rest(25, RIGHT, dict(LEFT, pose="thumb"))
        sim.rest(10, RIGHT, LEFT)
        sim.rest(25, RIGHT, dict(LEFT, pose="thumb_down"))
        sim.rest(10, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [("window", "maximize"), ("window", "minimize")])

    def test_off_when_one_hand_is_chosen(self):
        sim = TwoHandSim(3, settings=tuned(two_hands=0))
        sim.rest(40, RIGHT, LEFT)
        pinch(sim, RIGHT, LEFT)
        sim.rest(20, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [])

    def test_lost_button_hand_lets_go(self):
        sim = TwoHandSim(4)
        sim.rest(40, RIGHT, LEFT)
        for p in (0.4, 0.8, 1.0):
            sim.step(RIGHT, dict(LEFT, pinch=p))
        sim.rest(30, RIGHT, None)                              # one second out of view
        self.assertEqual(sim.actions(), [("down", "left"), ("up", "left")])


class BothHandsTest(unittest.TestCase):
    def test_each_gesture_once(self):
        self.assertEqual(bench.two_hand_gestures(), {"apart": True, "together": True, "pause_and_resume": True,
                                                     "enabled_after": True})

    def test_no_false_gestures_while_working(self):
        self.assertEqual(bench.two_hands_resting(), 0)

    def test_quick_cursor_sweep_is_not_a_gesture(self):
        """The pointer hand flies across while the other rests: only one hand moved."""
        sim = TwoHandSim(5)
        sim.rest(30, dict(RIGHT, ox=250), LEFT)
        for i in range(1, 9):
            sim.step(dict(RIGHT, ox=250 + 25 * i), LEFT)
        for i in range(1, 9):
            sim.step(dict(RIGHT, ox=450 - 25 * i), LEFT)
        sim.rest(30, dict(RIGHT, ox=250), LEFT)
        self.assertEqual(sim.actions(), [])

    def test_slow_spreading_is_not_a_gesture(self):
        sim = TwoHandSim(6)
        sim.rest(30, dict(RIGHT, ox=270), dict(LEFT, ox=200))
        for i in range(1, 61):                                 # two seconds
            k = i / 60
            sim.step(dict(RIGHT, ox=270 + 100 * k), dict(LEFT, ox=200 - 90 * k))
        self.assertEqual(sim.actions(), [])

    def test_pause_lets_nothing_through_but_its_own_gesture(self):
        sim = TwoHandSim(7)
        sim.rest(30, RIGHT, LEFT)
        sim.rest(40, dict(RIGHT, pose="thumb"), dict(LEFT, pose="thumb"))
        sim.rest(20, RIGHT, LEFT)
        self.assertFalse(sim.enabled)
        sim.events.clear()
        pinch(sim, RIGHT, LEFT)
        for i in range(1, 21):
            sim.step(dict(RIGHT, ox=RIGHT_REST[0] + 4 * i), LEFT)
        self.assertEqual(sim.actions(), [])                    # no clicks and no cursor moves (not even recorded)
        sim.rest(40, dict(RIGHT, pose="thumb"), dict(LEFT, pose="thumb"))
        self.assertEqual(sim.actions(), [("pause",)])
        self.assertTrue(sim.enabled)

    def test_one_thumb_still_shows_the_widgets(self):
        sim = TwoHandSim(8)
        sim.rest(30, RIGHT, LEFT)
        sim.rest(25, dict(RIGHT, pose="thumb"), LEFT)
        sim.rest(10, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [("widgets",)])

    def test_combos_can_be_switched_off(self):
        sim = TwoHandSim(9, settings=tuned(hand_combos=0))
        sim.rest(30, RIGHT, LEFT)
        sim.rest(40, dict(RIGHT, pose="thumb"), dict(LEFT, pose="thumb"))
        self.assertNotIn(("pause",), sim.actions())
        self.assertTrue(sim.enabled)


class DwellTest(unittest.TestCase):
    def test_still_cursor_clicks_once_per_place(self):
        result = bench.dwell_clicks()
        self.assertEqual(result["clicks"], 2)
        self.assertLess(result["first_after_s"], 2.0)

    def test_off_by_default(self):
        sim = TwoHandSim(10)
        sim.rest(120, dict(ox=cam_for(800, 500)[0], oy=cam_for(800, 500)[1]))
        self.assertEqual(sim.actions(), [])

    def test_no_second_click_right_after_a_pinch(self):
        sim = TwoHandSim(11, settings=tuned(dwell_click=1, dwell_ms=600))
        sim.rest(60, RIGHT, LEFT)                              # a dwell click
        sim.events.clear()
        pinch(sim, RIGHT, LEFT)                                # a click with the other hand, then stay still
        sim.rest(60, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [("down", "left"), ("up", "left")])

    def test_slider_size_and_time(self):
        settings = tuned(dwell_click=1, dwell_ms=2500)
        sim = TwoHandSim(12, settings=settings)
        sim.rest(60, RIGHT)
        self.assertEqual(sim.actions(), [])                    # 2 s are not enough
        sim.rest(45, RIGHT)
        self.assertEqual(sim.actions(), [("click", "left")])


if __name__ == "__main__":
    unittest.main()
