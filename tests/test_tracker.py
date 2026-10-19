"""Tracking thread pieces that run without a camera: the models, and the preview drawing."""

import importlib.util
import unittest
from collections import Counter
from types import SimpleNamespace

import numpy as np

from airmouse import bench, tracker
from airmouse.app_base import Session
from airmouse.settings import Settings


class CountingTest(unittest.TestCase):
    def test_actions_are_counted_for_the_session(self):
        trk = tracker.Tracker(Settings())
        for action in (("move", 1, 2), ("click", "left"), ("down", "left"), ("up", "left"), ("click", "right"),
                       ("wheel", 30), ("wheel", -30)):
            trk._note(action, 1.0)
        self.assertEqual(trk.stats, Counter(left=2, right=1, wheel=2))
        self.assertEqual([number for number, _t, _a in trk.events], [1, 2, 3, 4, 5, 6])   # moves are not kept

    def test_session_summary(self):
        session = Session()
        trk = SimpleNamespace(fps=29.6, stats=Counter(left=3, right=1, wheel=10))
        session.sample(trk, 100.0)
        session.sample(trk, 100.6)
        duration, fps, cpu, actions = session.summary(trk, 165.0)
        self.assertEqual((duration, fps), ("01:05", "30 кадр/с"))
        self.assertTrue(cpu.startswith("процессор "))
        self.assertEqual(actions, "клики 3  ·  правые 1  ·  прокрутка 10")
        self.assertEqual(len(session.fps), 2)
        session.sample(None, 170.0)
        self.assertIsNone(session.started)


@unittest.skipUnless(importlib.util.find_spec("mediapipe"), "mediapipe is not installed")
class TrackerTest(unittest.TestCase):
    def test_models_load_and_run(self):
        self.assertEqual(tracker.selftest(), 0)

    def test_hand_preview(self):
        trk = tracker.Tracker(Settings(mode="hand"))
        frame = np.zeros((480, 640, 3), np.uint8)
        trk._publish_preview(frame, bench.hand(300, 200), 1920, 1080)
        preview = trk.take_preview()
        self.assertEqual(preview.shape, (480, 640, 3))
        self.assertGreater(int(preview[250:300, 280:340].max()), 100)   # the palm dot
        self.assertIsNone(trk.take_preview())   # each frame is handed out once

    def test_face_preview(self):
        trk = tracker.Tracker(Settings(mode="head"))
        rng = np.random.default_rng(0)
        pts = [tuple(p) for p in rng.uniform((100, 100), (500, 400), (478, 2))]
        trk._publish_preview(np.zeros((480, 640, 3), np.uint8), pts, 1920, 1080)
        self.assertGreater(int(trk.take_preview().max()), 100)


if __name__ == "__main__":
    unittest.main()
