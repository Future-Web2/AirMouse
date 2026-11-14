"""Windows under AirMouse: keys and the wheel through SendInput, windows, sound (Core Audio), load,
the clipboard, the theme, one copy of the program. The mouse itself is winmouse.py.

system.py picks this module on Windows (linuxsystem.py on Linux) and adds what is the same on both.
"""

import ctypes
import os
import threading
import time
import uuid
from ctypes import wintypes

import cv2

from .i18n import _
from .keys import NAMED_KEYS, parse_keys
from .winmouse import VK_CONTROL, VK_MENU, Mouse, cursor_pos, enable_dpi_awareness, key_down, screen_size  # noqa: F401

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ole32 = ctypes.WinDLL("ole32")

# -- keys ------------------------------------------------------------------------------

# Sent with the "extended" flag, as a real keyboard does: the navigation block, Win, media keys.
EXTENDED = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x5B,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_user32.MapVirtualKeyW.restype = wintypes.UINT


def key_events(codes):
    """(code, flags) to press the keys together: all down in order, then up in reverse order."""
    down = [(code, KEYEVENTF_EXTENDEDKEY if code in EXTENDED else 0) for code in codes]
    return down + [(code, flags | KEYEVENTF_KEYUP) for code, flags in reversed(down)]


def _key_input(item, code, flags):
    item.type = INPUT_KEYBOARD
    item.u.ki = KEYBDINPUT(wVk=code, wScan=_user32.MapVirtualKeyW(code, 0), dwFlags=flags)


def press_keys(text):
    """Press a key combination ("ctrl+c", "win+d", "playpause") in whatever window is active."""
    events = key_events(parse_keys(text))
    inputs = (INPUT * len(events))()
    for item, (code, flags) in zip(inputs, events):
        _key_input(item, code, flags)
    _user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))


INPUT_MOUSE = 0
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_NOTCH = 120


def ctrl_wheel(steps):
    """Zoom in (steps > 0) or out where the cursor is: Ctrl held while the wheel turns, as browsers,
    documents and pictures understand it."""
    ctrl = NAMED_KEYS["ctrl"]
    inputs = (INPUT * 3)()
    _key_input(inputs[0], ctrl, 0)
    inputs[1].type = INPUT_MOUSE
    inputs[1].u.mi = MOUSEINPUT(0, 0, (steps * WHEEL_NOTCH) & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0)
    _key_input(inputs[2], ctrl, KEYEVENTF_KEYUP)
    _user32.SendInput(3, inputs, ctypes.sizeof(INPUT))


# -- windows ------------------------------------------------------------------------------

SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}   # desktop and taskbar
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.IsZoomed.argtypes = (wintypes.HWND,)
_user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.WindowFromPoint.argtypes = (wintypes.POINT,)
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_user32.GetAncestor.restype = wintypes.HWND
GA_ROOT = 2


def own_window_at(point):
    """True if AirMouse's own window (the main window or an on-screen panel) is at this screen point.
    Click-through windows (the cursor ring) are not found there."""
    if point is None:
        return False
    hwnd = _user32.WindowFromPoint(wintypes.POINT(int(point[0]), int(point[1])))
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(_user32.GetAncestor(hwnd, GA_ROOT) or hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


def window_command(name):
    """The active window: "maximize" (or restore it, if it already is) or "minimize".

    AirMouse's own windows, the desktop and the taskbar are left alone. True if done.
    """
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name_buffer = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, name_buffer, 64)
    if pid.value == os.getpid() or name_buffer.value in SHELL_CLASSES:
        return False
    if name == "minimize":
        _user32.ShowWindow(hwnd, SW_MINIMIZE)
    else:
        _user32.ShowWindow(hwnd, SW_RESTORE if _user32.IsZoomed(hwnd) else SW_MAXIMIZE)
    return True


def open_target(target):
    """Open a program, file, folder or web address as Explorer would. Returns an error text, or None."""
    target = os.path.expandvars(target.strip().strip('"'))
    if not target:
        return _("Не указано, что открыть")
    try:
        os.startfile(target)
    except OSError:
        return _("Не удалось открыть «{}»").format(target)
    return None


