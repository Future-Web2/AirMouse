"""On-screen widgets and the main window's picture on Linux, with Tk (winoverlay.py and blit.py on Windows).

A LayeredWindow is a borderless always-on-top Tk window holding the picture. Without a compositor
X11 cannot blend a window with what is behind it, so the see-through parts of the picture are cut
away with the SHAPE extension (python-xlib): a panel keeps its rounded corners, only its soft shadow
is left out. The cursor ring lets the mouse through with an empty input shape; where SHAPE is
missing the ring is not shown, since it would catch the clicks meant for what is under it.

Everything here runs in the Tk thread; mouse handlers, as on Windows, only change state.
"""

import time
import tkinter as tk

import numpy as np
from PIL import Image, ImageTk

from . import linuxsystem

SOLID = 128                 # alpha from which a pixel belongs to the window
_seen = (0.0, None)         # (time, (x, y)): where Tk last saw the pointer over an AirMouse window


def cursor_pos():
    """Where the cursor is, for the on-screen widgets. Under Wayland the system cannot be asked, so a
    position Tk has just seen over a widget (it is being dragged) comes first."""
    if linuxsystem.wayland() and time.monotonic() - _seen[0] < 0.25:
        return _seen[1]
    return linuxsystem.cursor_pos() or _seen[1] or (0, 0)


def _runs(row):
    """(start, end) of each run of True in a row, as a tuple."""
    padded = np.concatenate(([False], row, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return tuple(zip(edges[::2].tolist(), edges[1::2].tolist()))


def mask_rectangles(mask):
    """The True part of a 2-D mask as (x, y, w, h) rectangles: the runs of each row, with rows that are
    alike joined into one band (a rounded panel is a few thin bands at its corners and one big one)."""
    rects = []
    previous, start = (), 0
    for y in range(mask.shape[0] + 1):
        runs = _runs(mask[y]) if y < mask.shape[0] else ()
        if runs != previous:
            rects += [(x0, start, x1 - x0, y - start) for x0, x1 in previous]
            previous, start = runs, y
    return rects


def _shape(window_id, rects, input_rects=None):
    """Cut an X window down to rectangles, and what the mouse can touch to input_rects ([]: nothing).
    False without the SHAPE extension."""
    d = linuxsystem._x()
    if d is None or not d.has_extension("SHAPE"):
        return False
    from Xlib import X
    from Xlib.ext import shape
    window = d.create_resource_object("window", window_id)
    window.shape_rectangles(shape.SO.Set, shape.SK.Bounding, X.Unsorted, 0, 0, rects)
    if input_rects is not None:
        window.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, input_rects)
    d.flush()
    return True


def unpremultiply(bgra):
    """Premultiplied BGRA -> RGB colours as they are where the picture is solid."""
    alpha = np.maximum(bgra[..., 3:4], 1).astype(np.float32)
    return np.clip(bgra[..., 2::-1].astype(np.float32) * (255.0 / alpha), 0, 255).astype(np.uint8)


class LayeredWindow:
    """A borderless always-on-top window showing a picture (see overlay.py for what it does)."""

    def __init__(self, click_through=False, on_mouse=None, hand_at=None):
        self.click_through, self.on_mouse, self.hand_at = click_through, on_mouse, hand_at
        self.x = self.y = self.w = self.h = 0
        self.visible = False
        self.usable = True          # False: the ring cannot let the mouse through here, so it stays hidden
        self.win = tk.Toplevel()
        self.win.withdraw()
        self.win.overrideredirect(True)        # no frame, not in the taskbar, never takes the focus
        self.win.attributes("-topmost", True)
        self.label = tk.Label(self.win, borderwidth=0, highlightthickness=0, background="black")
        self.label.pack()
        self._photo = None
        self._mask = None
        self._hand = None
        if on_mouse is not None:
            for sequence, handler in (("<Motion>", self._motion), ("<ButtonPress-1>", self._down),
                                      ("<ButtonRelease-1>", self._up), ("<Leave>", self._leave),
                                      ("<Button-4>", lambda e: self._wheel(e, 120)),
                                      ("<Button-5>", lambda e: self._wheel(e, -120)),
                                      ("<MouseWheel>", lambda e: self._wheel(e, e.delta))):
                self.label.bind(sequence, handler)

    def show(self, bgra, x, y):
        """Show a premultiplied BGRA picture (h, w, 4) with its top-left corner at screen (x, y)."""
        if not self.usable:
            return
        h, w = bgra.shape[:2]
        picture = Image.fromarray(unpremultiply(bgra))
        if self._photo is None or (w, h) != (self.w, self.h):
            self._photo = ImageTk.PhotoImage(picture)
            self.label.configure(image=self._photo)
        else:
            self._photo.paste(picture)
        self.w, self.h, self.x, self.y = w, h, int(x), int(y)
        self.win.geometry(f"{w}x{h}+{self.x}+{self.y}")
        if not self.visible:
            self.win.deiconify()
            self.win.update_idletasks()
            self.visible = True
        mask = bgra[..., 3] >= SOLID
        if self._mask is None or mask.shape != self._mask.shape or not np.array_equal(mask, self._mask):
            self._mask = mask
            window_id = int(self.win.wm_frame(), 16)
            if not _shape(window_id, mask_rectangles(mask), [] if self.click_through else None) and self.click_through:
                self.usable = False
                self.hide()
                return
        self._note()

    def move(self, x, y):
        """Move without redrawing."""
        self.x, self.y = int(x), int(y)
        self.win.geometry(f"+{self.x}+{self.y}")
        self._note()

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False
        linuxsystem.note_window(id(self), None)

    def destroy(self):
        linuxsystem.note_window(id(self), None)
        if self.win is not None:
            self.win.destroy()
            self.win = None
            self.visible = False

    def _note(self):
        """Tell own_window_at where this window is (the ring is not in the way of anything)."""
        if not self.click_through:
            linuxsystem.note_window(id(self), (self.x, self.y, self.w, self.h))

    # the mouse, from Tk's events
    @staticmethod
    def _saw(event):
        global _seen
        _seen = (time.monotonic(), (event.x_root, event.y_root))

    def _motion(self, event):
        self._saw(event)
        self.on_mouse("move", event.x, event.y, 0)
        if self.hand_at is not None:
            hand = bool(self.hand_at(event.x, event.y))
            if hand != self._hand:
                self._hand = hand
                self.label.configure(cursor="hand2" if hand else "")

    def _down(self, event):
        self._saw(event)
        self.on_mouse("down", event.x, event.y, 0)

    def _up(self, event):
        self._saw(event)
        self.on_mouse("up", event.x, event.y, 0)

    def _leave(self, _event):
        self.on_mouse("leave", 0, 0, 0)

    def _wheel(self, event, delta):
        self.on_mouse("wheel", event.x, event.y, delta)


class TkBlitter:
    """Shows w x h RGB images in a Tk frame (on Windows blit.py puts them into the window with GDI)."""

    def __init__(self, view, w, h):
        self.label = tk.Label(view, borderwidth=0, highlightthickness=0)
        self.label.place(x=0, y=0, width=w, height=h)
        # The window's mouse handlers are bound to the frame; the picture covers it, so it passes them on.
        self.label.bindtags((str(view),) + self.label.bindtags())
        self.photo = ImageTk.PhotoImage(Image.new("RGB", (w, h)))
        self.label.configure(image=self.photo)

    def show(self, rgb, hdc=None):
        self.photo.paste(Image.fromarray(rgb))

    def repaint(self, hdc=None):
        """Nothing to do: Tk draws the picture again by itself."""
