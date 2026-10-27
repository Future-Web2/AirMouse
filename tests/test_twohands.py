"""Two hands (a pointer hand and a hand of buttons), two-hand gestures and the dwell click (twohands.py)."""

import unittest

from airmouse import bench, i18n, tuning
from airmouse.app_base import gesture_rows
from airmouse.bench import LEFT_REST, RIGHT_REST, TwoHandSim, cam_for, hand
from airmouse.gestures import HandFeatures
from airmouse.settings import Settings
from airmouse.twohands import PRECISE, SWIPES, ZOOM, Dwell, HandControl


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

    def test_kinds_picked_on_the_panel(self):
        self.assertEqual(bench.dwell_kinds(), {"as_picked": True, "kind_after": "left"})

    def test_own_panel_always_gets_a_plain_click(self):
        dwell = Dwell(tuned(dwell_click=1, dwell_ms=500))
        dwell.choose("right")
        self.assertEqual(dwell.update((100, 100), 0.0, True, own=True), [])
        self.assertEqual(dwell.update((100, 100), 0.6, True, own=True), [("click", "left")])
        self.assertEqual(dwell.kind, "right")                  # still picked for the next dwell elsewhere
        dwell.choose("nonsense")
        self.assertEqual(dwell.kind, "right")

    def test_a_dwell_drag_is_let_go_on_pause_and_when_switched_off(self):
        settings = tuned(dwell_click=1, dwell_ms=500)
        dwell = Dwell(settings)
        dwell.choose("drag")
        dwell.update((100, 100), 0.0, True)
        self.assertEqual(dwell.update((100, 100), 0.6, True), [("down", "left")])
        self.assertEqual(dwell.release_all(), [("up", "left")])
        dwell.choose("drag")
        dwell.update((300, 100), 1.0, True)
        self.assertEqual(dwell.update((300, 100), 1.6, True), [("down", "left")])
        tuning.set_value(settings, "dwell_click", 0)
        self.assertEqual(dwell.update((300, 100), 1.7, True), [("up", "left")])


class PreciseCursorTest(unittest.TestCase):
    def test_the_l_is_neither_a_pinch_nor_a_pose_of_its_own(self):
        f = HandFeatures(hand(200, 200, pose="l"))
        self.assertTrue(f.l_shape)
        self.assertFalse(f.open or f.two_fingers or f.thumb_up or f.thumb_down)
        self.assertGreater(min(f.pinch_index, f.pinch_middle), 0.6)
        self.assertTrue(HandFeatures(hand(200, 200, pose="l", left=True)).l_shape)
        for pose in ("open", "two", "thumb", "thumb_down", "right"):
            self.assertFalse(HandFeatures(hand(200, 200, pose=pose)).l_shape, pose)

    def test_slower_cursor_and_no_jump_after(self):
        result = bench.precise_cursor()
        self.assertAlmostEqual(result["share_of_movement"], 0.3, delta=0.05)
        self.assertLessEqual(result["jump_after_px"], 3.0)
        self.assertLessEqual(result["click_from_aim_px"], 3.0)

    def test_shown_as_its_own_mode(self):
        sim = TwoHandSim(20)
        sim.rest(20, RIGHT, LEFT)
        self.assertEqual(sim.control.mode, "move")
        sim.rest(10, RIGHT, dict(LEFT, pose="l"))
        self.assertEqual(sim.control.mode, PRECISE)
        sim.rest(10, RIGHT, LEFT)
        self.assertEqual(sim.control.mode, "move")
        self.assertEqual(sim.actions(), [])

    def test_off_at_speed_one(self):
        sim = TwoHandSim(21, settings=tuned(precise_speed=1.0))
        sim.rest(20, RIGHT, dict(LEFT, pose="l"))
        self.assertEqual(sim.control.mode, "move")

    def test_pointing_past_the_edge_still_reaches_it(self):
        sim = TwoHandSim(22)
        sim.rest(20, RIGHT, dict(LEFT, pose="l"))
        for i in range(1, 31):                                 # precise: the cursor stays well left of the hand
            sim.step(dict(RIGHT, ox=RIGHT_REST[0] + 3 * i), dict(LEFT, pose="l"))
        sim.rest(10, dict(RIGHT, ox=RIGHT_REST[0] + 90), LEFT)
        right_edge = cam_for(1919, 540)[0]
        for i in range(1, 21):                                 # now the hand goes right, to the edge and on
            sim.step(dict(RIGHT, ox=RIGHT_REST[0] + 90 + (right_edge + 60 - RIGHT_REST[0] - 90) * i / 20), LEFT)
        sim.rest(20, dict(RIGHT, ox=right_edge + 60), LEFT)
        self.assertGreaterEqual(sim.cursor[0], 1915)


