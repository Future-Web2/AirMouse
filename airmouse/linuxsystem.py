"""Linux under AirMouse: the mouse and keys, the screen, other programs' windows, sound, load, the
clipboard, one copy of the program. system.py picks this module on Linux (winsystem.py on Windows).

The mouse and keys go through uinput, a virtual input device in the kernel: it works the same under
X11 and Wayland, but /dev/uinput must be writable (the «input» group and the udev rule in
linux/99-airmouse-uinput.rules, see the README). Without it, under X11 the XTEST extension stands
in (python-xlib).

X11 tells a program where the cursor is, which keys are down and which window is active; Wayland
does not. There the last position AirMouse set stands in for the cursor, the Ctrl+Alt keys work
while an AirMouse window is active, and window commands become the desktop's own key combinations.
"""

import atexit
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2

from .i18n import _
from .keys import parse_keys

try:
    import fcntl
except ImportError:      # not Linux: the tests of this module run everywhere
    fcntl = None

CAMERA_API = cv2.CAP_V4L2
VK_CONTROL, VK_MENU = 0x11, 0x12
NO_INPUT = ("Нет доступа к /dev/uinput, поэтому AirMouse не может двигать мышь.\n"
            "Добавьте себя в группу input и правило udev (см. README), затем войдите в систему заново.")


def wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE") == "wayland"


def desktop():
    """The desktop environment, lower case: "gnome", "kde", "ubuntu:gnome", ... ("" if unknown)."""
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


# -- X11 ------------------------------------------------------------------------------------

_local = threading.local()


def _x():
    """This thread's connection to the X server (python-xlib), or None: no X server or no python-xlib.
    Under Wayland it is XWayland, which only knows about windows of X11 programs."""
    if not hasattr(_local, "display"):
        _local.display = None
        if os.environ.get("DISPLAY"):
            try:
                from Xlib import display
                _local.display = display.Display()
            except Exception:   # no server, no permission, no python-xlib: X11 features are off
                pass
    return _local.display


def _xtest():
    """The display, if it can fake input (XTEST); otherwise None."""
    d = _x()
    return d if d is not None and d.has_extension("XTEST") else None


# -- uinput: a virtual mouse and keyboard ----------------------------------------------------

UINPUT = "/dev/uinput"
EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
SYN_REPORT = 0
REL_WHEEL, REL_WHEEL_HI_RES = 0x08, 0x0B
ABS_X, ABS_Y = 0x00, 0x01
BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112}
X_BUTTONS = {"left": 1, "middle": 2, "right": 3}
BUS_VIRTUAL = 0x06
# ioctl requests of linux/uinput.h
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT, UI_SET_ABSBIT = 0x40045564, 0x40045565, 0x40045566, 0x40045567
UI_DEV_SETUP, UI_ABS_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x401C5504, 0x5501, 0x5502
EVENT = struct.Struct("llHHi")        # struct input_event: time (the kernel fills it in), type, code, value
SETTLE = 0.3                          # seconds the desktop needs to take in a new input device
WHEEL_NOTCH = 120

# Windows virtual-key codes (keys.py) -> Linux key codes (linux/input-event-codes.h)
KEY_CODES = {
    0x11: 29, 0x10: 42, 0x12: 56, 0x5B: 125,                       # ctrl, shift, alt, win (the left ones)
    0x0D: 28, 0x1B: 1, 0x09: 15, 0x20: 57, 0x08: 14,
    0x2D: 110, 0x2E: 111, 0x24: 102, 0x23: 107, 0x21: 104, 0x22: 109,
    0x25: 105, 0x26: 103, 0x27: 106, 0x28: 108, 0x2C: 99,
    0xAD: 113, 0xAE: 114, 0xAF: 115, 0xB0: 163, 0xB1: 165, 0xB2: 166, 0xB3: 164,
    0xBB: 13, 0xBD: 12, 0xBC: 51, 0xBE: 52,
}
KEY_CODES.update(zip(range(0x41, 0x5B), (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19,
                                         31, 20, 22, 47, 17, 45, 21, 44)))                  # A..Z
KEY_CODES.update(zip(range(0x30, 0x3A), (11, 2, 3, 4, 5, 6, 7, 8, 9, 10)))                  # 0..9
KEY_CODES.update(zip(range(0x70, 0x88), (59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88) + tuple(range(183, 195))))

