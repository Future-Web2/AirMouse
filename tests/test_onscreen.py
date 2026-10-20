"""On-screen widgets and the cursor ring, driven like the window procedure and the timer drive them.

Nothing is shown and nothing is pressed: windows, keys and the volume are stand-ins.
"""

import tempfile
import time
import unittest
from collections import Counter, deque
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from airmouse import onscreen
from airmouse.gestures import DRAG, MOVE, NO_HAND, PENDING, SCROLL
from airmouse.onscreen import (ButtonsWidget, ClockWidget, CursorRing, MediaWidget, OnScreen, StatusWidget,
                               SystemWidget, VolumeWidget, clean_specs, default_widgets)
from airmouse.settings import Settings


class FakeVolume:
    def __init__(self, level=0.5):
        self.value, self.mute, self.sets = level, False, []

    def level(self):
        return self.value

    def muted(self):
        return self.mute

    def set_level(self, value):
        self.sets.append(round(value, 3))
        self.value = value
        return True

    def set_muted(self, on):
        self.mute = on
        return True


class FakeLoad:
    def cpu(self):
        return 30.0

    def memory(self):
        return 60.0

    def battery(self):
        return 80.0, False


class Env:
    def __init__(self, s=1.0):
        self.s = s
        self.volume, self.load = FakeVolume(), FakeLoad()
        self.frame, self.frame_id = np.full((480, 640, 3), 90, np.uint8), 1
        self.requests, self.saved = [], 0
        self.mouse_at = (500, 400)

    def status(self):
        return "Курсор", onscreen.GREEN, "30 кадр/с"

    def camera_on(self):
        return True

    def cursor(self):
        return self.mouse_at

    def request(self, item):
        self.requests.append(item)

    def changed(self):
        self.saved += 1

    def place(self, widget):
        pass

    def clamp(self, widget, x, y):
        return int(x), int(y)


def make(kind, env=None, **spec):
    env = env or Env()
    base = next(s for s in default_widgets() if s["type"] == kind)
    widget = onscreen.WIDGET_CLASSES[kind](dict(base, x=100, y=50, **spec), env)
    return widget, env


def click(widget, x, y):
    """Mouse down and up at logical panel point (x, y)."""
    px, py = widget.m + x * widget.s, widget.m + y * widget.s
    widget.mouse("down", px, py, 0)
    widget.mouse("up", px, py, 0)


def centre(widget, part):
    x, y, w, h = dict(widget.parts())[part]
    return x + w / 2, y + h / 2


class SpecsTest(unittest.TestCase):
    def test_empty_gives_the_defaults(self):
        self.assertEqual(clean_specs([]), default_widgets())
        self.assertEqual(clean_specs("rubbish"), default_widgets())

    def test_damaged_entries(self):
        specs = clean_specs([
            {"type": "clock", "on": False, "x": 10.7, "y": "far"},
            {"type": "clock"},                                     # a second clock is dropped
            {"type": "teleport"},
            "nonsense",
            {"type": "buttons", "title": "Мои", "buttons": [
                {"label": "", "do": "keys", "value": "ctrl+c"},
                {"label": "Плохая", "do": "rm -rf", "value": "/"},
                {"label": "Сайт", "do": "open", "value": "https://example.com"}] + [
                {"label": f"К{i}", "do": "keys", "value": "f5"} for i in range(20)]},
        ])
        kinds = [s["type"] for s in specs]
        self.assertEqual(kinds.count("clock"), 1)
        self.assertEqual(specs[0], {"type": "clock", "on": False, "x": 10})
        self.assertEqual(sorted(set(kinds)), sorted(onscreen.KINDS))   # missing built-ins come back
        panel = next(s for s in specs if s["type"] == "buttons")
        self.assertEqual(len(panel["buttons"]), onscreen.MAX_BUTTONS)
        self.assertEqual(panel["buttons"][0]["label"], "Кнопка")
        self.assertNotIn("rm -rf", [b["do"] for b in panel["buttons"]])


