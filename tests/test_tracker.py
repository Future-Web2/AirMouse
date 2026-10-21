"""Tracking thread pieces that run without a camera: the models, and the preview drawing."""

import importlib.util
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest import mock

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


class LoopTest(unittest.TestCase):
    """The tracking loop with a scripted camera and model: two hands, their commands, pause by gesture."""

    def run_script(self, frames):
        clock = {"t": 50.0}

        def perf_counter():
            clock["t"] += 1 / 30
            return clock["t"]

        trk = tracker.Tracker(Settings(mode="hand"))
        script = iter(frames)

        class Camera:
            def read(self):
                try:
                    hands = next(script)
                except StopIteration:
                    trk._stop.set()
                    hands = []
                Camera.hands = hands
                return True, np.zeros((480, 640, 3), np.uint8)

            def release(self):
                pass

        class Landmarker:
            def detect_for_video(self, image, ms):
                marks = [[SimpleNamespace(x=x / 640, y=y / 480, z=z / 640) for x, y, z in pts]
                         for pts in Camera.hands]
                return SimpleNamespace(hand_landmarks=marks)

            def close(self):
                pass

        done, keys, windows = [], [], []
        mouse = SimpleNamespace(do=done.append, release_all=lambda: None)
        fake_mp = SimpleNamespace(Image=lambda image_format, data: None, ImageFormat=SimpleNamespace(SRGB=1))
        with mock.patch.object(tracker, "_open_camera", lambda *a: Camera()), \
                mock.patch.object(tracker, "create_landmarker", lambda *a: Landmarker()), \
                mock.patch.object(tracker, "mediapipe", lambda: fake_mp), \
                mock.patch.object(tracker, "time", SimpleNamespace(perf_counter=perf_counter, sleep=lambda s: None)), \
                mock.patch.object(tracker.winmouse, "Mouse", lambda: mouse), \
                mock.patch.object(tracker.winmouse, "cursor_pos", lambda: (960, 540)), \
                mock.patch.object(tracker.winmouse, "screen_size", lambda: (1920, 1080)), \
                mock.patch.object(tracker.system, "press_keys", keys.append), \
                mock.patch.object(tracker.system, "window_command", windows.append):
            trk._run()
        self.assertIsNone(trk.error)
        return trk, done, keys, windows

    def test_two_hands_through_the_loop(self):
        right, left = bench.hand(330, 230), bench.hand(130, 240, left=True)
        frames = [[right, left]] * 30
        frames += [[bench.hand(330, 230), bench.hand(130, 240, pinch=p, left=True)] for p in (0.5, 1.0, 1.0, 1.0)]
        frames += [[right, left]] * 10
        frames += [[right, bench.hand(130, 240, pose="thumb", left=True)]] * 25 + [[right, left]] * 5
        frames += [[bench.hand(330, 230, pose="thumb"), bench.hand(130, 240, pose="thumb", left=True)]] * 40
        frames += [[right, left]] * 5
        frames += [[right, bench.hand(130, 240, pinch=p, left=True)] for p in (0.5, 1.0, 1.0, 1.0, 0.0)]
        trk, done, keys, windows = self.run_script(frames)
        buttons = [a for a in done if a[0] != "move"]
        self.assertEqual(buttons, [("down", "left"), ("up", "left")])      # the click; nothing while paused
        self.assertEqual(windows, ["maximize"])
        self.assertEqual((trk.pause_toggles, trk.control_enabled, trk.widget_toggles), (1, False, 0))
        self.assertEqual(keys, [])
        preview = trk.take_preview()
        self.assertEqual(preview.shape, (480, 640, 3))


if __name__ == "__main__":
    unittest.main()