# ... and -> X keysyms (both sides of the keyboard where there are two)
KEYSYMS = {
    0x11: (0xFFE3, 0xFFE4), 0x10: (0xFFE1, 0xFFE2), 0x12: (0xFFE9, 0xFFEA, 0xFE03), 0x5B: (0xFFEB, 0xFFEC),
    0x0D: (0xFF0D,), 0x1B: (0xFF1B,), 0x09: (0xFF09,), 0x20: (0x20,), 0x08: (0xFF08,),
    0x2D: (0xFF63,), 0x2E: (0xFFFF,), 0x24: (0xFF50,), 0x23: (0xFF57,), 0x21: (0xFF55,), 0x22: (0xFF56,),
    0x25: (0xFF51,), 0x26: (0xFF52,), 0x27: (0xFF53,), 0x28: (0xFF54,), 0x2C: (0xFF61,),
    0xAD: (0x1008FF12,), 0xAE: (0x1008FF11,), 0xAF: (0x1008FF13,), 0xB0: (0x1008FF17,), 0xB1: (0x1008FF16,),
    0xB2: (0x1008FF15,), 0xB3: (0x1008FF14,),
    0xBB: (0x3D,), 0xBD: (0x2D,), 0xBC: (0x2C,), 0xBE: (0x2E,),
}
KEYSYMS.update({vk: (vk + 0x20,) for vk in range(0x41, 0x5B)})          # a..z
KEYSYMS.update({vk: (vk,) for vk in range(0x30, 0x3A)})                 # 0..9
KEYSYMS.update({vk: (0xFFBE + vk - 0x70,) for vk in range(0x70, 0x88)})  # F1..F24


class UInput:
    """A virtual input device in the kernel. emit() delivers events together, in one write, so that
    events sent from two threads at once never mix."""

    def __init__(self, name, keys=(), rel=(), absolute=None):
        """absolute: (width, height): a pointer that is put at screen positions, like a tablet."""
        self.fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        try:
            if keys:
                fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
                for code in keys:
                    fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            if rel:
                fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_REL)
                for code in rel:
                    fcntl.ioctl(self.fd, UI_SET_RELBIT, code)
            if absolute:
                fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
                for code, size in ((ABS_X, absolute[0]), (ABS_Y, absolute[1])):
                    fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
                    # struct uinput_abs_setup: code, then value, minimum, maximum, fuzz, flat, resolution
                    fcntl.ioctl(self.fd, UI_ABS_SETUP, struct.pack("H2x6i", code, 0, 0, size - 1, 0, 0, 0))
            # struct uinput_setup: bus, vendor, product, version, name, force-feedback effects
            fcntl.ioctl(self.fd, UI_DEV_SETUP, struct.pack("4H80sI", BUS_VIRTUAL, 0x1209, 0xA1E0, 1, name.encode(), 0))
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(SETTLE)

    def emit(self, events):
        """(kind, code, value) events, followed by the report that makes them happen together."""
        os.write(self.fd, b"".join(EVENT.pack(0, 0, *event) for event in list(events) + [(EV_SYN, SYN_REPORT, 0)]))

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


_devices = {}
_devices_lock = threading.Lock()


def _device(kind):
    """The virtual "pointer" or "keyboard", made once; None if /dev/uinput cannot be used."""
    with _devices_lock:
        if kind not in _devices:
            try:
                if kind == "pointer":
                    _devices[kind] = UInput("AirMouse pointer", keys=tuple(BUTTONS.values()),
                                            rel=(REL_WHEEL, REL_WHEEL_HI_RES), absolute=screen_size())
                else:
                    _devices[kind] = UInput("AirMouse keyboard", keys=sorted(set(KEY_CODES.values())))
            except (OSError, AttributeError):    # no /dev/uinput, no permission (AttributeError: no fcntl)
                _devices[kind] = None
        return _devices[kind]


@atexit.register
def _close_devices():
    for device in _devices.values():
        if device is not None:
            try:
                device.close()
            except OSError:
                pass
    _devices.clear()


def _no_input():
    return ValueError(_(NO_INPUT))


