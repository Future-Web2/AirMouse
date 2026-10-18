"""Mouse input through the Win32 SendInput API (the same path a real mouse uses)."""

import ctypes
import math
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT(ctypes.Structure):
    # The real INPUT holds a union; its mouse member is the largest one,
    # so this struct has the same size and layout.
    _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short


def enable_dpi_awareness():
    """Work in real screen pixels and keep the window sharp on scaled displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def screen_size():
    """Size of the primary monitor."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor_pos():
    pt = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return None  # e.g. while the UAC prompt or lock screen is shown
    return pt.x, pt.y


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _send(flags, dx=0, dy=0, data=0):
    event = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0))
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


class Mouse:
    """Performs actions from the gesture engine and remembers which buttons it holds."""

    def __init__(self):
        self.width, self.height = screen_size()
        self._held = set()

    def do(self, action):
        kind = action[0]
        if kind == "move":
            # Absolute coordinates run 0..65535 across the primary monitor.
            x = min(65535, math.ceil(action[1] * 65536 / self.width))
            y = min(65535, math.ceil(action[2] * 65536 / self.height))
            _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, x, y)
        elif kind == "down":
            _send(_BUTTONS[action[1]][0])
            self._held.add(action[1])
        elif kind == "up":
            _send(_BUTTONS[action[1]][1])
            self._held.discard(action[1])
        elif kind == "click":
            down, up = _BUTTONS[action[1]]
            _send(down)
            _send(up)
        elif kind == "wheel":
            _send(MOUSEEVENTF_WHEEL, data=action[1])

    def release_all(self):
        for button in list(self._held):
            self.do(("up", button))
