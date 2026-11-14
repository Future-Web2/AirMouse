"""AirMouse on Linux (linuxsystem.py, linuxwindows.py), with stand-ins for the kernel, X11 and commands.

These run on any system: nothing here opens /dev/uinput, talks to an X server or runs a program.
"""

import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from airmouse import glass, i18n, keys, linuxsystem as lx
from airmouse.linuxwindows import mask_rectangles, unpremultiply


class FakeDevice:
    """A virtual input device that keeps what was emitted (all devices share one log)."""

    def __init__(self, name, log):
        self.name, self.log = name, log

    def emit(self, events):
        self.log.append((self.name, list(events)))


def devices(log, pointer=True, keyboard=True):
    made = {"pointer": FakeDevice("pointer", log) if pointer else None,
            "keyboard": FakeDevice("keyboard", log) if keyboard else None}
    return mock.patch.object(lx, "_device", lambda kind: made[kind])


def environment(**values):
    """os.environ with only these desktop variables set."""
    clean = {k: v for k, v in os.environ.items()
             if k not in ("WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "DISPLAY", "GTK_THEME")}
    return mock.patch.dict(os.environ, dict(clean, **values), clear=True)


class UInputTest(unittest.TestCase):
    def test_device_is_set_up_and_events_are_written_together(self):
        calls, written = [], []
        fcntl = SimpleNamespace(ioctl=lambda fd, request, arg=0: calls.append((request, arg)))
        with mock.patch.object(lx, "fcntl", fcntl), mock.patch.object(lx.os, "open", lambda path, flags: 7), \
                mock.patch.object(lx.os, "O_NONBLOCK", 0o4000, create=True), \
                mock.patch.object(lx.os, "write", lambda fd, data: written.append(data)), \
                mock.patch.object(lx.time, "sleep", lambda s: None):
            device = lx.UInput("AirMouse pointer", keys=(lx.BUTTONS["left"],), rel=(lx.REL_WHEEL,), absolute=(1920, 1080))
            device.emit([(lx.EV_ABS, lx.ABS_X, 100), (lx.EV_ABS, lx.ABS_Y, 200)])
        requests = [r for r, _a in calls]
        self.assertEqual(requests[-2:], [lx.UI_DEV_SETUP, lx.UI_DEV_CREATE])
        self.assertIn((lx.UI_SET_EVBIT, lx.EV_ABS), calls)
        self.assertIn((lx.UI_SET_KEYBIT, lx.BUTTONS["left"]), calls)
        axis = [a for r, a in calls if r == lx.UI_ABS_SETUP]
        self.assertEqual(struct.unpack("H2x6i", axis[0])[:4], (lx.ABS_X, 0, 0, 1919))
        self.assertEqual(struct.unpack("4H80sI", calls[-2][1])[4].rstrip(b"\0"), b"AirMouse pointer")
        events = [lx.EVENT.unpack_from(written[0], i * lx.EVENT.size)[2:] for i in range(3)]
        self.assertEqual(events, [(lx.EV_ABS, lx.ABS_X, 100), (lx.EV_ABS, lx.ABS_Y, 200), (lx.EV_SYN, 0, 0)])

    def test_every_key_airmouse_knows_has_a_linux_code(self):
        codes = set(keys.NAMED_KEYS.values()) | set(range(0x41, 0x5B)) | set(range(0x30, 0x3A)) | set(range(0x70, 0x88))
        self.assertLessEqual(codes, set(lx.KEY_CODES))
        self.assertLessEqual(codes, set(lx.KEYSYMS))
        self.assertEqual(len(set(lx.KEY_CODES.values())), len(lx.KEY_CODES))      # no two keys share a code
        self.assertEqual(lx.KEY_CODES[ord("C")], 46)
        self.assertEqual(lx.KEY_CODES[0x7B], 88)                                  # F12


class MouseTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(lx, "screen_size", lambda: (1920, 1080))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_move_click_drag_and_wheel(self):
        log = []
        with devices(log):
            mouse = lx.Mouse()
            mouse.do(("move", 2500, -5))                 # off the screen: put at its edge
            mouse.do(("click", "right"))
            mouse.do(("down", "left"))
            mouse.do(("wheel", 30))
            mouse.do(("wheel", 30))
            mouse.do(("wheel", 60))                      # a whole notch by now
            mouse.release_all()
        self.assertEqual(log[0], ("pointer", [(lx.EV_ABS, lx.ABS_X, 1919), (lx.EV_ABS, lx.ABS_Y, 0)]))
        self.assertEqual(lx.cursor_pos.__module__, "airmouse.linuxsystem")
        buttons = [e for _n, events in log for e in events if e[0] == lx.EV_KEY]
        right, left = lx.BUTTONS["right"], lx.BUTTONS["left"]
        self.assertEqual(buttons, [(1, right, 1), (1, right, 0), (1, left, 1), (1, left, 0)])
        wheel = [e for _n, events in log for e in events if e[0] == lx.EV_REL]
        self.assertEqual(wheel, [(2, lx.REL_WHEEL_HI_RES, 30), (2, lx.REL_WHEEL_HI_RES, 30),
                                 (2, lx.REL_WHEEL_HI_RES, 60), (2, lx.REL_WHEEL, 1)])

    def test_without_uinput_or_x11_it_says_how_to_fix_it(self):
        with devices([], pointer=False, keyboard=False), mock.patch.object(lx, "_xtest", lambda: None):
            with self.assertRaises(RuntimeError) as caught:
                lx.Mouse()
            self.assertIn("/dev/uinput", str(caught.exception))
            with self.assertRaises(ValueError):
                lx.press_keys("ctrl+c")

    def test_wayland_cursor_is_where_airmouse_put_it(self):
        with devices([]), environment(WAYLAND_DISPLAY="wayland-0"):
            lx.Mouse().do(("move", 300, 400))
            self.assertEqual(lx.cursor_pos(), (300, 400))


class KeysTest(unittest.TestCase):
    def pressed(self, text, **env):
        log = []
        with devices(log), environment(**env), mock.patch.object(lx, "_show_desktop", lambda: False):
            lx.press_keys(text)
        return [e for _n, events in log for e in events if e[0] == lx.EV_KEY]

    def test_down_in_order_up_in_reverse(self):
        ctrl, shift, s = lx.KEY_CODES[0x11], lx.KEY_CODES[0x10], lx.KEY_CODES[ord("S")]
        self.assertEqual(self.pressed("ctrl+shift+s"), [(1, ctrl, 1), (1, shift, 1), (1, s, 1),
                                                       (1, s, 0), (1, shift, 0), (1, ctrl, 0)])

    def test_windows_shortcuts_as_the_desktop_knows_them(self):
        meta, w = lx.KEY_CODES[0x5B], lx.KEY_CODES[ord("W")]
        self.assertEqual(self.pressed("win+tab", XDG_CURRENT_DESKTOP="KDE"), [(1, meta, 1), (1, w, 1), (1, w, 0), (1, meta, 0)])
        self.assertEqual(self.pressed("win+tab", XDG_CURRENT_DESKTOP="ubuntu:GNOME"), [(1, meta, 1), (1, meta, 0)])
        alt = lx.KEY_CODES[0x12]
        self.assertEqual(self.pressed("win+plus", XDG_CURRENT_DESKTOP="GNOME")[:2], [(1, alt, 1), (1, meta, 1)])
        self.assertEqual(lx.shortcut("ctrl+c"), "ctrl+c")

    def test_show_desktop_goes_to_the_window_manager_under_x11(self):
        log = []
        with devices(log), mock.patch.object(lx, "_show_desktop", lambda: True):
            lx.press_keys("win+d")
        self.assertEqual(log, [])

    def test_bad_keys_are_an_error_before_anything_is_pressed(self):
        log = []
        with devices(log), self.assertRaises(ValueError):
            lx.press_keys("ctrl+what")
        self.assertEqual(log, [])

    def test_zoom_holds_ctrl_around_the_wheel(self):
        log = []
        with devices(log):
            lx.ctrl_wheel(-2)
        ctrl = lx.KEY_CODES[0x11]
        self.assertEqual([name for name, _e in log], ["keyboard", "pointer", "keyboard"])
        self.assertEqual(log[0][1], [(lx.EV_KEY, ctrl, 1)])
        self.assertIn((lx.EV_REL, lx.REL_WHEEL, -2), log[1][1])
        self.assertEqual(log[2][1], [(lx.EV_KEY, ctrl, 0)])

    def test_window_commands_under_wayland_are_the_desktops_keys(self):
        pressed = []
        with environment(WAYLAND_DISPLAY="wayland-0", XDG_CURRENT_DESKTOP="KDE"), \
                mock.patch.object(lx, "press_keys", pressed.append):
            lx.window_command("maximize")
        with environment(WAYLAND_DISPLAY="wayland-0", XDG_CURRENT_DESKTOP="GNOME"), \
                mock.patch.object(lx, "press_keys", pressed.append):
            lx.window_command("minimize")
        self.assertEqual(pressed, ["win+pageup", "win+h"])


class ScreenTest(unittest.TestCase):
    def test_own_windows(self):
        lx.note_window("main", (100, 100, 400, 300))
        lx.note_window("panel", (900, 50, 200, 100))
        try:
            self.assertTrue(lx.own_window_at((150, 120)))
            self.assertTrue(lx.own_window_at((1099, 149)))
            self.assertFalse(lx.own_window_at((1100, 149)))
            self.assertFalse(lx.own_window_at(None))
            lx.note_window("panel", None)
            self.assertFalse(lx.own_window_at((950, 60)))
        finally:
            lx.note_window("main", None)

    def test_screen_size_from_the_window_without_x11(self):
        with mock.patch.object(lx, "_x", lambda: None), mock.patch.object(lx, "_screen", None):
            self.assertEqual(lx.screen_size(), (1920, 1080))
            lx.note_screen(2560, 1440)
            self.assertEqual(lx.screen_bounds(), (0, 0, 2560, 1440))
            self.assertFalse(lx.key_down(lx.VK_CONTROL))


class SoundTest(unittest.TestCase):
    def read(self, outputs, programs):
        with mock.patch.object(lx.shutil, "which", lambda p: p if p in programs else None), \
                mock.patch.object(lx, "_run", lambda *args: outputs.get(args[:2])):
            return lx.read_volume()

    def test_pipewire_and_pulseaudio(self):
        wpctl = {("wpctl", "get-volume"): "Volume: 0.40 [MUTED]\n"}
        self.assertEqual(self.read(wpctl, {"wpctl"}), (0.40, True))
        pactl = {("pactl", "get-sink-volume"): "Volume: front-left: 41943 /  64% / -11.63 dB,   front-right: ...\n",
                 ("pactl", "get-sink-mute"): "Mute: no\n"}
        self.assertEqual(self.read(pactl, {"pactl"}), (0.64, False))
        self.assertEqual(self.read({}, set()), (None, False))

    def test_setting_it(self):
        ran = []
        with mock.patch.object(lx.shutil, "which", lambda p: p if p == "wpctl" else None), \
                mock.patch.object(lx, "_run", lambda *args: ran.append(args) or ""):
            volume = lx.Volume()
            self.assertTrue(volume.set_level(0.5))
            self.assertTrue(volume.set_muted(True))
        self.assertEqual(ran, [("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.50"),
                               ("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1")])


class LoadTest(unittest.TestCase):
    def test_proc_and_sys(self):
        with tempfile.TemporaryDirectory() as folder:
            proc, power = Path(folder, "proc"), Path(folder, "power")
            (proc / "self").mkdir(parents=True)
            (proc / "meminfo").write_text("MemTotal:  8000000 kB\nMemFree: 1000000 kB\nMemAvailable:  2000000 kB\n")
            (proc / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 1 2 3\n")
            (proc / "self" / "statm").write_text("5000 2560 100 1 0 300 0\n")
            (proc / "self" / "stat").write_text("42 (python3 (x)) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 300 20\n")
            (proc / "uptime").write_text("13.00 50.00\n")
            for name, files in (("AC", {"type": "Mains", "online": "1"}),
                                ("BAT0", {"type": "Battery", "capacity": "81", "status": "Discharging"})):
                (power / name).mkdir(parents=True)
                for key, value in files.items():
                    (power / name / key).write_text(value + "\n")
            with mock.patch.object(lx, "PROC", proc), mock.patch.object(lx, "POWER", power), \
                    mock.patch.object(lx.os, "sysconf", lambda key: {"SC_PAGE_SIZE": 4096, "SC_CLK_TCK": 100}[key],
                                      create=True):
                load = lx.SystemLoad()
                self.assertEqual(load.cpu(), 0.0)                       # the first call starts measuring
                (proc / "stat").write_text("cpu  150 0 150 900 0 0 0 0 0 0\n")
                self.assertAlmostEqual(load.cpu(), 50.0)                # 100 of 200 ticks busy
                self.assertAlmostEqual(load.memory(), 75.0)
                self.assertEqual(load.battery(), (81.0, True))          # on the charger
                self.assertAlmostEqual(lx.process_memory_mb(), 10.0)
                self.assertAlmostEqual(lx.process_uptime(), 10.0)       # 13 s since boot, started at 3 s


class ProgramsTest(unittest.TestCase):
    def test_open_target(self):
        started = []
        installed = {"onboard", "firefox", "xdg-open"}
        with mock.patch.object(lx.shutil, "which", lambda p: p if p in installed else None), \
                mock.patch.object(lx, "_start", started.append):
            self.assertIsNone(lx.open_target("osk"))                       # the Windows on-screen keyboard
            self.assertIsNone(lx.open_target("firefox https://example.com"))
            self.assertIsNone(lx.open_target("https://example.com"))
            self.assertIsNotNone(lx.open_target("calc"))                   # no calculator installed
            self.assertIsNotNone(lx.open_target("  "))
        self.assertEqual(started, [["onboard"], ["firefox", "https://example.com"], ["xdg-open", "https://example.com"]])

    def test_copy_picture(self):
        given = []

        class Process:
            def __init__(self, command, **kwargs):
                given.append(command)
                self.stdin = SimpleNamespace(write=lambda data: given.append(data[:8]), close=lambda: None)
        picture = np.zeros((4, 6, 3), np.uint8)
        with mock.patch.object(lx.subprocess, "Popen", Process):
            with environment(WAYLAND_DISPLAY="wayland-0"), mock.patch.object(lx.shutil, "which", lambda p: p):
                self.assertTrue(lx.copy_picture(picture))
            with environment(DISPLAY=":0"), mock.patch.object(lx.shutil, "which", lambda p: p if p == "xclip" else None):
                self.assertTrue(lx.copy_picture(picture))
            with environment(), mock.patch.object(lx.shutil, "which", lambda p: None):
                self.assertFalse(lx.copy_picture(picture))
        self.assertEqual(given[0][0], "wl-copy")
        self.assertEqual(given[1], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(given[2][:3], ["xclip", "-selection", "clipboard"])

    def test_dark_theme(self):
        with environment(GTK_THEME="Adwaita:dark"):
            self.assertTrue(lx.dark_theme())
        with environment(), mock.patch.object(lx.shutil, "which", lambda p: p), \
                mock.patch.object(lx, "_run", lambda *args: "'prefer-dark'\n" if "color-scheme" in args else ""):
            self.assertTrue(lx.dark_theme())
        with environment(), mock.patch.object(lx.shutil, "which", lambda p: None):
            self.assertFalse(lx.dark_theme())

    def test_one_copy_of_the_program(self):
        locked = []

        def flock(handle, flags):
            if locked:
                raise BlockingIOError
            locked.append(handle)
        fcntl = SimpleNamespace(flock=flock, LOCK_EX=2, LOCK_NB=4)
        with tempfile.TemporaryDirectory() as folder, environment(XDG_RUNTIME_DIR=folder), \
                mock.patch.object(lx, "fcntl", fcntl), mock.patch.object(lx.os, "getuid", lambda: 1000, create=True):
            self.assertTrue(lx.single_instance())
            self.assertFalse(lx.single_instance())
            self.assertTrue(Path(folder, "airmouse-1000.lock").exists())
            lx._instance_lock.close()
            locked[0].close()


class LanguageAndSettingsTest(unittest.TestCase):
    def test_language_from_the_locale(self):
        with mock.patch.object(i18n.sys, "platform", "linux"):
            for locale, language in (("ru_RU.UTF-8", "ru"), ("uz_UZ.UTF-8", "ru"), ("en_US.UTF-8", "en"), ("", "en")):
                with mock.patch.dict(os.environ, {"LANG": locale, "LC_ALL": "", "LC_MESSAGES": ""}):
                    self.assertEqual(i18n.system_language(), language, locale)

    def test_settings_folder(self):
        from airmouse import settings
        with mock.patch.object(settings.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/home/u/.config"}):
            self.assertEqual(settings._settings_dir(), Path("/home/u/.config/AirMouse"))


class WindowsOnLinuxTest(unittest.TestCase):
    def test_rounded_panel_is_a_few_rectangles(self):
        from airmouse.overlay import round_mask
        mask = round_mask(120, 80, 14) >= 0.5
        rects = mask_rectangles(mask)
        rebuilt = np.zeros_like(mask)
        for x, y, w, h in rects:
            rebuilt[y:y + h, x:x + w] = True
        np.testing.assert_array_equal(rebuilt, mask)
        self.assertLess(len(rects), 40)
        self.assertEqual(mask_rectangles(np.zeros((5, 5), bool)), [])
        self.assertEqual(mask_rectangles(np.array([[1, 0, 1], [1, 0, 1]], bool)), [(0, 0, 1, 2), (2, 0, 1, 2)])

    def test_colours_come_out_of_premultiplied(self):
        bgra = np.array([[[50, 100, 150, 200], [0, 0, 0, 0]]], np.uint8)     # blue, green, red, alpha
        np.testing.assert_allclose(unpremultiply(bgra)[0, 0], (191, 127, 63), atol=1)   # red, green, blue

    def test_fonts_and_icons_without_segoe(self):
        with mock.patch.object(glass.sys, "platform", "linux"), \
                mock.patch.object(glass.shutil, "which", lambda p: "/usr/bin/fc-match"), \
                mock.patch.object(glass.subprocess, "run",
                                  lambda *a, **k: SimpleNamespace(stdout="/usr/share/fonts/NotoSans-SemiBold.ttf")):
            glass.font_files.cache_clear()
            try:
                files = glass.font_files("semibold")
                self.assertEqual(files[0], Path("/usr/share/fonts/NotoSans-SemiBold.ttf"))
                self.assertTrue(str(files[-1]).endswith("DejaVuSans-Bold.ttf"))
                self.assertEqual(glass.font_files("icons"), ())
            finally:
                glass.font_files.cache_clear()
        from airmouse import onscreen
        icons = [getattr(onscreen, n) for n in dir(onscreen) if n.startswith("ICON_")] + [glass.ICON_CAMERA]
        self.assertEqual([i for i in icons if i not in glass.ICON_TEXT], [])


if __name__ == "__main__":
    unittest.main()
