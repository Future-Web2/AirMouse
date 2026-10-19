"""KPI measurements (see docs/KPI.md): start-up, window drawing, tracking cost and cursor quality.

    python main.py --bench [report.json]
    AirMouse.exe --bench report.json     (the built app has no console, so name a file)

Nothing appears on screen and the camera stays off: the window is built hidden
and fed synthetic camera images, the models run on blank frames, and the cursor
numbers come from the real gesture engine driven by a simulated, noisy hand.
"""

import ctypes
import json
import math
import statistics
import sys
import time
from ctypes import wintypes
from pathlib import Path

FPS = 30
SCREEN_W, SCREEN_H = 1920, 1080
FRAME_W, FRAME_H = 640, 480

# -- process clock and memory ------------------------------------------------------

_k32 = ctypes.WinDLL("kernel32")
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
_k32.GetSystemTimePreciseAsFileTime.argtypes = (ctypes.POINTER(wintypes.FILETIME),)


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


_k32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MemoryCounters), wintypes.DWORD)


def _ticks(filetime):
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def uptime():
    """Seconds since this process started (includes the .exe loader and Python's own start-up)."""
    created, ended, kernel, user, now = (wintypes.FILETIME() for _ in range(5))
    _k32.GetProcessTimes(_k32.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(ended),
                         ctypes.byref(kernel), ctypes.byref(user))
    _k32.GetSystemTimePreciseAsFileTime(ctypes.byref(now))
    return (_ticks(now) - _ticks(created)) / 1e7


def memory_mb():
    """RAM this process uses now (working set), MB."""
    counters = _MemoryCounters(cb=ctypes.sizeof(_MemoryCounters))
    _k32.K32GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2 ** 20


def _timed(fn, runs, warmup=3):
    """Median and 95th percentile of fn's run time, ms."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {"median_ms": round(statistics.median(times), 2), "p95_ms": round(times[round(0.95 * (runs - 1))], 2)}


def _isolate_settings():
    """Default settings in a temporary folder: never read or change the user's own."""
    import tempfile

    from . import settings
    folder = Path(tempfile.mkdtemp(prefix="airmouse_bench_"))
    settings.SETTINGS_DIR = folder
    settings.SETTINGS_FILE = folder / "settings.json"


def _hide_windows():
    """Make every Tk window start withdrawn, so nothing is drawn on screen."""
    import tkinter as tk
    if getattr(tk.Tk, "hidden_for_bench", False):
        return

    class HiddenTk(tk.Tk):
        hidden_for_bench = True

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.withdraw()

    tk.Tk = HiddenTk


# -- start-up and window ---------------------------------------------------------------

class _OffscreenDC:
    """A device context drawing into memory: times putting the image in a window without showing one."""

    def __init__(self, w, h):
        self.user32, self.gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
        self.user32.GetDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
        self.gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
        self.gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
        self.gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
        self.gdi32.DeleteDC.argtypes = (wintypes.HDC,)
        screen = self.user32.GetDC(None)
        self.dc = self.gdi32.CreateCompatibleDC(screen)
        self.bitmap = self.gdi32.CreateCompatibleBitmap(screen, w, h)
        self.gdi32.SelectObject(self.dc, self.bitmap)
        self.user32.ReleaseDC(None, screen)

    def close(self):
        self.gdi32.DeleteDC(self.dc)
        self.gdi32.DeleteObject(self.bitmap)


def startup():
    """From process start to the first finished frame of the main window (Liquid Glass, 100%)."""
    start = uptime()
    t0 = time.perf_counter()
    from . import ui
    t1 = time.perf_counter()
    app = ui.App(scale=1.0)
    t2 = time.perf_counter()
    app.blitter.show(app.render(time.perf_counter(), 1 / FPS))
    t3 = time.perf_counter()
    result = {
        "process_ready_s": round(start, 3),
        "import_ui_s": round(t1 - t0, 3),
        "build_window_s": round(t2 - t1, 3),
        "first_frame_s": round(t3 - t2, 3),
        "total_s": round(uptime(), 3),
        "mediapipe_loaded": "mediapipe" in sys.modules,
    }
    app.onscreen.close()
    app.root.destroy()
    return result


