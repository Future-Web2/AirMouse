"""Eyes and head modes: face measurements in, mouse actions out."""

import math
import unittest

import numpy as np

from airmouse.face import EYES_CLOSED, NO_FACE, FaceEngine, FaceFrame, GazeModel, read_face
from airmouse.gestures import DRAG, MOVE, SCROLL
from airmouse.settings import Settings

FPS = 30
OPEN, SHUT = 0.1, 0.9


class FaceSim:
    """Feeds FaceFrames to the real FaceEngine at 30 frames per second."""

    def __init__(self, use_gaze=False, settings=None):
        self.settings = settings or Settings()
        self.engine = FaceEngine(self.settings, 1920, 1080, use_gaze=use_gaze)
        self.t = 50.0
        self.cursor = (960, 540)
        self.events = []

    def step(self, head=(0.0, 0.5), blink=(OPEN, OPEN), jaw=0.1, brow=0.1, gaze=(0.5, 0.0), frames=1):
        for _ in range(frames):
            self.t += 1 / FPS
            face = FaceFrame(gaze=gaze, head=head, blink=blink, jaw=jaw, brow=brow)
            for action in self.engine.update(face, self.t, self.cursor):
                if action[0] == "move":
                    self.cursor = action[1:]
                else:
                    self.events.append(action)

    def gone(self, frames):
        for _ in range(frames):
            self.t += 1 / FPS
            self.events += self.engine.update(None, self.t, self.cursor)

    def blink(self, seconds, blink=(SHUT, SHUT)):
        self.step(blink=blink, frames=round(seconds * FPS))
        self.step(frames=25)


