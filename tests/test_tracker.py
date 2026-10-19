"""Tracking thread pieces that run without a camera: the models, and the preview drawing."""

import importlib.util
import unittest

import numpy as np

from airmouse import bench, tracker
from airmouse.settings import Settings


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
