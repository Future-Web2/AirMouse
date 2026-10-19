"""Keys, volume and load. Nothing here presses a key or changes the volume: only reading and parsing."""

import time
import unittest

from airmouse import system
from airmouse.system import KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP


class KeysTest(unittest.TestCase):
    def test_combinations(self):
        self.assertEqual(system.parse_keys("ctrl+shift+s"), [0x11, 0x10, ord("S")])
        self.assertEqual(system.parse_keys(" Win + D "), [0x5B, ord("D")])
        self.assertEqual(system.parse_keys("alt+f4"), [0x12, 0x73])
        self.assertEqual(system.parse_keys("playpause"), [0xB3])
        self.assertEqual(system.parse_keys("control+escape"), [0x11, 0x1B])

    def test_unknown_keys_are_explained(self):
        for text in ("", "ctrl+", "ctrl+qq", "f25", "ктрл+c"):
            with self.assertRaises(ValueError) as caught:
                system.parse_keys(text)
            self.assertTrue(str(caught.exception))

    def test_keys_go_down_in_order_and_up_in_reverse(self):
        events = system.key_events([0x5B, ord("D")])
        self.assertEqual(events, [(0x5B, KEYEVENTF_EXTENDEDKEY), (ord("D"), 0),
                                  (ord("D"), KEYEVENTF_KEYUP), (0x5B, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP)])

    def test_check_action(self):
        self.assertIsNone(system.check_action({"do": "keys", "value": "ctrl+c"}))
        self.assertIsNotNone(system.check_action({"do": "keys", "value": "ctrl+what"}))
        self.assertIsNone(system.check_action({"do": "open", "value": "notepad"}))
        self.assertIsNotNone(system.check_action({"do": "open", "value": "  "}))
        self.assertIsNotNone(system.check_action({"do": "format c:"}))

    def test_bad_action_reports_instead_of_pressing(self):
        self.assertIsNotNone(system.run_action({"do": "keys", "value": "ctrl+nothing"}))
        self.assertIsNotNone(system.run_action({"do": "nothing"}))
        self.assertIsNotNone(system.open_target(""))


class VolumeTest(unittest.TestCase):
    def test_reading_the_volume(self):
        volume = system.Volume()
        level = volume.level()
        if level is None:
            self.skipTest("no playback device")
        self.assertTrue(0.0 <= level <= 1.0)
        self.assertIsInstance(volume.muted(), bool)


class LoadTest(unittest.TestCase):
    def test_system_load(self):
        load = system.SystemLoad()
        self.assertEqual(load.cpu(), 0.0)          # the first call only starts measuring
        time.sleep(0.05)
        self.assertTrue(0.0 <= load.cpu() <= 100.0)
        self.assertTrue(0.0 < load.memory() <= 100.0)
        battery = load.battery()
        if battery is not None:
            self.assertTrue(0.0 <= battery[0] <= 100.0)
            self.assertIsInstance(battery[1], bool)

    def test_own_load(self):
        load = system.ProcessLoad()
        load.cpu()
        sum(i * i for i in range(200_000))
        self.assertTrue(0.0 <= load.cpu() <= 100.0)
        self.assertGreater(system.process_memory_mb(), 5)


if __name__ == "__main__":
    unittest.main()