class HeadModeTest(unittest.TestCase):
    def test_first_head_position_is_the_screen_centre(self):
        sim = FaceSim()
        sim.cursor = (100, 100)
        sim.step(head=(0.03, 0.55), frames=60)
        self.assertLess(math.dist(sim.cursor, (960, 540)), 15)

    def test_turning_the_head_moves_the_cursor(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.step(head=(0.05, 0.5), frames=45)
        right = sim.cursor
        self.assertGreater(right[0], 1300)
        sim.step(head=(0.0, 0.47), frames=45)
        self.assertLess(sim.cursor[1], 540 - 100)

    def test_recenter(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.engine.recenter()
        sim.step(head=(0.04, 0.5), frames=60)
        self.assertLess(math.dist(sim.cursor, (960, 540)), 15)


class BlinkTest(unittest.TestCase):
    def test_long_blink_is_a_left_click(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.blink(0.6)
        self.assertEqual(sim.events, [("click", "left")])

    def test_ordinary_blink_does_nothing(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.blink(0.15)
        self.assertEqual(sim.events, [])

    def test_eyes_closed_for_long_is_resting_not_clicking(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.blink(2.5)
        self.assertEqual(sim.events, [])

    def test_cursor_is_pinned_while_the_eyes_are_closed(self):
        sim = FaceSim()
        sim.step(frames=30)
        pinned = sim.cursor
        sim.step(head=(0.05, 0.5), blink=(SHUT, SHUT), frames=12)
        self.assertEqual(sim.engine.mode, EYES_CLOSED)
        self.assertEqual(sim.cursor, pinned)

    def test_two_long_blinks_make_a_double_click(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.blink(0.6)
        sim.blink(0.6)
        self.assertEqual(sim.events, [("click", "left")] * 3)   # one click, then the double click

    def test_wink_is_a_right_click(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.blink(0.5, blink=(SHUT, OPEN))
        self.assertEqual(sim.events, [("click", "right")])


class MouthAndBrowsTest(unittest.TestCase):
    def test_open_mouth_holds_the_button(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.step(jaw=0.7, frames=5)
        self.assertEqual(sim.events, [("down", "left")])
        self.assertEqual(sim.engine.mode, DRAG)
        sim.step(head=(0.04, 0.5), jaw=0.7, frames=30)   # drag
        sim.step(jaw=0.05, frames=5)
        self.assertEqual(sim.events, [("down", "left"), ("up", "left")])
        self.assertEqual(sim.engine.mode, MOVE)

    def test_raised_brows_and_tilt_scroll(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.step(brow=0.8, frames=4)
        self.assertEqual(sim.engine.mode, SCROLL)
        held = sim.cursor
        sim.step(head=(0.0, 0.45), brow=0.8, frames=30)   # head up
        self.assertEqual(sim.cursor, held)
        wheel = sum(a[1] for a in sim.events if a[0] == "wheel")
        self.assertGreater(wheel, 0)
        sim.step(brow=0.1, frames=5)
        self.assertEqual(sim.engine.mode, MOVE)

    def test_losing_the_face_lets_go_of_the_button(self):
        sim = FaceSim()
        sim.step(frames=30)
        sim.step(jaw=0.7, frames=5)
        sim.gone(15)
        self.assertEqual(sim.events[-1], ("up", "left"))
        self.assertEqual(sim.engine.mode, NO_FACE)


def synthetic_gaze_data(c=(-0.4, -0.3), noise=0.002, seed=0):
    """Calibration samples from a known eye -> screen map, with head movement the eyes compensate."""
    rng = np.random.default_rng(seed)

    def eyes_for(target, head):
        ex = 0.35 + 0.3 * target[0] / 1920
        ey = 0.05 + 0.2 * target[1] / 1080
        return ex - c[0] * head[0] + rng.normal(0, noise), ey - c[1] * head[1] + rng.normal(0, noise)

    head_samples = []
    for i in range(60):
        head = (0.05 * math.sin(i / 6), 0.5 + 0.04 * math.cos(i / 9))
        head_samples.append((eyes_for((960, 540), (head[0], head[1] - 0.5)), (head[0], head[1] - 0.5)))
    dots = [(x, y) for y in (86, 540, 994) for x in (154, 960, 1766)]
    dot_samples = [(d, eyes_for(d, (0.0, 0.0)), (0.0, 0.0)) for d in dots for _ in range(20)]
    return head_samples, dot_samples, eyes_for


class GazeModelTest(unittest.TestCase):
    def test_fit_recovers_the_map(self):
        head_samples, dot_samples, eyes_for = synthetic_gaze_data()
        model = GazeModel.fit(head_samples, dot_samples)
        self.assertIsNotNone(model)
        self.assertLess(model.error, 25)
        for target in ((500, 300), (1500, 800)):
            for head in ((0.0, 0.0), (0.03, -0.02)):   # turning the head must not move the estimate
                predicted = model.predict(eyes_for(target, head), head)
                self.assertLess(math.dist(predicted, target), 60)

    def test_too_few_dots(self):
        head_samples, dot_samples, _ = synthetic_gaze_data()
        self.assertIsNone(GazeModel.fit(head_samples, dot_samples[:60]))

    def test_model_survives_a_settings_round_trip(self):
        head_samples, dot_samples, eyes_for = synthetic_gaze_data()
        model = GazeModel.fit(head_samples, dot_samples)
        again = GazeModel(dict(model.data))
        self.assertEqual(again.predict((0.5, 0.1), (0.0, 0.0)), model.predict((0.5, 0.1), (0.0, 0.0)))

    def test_gaze_mode_waits_for_calibration(self):
        sim = FaceSim(use_gaze=True)
        sim.step(frames=30)
        self.assertEqual(sim.cursor, (960, 540))
        self.assertEqual(sim.events, [])


class ReadFaceTest(unittest.TestCase):
    def points(self, iris_shift=0.0):
        pts = [(0.0, 0.0)] * 478
        pts[33], pts[133], pts[362], pts[263] = (100, 100), (140, 100), (180, 100), (220, 100)
        for i in range(468, 473):
            pts[i] = (120 + iris_shift, 100)
        for i in range(473, 478):
            pts[i] = (200 + iris_shift, 100)
        pts[1] = (160, 140)   # nose tip
        return pts

    def test_centred_irises_and_nose(self):
        face = read_face(self.points(), {"eyeBlinkLeft": 0.2, "jawOpen": 0.5, "browInnerUp": 0.3})
        self.assertAlmostEqual(face.gaze[0], 0.5)
        self.assertAlmostEqual(face.head[0], 0.0)
        self.assertAlmostEqual(face.head[1], 40 / 120)
        self.assertEqual(face.blink, (0.2, 0.0))
        self.assertEqual((face.jaw, face.brow), (0.5, 0.3))

    def test_looking_right(self):
        self.assertGreater(read_face(self.points(iris_shift=6), {}).gaze[0], 0.6)


if __name__ == "__main__":
    unittest.main()
