"""Camera -> MediaPipe hand or face tracking -> gestures -> mouse, on a background thread."""

import importlib.util
import math
import sys
import threading
import time
import types
from collections import Counter, deque
from functools import lru_cache

import cv2
import numpy as np

from . import resource_path, system, tuning, winmouse
from .face import EYES, EYES_CLOSED, NO_FACE, NOSE_TIP, FaceEngine, read_face
from .gestures import DRAG, MOVE, NO_HAND, PENDING, PRESSED, RIGHT, SCROLL, palm_center, zone_rect
from .twohands import Dwell, HandControl

HAND_MODEL = "models/hand_landmarker.task"
FACE_MODEL = "models/face_landmarker.task"
FRAME_W, FRAME_H = 640, 480

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)

# BGR colours of the hand / face drawing for each mode
MODE_COLORS = {
    NO_HAND: (150, 150, 150),
    NO_FACE: (150, 150, 150),
    MOVE: (110, 200, 80),
    PENDING: (0, 200, 255),
    PRESSED: (0, 200, 255),
    EYES_CLOSED: (0, 200, 255),
    DRAG: (60, 90, 255),
    RIGHT: (220, 110, 230),
    SCROLL: (255, 170, 50),
}
PAUSED_COLOR = (150, 150, 150)
BUTTON_HAND_COLOR = (240, 190, 90)    # the second hand, the one with the buttons


def mediapipe():
    """The mediapipe module, imported on first use: it takes a while, and the window does not wait for it."""
    if "matplotlib" not in sys.modules and importlib.util.find_spec("matplotlib") is None:
        # mediapipe.tasks imports matplotlib for plotting helpers AirMouse never
        # calls. The app is built without it (big and slow to import), so an
        # empty stand-in lets that import succeed.
        plt = types.ModuleType("matplotlib.pyplot")
        stub = types.ModuleType("matplotlib")
        stub.pyplot = plt
        sys.modules.update({"matplotlib": stub, "matplotlib.pyplot": plt})
    import mediapipe as mp
    return mp


def _warm_up():
    try:
        mediapipe()
        from mediapipe.tasks.python.core import mediapipe_c_bindings
        mediapipe_c_bindings.load_raw_library()   # the 60 MB library itself, slow the first time too
    except Exception:  # «Старт» loads it again and reports what went wrong
        pass


def preload():
    """Load MediaPipe in the background while the user looks at the window, so «Старт» is quick."""
    threading.Thread(target=_warm_up, name="AirMousePreload", daemon=True).start()


@lru_cache(maxsize=1)
def face_connections():
    mediapipe()
    from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections as C
    return [
        (c.start, c.end)
        for group in (C.FACE_LANDMARKS_FACE_OVAL, C.FACE_LANDMARKS_LEFT_EYE, C.FACE_LANDMARKS_RIGHT_EYE,
                      C.FACE_LANDMARKS_LEFT_EYEBROW, C.FACE_LANDMARKS_RIGHT_EYEBROW, C.FACE_LANDMARKS_LIPS)
        for c in group
    ]


def create_landmarker(kind="hand", confidence=0.6, hands=1):
    """kind: "hand", or "gaze" / "head" for the face model. confidence: how sure the hand model must be.
    hands: how many hands to look for (2: a second hand for the buttons, see twohands.py)."""
    mediapipe()
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        FaceLandmarker, FaceLandmarkerOptions, HandLandmarker, HandLandmarkerOptions, RunningMode,
    )
    # Pass the model as bytes: MediaPipe cannot open paths with non-Latin characters.
    if kind == "hand":
        return HandLandmarker.create_from_options(HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=resource_path(HAND_MODEL).read_bytes()),
            running_mode=RunningMode.VIDEO,
            num_hands=hands,
            min_hand_detection_confidence=confidence,
            min_hand_presence_confidence=confidence,
            min_tracking_confidence=confidence,
        ))
    return FaceLandmarker.create_from_options(FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_buffer=resource_path(FACE_MODEL).read_bytes()),
        running_mode=RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
    ))


def selftest():
    """Load both models and run them once on a blank frame (checks a built .exe)."""
    mp = mediapipe()
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((FRAME_H, FRAME_W, 3), np.uint8))
    for kind in ("hand", "head"):
        landmarker = create_landmarker(kind)
        try:
            landmarker.detect_for_video(image, 0)
        finally:
            landmarker.close()
    return 0