class ZoomTest(unittest.TestCase):
    def test_both_v_apart_and_together(self):
        self.assertEqual(bench.zoom_gesture(), {"zoom_in_steps": 3, "zoom_out_steps": -3, "other_actions": 0})

    def test_magnifier_and_off(self):
        sim = TwoHandSim(23, settings=tuned(zoom_mode=2))
        right, left = dict(RIGHT, ox=300, pose="two"), dict(LEFT, ox=200, pose="two")
        sim.rest(20, right, left)
        for i in range(1, 16):
            sim.step(dict(right, ox=300 + 4 * i), dict(left, ox=200 - 4 * i))
        self.assertEqual(sim.actions(), [("keys", "win+plus")] * 2)
        sim = TwoHandSim(23, settings=tuned(zoom_mode=0))
        sim.rest(20, right, left)
        for i in range(1, 16):
            sim.step(dict(right, ox=300 + 4 * i), dict(left, ox=200 - 4 * i))
        self.assertNotIn("zoom", [a[0] for a in sim.actions()])
        self.assertNotEqual(sim.control.mode, ZOOM)


class SwipeTest(unittest.TestCase):
    def test_slides_and_no_false_swipes(self):
        self.assertEqual(bench.swipes(), {"next": True, "previous": True, "both_apart_is_all_windows": True,
                                          "coming_into_view": 0})

    def test_nothing_until_a_command_is_picked(self):
        sim = TwoHandSim(24)
        sim.rest(30, RIGHT, dict(LEFT, ox=230))
        for i in range(1, 7):
            sim.step(RIGHT, dict(LEFT, ox=230 - 30 * i))
        sim.rest(20, RIGHT, dict(LEFT, ox=50))
        self.assertEqual(sim.actions(), [])

    def test_commands(self):
        for value, (to_left, to_right) in SWIPES.items():
            sim = TwoHandSim(25, settings=tuned(swipe_action=value))
            sim.rest(30, RIGHT, dict(LEFT, ox=230))
            for i in range(1, 7):
                sim.step(RIGHT, dict(LEFT, ox=230 - 30 * i))
            sim.rest(30, RIGHT, dict(LEFT, ox=50))
            for i in range(1, 7):
                sim.step(RIGHT, dict(LEFT, ox=50 + 30 * i))
            sim.rest(10, RIGHT, dict(LEFT, ox=230))
            self.assertEqual(sim.actions(), [("keys", to_left), ("keys", to_right)], value)


class OneHandPauseTest(unittest.TestCase):
    def test_thumb_down_pauses_and_resumes(self):
        result = bench.one_hand_pause()
        self.assertEqual((result["pauses"], result["actions_while_paused"], result["enabled_after"]), (2, 0, True))
        self.assertLess(result["seconds_to_pause"], 1.2)

    def test_both_thumbs_down_do_nothing(self):
        sim = TwoHandSim(26)
        sim.rest(20, RIGHT, LEFT)
        sim.rest(45, dict(RIGHT, pose="thumb_down"), dict(LEFT, pose="thumb_down"))
        sim.rest(10, RIGHT, LEFT)
        self.assertEqual(sim.actions(), [])

    def test_can_be_switched_off(self):
        sim = TwoHandSim(27, settings=tuned(thumb_pause=0))
        sim.rest(20, RIGHT)
        sim.rest(45, dict(RIGHT, pose="thumb_down"))
        self.assertEqual(sim.actions(), [])
        self.assertTrue(sim.enabled)


class GestureCardTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("ru")

    def test_lists_what_is_switched_on(self):
        rows = dict(gesture_rows("hand", Settings()))
        self.assertIn("Вторая рука: «L»", rows)
        self.assertIn("Обе руки «V»: развести", rows)
        self.assertNotIn("Вторая рука: взмах ← / →", rows)            # off until a command is picked
        rows = dict(gesture_rows("hand", tuned(swipe_action=2, two_hands=0, thumb_pause=0)))
        self.assertNotIn("Вторая рука: щипок", rows)
        self.assertNotIn("Большой палец вниз, 1 с", rows)
        self.assertEqual(len(gesture_rows("head", Settings())), 5)
        i18n.set_language("en")
        rows = dict(gesture_rows("hand", tuned(swipe_action=2)))
        self.assertEqual(rows["Second hand: swipe ← / →"], "slides → / ←")


if __name__ == "__main__":
    unittest.main()