def _keys(codes, press):
    """Keys (virtual-key codes) down (press True) or up, one after another, each in a report of its own
    (as a keyboard sends them: some programs miss keys that come in one report)."""
    keyboard = _device("keyboard")
    if keyboard is not None:
        for code in codes:
            keyboard.emit([(EV_KEY, KEY_CODES[code], 1 if press else 0)])
        return
    d = _xtest()
    if d is None:
        raise _no_input()
    from Xlib import X
    from Xlib.ext import xtest
    for code in codes:
        keycode = d.keysym_to_keycode(KEYSYMS[code][0])
        if keycode:
            xtest.fake_input(d, X.KeyPress if press else X.KeyRelease, keycode)
    d.sync()


def _wheel(amount, pending=0):
    """Turn the wheel by amount (120 a notch; less is smooth scrolling where the desktop can).
    pending: the part of a notch already turned. Returns the part left over for next time."""
    total = pending + amount
    notches = int(total / WHEEL_NOTCH)            # towards zero
    pointer = _device("pointer")
    if pointer is not None:
        pointer.emit([(EV_REL, REL_WHEEL_HI_RES, int(amount))] + ([(EV_REL, REL_WHEEL, notches)] if notches else []))
        return total - notches * WHEEL_NOTCH
    d = _xtest()
    if d is None:
        raise _no_input()
    from Xlib import X
    from Xlib.ext import xtest
    for _i in range(abs(notches)):                  # X11 knows only whole notches: buttons 4 (up) and 5 (down)
        button = 4 if notches > 0 else 5
        xtest.fake_input(d, X.ButtonPress, button)
        xtest.fake_input(d, X.ButtonRelease, button)
    d.sync()
    return total - notches * WHEEL_NOTCH


# -- shortcuts --------------------------------------------------------------------------------

def shortcut(combo):
    """A Windows key combination AirMouse uses, as this Linux desktop knows it."""
    kde = "kde" in desktop()
    table = {
        "win+tab": "win+w" if kde else "win",                       # all windows: KDE Overview, GNOME Activities
        "win+plus": "win+plus" if kde else "alt+win+plus",          # screen magnifier (GNOME: switch it on with
        "win+minus": "win+minus" if kde else "alt+win+minus",       # Alt+Super+8 first)
        "win+shift+s": "win+shift+printscreen" if kde else "printscreen",   # a screenshot of a part
    }
    return table.get(combo, combo)


def press_keys(text):
    """Press a key combination ("ctrl+c", "win+d", "playpause") in whatever window is active."""
    parse_keys(text)                         # a malformed combination is an error, whatever the desktop
    combo = text.lower().replace(" ", "")
    if combo == "win+d" and _show_desktop():
        return
    codes = parse_keys(shortcut(combo))
    _keys(codes, True)
    _keys(list(reversed(codes)), False)


def ctrl_wheel(steps):
    """Zoom in (steps > 0) or out where the cursor is: Ctrl held while the wheel turns."""
    _keys([VK_CONTROL], True)
    try:
        _wheel(steps * WHEEL_NOTCH)
    finally:
        _keys([VK_CONTROL], False)


# -- the mouse -----------------------------------------------------------------------------

_last_cursor = None       # where AirMouse last put the cursor (Wayland does not say where it is)
_screen = None            # the screen size from the window (note_screen), when the display cannot be asked


class Mouse:
    """Performs actions from the gesture engines (as winmouse.Mouse does): uinput, or XTEST under X11."""

    def __init__(self):
        self.width, self.height = screen_size()
        self._held = set()
        self._wheel = 0
        self._pointer = _device("pointer")
        _device("keyboard")     # made now, while the camera starts, so that the first keys are not lost
        if self._pointer is None and _xtest() is None:
            raise RuntimeError(_(NO_INPUT))

    def do(self, action):
        global _last_cursor
        kind = action[0]
        if kind == "move":
            x = min(max(int(action[1]), 0), self.width - 1)
            y = min(max(int(action[2]), 0), self.height - 1)
            _last_cursor = (x, y)
            if self._pointer is not None:
                self._pointer.emit([(EV_ABS, ABS_X, x), (EV_ABS, ABS_Y, y)])
            else:
                self._fake("motion", x, y)
        elif kind in ("down", "up", "click"):
            button = action[1]
            for press in {"down": (True,), "up": (False,), "click": (True, False)}[kind]:
                if self._pointer is not None:
                    self._pointer.emit([(EV_KEY, BUTTONS[button], 1 if press else 0)])
                else:
                    self._fake("button", X_BUTTONS[button], press)
            if kind == "down":
                self._held.add(button)
            elif kind == "up":
                self._held.discard(button)
        elif kind == "wheel":
            self._wheel = _wheel(action[1], self._wheel)

    def _fake(self, kind, a, b):
        from Xlib import X
        from Xlib.ext import xtest
        d = _xtest()
        if kind == "motion":
            xtest.fake_input(d, X.MotionNotify, x=a, y=b)
        else:
            xtest.fake_input(d, X.ButtonPress if b else X.ButtonRelease, a)
        d.sync()

    def release_all(self):
        for button in list(self._held):
            self.do(("up", button))