def window(scale, frames=40):
    """Cost of one frame of the Liquid Glass window (draw it and put it on screen), camera off and on."""
    from . import ui
    from .glass import LiquidBackdrop
    app = ui.App(scale=scale)
    screen = _OffscreenDC(*app.size)
    cams = [LiquidBackdrop(FRAME_W, FRAME_H, seed=11).render(i * 0.15) for i in range(6)]
    clock = [0]

    def frame(camera):
        clock[0] += 1
        if camera:
            app._on_frame(cams[clock[0] % len(cams)])
        app.blitter.show(app.render(clock[0] / FPS, 1 / FPS), screen.dc)

    result = {
        "size": "%dx%d" % app.size,
        "camera_off": _timed(lambda: frame(False), frames),
        "camera_on": _timed(lambda: frame(True), frames),
    }
    screen.close()
    app.onscreen.close()
    app.root.destroy()
    return result


# -- on-screen widgets ----------------------------------------------------------------------

class _WidgetEnv:
    """What widgets ask of OnScreen, without windows: a camera picture and the real (read-only) system."""

    def __init__(self, s):
        import cv2

        from . import system
        from .glass import LiquidBackdrop
        self.s = s
        self.volume, self.load = system.Volume(), system.SystemLoad()
        self.frame = cv2.resize(LiquidBackdrop(FRAME_W, FRAME_H, seed=11).render(0.5), (FRAME_W, FRAME_H))
        self.frame_id = 0

    def status(self):
        return "Курсор", (94, 224, 122), f"{30 - self.frame_id % 2} кадр/с"

    def camera_on(self):
        return True

    def cursor(self):
        return 0, 0

    def request(self, item):
        pass

    def changed(self):
        pass

    def place(self, widget):
        pass

    def clamp(self, widget, x, y):
        return x, y


def onscreen_widgets(scale=1.5, frames=30):
    """Redrawing the widgets and the cursor ring, ready for the window (no window is shown).

    The status widget redraws with every camera frame it shows (at most 15 a second),
    the cursor ring whenever the gesture changes; the others about once a second or less.
    """
    from . import onscreen
    env = _WidgetEnv(scale)
    status = onscreen.StatusWidget({"type": "status", "on": True, "x": 0, "y": 0}, env)
    clock = [0.0]

    def status_frame():
        clock[0] += 1 / 15
        env.frame_id += 1
        status.tick(clock[0])
        status.render(clock[0]).bgra()

    ring = onscreen.CursorRing(scale)
    progress = [0.0]

    def ring_frame():
        progress[0] = (progress[0] + 0.07) % 1.0
        ring.render(ring.state(onscreen.MOVE, progress[0], 0.0)).bgra()

    everything = []
    for spec in onscreen.default_widgets():
        widget = onscreen.WIDGET_CLASSES[spec["type"]](dict(spec, x=0, y=0), env)
        widget.tick(0.0)
        everything.append(widget)
    t = time.perf_counter()
    for widget in everything:
        widget.render(0.0).bgra()
    return {
        "status_with_camera": _timed(status_frame, frames),
        "cursor_ring": _timed(ring_frame, frames),
        "all_widgets_once_ms": round((time.perf_counter() - t) * 1000, 1),
    }


# -- tracking ---------------------------------------------------------------------------

def tracking(frames=30):
    """Model loading and per-frame cost of tracking.

    The models run on blank frames, so the hand / face search runs on every
    frame (the slower case: with a hand in view MediaPipe only follows it).
    """
    import cv2
    import numpy as np

    from . import tracker
    from .gestures import GestureEngine
    from .glass import LiquidBackdrop
    from .settings import Settings
    mp = tracker.mediapipe()
    blank = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((FRAME_H, FRAME_W, 3), np.uint8))
    result = {}
    for kind in ("hand", "head"):
        t = time.perf_counter()
        landmarker = tracker.create_landmarker(kind)
        load_ms = (time.perf_counter() - t) * 1000
        stamp = [0]

        def detect():
            stamp[0] += 33
            landmarker.detect_for_video(blank, stamp[0])

        result[kind] = {"load_model_ms": round(load_ms), **_timed(detect, frames, warmup=5)}
        if kind == "hand":
            result["memory_mb"] = round(memory_mb())
        landmarker.close()

    # Everything else the tracking thread does per frame (all but the camera and the model).
    trk = tracker.Tracker(Settings())
    engine = GestureEngine(trk.settings, SCREEN_W, SCREEN_H)
    camera = cv2.cvtColor(LiquidBackdrop(FRAME_W, FRAME_H, seed=3).render(1.0), cv2.COLOR_RGB2BGR)
    rng = np.random.default_rng(0)
    ox, oy = cam_for(960, 540)
    clock = [100.0]

    def rest_of_frame():
        clock[0] += 1 / FPS
        frame = cv2.flip(camera, 1)
        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pts = noisy(hand(ox, oy), rng)
        engine.update(pts, FRAME_W, FRAME_H, clock[0], (960, 540))
        trk._publish_preview(frame, pts, SCREEN_W, SCREEN_H)
        trk.take_preview()

    result["rest_of_frame"] = _timed(rest_of_frame, 60)
    return result


