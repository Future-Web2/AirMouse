"""The notebook («Блокнот»): pages of white paper to draw on with the hand, like Paint.

A page keeps the picture it was opened with and the strokes drawn since, so the
last ones can be undone (clearing the page is a step too). Pages are saved as PNG
in %APPDATA%\\AirMouse\\notebook a moment after a change, and come back next time.
A page can also be copied to the clipboard as a picture, to paste anywhere.

Drawing happens in page pixels, whatever size the notebook is shown at.
"""

import ctypes
import struct
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np

PAGE_W, PAGE_H = 1600, 1000
PAPER = (255, 255, 255)
# (r, g, b): graphite, blue, red, green, amber
COLORS = ((32, 33, 38), (37, 99, 235), (220, 38, 38), (22, 150, 70), (245, 170, 10))
WIDTHS = {"pen": 6, "marker": 22, "eraser": 56}       # line width in page pixels
SAVE_DELAY = 1.0                                     # seconds after the last change


class Clear:
    """An undoable step that wipes the page."""


class Stroke:
    def __init__(self, tool, color, point):
        self.tool = tool
        self.color = PAPER if tool == "eraser" else tuple(color)
        self.width = WIDTHS[tool]
        self.points = [point]


def _draw(image, stroke, start=0):
    """Draw stroke.points[start:] (joined to the point before them) onto the image."""
    pts = stroke.points
    color = tuple(int(c) for c in stroke.color)
    if len(pts) == 1:
        x, y = pts[0]
        cv2.circle(image, (int(x * 16), int(y * 16)), int(stroke.width * 8), color, -1, cv2.LINE_AA, 4)
        return
    line = np.array([[x * 16, y * 16] for x, y in pts[max(start - 1, 0):]], np.int32)
    cv2.polylines(image, [line], False, color, stroke.width, cv2.LINE_AA, 4)   # thick lines have round ends


def blank():
    return np.full((PAGE_H, PAGE_W, 3), PAPER, np.uint8)


def read_png(path):
    """A page from a PNG (any path, also with Cyrillic letters), fitted to the page size."""
    data = np.fromfile(str(path), np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        return blank()
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    if image.shape[:2] != (PAGE_H, PAGE_W):
        image = cv2.resize(image, (PAGE_W, PAGE_H), interpolation=cv2.INTER_AREA)
    return image


def write_png(path, image):
    ok, data = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if ok:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data.tofile(str(path))
    return ok


class Page:
    def __init__(self, path=None):
        self.path = path
        self._base = None          # the picture the page was opened with
        self._image = None
        self.steps = []            # Stroke or Clear, oldest first
        self.version = 0           # changes whenever the picture does
        self.unsaved = False

    @property
    def image(self):
        if self._image is None:
            self._base = read_png(self.path) if self.path is not None and Path(self.path).exists() else blank()
            self._image = self._base.copy()
        return self._image

    def begin(self, tool, color, point):
        stroke = Stroke(tool, color, point)
        self.steps.append(stroke)
        _draw(self.image, stroke)
        self._changed()
        return stroke

    def extend(self, stroke, point):
        last = stroke.points[-1]
        if abs(point[0] - last[0]) + abs(point[1] - last[1]) < 1.0:
            return
        stroke.points.append(point)
        _draw(self.image, stroke, len(stroke.points) - 1)
        self._changed()

    def clear(self):
        if not self.steps or not isinstance(self.steps[-1], Clear):
            self.steps.append(Clear())
            self.image[:] = PAPER
            self._changed()

    def undo(self):
        if not self.steps:
            return False
        self.steps.pop()
        image = self.image
        start = max((i for i, step in enumerate(self.steps) if isinstance(step, Clear)), default=-1)
        image[:] = PAPER if start >= 0 else self._base
        for step in self.steps[start + 1:]:
            _draw(image, step)
        self._changed()
        return True

    def _changed(self):
        self.version += 1
        self.unsaved = True

    def save(self):
        if self.unsaved and self.path is not None:
            write_png(self.path, self.image)
        self.unsaved = False


class Notebook:
    """The pages, the one being drawn on, and saving. folder None: nothing is saved (tests, the video)."""

    def __init__(self, folder=None):
        self.folder = Path(folder) if folder is not None else None
        files = sorted(self.folder.glob("page_*.png")) if self.folder is not None and self.folder.is_dir() else []
        self.pages = [Page(path) for path in files] or [Page(self._path(1))]
        self.index = len(self.pages) - 1
        self.tool, self.color = "pen", COLORS[0]
        self.stroke = None
        self.changed_at = 0.0

    def _path(self, number):
        return self.folder / f"page_{number:03d}.png" if self.folder is not None else None

    @property
    def page(self):
        return self.pages[self.index]

    # drawing, in page pixels
    def begin(self, point):
        self.stroke = self.page.begin(self.tool, self.color, point)
        self.changed_at = time.perf_counter()

    def extend(self, point):
        if self.stroke is not None:
            self.page.extend(self.stroke, point)
            self.changed_at = time.perf_counter()

    def end(self):
        self.stroke = None
        self.changed_at = time.perf_counter()

    def undo(self):
        self.end()
        self.page.undo()

    def clear(self):
        self.end()
        self.page.clear()

    # pages
    def go(self, step):
        self.end()
        self.save()
        self.index = min(max(self.index + step, 0), len(self.pages) - 1)

    def add_page(self):
        self.end()
        self.save()
        number = max((int(p.path.stem[5:]) for p in self.pages if p.path is not None and p.path.stem[5:].isdigit()),
                     default=0) + 1
        self.pages.append(Page(self._path(number)))
        self.index = len(self.pages) - 1

    def save(self):
        for page in self.pages:
            page.save()

    def save_if_due(self, now):
        """Save a moment after the last change (not in the middle of a stroke)."""
        if self.stroke is None and self.page.unsaved and now - self.changed_at >= SAVE_DELAY:
            self.save()
            return True
        return False

    def copy(self):
        return copy_to_clipboard(self.page.image)


# -- the clipboard ------------------------------------------------------------------------

CF_DIB, GMEM_MOVEABLE = 8, 0x0002


def dib(image):
    """An RGB image as a packed device-independent bitmap (what the clipboard takes as CF_DIB)."""
    h, w = image.shape[:2]
    stride = (w * 3 + 3) & ~3
    header = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, stride * h, 2835, 2835, 0, 0)
    rows = np.zeros((h, stride), np.uint8)
    rows[:, :w * 3] = image[::-1, :, ::-1].reshape(h, w * 3)      # bottom-up, blue first
    return header + rows.tobytes()


def copy_to_clipboard(image):
    """Put the picture on the clipboard. False if Windows would not let us."""
    data = dib(image)
    user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = (wintypes.UINT, ctypes.c_size_t), wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = (wintypes.HGLOBAL,), ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = (wintypes.UINT, wintypes.HANDLE), wintypes.HANDLE
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_DIB, handle):     # on success the clipboard owns the memory
            kernel32.GlobalFree(handle)
            return False
    finally:
        user32.CloseClipboard()
    return True