# -- volume (Windows Core Audio through COM) ----------------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    u = uuid.UUID(text)
    return _GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))


_CLSID_DEVICE_ENUMERATOR = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
_IID_DEVICE_ENUMERATOR = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
_IID_ENDPOINT_VOLUME = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")
_CLSCTX_ALL = 23
_RENDER, _MULTIMEDIA = 0, 1

_ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoCreateInstance.argtypes = (ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_GUID),
                                    ctypes.POINTER(ctypes.c_void_p))
_ole32.CoCreateInstance.restype = ctypes.HRESULT
_com = threading.local()


def _method(obj, index, *argtypes, restype=ctypes.HRESULT):
    """Method number `index` of a COM object's table (0-2 are IUnknown's)."""
    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])


def _release(obj):
    if obj:
        _method(obj, 2, restype=wintypes.ULONG)(obj)


class Volume:
    """Master volume of the default playback device. Every call asks for the device again,
    so switching speakers to headphones is followed. Without a device: level() is None."""

    def _endpoint(self):
        if not getattr(_com, "ready", False):
            _ole32.CoInitializeEx(None, 2)   # apartment threaded; fine if this thread already has COM
            _com.ready = True
        enumerator, device, volume = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _ole32.CoCreateInstance(ctypes.byref(_CLSID_DEVICE_ENUMERATOR), None, _CLSCTX_ALL,
                                    ctypes.byref(_IID_DEVICE_ENUMERATOR), ctypes.byref(enumerator))
            _method(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
                enumerator, _RENDER, _MULTIMEDIA, ctypes.byref(device))      # GetDefaultAudioEndpoint
            _method(device, 3, ctypes.POINTER(_GUID), wintypes.DWORD, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p))(
                device, ctypes.byref(_IID_ENDPOINT_VOLUME), _CLSCTX_ALL, None, ctypes.byref(volume))   # Activate
        finally:
            _release(device)
            _release(enumerator)
        return volume

    def _use(self, fn, default=None):
        try:
            volume = self._endpoint()
        except OSError:
            return default
        try:
            return fn(volume)
        except OSError:
            return default
        finally:
            _release(volume)

    def level(self):
        """0..1, or None without a playback device."""
        def get(volume):
            value = ctypes.c_float()
            _method(volume, 9, ctypes.POINTER(ctypes.c_float))(volume, ctypes.byref(value))   # GetMasterVolumeLevelScalar
            return min(max(value.value, 0.0), 1.0)
        return self._use(get)

    def set_level(self, value):
        value = min(max(float(value), 0.0), 1.0)
        return self._use(lambda v: _method(v, 7, ctypes.c_float, ctypes.c_void_p)(v, value, None) or True, False)

    def muted(self):
        def get(volume):
            value = wintypes.BOOL()
            _method(volume, 15, ctypes.POINTER(wintypes.BOOL))(volume, ctypes.byref(value))     # GetMute
            return bool(value.value)
        return self._use(get, False)

    def set_muted(self, on):
        return self._use(lambda v: _method(v, 14, wintypes.BOOL, ctypes.c_void_p)(v, bool(on), None) or True, False)


# -- load ---------------------------------------------------------------------------------

class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
                                                "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual",
                                                "ullAvailExtendedVirtual")]


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD)]


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


_kernel32.GetSystemTimes.argtypes = (ctypes.POINTER(wintypes.FILETIME),) * 3
_kernel32.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(_MemoryStatus),)
_kernel32.GetSystemPowerStatus.argtypes = (ctypes.POINTER(_PowerStatus),)
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
_kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MemoryCounters), wintypes.DWORD)


def _ticks(filetime):
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def process_memory_mb():
    """RAM this process uses now (working set), MB."""
    counters = _MemoryCounters(cb=ctypes.sizeof(_MemoryCounters))
    _kernel32.K32GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2 ** 20