# -- simulated hand -----------------------------------------------------------------------

def hand(ox, oy, pinch=0.0, pose="open"):
    """21 hand landmarks in camera pixels (z = 0); (ox, oy) is the middle knuckle, palm length 100 px.

    pinch: how far the thumb tip has moved to the index tip (0 = open hand, 1 = touching).
    pose: "open"; "two" folds the ring and little fingers (scroll); "right" aims the
    thumb between the index and middle tips (right click); "thumb" is a fist with
    the thumb up (shows / hides the on-screen widgets).
    """
    mcp = {5: (ox - 50, oy + 5), 9: (ox, oy), 13: (ox + 50, oy + 5), 17: (ox + 95, oy + 15)}
    folded = {13, 17} if pose == "two" else set(mcp) if pose == "thumb" else set()
    pts = [None] * 21
    pts[0] = (ox, oy + 100, 0.0)
    for i, (mx, my) in mcp.items():
        for k, off in enumerate((0, -30, -15, 10) if i in folded else (0, -40, -65, -90)):
            pts[i + k] = (mx, my + off, 0.0)
    pts[1], pts[2], pts[3] = (ox - 60, oy + 80, 0.0), (ox - 85, oy + 55, 0.0), (ox - 100, oy + 30, 0.0)
    if pose == "thumb":
        pts[1], pts[2], pts[3], pts[4] = ((ox - 55, oy + 75, 0.0), (ox - 72, oy + 35, 0.0),
                                          (ox - 78, oy - 20, 0.0), (ox - 80, oy - 80, 0.0))
        return pts
    if pose == "right":
        tip = ((pts[8][0] + pts[12][0]) / 2, pts[8][1] + 5)
    else:
        tip = (pts[8][0], pts[8][1] + 8)
    away = (ox - 110, oy + 5)
    pts[4] = (away[0] + (tip[0] - away[0]) * pinch, away[1] + (tip[1] - away[1]) * pinch, 0.0)
    return pts


def noisy(pts, rng, sigma=0.8, common=0.5):
    """Tracking noise: each landmark shakes a little (sigma px), the whole hand together (common px)."""
    cx, cy = rng.normal(0.0, common, 2)
    shake = rng.normal(0.0, sigma, (len(pts), 2))
    return [(x + cx + dx, y + cy + dy, z) for (x, y, z), (dx, dy) in zip(pts, shake)]


def cam_for(sx, sy, settings=None):
    """Middle-knuckle position in the camera image that puts the palm on screen point (sx, sy)."""
    from .gestures import zone_rect
    from .settings import Settings
    x0, y0, x1, y1 = zone_rect(settings or Settings(), FRAME_W, FRAME_H, SCREEN_W, SCREEN_H)
    px = (x0 + sx / (SCREEN_W - 1) * (x1 - x0)) * FRAME_W
    py = (y0 + sy / (SCREEN_H - 1) * (y1 - y0)) * FRAME_H
    return px - 19, py - 25   # the palm centre of hand() is (ox + 19, oy + 25)


