"""What AirMouse asks of the operating system: the mouse and keys, the screen, other programs' windows,
sound, load, the clipboard, opening things.

Windows (winsystem.py, winmouse.py) and Linux (linuxsystem.py) each do it their own way; this
module picks the one for this computer and adds what is the same on both: the actions of the
buttons on the on-screen panels.
"""

import sys

from .i18n import _
from .keys import ALIASES, NAMED_KEYS, parse_keys  # noqa: F401

if sys.platform == "win32":
    from .winsystem import (  # noqa: F401
        CAMERA_API, VK_CONTROL, VK_MENU, Mouse, ProcessLoad, SystemLoad, Volume,
        copy_picture, ctrl_wheel, cursor_pos, dark_theme, enable_dpi_awareness, key_down, note_screen, note_window,
        open_target, own_window_at, press_keys, process_memory_mb, process_uptime, screen_bounds, screen_size,
        show_message, single_instance, window_command, window_in_front,
    )
else:
    from .linuxsystem import (  # noqa: F401
        CAMERA_API, VK_CONTROL, VK_MENU, Mouse, ProcessLoad, SystemLoad, Volume,
        copy_picture, ctrl_wheel, cursor_pos, dark_theme, enable_dpi_awareness, key_down, note_screen, note_window,
        open_target, own_window_at, press_keys, process_memory_mb, process_uptime, screen_bounds, screen_size,
        show_message, single_instance, window_command, window_in_front,
    )


def run_action(action):
    """action: {"do": "keys", "value": "ctrl+c"} or {"do": "open", "value": "notepad"}.

    Returns an error text for the user, or None when it worked.
    """
    do, value = action.get("do"), str(action.get("value", ""))
    if do == "keys":
        try:
            press_keys(value)
        except ValueError as exc:
            return str(exc)
        return None
    if do == "open":
        return open_target(value)
    return _("Неизвестное действие")


def check_action(action):
    """The error run_action would give for a malformed action, without running it; None if it is fine."""
    if action.get("do") == "keys":
        try:
            parse_keys(str(action.get("value", "")))
        except ValueError as exc:
            return str(exc)
        return None
    if action.get("do") == "open":
        return None if str(action.get("value", "")).strip() else _("Не указано, что открыть")
    return _("Неизвестное действие")