class SystemLoad:
    """Processor, memory and battery of the whole computer."""

    def __init__(self):
        self._last = None

    def cpu(self):
        """Processor load in % since the previous call (0 the first time)."""
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        _kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        now = (_ticks(idle), _ticks(kernel) + _ticks(user))   # kernel time includes the idle time
        last, self._last = self._last, now
        if last is None or now[1] <= last[1]:
            return 0.0
        busy = (now[1] - last[1]) - (now[0] - last[0])
        return min(max(100.0 * busy / (now[1] - last[1]), 0.0), 100.0)

    @staticmethod
    def memory():
        """Memory in use, %."""
        status = _MemoryStatus(dwLength=ctypes.sizeof(_MemoryStatus))
        _kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return float(status.dwMemoryLoad)

    @staticmethod
    def battery():
        """(charge %, charging) or None on a computer without a battery."""
        status = _PowerStatus()
        if not _kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        if status.BatteryFlag & 128 or status.BatteryLifePercent > 100:   # 128: no battery
            return None
        return float(status.BatteryLifePercent), status.ACLineStatus == 1


class ProcessLoad:
    """Processor time AirMouse itself uses, as % of the whole computer (like Task Manager)."""

    def __init__(self):
        self._last = None
        self._cores = os.cpu_count() or 1

    def cpu(self):
        created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
        _kernel32.GetProcessTimes(_kernel32.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(ended),
                                  ctypes.byref(kernel), ctypes.byref(user))
        now = (time.perf_counter(), (_ticks(kernel) + _ticks(user)) / 1e7)
        last, self._last = self._last, now
        if last is None or now[0] <= last[0]:
            return 0.0
        return min(100.0 * (now[1] - last[1]) / (now[0] - last[0]) / self._cores, 100.0)


_kernel32.GetSystemTimePreciseAsFileTime.argtypes = (ctypes.POINTER(wintypes.FILETIME),)


def process_uptime():
    """Seconds since this process started (includes the .exe loader and Python's own start-up)."""
    created, ended, kernel, user, now = (wintypes.FILETIME() for _ in range(5))
    _kernel32.GetProcessTimes(_kernel32.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(ended),
                              ctypes.byref(kernel), ctypes.byref(user))
    _kernel32.GetSystemTimePreciseAsFileTime(ctypes.byref(now))
    return (_ticks(now) - _ticks(created)) / 1e7


# -- the clipboard ------------------------------------------------------------------------

CF_DIB, GMEM_MOVEABLE = 8, 0x0002


def copy_picture(image):
    """Put an RGB picture on the clipboard. False if Windows would not let us."""
    from .notebook import dib
    data = dib(image)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = (wintypes.UINT, ctypes.c_size_t), wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = (wintypes.HGLOBAL,), ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    user32 = ctypes.WinDLL("user32")
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


# -- the screen, the windows of AirMouse, the desktop ---------------------------------------------

CAMERA_API = cv2.CAP_DSHOW          # DirectShow opens much faster than the default on Windows
SM_XVIRTUALSCREEN = 76              # ... 77-79: top, width, height of all monitors together
ERROR_ALREADY_EXISTS = 183
_instance_mutex = None
_user32.GetParent.argtypes = (wintypes.HWND,)
_user32.GetParent.restype = wintypes.HWND


def screen_bounds():
    """(left, top, width, height) of all monitors together."""
    return tuple(_user32.GetSystemMetrics(SM_XVIRTUALSCREEN + i) for i in range(4))


def note_screen(width, height):
    """The window's idea of the screen size (Linux uses it when it cannot ask the display)."""


def note_window(key, rect):
    """Where one of AirMouse's own windows is (Linux needs it for own_window_at; Windows asks the system)."""


def window_in_front(root):
    """True if the Tk window `root` is the active one."""
    return _user32.GetForegroundWindow() == _user32.GetParent(root.winfo_id())


def dark_theme():
    """True if Windows apps are set to the dark theme."""
    try:
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def single_instance():
    """True unless AirMouse is already running; the mutex lives as long as this process."""
    global _instance_mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _instance_mutex = kernel32.CreateMutexW(None, False, r"Local\AirMouse.SingleInstance")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def show_message(text):
    """A message box before any window exists."""
    _user32.MessageBoxW(None, text, "AirMouse", 0x40)