class HandSim:
    """Feeds a simulated hand to the real GestureEngine, frame by frame, and records what it does."""

    def __init__(self, seed=0, settings=None, fps=FPS, sigma=0.8, common=0.5):
        import numpy as np

        from .gestures import GestureEngine
        from .settings import Settings
        self.settings = settings or Settings()
        self.engine = GestureEngine(self.settings, SCREEN_W, SCREEN_H)
        self.rng = np.random.default_rng(seed)
        self.fps, self.sigma, self.common = fps, sigma, common
        self.t = 100.0
        self.cursor = (SCREEN_W // 2, SCREEN_H // 2)
        self.moves = 0
        self.events = []    # (time, action, cursor) of everything but cursor moves

    def step(self, ox, oy, pinch=0.0, pose="open", shift=(0.0, 0.0)):
        """One camera frame; shift moves the tracked hand without moving the real one (a glitch)."""
        self.t += 1.0 / self.fps
        pts = noisy(hand(ox + shift[0], oy + shift[1], pinch, pose), self.rng, self.sigma, self.common)
        for action in self.engine.update(pts, FRAME_W, FRAME_H, self.t, self.cursor):
            if action[0] == "move":
                self.cursor = action[1:]
                self.moves += 1
            else:
                self.events.append((self.t, action, self.cursor))

    def rest(self, frames, ox, oy, **kwargs):
        for _ in range(frames):
            self.step(ox, oy, **kwargs)

    def gone(self, frames):
        """Frames in which the camera sees no hand."""
        for _ in range(frames):
            self.t += 1.0 / self.fps
            for action in self.engine.update(None, FRAME_W, FRAME_H, self.t, self.cursor):
                self.events.append((self.t, action, self.cursor))

    def pinch(self, ox, oy, close=3, hold=3, release=3, pose="open", sink=4.0):
        """Thumb to index (pose "right": to index and middle) and back.

        The palm sinks `sink` px while the fingers close, as a real one does.
        """
        for i in range(1, close + 1):
            self.step(ox, oy + sink * i / close, pinch=i / close, pose=pose)
        self.rest(hold, ox, oy + sink, pinch=1.0, pose=pose)
        for i in range(release - 1, -1, -1):
            self.step(ox, oy + sink * i / release, pinch=i / release, pose=pose)

    def presses(self, button="left"):
        """Cursor positions of the presses of a button (a click, or a down before an up)."""
        return [cursor for _t, action, cursor in self.events
                if action[0] in ("click", "down") and action[1] == button]


def still_hand(seconds=10.0, sigma=0.8, common=0.5, fps=FPS, seed=1, settings=None):
    """A hand held still: how often and how far the cursor moves anyway."""
    sim = HandSim(seed, settings=settings, fps=fps, sigma=sigma, common=common)
    ox, oy = cam_for(960, 540)
    sim.rest(int(1.5 * fps), ox, oy)
    sim.moves, first, spread = 0, sim.cursor, 0.0
    for _ in range(int(seconds * fps)):
        sim.step(ox, oy)
        spread = max(spread, math.dist(first, sim.cursor))
    return {"moves_per_min": round(sim.moves / seconds * 60, 1), "spread_px": round(spread, 1)}


def lag_ms(speed, seed=2):
    """How far behind the hand the cursor runs while the hand moves at `speed` screen px/s, in ms."""
    seconds = 0.9
    sim = HandSim(seed)
    x0 = SCREEN_W / 2 - speed * seconds / 2
    sim.rest(45, *cam_for(x0, 540))
    lags = []
    frames = int(seconds * FPS)
    for i in range(1, frames + 1):
        x = x0 + speed * i / FPS
        sim.step(*cam_for(x, 540))
        if i > frames // 2:
            lags.append((x - sim.cursor[0]) / speed * 1000)
    return round(statistics.mean(lags), 1)


def click_offset(seed=3):
    """Move, stop and pinch: how far the click lands from where the cursor stopped, px."""
    sim = HandSim(seed)
    start, stop = cam_for(700, 700), cam_for(1250, 420)
    sim.rest(30, *start)
    for i in range(1, 19):   # 0.6 s, eased
        k = i / 18
        k = k * k * (3 - 2 * k)
        sim.step(start[0] + (stop[0] - start[0]) * k, start[1] + (stop[1] - start[1]) * k)
    sim.rest(8, *stop)
    before = sim.cursor
    sim.pinch(*stop)
    sim.rest(10, *stop)
    clicks = sim.presses()
    return {"clicks": len(clicks), "offset_px": round(math.dist(clicks[0], before), 1) if clicks else None}


def pinch_series(count=20, seed=4, fps=FPS, settings=None):
    """Pinches of random speed: every one should be exactly one left click (at any camera frame rate)."""
    sim = HandSim(seed, settings=settings, fps=fps)
    rng = sim.rng
    k = fps / FPS             # the same gestures in time, more frames at a higher rate
    ox, oy = cam_for(960, 540)
    sim.rest(round(30 * k), ox, oy)
    for _ in range(count):
        sim.pinch(ox, oy, close=round(rng.integers(2, 5) * k), hold=round(rng.integers(2, 8) * k),
                  release=round(rng.integers(2, 5) * k))
        sim.rest(round(rng.integers(18, 30) * k), ox, oy)
    actions = [a for _t, a, _c in sim.events]
    return {"pinches": count, "left": len(sim.presses()), "right": len(sim.presses("right")),
            "scroll": sum(a[0] == "wheel" for a in actions), "widgets": actions.count(("widgets",))}


def thumbs_up(seed=8):
    """A thumbs up held for a second, three times: each must show / hide the widgets once, and nothing else."""
    sim = HandSim(seed)
    ox, oy = cam_for(960, 540)
    sim.rest(30, ox, oy)
    starts = []
    for _ in range(3):
        starts.append(sim.t)
        sim.rest(30, ox, oy, pose="thumb")
        sim.rest(20, ox, oy)
    toggles = [t for t, action, _c in sim.events if action == ("widgets",)]
    delays = [min((t - start for t in toggles if t > start), default=None) for start in starts]
    return {"held": 3, "toggles": len(toggles), "other_actions": len(sim.events) - len(toggles),
            "seconds_to_toggle": None if None in delays else round(max(delays), 2)}


def double_click(seed=5):
    """Two quick pinches: two left clicks on the same pixel within Windows' double-click time."""
    sim = HandSim(seed)
    ox, oy = cam_for(960, 540)
    sim.rest(30, ox, oy)
    sim.pinch(ox, oy, close=2, hold=2, release=2)
    sim.rest(4, ox, oy)
    sim.pinch(ox, oy, close=2, hold=2, release=2)
    sim.rest(20, ox, oy)
    times = [t for t, a, _c in sim.events if a[0] in ("click", "down") and a[1] == "left"]
    clicks = sim.presses()
    ok = len(clicks) == 2 and clicks[0] == clicks[1] and times[1] - times[0] <= 0.5
    return {"clicks": len(clicks), "same_pixel": ok}


def false_actions(seconds=60.0, seed=6, fps=FPS):
    """An open hand that shakes (tremor and heavy tracking noise) but does nothing: count the actions."""
    sim = HandSim(seed, sigma=1.5, common=1.0, fps=fps)
    ox, oy = cam_for(960, 540)
    for i in range(int(seconds * fps)):
        t = i / fps
        sim.step(ox + 2.0 * math.sin(2 * math.pi * 6 * t), oy + 2.0 * math.cos(2 * math.pi * 5 * t))
    return len(sim.events)


def glitch(seed=7, settings=None):
    """One frame where tracking jumps 40 px: how far the cursor follows the jump, px."""
    sim = HandSim(seed, settings=settings)
    ox, oy = cam_for(960, 540)
    sim.rest(45, ox, oy)
    rest_at, worst = sim.cursor, 0.0
    sim.step(ox, oy, shift=(40.0, -25.0))
    for _ in range(15):
        worst = max(worst, math.dist(rest_at, sim.cursor))
        sim.step(ox, oy)
    return round(worst, 1)


def cursor_quality():
    return {
        "still_hand": still_hand(),
        "still_hand_bad_light": still_hand(sigma=1.5, common=1.0, fps=15),
        "lag_ms_300px_s": lag_ms(300),
        "lag_ms_1500px_s": lag_ms(1500),
        "click": click_offset(),
        "pinch_series": pinch_series(),
        "double_click": double_click(),
        "false_actions_per_min": false_actions(),
        "glitch_px": glitch(),
        "thumbs_up": thumbs_up(),
    }


# -- report -----------------------------------------------------------------------------

def run(out_path=None):
    from . import winmouse
    winmouse.enable_dpi_awareness()   # as the app does, before any window
    _isolate_settings()
    _hide_windows()
    report = {"startup": startup()}
    report["window_100"] = window(1.0)
    report["window_150"] = window(1.5)
    report["widgets_150"] = onscreen_widgets(1.5)
    report["tracking"] = tracking()
    report["cursor"] = cursor_quality()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    print(text)
    return 0