CAMERA_SIZES = {640: (640, 480), 1280: (1280, 720)}


def _open_camera(index, width=FRAME_W, fps=30):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)  # DirectShow opens much faster on Windows
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Не удалось открыть камеру №{index}.\n"
                           "Проверьте, что она подключена и не занята другой программой.")
    w, h = CAMERA_SIZES.get(int(width), (FRAME_W, FRAME_H))
    if fps > 30 or w > FRAME_W:
        # Most webcams give 60 frames per second or HD only as MJPG; the default format tops out lower.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


class Tracker:
    """Runs capture, tracking and gestures on a background thread.

    The UI reads `mode`, `fps`, `palm`, `face`, `error` and `take_preview()`;
    it sets `control_enabled` to pause or resume mouse control. For the
    on-screen widgets: `progress`, `stats`, `events` and `widget_toggles`. Hand gestures can pause and
    resume control themselves: `pause_toggles` counts them.
    """

    def __init__(self, settings):
        self.settings = settings
        self.kind = settings.mode      # "hand", "gaze" or "head"; fixed for this run
        self.control_enabled = True
        self.mode = NO_HAND if self.kind == "hand" else NO_FACE
        self.palm = None      # hand: palm centre in the camera image, 0..1
        self.face = None      # face: (time, FaceFrame or None) of the newest frame
        self.fps = 0.0
        self.error = None
        self.progress = 0.0               # how near the next click is (fingers closing, eyes shut), 0..1
        self.stats = Counter()            # done this run: "left" and "right" clicks, "wheel" steps
        self.events = deque(maxlen=32)    # (number, time, action) of clicks, presses and scroll steps
        self.widget_toggles = 0           # thumbs-up gestures so far
        self.pause_toggles = 0            # pause / resume gestures so far (both thumbs up)
        self._event_number = 0
        self._preview = None
        self._recenter = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="AirMouseTracker", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    @property
    def running(self):
        return self._thread.is_alive()

    def recenter(self):
        """Head mode: make the current head position the screen centre."""
        self._recenter = True

    def take_preview(self):
        """Newest camera frame with the hand / face drawn on it (RGB), or None if nothing new."""
        with self._lock:
            frame, self._preview = self._preview, None
        return frame

    def _run(self):
        mouse = winmouse.Mouse()
        cap = landmarker = None
        try:
            s = self.settings
            cap = _open_camera(s.camera_index, tuning.get(s, "camera_width"), tuning.get(s, "camera_fps"))
            mp = mediapipe()
            hand_count = 2 if tuning.get(s, "two_hands") else 1
            landmarker = create_landmarker(self.kind, tuning.get(s, "hand_confidence"), hand_count)
            sw, sh = winmouse.screen_size()
            if self.kind == "hand":
                control = HandControl(self.settings, sw, sh)
            else:
                engine = FaceEngine(self.settings, sw, sh, use_gaze=self.kind == "gaze")
                dwell = Dwell(self.settings, sw)
            t0 = last_t = time.perf_counter()
            last_ms = -1
            failures = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > 50:
                        raise RuntimeError("Камера перестала отдавать изображение.")
                    time.sleep(0.02)
                    continue
                failures = 0
                t = time.perf_counter()
                if tuning.get(s, "mirror"):
                    frame = cv2.flip(frame, 1)  # mirror, so moving right moves the cursor right
                h, w = frame.shape[:2]

                ms = max(int((t - t0) * 1000), last_ms + 1)  # MediaPipe needs increasing timestamps
                last_ms = ms
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)

                second = None
                if self.kind == "hand":
                    hands = [[(p.x * w, p.y * h, p.z * w) for p in marks] for marks in result.hand_landmarks]
                    actions = control.update(hands, w, h, t, winmouse.cursor_pos(), self.control_enabled)
                    pts, second = control.pointer, control.second
                    self.palm = (palm_center(pts)[0] / w, palm_center(pts)[1] / h) if pts else None
                    self._perform(actions, mouse, t)
                    self.mode, self.progress = control.mode, control.progress
                else:
                    pts = face = None
                    if result.face_landmarks:
                        pts = [(p.x * w, p.y * h) for p in result.face_landmarks[0]]
                        shapes = result.face_blendshapes[0] if result.face_blendshapes else []
                        face = read_face(pts, {s.category_name: s.score for s in shapes})
                    self.face = (t, face)
                    if self._recenter:
                        self._recenter = False
                        engine.recenter()
                    if self.control_enabled:
                        here = winmouse.cursor_pos()
                        actions = engine.update(face, t, here)
                        for action in actions:
                            if action[0] == "move":
                                here = action[1:]
                        if any(a[0] in ("click", "down", "up", "wheel") for a in actions):
                            dwell.disarm(here)
                        else:
                            actions += dwell.update(here, t, face is not None and engine.mode == MOVE)
                    else:
                        actions = engine.release_all()
                        dwell.reset()
                    self._perform(actions, mouse, t)
                    self.mode = engine.mode
                    self.progress = max(engine.progress, dwell.progress)

                self._publish_preview(frame, pts, sw, sh, second)
                dt = t - last_t
                last_t = t
                if dt > 0:
                    self.fps = 1.0 / dt if self.fps == 0 else 0.9 * self.fps + 0.1 / dt
        except Exception as exc:  # shown to the user by the UI
            self.error = str(exc) or exc.__class__.__name__
        finally:
            mouse.release_all()
            if landmarker is not None:
                landmarker.close()
            if cap is not None:
                cap.release()

    def _perform(self, actions, mouse, t):
        for action in actions:
            kind = action[0]
            if kind == "widgets":
                self.widget_toggles += 1
            elif kind == "pause":
                self.control_enabled = not self.control_enabled
                self.pause_toggles += 1
            elif kind == "keys":
                system.press_keys(action[1])
            elif kind == "window":
                system.window_command(action[1])
            else:
                mouse.do(action)
                self._note(action, t)

    def _note(self, action, t):
        """Count what was done and keep it for the cursor ring (which flashes on clicks)."""
        kind = action[0]
        if kind == "move":
            return
        if kind in ("click", "down"):
            self.stats["right" if action[1] == "right" else "left"] += 1
        elif kind == "wheel":
            self.stats["wheel"] += 1
        self._event_number += 1
        self.events.append((self._event_number, t, action))

    def _publish_preview(self, frame, pts, screen_w, screen_h, second=None):
        """Draw the hand (and the second hand, if any) or the face on the frame and keep it for the UI."""
        h, w = frame.shape[:2]
        color = MODE_COLORS.get(self.mode, MODE_COLORS[MOVE]) if self.control_enabled else PAUSED_COLOR
        if self.kind == "hand":
            x0, y0, x1, y1 = zone_rect(self.settings, w, h, screen_w, screen_h)
            cv2.rectangle(frame, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)),
                          (230, 230, 230), 1, cv2.LINE_AA)
        if pts and self.kind == "hand":
            points = [(int(p[0]), int(p[1])) for p in pts]
            for a, b in HAND_CONNECTIONS:
                cv2.line(frame, points[a], points[b], color, 2, cv2.LINE_AA)
            for p in points:
                cv2.circle(frame, p, 3, (255, 255, 255), -1, cv2.LINE_AA)
            px, py = palm_center(pts)
            cv2.circle(frame, (int(px), int(py)), 9, color, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(px), int(py)), 9, (255, 255, 255), 2, cv2.LINE_AA)
        if second and self.kind == "hand":
            points = [(int(p[0]), int(p[1])) for p in second]
            for a, b in HAND_CONNECTIONS:
                cv2.line(frame, points[a], points[b], BUTTON_HAND_COLOR, 2, cv2.LINE_AA)
            for p in points:
                cv2.circle(frame, p, 3, (255, 255, 255), -1, cv2.LINE_AA)
        if pts and self.kind != "hand":
            points = [(int(p[0]), int(p[1])) for p in pts]
            for a, b in face_connections():
                cv2.line(frame, points[a], points[b], color, 1, cv2.LINE_AA)
            for _c1, _c2, iris in EYES:
                cx = sum(pts[i][0] for i in iris) / len(iris)
                cy = sum(pts[i][1] for i in iris) / len(iris)
                r = max(2, int(math.dist(pts[iris[1]], pts[iris[3]]) / 2))
                cv2.circle(frame, (int(cx), int(cy)), r, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.circle(frame, (int(cx), int(cy)), 2, color, -1, cv2.LINE_AA)
            cv2.circle(frame, points[NOSE_TIP], 6, color, -1, cv2.LINE_AA)
            cv2.circle(frame, points[NOSE_TIP], 6, (255, 255, 255), 2, cv2.LINE_AA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with self._lock:
            self._preview = rgb
