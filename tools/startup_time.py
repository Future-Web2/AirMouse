"""Time from starting AirMouse.exe until its window is on screen (docs/KPI.md).

    python tools\\startup_time.py dist\\AirMouse\\AirMouse.exe [runs]

The app is started minimized so it does not take the focus, then closed again
as soon as its window exists. The first run after a build or a reboot is the
"cold" one (files not cached yet); the median of the others is the "warm" start.
"""

import ctypes
import statistics
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

SW_SHOWMINNOACTIVE = 7
WM_CLOSE = 0x0010


def app_window(pid):
    """The visible top-level window titled "AirMouse" of process pid, or None."""
    found = []

    def check(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, title, 64)
            if title.value == "AirMouse":
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(check), 0)
    return found[0] if found else None


def start_once(exe, timeout=60.0):
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = SW_SHOWMINNOACTIVE
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe], startupinfo=info)
    try:
        while True:
            hwnd = app_window(proc.pid)
            if hwnd:
                elapsed = time.perf_counter() - t0
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                proc.wait(timeout=20)
                return elapsed
            if proc.poll() is not None:
                raise RuntimeError(f"AirMouse exited with code {proc.returncode} before showing a window")
            if time.perf_counter() - t0 > timeout:
                raise TimeoutError("no window after %.0f s" % timeout)
            time.sleep(0.005)
    finally:
        if proc.poll() is None:
            proc.kill()


def main():
    exe = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    times = [start_once(exe) for _ in range(runs)]
    print("runs: " + ", ".join(f"{t:.2f}" for t in times) + " s")
    print(f"first: {times[0]:.2f} s   warm median: {statistics.median(times[1:]):.2f} s")


if __name__ == "__main__":
    main()
