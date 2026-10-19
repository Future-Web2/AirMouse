"""Settings file: defaults, round trip, and damaged files."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from airmouse import settings
from airmouse.settings import Settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.saved = settings.SETTINGS_DIR, settings.SETTINGS_FILE
        self.dir = Path(tempfile.mkdtemp())
        settings.SETTINGS_DIR = self.dir / "AirMouse"
        settings.SETTINGS_FILE = settings.SETTINGS_DIR / "settings.json"

    def tearDown(self):
        settings.SETTINGS_DIR, settings.SETTINGS_FILE = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_defaults_without_a_file(self):
        self.assertEqual(Settings.load(), Settings())

    def test_round_trip(self):
        s = Settings(design="classic", mode="head", smoothing=0.25, invert_scroll=True,
                     gaze_model={"error": 42.0, "c": [0.1, 0.2]})
        s.save()
        self.assertEqual(Settings.load(), s)

    def test_damaged_file_gives_defaults(self):
        settings.SETTINGS_DIR.mkdir(parents=True)
        settings.SETTINGS_FILE.write_text("{not json", encoding="utf-8")
        self.assertEqual(Settings.load(), Settings())

    def test_bad_values_are_skipped_and_unknown_keys_ignored(self):
        settings.SETTINGS_DIR.mkdir(parents=True)
        settings.SETTINGS_FILE.write_text(json.dumps(
            {"smoothing": "very", "camera_index": "2", "scroll_speed": 3, "colour": "red"}), encoding="utf-8")
        s = Settings.load()
        self.assertEqual(s.smoothing, Settings().smoothing)
        self.assertEqual(s.camera_index, 2)
        self.assertEqual(s.scroll_speed, 3.0)
        self.assertIsInstance(s.scroll_speed, float)


if __name__ == "__main__":
    unittest.main()
