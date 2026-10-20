"""The notebook («Блокнот»): pages, strokes, undo, saving, and drawing on it with the mouse and by hand."""

import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from airmouse import bench, notebook, onscreen
from airmouse.gestures import GestureEngine
from airmouse.notebook import COLORS, PAGE_H, PAGE_W, PAPER, Notebook
from airmouse.onscreen import NotebookWidget
from airmouse.settings import Settings

from .test_onscreen import Env


def ink(image):
    """Where the page is not paper."""
    return np.any(image != np.array(PAPER, np.uint8), axis=2)


class ModelTest(unittest.TestCase):
    def test_a_stroke_draws_and_undo_takes_it_back(self):
        book = Notebook()
        book.begin((100, 500))
        for x in range(110, 900, 10):
            book.extend((x, 500))
        book.end()
        drawn = ink(book.page.image)
        self.assertTrue(drawn[500, 100:890].all())
        self.assertFalse(drawn[600].any())
        np.testing.assert_array_equal(book.page.image[500, 500], COLORS[0])
        book.undo()
        self.assertFalse(ink(book.page.image).any())

    def test_tools(self):
        book = Notebook()
        book.tool = "marker"
        book.begin((200, 200))
        book.extend((800, 200))
        book.end()
        marker = int(ink(book.page.image)[:, 500].sum())
        self.assertGreater(marker, 15)                              # a thick line
        book.tool = "eraser"
        book.begin((500, 120))
        book.extend((500, 280))
        book.end()
        self.assertFalse(ink(book.page.image)[150:250, 480:520].any())   # rubbed out
        self.assertTrue(ink(book.page.image)[200, 300])

    def test_clear_can_be_undone(self):
        book = Notebook()
        book.begin((300, 300))
        book.extend((600, 400))
        book.clear()
        self.assertFalse(ink(book.page.image).any())
        book.undo()
        self.assertTrue(ink(book.page.image).any())

    def test_pages_are_saved_and_come_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Мои рисунки"                     # Cyrillic in the path, as in many user names
            book = Notebook(folder)
            book.begin((800, 500))
            book.extend((900, 600))
            book.end()
            book.add_page()
            book.begin((100, 100))
            book.end()
            self.assertFalse(book.save_if_due(time.perf_counter()))       # not yet: just changed
            self.assertTrue(book.save_if_due(time.perf_counter() + notebook.SAVE_DELAY))
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["page_001.png", "page_002.png"])

            again = Notebook(folder)
            self.assertEqual((len(again.pages), again.index), (2, 1))       # opens on the last page
            again.go(-1)
            self.assertTrue(ink(again.page.image)[550, 850])
            again.begin((1500, 900))
            again.end()
            again.undo()                                                    # back to what was saved, not blank
            self.assertTrue(ink(again.page.image)[550, 850])

    def test_no_saving_mid_stroke(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = Notebook(Path(tmp))
            book.begin((10, 10))
            self.assertFalse(book.save_if_due(time.perf_counter() + 60))
            book.end()
            self.assertTrue(book.save_if_due(time.perf_counter() + 60))

    def test_clipboard_bitmap(self):
        image = np.zeros((2, 3, 3), np.uint8)
        image[1, 0] = (10, 20, 30)                    # bottom-left pixel, RGB
        data = notebook.dib(image)
        size, w, h, planes, bits = struct.unpack("<IiiHH", data[:16])
        self.assertEqual((size, w, h, planes, bits), (40, 3, 2, 1, 24))
        self.assertEqual(len(data), 40 + 2 * 12)       # rows padded to 4 bytes
        self.assertEqual(tuple(data[40:43]), (30, 20, 10))   # first row is the bottom one, blue first


def make_widget(s=1.0, x=600, y=200):
    env = Env(s)
    env.notebook = Notebook()
    widget = NotebookWidget({"type": "notebook", "on": True, "x": x, "y": y}, env)
    return widget, env


def at(widget, x, y):
    """Logical panel point -> the widget window's pixels."""
    return widget.m + x * widget.s, widget.m + y * widget.s


def click(widget, part):
    x, y, w, h = dict(widget.parts())[part]
    widget.mouse("down", *at(widget, x + w / 2, y + h / 2), 0)
    widget.mouse("up", *at(widget, x + w / 2, y + h / 2), 0)


class WidgetTest(unittest.TestCase):
    def test_drawing_with_the_mouse(self):
        widget, _env = make_widget(1.5)
        px, py, pw, ph = widget.paper()
        widget.mouse("down", *at(widget, px + pw * 0.25, py + ph / 2), 0)
        widget.mouse("move", *at(widget, px + pw * 0.75, py + ph / 2), 0)
        widget.mouse("up", *at(widget, px + pw * 0.75, py + ph / 2), 0)
        drawn = ink(widget.book.page.image)
        self.assertTrue(drawn[PAGE_H // 2, PAGE_W // 4 + 10:PAGE_W * 3 // 4 - 10].all())
        self.assertIsNone(widget.book.stroke)
        layer = widget.render(time.perf_counter())
        self.assertEqual((layer.w, layer.h), widget.window_size())

    def test_letting_go_outside_still_ends_the_stroke(self):
        widget, _env = make_widget()
        px, py, pw, ph = widget.paper()
        widget.mouse("down", *at(widget, px + 50, py + 50), 0)
        widget.mouse("move", *at(widget, px + pw + 200, py + 50), 0)    # off the notebook
        widget.mouse("up", *at(widget, px + pw + 200, py + 50), 0)
        self.assertIsNone(widget.book.stroke)
        self.assertTrue(ink(widget.book.page.image)[int(50 / ph * PAGE_H), PAGE_W - 5])

    def test_tools_colours_and_pages(self):
        widget, env = make_widget()
        book = widget.book
        click(widget, "marker")
        click(widget, "c2")
        self.assertEqual((book.tool, book.color), ("marker", COLORS[2]))
        click(widget, "eraser")
        click(widget, "c1")                       # picking a colour puts the eraser down
        self.assertEqual((book.tool, book.color), ("pen", COLORS[1]))
        click(widget, "add")
        click(widget, "add")
        self.assertEqual((len(book.pages), book.index), (3, 2))
        click(widget, "back")
        click(widget, "back")
        click(widget, "back")
        self.assertEqual(book.index, 0)
        click(widget, "forward")
        self.assertEqual(book.index, 1)
        click(widget, "copy")
        self.assertEqual(env.requests, [("copy_page", widget)])
        click(widget, "close")
        self.assertFalse(widget.spec["on"])
        self.assertGreater(env.saved, 0)

    def test_big_fits_the_screen_and_comes_back(self):
        with mock.patch.object(onscreen.winmouse, "screen_size", lambda: (1920, 1080)):
            for s in (1.0, 1.5):
                widget, _env = make_widget(s, x=40, y=30)
                small = widget.panel_size()
                click(widget, "big")
                w, h = widget.panel_size()
                self.assertGreater(w, small[0])
                self.assertTrue(w <= 1920 and h <= 1080, (s, w, h))
                self.assertEqual((widget.spec["x"], widget.spec["y"]), ((1920 - w) // 2, (1080 - h) // 2))
                self.assertEqual(widget.render(time.perf_counter()).w, widget.window_size()[0])
                click(widget, "big")
                self.assertEqual((widget.panel_size(), widget.spec["x"], widget.spec["y"]), (small, 40, 30))

    def test_redrawn_only_after_a_change(self):
        widget, _env = make_widget()
        widget.render(1.0)
        widget.dirty = False
        widget.tick(1.1)
        self.assertFalse(widget.dirty)
        widget.book.begin((10, 10))
        widget.tick(1.2)
        self.assertTrue(widget.dirty)


class HandTest(unittest.TestCase):
    """Pinch on the paper and move the hand: the real gesture engine draws a line, without stray clicks."""

    def test_drawing_by_hand(self):
        widget, _env = make_widget()
        sx, sy = widget.spec["x"], widget.spec["y"]
        px, py, pw, ph = widget.paper()
        start, end = (sx + px + 100, sy + py + 180), (sx + px + 460, sy + py + 180)
        engine = GestureEngine(Settings(), bench.SCREEN_W, bench.SCREEN_H)
        rng = np.random.default_rng(3)
        state = {"cursor": start, "t": 100.0}
        events = []

        def local(cursor):
            return cursor[0] - sx + widget.m, cursor[1] - sy + widget.m

        def frame(x, y, pinch=0.0):
            state["t"] += 1 / 30
            ox, oy = bench.cam_for(x, y)
            pts = bench.noisy(bench.hand(ox, oy, pinch), rng, 0.8, 0.5)
            for action in engine.update(pts, bench.FRAME_W, bench.FRAME_H, state["t"], state["cursor"]):
                if action[0] == "move":
                    state["cursor"] = action[1:]
                    widget.mouse("move", *local(state["cursor"]), 0)
                else:
                    events.append(action)
                    if action[0] == "click":
                        widget.mouse("down", *local(state["cursor"]), 0)
                        widget.mouse("up", *local(state["cursor"]), 0)
                    elif action[0] in ("down", "up"):
                        widget.mouse(action[0], *local(state["cursor"]), 0)

        for _ in range(30):
            frame(*start)
        for i in range(1, 4):
            frame(*start, pinch=i / 3)
        for _ in range(8):
            frame(*start, pinch=1.0)
        for i in range(1, 37):
            k = i / 36
            frame(start[0] + (end[0] - start[0]) * k, start[1], pinch=1.0)
        for _ in range(4):
            frame(*end, pinch=1.0)
        for i in range(2, -1, -1):
            frame(*end, pinch=i / 3)
        for _ in range(10):
            frame(*end)

        self.assertEqual([a[0] for a in events], ["down", "up"])
        self.assertEqual(len(widget.book.page.steps), 1)
        stroke = widget.book.page.steps[0]
        first = stroke.points[0]
        self.assertLess(abs(first[0] - 100 / pw * PAGE_W), 0.03 * PAGE_W)
        row = int(180 / ph * PAGE_H)
        drawn = ink(widget.book.page.image)[row - 12:row + 12].any(axis=0)
        x0, x1 = int(100 / pw * PAGE_W), int(460 / pw * PAGE_W)
        self.assertGreater(drawn[x0:x1].mean(), 0.9)     # the line runs the whole way


if __name__ == "__main__":
    unittest.main()
