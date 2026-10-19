"""Hand mode: a simulated hand goes into the real gesture engine, mouse actions come out."""

import math
import unittest

from airmouse.bench import HandSim, cam_for, hand
from airmouse.gestures import DRAG, MOVE, NO_HAND, SCROLL, HandFeatures, leash_px, zone_rect
from airmouse.settings import Settings

LEASH = leash_px(Settings(), 1.0)


def quiet(**kwargs):
    """A hand with no tracking noise, for exact checks."""
    return HandSim(sigma=0.0, common=0.0, **kwargs)


def kinds(sim):
    return [action for _t, action, _c in sim.events]


class HandFeaturesTest(unittest.TestCase):
    def test_open_hand(self):
        f = HandFeatures(hand(300, 200))
        self.assertGreater(f.pinch_index, 1.0)
        self.assertGreater(f.pinch_middle, 1.0)
        self.assertFalse(f.two_fingers)

    def test_pinch(self):
        f = HandFeatures(hand(300, 200, pinch=1.0))
        self.assertLess(f.pinch_index, 0.15)
        self.assertGreater(f.pinch_middle, 0.45)

    def test_right_click_pose_touches_both_fingers(self):
        f = HandFeatures(hand(300, 200, pinch=1.0, pose="right"))
        self.assertLess(f.pinch_index, 0.3)
        self.assertLess(f.pinch_middle, 0.3)

    def test_scroll_pose(self):
        self.assertTrue(HandFeatures(hand(300, 200, pose="two")).two_fingers)

    def test_measurements_do_not_depend_on_distance(self):
        near = hand(300, 200, pinch=0.5)
        far = [(x / 2, y / 2, z / 2) for x, y, z in near]
        self.assertAlmostEqual(HandFeatures(near).pinch_index, HandFeatures(far).pinch_index)


class ZoneTest(unittest.TestCase):
    def test_zone_has_the_shape_of_the_screen(self):
        s = Settings()
        x0, y0, x1, y1 = zone_rect(s, 640, 480, 1920, 1080)
        self.assertAlmostEqual((x1 - x0) * 640 / ((y1 - y0) * 480), 1920 / 1080)
        self.assertAlmostEqual((x0 + x1) / 2, s.zone_center_x)
        self.assertAlmostEqual((y0 + y1) / 2, s.zone_center_y)

    def test_higher_cursor_speed_means_a_smaller_zone(self):
        self.assertGreater(Settings(cursor_speed=0.0).zone_size, Settings(cursor_speed=1.0).zone_size)


class CursorTest(unittest.TestCase):
    def test_palm_in_the_middle_of_the_zone_puts_the_cursor_in_the_middle(self):
        sim = quiet()
        sim.rest(60, *cam_for(960, 540))
        self.assertLessEqual(math.dist(sim.cursor, (960, 540)), LEASH + 1)

    def test_cursor_starts_where_it_was_and_glides_to_the_hand(self):
        sim = quiet()
        sim.cursor = (200, 200)
        sim.step(*cam_for(1500, 800))
        self.assertEqual(sim.cursor, (200, 200))   # no jump in the first frame
        sim.rest(45, *cam_for(1500, 800))
        self.assertLessEqual(math.dist(sim.cursor, (1500, 800)), LEASH + 1)

    def test_cursor_follows_the_hand_across_the_screen(self):
        sim = quiet()
        sim.rest(30, *cam_for(200, 540))
        xs = []
        for i in range(60):
            sim.step(*cam_for(200 + 25 * i, 540))
            xs.append(sim.cursor[0])
        self.assertTrue(all(b >= a for a, b in zip(xs, xs[1:])), "the cursor went backwards")
        sim.rest(30, *cam_for(1675, 540))
        self.assertLessEqual(math.dist(sim.cursor, (1675, 540)), LEASH + 1)

    def test_cursor_stays_on_screen(self):
        sim = quiet()
        sim.rest(60, *cam_for(-500, 2000))
        x, y = sim.cursor
        self.assertTrue(0 <= x <= 1919 and 0 <= y <= 1079)

    def test_after_the_real_mouse_moved_the_cursor_glides_back(self):
        sim = quiet()
        sim.rest(30, *cam_for(960, 540))
        sim.cursor = (300, 300)          # the user moved the mouse by hand
        away = math.dist((300, 300), (960, 540))
        sim.step(*cam_for(960, 540))
        self.assertLess(math.dist(sim.cursor, (300, 300)), 0.3 * away)   # starts from there, no jump
        sim.rest(45, *cam_for(960, 540))
        self.assertLessEqual(math.dist(sim.cursor, (960, 540)), LEASH + 1)