class RenderTest(unittest.TestCase):
    def test_every_widget_draws_a_panel_with_room_for_its_shadow(self):
        for s in (1.0, 1.5):
            for kind in onscreen.KINDS:
                widget, _env = make(kind, Env(s))
                widget.tick(time.perf_counter())
                layer = widget.render(time.perf_counter())
                self.assertEqual((layer.w, layer.h), widget.window_size(), kind)
                self.assertGreater(float(layer.alpha[layer.h // 2, layer.w // 2]), 0.8, kind)
                self.assertLess(float(layer.alpha[0, 0]), 0.02, kind)


class InputTest(unittest.TestCase):
    def test_button_runs_its_action(self):
        widget, env = make("buttons")
        click(widget, *centre(widget, "b1"))
        self.assertEqual(env.requests, [("action", widget.spec["buttons"][1], widget)])

    def test_letting_go_elsewhere_does_nothing(self):
        widget, env = make("buttons")
        x, y = centre(widget, "b0")
        widget.mouse("down", widget.m + x, widget.m + y, 0)
        widget.mouse("up", 1, 1, 0)
        self.assertEqual(env.requests, [])

    def test_dragging_the_background_moves_the_widget(self):
        widget, env = make("media")
        widget.mouse("down", widget.m + 2, widget.m + 2, 0)     # a corner: no button there
        env.mouse_at = (560, 430)
        widget.mouse("move", 0, 0, 0)
        widget.mouse("up", 0, 0, 0)
        self.assertEqual((widget.spec["x"], widget.spec["y"]), (160, 80))
        self.assertEqual(env.saved, 1)

    def test_media_keys(self):
        widget, env = make("media")
        click(widget, *centre(widget, "play"))
        click(widget, *centre(widget, "next"))
        self.assertEqual(env.requests, [("keys", "playpause"), ("keys", "nexttrack")])

    def test_volume(self):
        widget, env = make("volume")
        widget.tick(time.perf_counter())
        x0, x1 = widget.TRACK
        widget.mouse("down", widget.m + x0 + 0.75 * (x1 - x0), widget.m + 36, 0)
        widget.mouse("move", widget.m + x0 + 0.25 * (x1 - x0), widget.m + 36, 0)
        widget.mouse("up", widget.m + x0 + 0.25 * (x1 - x0), widget.m + 36, 0)
        self.assertEqual(env.volume.sets, [0.75, 0.25])
        widget.mouse("wheel", widget.m + 100, widget.m + 36, 120)
        self.assertAlmostEqual(env.volume.value, 0.29)
        click(widget, *centre(widget, "mute"))
        self.assertTrue(env.volume.mute)

    def test_volume_without_a_device(self):
        widget, env = make("volume")
        env.volume.value = None
        widget.tick(time.perf_counter())
        widget.mouse("wheel", widget.m + 100, widget.m + 36, 120)
        click(widget, *centre(widget, "mute"))
        self.assertEqual((env.volume.sets, env.volume.mute), ([], False))
        widget.render(time.perf_counter())

    def test_status_gear_opens_the_editor(self):
        widget, env = make("status")
        click(widget, *centre(widget, "settings"))
        self.assertEqual(env.requests, [("editor",)])

    def test_hand_cursor_only_over_buttons(self):
        widget, _env = make("buttons")
        x, y = centre(widget, "b0")
        self.assertIsNotNone(widget.part_at(widget.m + x, widget.m + y))
        self.assertIsNone(widget.part_at(widget.m + 2, widget.m + 2))

    def test_error_shows_and_goes(self):
        widget, _env = make("buttons")
        height = widget.logical_size()[1]
        widget.show_error("Не удалось открыть «x»")
        self.assertGreater(widget.logical_size()[1], height)
        widget.tick(time.perf_counter() + widget.ERROR_TIME + 0.1)
        self.assertEqual(widget.logical_size()[1], height)


class RingTest(unittest.TestCase):
    def test_states(self):
        ring, now = CursorRing(1.0), 10.0
        self.assertEqual(ring.state(MOVE, 0.01, now), (MOVE, 0.0, None, 0))
        self.assertEqual(ring.state(MOVE, 0.444, now)[1], 0.44)
        self.assertEqual(ring.state(DRAG, 0.9, now)[1], 0.0)       # no filling while dragging
        ring.event(("click", "left"), now)
        self.assertIsNotNone(ring.state(MOVE, 0, now + 0.1)[2])
        self.assertIsNone(ring.state(MOVE, 0, now + 1.0)[2])
        ring.event(("wheel", -30), now)
        self.assertEqual(ring.state(SCROLL, 0, now + 0.1)[3], -1)

    def test_render(self):
        ring = CursorRing(1.5)
        for state in (ring.state(MOVE, 0.5, 0), ring.state(PENDING, 0, 0), ring.state(SCROLL, 0, 0)):
            layer = ring.render(state)
            self.assertEqual((layer.w, layer.h), (ring.size, ring.size))
            self.assertLess(float(layer.alpha[ring.size // 2, ring.size // 2]), 0.01)   # the cursor stays visible
            self.assertGreater(float(layer.alpha.max()), 0.5)


class FakeWindow:
    def __init__(self, click_through=False, on_mouse=None, hand_at=None):
        self.visible, self.x, self.y, self.shows = False, 0, 0, 0

    def show(self, bgra, x, y):
        self.visible, self.x, self.y = True, x, y
        self.shows += 1

    def move(self, x, y):
        self.x, self.y = x, y

    def hide(self):
        self.visible = False

    def destroy(self):
        self.visible = False


class FakeApp:
    def __init__(self):
        self.settings = Settings()
        self.tracker = None
        self._has_frame = False
        self.saves = self.editors = 0

    def after(self, ms, fn, *args):
        pass                      # the tests call the timer themselves

    def _status(self):
        return "Курсор", onscreen.GREEN, "30 кадр/с"

    def _schedule_save(self):
        self.saves += 1

    def open_widget_editor(self):
        self.editors += 1


def tracker(mode=MOVE):
    return SimpleNamespace(mode=mode, progress=0.0, widget_toggles=0, events=deque(), stats=Counter(),
                           control_enabled=True, fps=30.0)


class ManagerTest(unittest.TestCase):
    def setUp(self):
        # Stand-in windows (nothing may appear on the user's screen) and a fixed cursor.
        for name, value in (("LayeredWindow", FakeWindow), ("cursor_pos", lambda: (800, 500))):
            patcher = mock.patch.object(onscreen, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        folder = tempfile.TemporaryDirectory()          # the notebook's pages, not the user's
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(onscreen.settings_file, "SETTINGS_DIR", Path(folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = FakeApp()
        self.screen = OnScreen(self.app, 1.0)
        self.addCleanup(self.screen.close)
        for _widget, window in self.screen.items:
            assert isinstance(window, FakeWindow)

    def windows(self):
        return {widget.spec["type"]: window for widget, window in self.screen.items}

    def run_timer(self, start, ticks=8):
        """A few timer ticks: widgets appear one per tick the first time."""
        for i in range(ticks):
            self.screen._update(start + i / 100)

    def test_nothing_shows_until_tracking_runs(self):
        self.screen._update(1.0)
        self.assertFalse(any(w.visible for w in self.windows().values()))

    def test_widgets_and_ring_while_running(self):
        self.app.tracker, self.app._has_frame = tracker(), True
        self.assertTrue(self.screen._update(1.0))
        self.run_timer(1.0)
        windows = self.windows()
        self.assertTrue(windows["status"].visible)
        self.assertFalse(windows["clock"].visible)            # off by default
        self.assertTrue(self.screen._ring_window.visible)
        self.assertEqual((self.screen._ring_window.x, self.screen._ring_window.y),
                         (800 - self.screen.ring.size // 2, 500 - self.screen.ring.size // 2))
        self.app.tracker.mode = NO_HAND
        self.screen._update(1.1)
        self.assertFalse(self.screen._ring_window.visible)

    def test_thumbs_up_hides_and_shows(self):
        self.app.tracker, self.app._has_frame = tracker(), True
        self.run_timer(1.0)
        self.app.tracker.widget_toggles += 1
        self.screen._update(1.1)
        self.assertFalse(self.app.settings.widgets_on)
        self.assertFalse(self.windows()["status"].visible)
        self.assertGreater(self.app.saves, 0)
        self.app.tracker.widget_toggles += 1
        self.run_timer(1.2)
        self.assertTrue(self.windows()["status"].visible)

    def test_only_changed_widgets_are_redrawn(self):
        self.app.tracker, self.app._has_frame = tracker(), True
        self.run_timer(1.0)
        media = self.windows()["media"]
        shows = media.shows
        self.screen._update(1.1)
        self.assertEqual(media.shows, shows)

    def test_requests_run_in_the_timer(self):
        widget = next(w for w, _window in self.screen.items if w.spec["type"] == "buttons")
        pressed = []
        with mock.patch.object(onscreen.system, "press_keys", pressed.append), \
                mock.patch.object(onscreen.system, "run_action", lambda action: "Не удалось открыть «x»"):
            self.screen.request(("keys", "playpause"))
            self.screen.request(("action", widget.spec["buttons"][0], widget))
            self.screen.request(("editor",))
            self.screen._update(1.0)
        self.assertEqual(pressed, ["playpause"])
        self.assertEqual(widget.error[0], "Не удалось открыть «x»")
        self.assertEqual(self.app.editors, 1)

    def test_notebook_opens_without_the_camera(self):
        self.screen._update(1.0)
        self.assertFalse(any(w.visible for w in self.windows().values()))
        self.app.settings.widgets_on = False                  # hidden by a thumbs up earlier
        self.assertTrue(self.screen.toggle_notebook())
        self.run_timer(1.1)
        windows = self.windows()
        self.assertTrue(windows["notebook"].visible)
        self.assertFalse(windows["status"].visible)           # the others still wait for the camera
        self.assertTrue(self.app.settings.widgets_on)
        self.assertFalse(self.screen.toggle_notebook())
        self.screen._update(1.2)
        self.assertFalse(windows["notebook"].visible)

    def test_pen_on_the_mini_panel_opens_the_notebook(self):
        status = next(w for w, _window in self.screen.items if w.spec["type"] == "status")
        click(status, *centre(status, "notebook"))
        self.screen._update(1.0)
        notebook = next(w for w, _window in self.screen.items if w.spec["type"] == "notebook")
        self.assertTrue(notebook.spec["on"])

    def test_copy_shows_how_it_went(self):
        notebook = next(w for w, _window in self.screen.items if w.spec["type"] == "notebook")
        self.assertIs(notebook.book, self.screen.notebook)    # one notebook, whatever the widget windows
        with mock.patch.object(self.screen.notebook, "copy", lambda: True):
            self.screen.request(("copy_page", notebook))
            self.screen._update(1.0)
        self.assertIn("Скопировано", notebook.note[0])

    def test_arrange_keeps_widgets_on_the_screen_in_a_column(self):
        self.screen.arrange()
        sw, sh = onscreen.winmouse.screen_size()
        boxes = []
        for widget, _window in self.screen.items:
            w, h = widget.panel_size()
            x, y = widget.spec["x"], widget.spec["y"]
            self.assertTrue(0 <= x and x + w <= sw and 0 <= y and y + h <= sh)
            boxes.append((x, y, x + w, y + h))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3], "overlap")


class OtherWidgetsTest(unittest.TestCase):
    def test_clock_redraws_when_the_minute_changes(self):
        widget, _env = make("clock")
        widget.tick(0)
        widget.dirty = False
        widget.tick(1)
        self.assertFalse(widget.dirty)
        widget._minute = "old"
        widget.tick(2)
        self.assertTrue(widget.dirty)

    def test_system_widget_reads_the_load(self):
        widget, _env = make("system")
        widget.tick(5.0)
        self.assertEqual(widget.values, {"cpu": 30.0, "memory": 60.0, "battery": 80.0, "charging": False})

    def test_status_preview_is_limited_to_15_frames_a_second(self):
        widget, env = make("status")
        widget.tick(1.0)
        widget.render(1.0)
        widget.dirty = False
        env.frame_id += 1
        widget.tick(1.01)
        self.assertFalse(widget.dirty)
        widget.tick(1.0 + 1 / 14)
        self.assertTrue(widget.dirty)


if __name__ == "__main__":
    unittest.main()
