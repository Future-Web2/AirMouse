"""Key names AirMouse understands ("ctrl+shift+s", "win+d", "playpause"), the same on Windows and Linux.

Keys are kept as Windows virtual-key codes; linuxsystem.py turns them into Linux key codes.
"""

from .i18n import _

NAMED_KEYS = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "printscreen": 0x2C,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "nexttrack": 0xB0, "prevtrack": 0xB1, "stop": 0xB2, "playpause": 0xB3,
    "plus": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE,
}
ALIASES = {
    "control": "ctrl", "windows": "win", "cmd": "win", "escape": "esc", "return": "enter",
    "del": "delete", "ins": "insert", "pgup": "pageup", "pgdn": "pagedown", "prtsc": "printscreen",
    "mute": "volumemute", "next": "nexttrack", "prev": "prevtrack", "play": "playpause", "pause": "playpause",
}


def parse_keys(text):
    """"ctrl+shift+s" -> virtual-key codes. ValueError (with a message for the user) for anything unknown."""
    codes = []
    for part in text.lower().replace(" ", "").split("+"):
        name = ALIASES.get(part, part)
        if name in NAMED_KEYS:
            codes.append(NAMED_KEYS[name])
        elif len(name) == 1 and name.isascii() and name.isalnum():
            codes.append(ord(name.upper()))
        elif len(name) > 1 and name[0] == "f" and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
            codes.append(0x70 + int(name[1:]) - 1)
        else:
            raise ValueError(_("Неизвестная клавиша: «{}»").format(part) if part else _("Пустая клавиша в сочетании"))
    return codes
