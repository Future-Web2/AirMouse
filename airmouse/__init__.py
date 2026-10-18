"""AirMouse: control the Windows mouse with hand gestures in front of a webcam."""

import sys
from pathlib import Path


def resource_path(relative):
    """Path to a bundled file, both when run from source and from the built .exe."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return Path(base) / relative