class ClickTest(unittest.TestCase):
    def test_pinch_is_one_left_click(self):
        sim = quiet()
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        before = sim.cursor
        sim.pinch(ox, oy)
        sim.rest(20, ox, oy)
        self.assertEqual(sim.presses(), [before])
        self.assertEqual(sim.presses("right"), [])

    def test_pinch_with_two_fingers_is_a_right_click(self):
        sim = quiet()
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        sim.pinch(ox, oy, pose="right")
        sim.rest(20, ox, oy)
        self.assertEqual(len(sim.presses("right")), 1)
        self.assertEqual(sim.presses(), [])

    def test_long_pinch_without_moving_is_still_a_click(self):
        sim = quiet()
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        sim.pinch(ox, oy, hold=15)
        sim.rest(20, ox, oy)
        self.assertEqual(kinds(sim), [("down", "left"), ("up", "left")])

    def test_pinch_hold_and_move_drags(self):
        sim = quiet()
        ox, oy = cam_for(600, 540)
        sim.rest(30, ox, oy)
        for i in range(1, 4):
            sim.step(ox, oy, pinch=i / 3)
        sim.rest(6, ox, oy, pinch=1.0)
        start = sim.cursor
        for i in range(1, 31):
            sim.step(ox + 4 * i, oy, pinch=1.0)
        self.assertEqual(sim.engine.mode, DRAG)
        sim.rest(3, ox + 120, oy, pinch=0.0)
        self.assertEqual(kinds(sim), [("down", "left"), ("up", "left")])
        self.assertGreater(sim.cursor[0] - start[0], 400)
        self.assertEqual(sim.engine.mode, MOVE)

    def test_double_click_lands_on_one_pixel(self):
        sim = quiet()
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        sim.pinch(ox, oy, close=2, hold=2, release=2)
        sim.rest(4, ox, oy)
        sim.pinch(ox, oy, close=2, hold=2, release=2)
        presses = sim.presses()
        self.assertEqual(len(presses), 2)
        self.assertEqual(presses[0], presses[1])


class ScrollTest(unittest.TestCase):
    def scroll(self, invert):
        sim = quiet(settings=Settings(invert_scroll=invert))
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        sim.rest(6, ox, oy, pose="two")
        self.assertEqual(sim.engine.mode, SCROLL)
        held = sim.cursor
        for i in range(1, 21):
            sim.step(ox, oy - 2 * i, pose="two")   # hand goes up
        self.assertEqual(sim.cursor, held)          # the cursor does not move while scrolling
        return sum(a[1] for a in kinds(sim) if a[0] == "wheel")

    def test_hand_up_scrolls_up(self):
        self.assertGreater(self.scroll(invert=False), 0)

    def test_inverted(self):
        self.assertLess(self.scroll(invert=True), 0)


class HandLostTest(unittest.TestCase):
    def drag(self):
        sim = quiet()
        ox, oy = cam_for(960, 540)
        sim.rest(30, ox, oy)
        for i in range(1, 4):
            sim.step(ox, oy, pinch=i / 3)
        sim.rest(8, ox, oy, pinch=1.0)
        self.assertIn(("down", "left"), kinds(sim))
        return sim, ox, oy

    def test_a_short_dropout_keeps_the_button(self):
        sim, ox, oy = self.drag()
        sim.gone(3)
        sim.rest(3, ox, oy, pinch=1.0)
        self.assertNotIn(("up", "left"), kinds(sim))

    def test_losing_the_hand_lets_go_of_the_button(self):
        sim, _ox, _oy = self.drag()
        sim.gone(15)
        self.assertEqual(kinds(sim)[-1], ("up", "left"))
        self.assertEqual(sim.engine.mode, NO_HAND)


if __name__ == "__main__":
    unittest.main()
