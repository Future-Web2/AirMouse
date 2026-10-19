"""User settings, stored in %APPDATA%\\AirMouse\\settings.json."""

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

SETTINGS_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "AirMouse"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


@dataclass
class Settings:
    design: str = "glass"           # window design: "glass" (Liquid Glass) or "classic"
    mode: str = "hand"              # what moves the cursor: "hand", "gaze" (eyes) or "head"
    camera_index: int = 0
    smoothing: float = 0.7          # 0 = fastest, 1 = most stable
    cursor_speed: float = 0.5       # 0 = slow and precise, 1 = small hand moves cross the screen
    zone_center_x: float = 0.5      # centre of the hand zone in the camera image, 0..1
    zone_center_y: float = 0.55
    pinch_threshold: float = 0.30   # fingertip distance (in palm lengths) that counts as touching
    blink_time: float = 0.4         # eyes closed at least this long (seconds) -> click
    scroll_speed: float = 2.5
    invert_scroll: bool = False
    always_on_top: bool = False
    gaze_model: dict = field(default_factory=dict)   # from the gaze calibration
    widgets_on: bool = True         # on-screen widgets while AirMouse runs (thumbs up / Ctrl+Alt+W toggle)
    cursor_ring: bool = True        # ring around the cursor showing the gesture in progress
    widgets: list = field(default_factory=list)      # the on-screen widgets (see onscreen.py)

    @property
    def zone_size(self):
        """Width of the hand zone as a fraction of the camera image."""
        return 0.85 - 0.5 * self.cursor_speed

    @classmethod
    def load(cls):
        settings = cls()
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return settings
        for f in fields(cls):
            if f.name in data:
                try:
                    setattr(settings, f.name, type(getattr(settings, f.name))(data[f.name]))
                except (TypeError, ValueError):
                    pass
        return settings

    def save(self):
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