def cursor_pos():
    """Where the cursor is. X11 is asked; under Wayland, which does not tell, where AirMouse last put it."""
    if not wayland():
        d = _x()
        if d is not None:
            try:
                pointer = d.screen().root.query_pointer()
                return pointer.root_x, pointer.root_y
            except Exception:
                pass
    return _last_cursor


def screen_size():
    """Size of the whole screen (all monitors of the X screen together)."""
    d = _x()
    if d is not None:
        screen = d.screen()
        return screen.width_in_pixels, screen.height_in_pixels
    return _screen or (1920, 1080)


def screen_bounds():
    """(left, top, width, height) of the whole screen."""
    return (0, 0) + tuple(screen_size())


def note_screen(width, height):
    """The window's idea of the screen size, used when the display cannot be asked."""
    global _screen
    _screen = (int(width), int(height))


def enable_dpi_awareness():
    """Nothing to do: X11 and XWayland give real pixels."""


_keymap = (0.0, None)


def key_down(vk):
    """True while the key is held. X11 is asked; under Wayland it answers only while an X11 window
    (an AirMouse window) is active."""
    global _keymap
    d = _x()
    if d is None:
        return False
    now = time.monotonic()
    if _keymap[1] is None or now - _keymap[0] > 0.01:        # one question for the keys of one shortcut
        _keymap = (now, d.query_keymap())
    keys = _keymap[1]
    for keysym in KEYSYMS.get(vk, ()):
        code = d.keysym_to_keycode(keysym)
        if code and keys[code // 8] >> (code % 8) & 1:
            return True
    return False


# -- AirMouse's own windows --------------------------------------------------------------------

_own = {}       # key -> (x, y, w, h) on the screen


def note_window(key, rect):
    """Where one of AirMouse's own windows is now (None: hidden). own_window_at looks here."""
    if rect is None:
        _own.pop(key, None)
    else:
        _own[key] = tuple(rect)


def own_window_at(point):
    """True if one of AirMouse's own windows (main window, on-screen panels) is at this screen point."""
    if point is None:
        return False
    px, py = point
    return any(x <= px < x + w and y <= py < y + h for x, y, w, h in list(_own.values()))


def window_in_front(root):
    """True if the Tk window `root` is the active one."""
    return root.focus_displayof() is not None


# -- other programs' windows ---------------------------------------------------------------------

def _client_message(d, window, kind, data):
    from Xlib import X
    from Xlib.protocol import event
    message = event.ClientMessage(window=window, client_type=d.intern_atom(kind), data=(32, data))
    d.screen().root.send_event(message, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    d.flush()


def _ewmh():
    """The X display when the window manager can be asked about windows (X11, not Wayland), else None."""
    return None if wayland() else _x()


def _show_desktop():
    """Show the desktop (or the windows again) through the window manager. False if it cannot (Wayland)."""
    d = _ewmh()
    if d is None:
        return False
    from Xlib import X
    showing = d.screen().root.get_full_property(d.intern_atom("_NET_SHOWING_DESKTOP"), X.AnyPropertyType)
    now = bool(showing and showing.value and showing.value[0])
    _client_message(d, d.screen().root, "_NET_SHOWING_DESKTOP", [0 if now else 1, 0, 0, 0, 0])
    return True


def window_command(name):
    """The active window: "maximize" (or restore it, if it already is) or "minimize". True if done.

    X11: through the window manager; AirMouse's own windows, the desktop and panels are left alone.
    Wayland: the desktop's own keys (KDE: Meta+PgUp / PgDown; GNOME and others: Super+Up / Super+H).
    """
    d = _ewmh()
    if d is None:
        kde = "kde" in desktop()
        keys = {"maximize": "win+pageup" if kde else "win+up", "minimize": "win+pagedown" if kde else "win+h"}
        press_keys(keys[name])
        return True
    from Xlib import X
    atom = d.intern_atom
    active = d.screen().root.get_full_property(atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
    if not active or not active.value or not active.value[0]:
        return False
    window = d.create_resource_object("window", active.value[0])
    pid = window.get_full_property(atom("_NET_WM_PID"), X.AnyPropertyType)
    if pid and pid.value and pid.value[0] == os.getpid():
        return False
    kinds = window.get_full_property(atom("_NET_WM_WINDOW_TYPE"), X.AnyPropertyType)
    if kinds and {atom("_NET_WM_WINDOW_TYPE_DESKTOP"), atom("_NET_WM_WINDOW_TYPE_DOCK")} & set(kinds.value):
        return False
    if name == "minimize":
        _client_message(d, window, "WM_CHANGE_STATE", [3, 0, 0, 0, 0])            # 3: IconicState
    else:                                                                         # 2: toggle
        _client_message(d, window, "_NET_WM_STATE",
                        [2, atom("_NET_WM_STATE_MAXIMIZED_VERT"), atom("_NET_WM_STATE_MAXIMIZED_HORZ"), 1, 0])
    return True


# -- opening things ---------------------------------------------------------------------------

# Names the default buttons use (Windows programs) -> programs that do the same on Linux
PROGRAMS = {
    "osk": ("onboard", "florence", "squeekboard"),
    "notepad": ("gnome-text-editor", "gedit", "kate", "mousepad", "xed", "pluma"),
    "calc": ("gnome-calculator", "kcalc", "galculator", "mate-calc"),
}


def _start(command):
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def open_target(target):
    """Open a program, file, folder or web address (xdg-open). Returns an error text, or None."""
    target = os.path.expanduser(os.path.expandvars(target.strip().strip('"')))
    if not target:
        return _("Не указано, что открыть")
    failed = _("Не удалось открыть «{}»").format(target)
    if target.lower() in PROGRAMS:
        program = next((p for p in PROGRAMS[target.lower()] if shutil.which(p)), None)
        command = [program] if program else None
    else:
        try:
            parts = shlex.split(target)
        except ValueError:
            parts = [target]
        command = parts if parts and shutil.which(parts[0]) else ["xdg-open", target]
    if command is None:
        return failed
    try:
        _start(command)
    except OSError:
        return failed
    return None


# -- sound ------------------------------------------------------------------------------------

def _run(*args):
    """A command's output (in English, to be read), or None if it failed."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=1.5, check=True,
                              env=dict(os.environ, LC_ALL="C"))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


class Volume:
    """Volume of the default output: PipeWire (wpctl) or PulseAudio (pactl). Without either, level() is None."""

    FRESH = 0.2     # seconds a reading is used again (the widget asks for level and mute one after the other)

    def __init__(self):
        self._read_at, self._state = -1.0, (None, False)

    def _read(self):
        now = time.monotonic()
        if now - self._read_at >= self.FRESH:
            self._read_at, self._state = now, read_volume()
        return self._state

    def level(self):
        """0..1, or None without a sound server."""
        return self._read()[0]

    def muted(self):
        return self._read()[1]

    def set_level(self, value):
        value = min(max(float(value), 0.0), 1.0)
        self._read_at = -1.0
        if shutil.which("wpctl"):
            return _run("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value:.2f}") is not None
        if shutil.which("pactl"):
            return _run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{round(value * 100)}%") is not None
        return False

    def set_muted(self, on):
        self._read_at = -1.0
        if shutil.which("wpctl"):
            return _run("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if on else "0") is not None
        if shutil.which("pactl"):
            return _run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if on else "0") is not None
        return False


def read_volume():
    """(level 0..1 or None, muted) of the default output."""
    if shutil.which("wpctl"):
        out = _run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@") or ""       # "Volume: 0.40 [MUTED]"
        found = re.search(r"Volume:\s*([\d.]+)", out)
        if found:
            return min(max(float(found.group(1)), 0.0), 1.0), "MUTED" in out
    if shutil.which("pactl"):
        out = _run("pactl", "get-sink-volume", "@DEFAULT_SINK@") or ""       # "... 26214 /  40% / ..."
        found = re.search(r"(\d+)%", out)
        if found:
            mute = _run("pactl", "get-sink-mute", "@DEFAULT_SINK@") or ""      # "Mute: yes"
            return min(int(found.group(1)) / 100, 1.0), "yes" in mute
    return None, False


# -- load ---------------------------------------------------------------------------------------

PROC = Path("/proc")
POWER = Path("/sys/class/power_supply")


class SystemLoad:
    """Processor, memory and battery of the whole computer (from /proc and /sys)."""

    def __init__(self):
        self._last = None

    def cpu(self):
        """Processor load in % since the previous call (0 the first time)."""
        try:
            fields = [int(v) for v in (PROC / "stat").read_text().split("\n", 1)[0].split()[1:9]]
        except (OSError, ValueError):
            return 0.0
        now = (fields[3] + fields[4], sum(fields))          # idle + iowait; all of user .. steal
        last, self._last = self._last, now
        if last is None or now[1] <= last[1]:
            return 0.0
        busy = (now[1] - last[1]) - (now[0] - last[0])
        return min(max(100.0 * busy / (now[1] - last[1]), 0.0), 100.0)

    @staticmethod
    def memory():
        """Memory in use, %."""
        try:
            info = {k: int(v.split()[0]) for k, v in (line.split(":", 1) for line in
                                                     (PROC / "meminfo").read_text().splitlines() if ":" in line)}
            return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])
        except (OSError, KeyError, ValueError, ZeroDivisionError):
            return 0.0

    @staticmethod
    def battery():
        """(charge %, charging) or None on a computer without a battery."""
        def read(path):
            try:
                return path.read_text().strip()
            except OSError:
                return ""
        supplies = sorted(POWER.glob("*")) if POWER.exists() else []
        plugged = any(read(s / "type") == "Mains" and read(s / "online") == "1" for s in supplies)
        for supply in supplies:
            if read(supply / "type") == "Battery" and read(supply / "capacity").isdigit():
                return float(read(supply / "capacity")), plugged or read(supply / "status") == "Charging"
        return None


class ProcessLoad:
    """Processor time AirMouse itself uses, as % of the whole computer."""

    def __init__(self):
        self._last = None
        self._cores = os.cpu_count() or 1

    def cpu(self):
        times = os.times()
        now = (time.perf_counter(), times.user + times.system)
        last, self._last = self._last, now
        if last is None or now[0] <= last[0]:
            return 0.0
        return min(100.0 * (now[1] - last[1]) / (now[0] - last[0]) / self._cores, 100.0)


def process_memory_mb():
    """RAM this process uses now (resident), MB."""
    try:
        pages = int((PROC / "self" / "statm").read_text().split()[1])
    except (OSError, ValueError, IndexError):
        return 0.0
    return pages * os.sysconf("SC_PAGE_SIZE") / 2 ** 20


def process_uptime():
    """Seconds since this process started."""
    try:
        started = int((PROC / "self" / "stat").read_text().rsplit(")", 1)[1].split()[19])   # field 22: starttime
        since_boot = float((PROC / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0
    return since_boot - started / os.sysconf("SC_CLK_TCK")


# -- the clipboard, the theme, one copy of the program -----------------------------------------------

def copy_picture(image):
    """Put an RGB picture on the clipboard as PNG: wl-copy under Wayland, xclip under X11.
    False if neither is installed."""
    if wayland() and shutil.which("wl-copy"):
        command = ["wl-copy", "--type", "image/png"]
    elif shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard", "-target", "image/png", "-in"]
    else:
        return False
    ok, png = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if not ok:
        return False
    try:   # both stay in the background to hand the picture out, until something else is copied
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        process.stdin.write(png.tobytes())
        process.stdin.close()
    except OSError:
        return False
    return True


def dark_theme():
    """True if the desktop prefers dark apps (GNOME's setting, which others follow, or GTK_THEME)."""
    if "dark" in os.environ.get("GTK_THEME", "").lower():
        return True
    if not shutil.which("gsettings"):
        return False
    if "dark" in (_run("gsettings", "get", "org.gnome.desktop.interface", "color-scheme") or ""):
        return True
    return "dark" in (_run("gsettings", "get", "org.gnome.desktop.interface", "gtk-theme") or "").lower()


_instance_lock = None


def single_instance():
    """True unless AirMouse is already running: a lock on a file, held as long as this process lives."""
    global _instance_lock
    folder = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    _instance_lock = open(os.path.join(folder, f"airmouse-{os.getuid()}.lock"), "w")
    try:
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def show_message(text):
    """A message box before any window exists (on the console if there is no display)."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("AirMouse", text, parent=root)
        root.destroy()
    except Exception:
        print(text, file=sys.stderr)
