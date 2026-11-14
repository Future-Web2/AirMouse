#!/usr/bin/env bash
# Sets AirMouse up on Linux, once, from the folder it was unpacked to:
#   1. a menu entry (only for you, no password needed);
#   2. access to /dev/uinput, so that AirMouse can move the mouse under X11 and Wayland
#      (asks for your password: it installs a udev rule and adds you to the input group).
#
#   ./install.sh            both
#   ./install.sh --menu     only the menu entry
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

applications="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$applications"
cat > "$applications/airmouse.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=AirMouse
Comment=Control the mouse with your hands, eyes or head through a webcam
Comment[ru]=Управление мышью руками, взглядом или головой через веб-камеру
Exec="$here/AirMouse"
Icon=$here/airmouse.png
Terminal=false
Categories=Utility;Accessibility;
EOF
echo "Menu entry: $applications/airmouse.desktop"

if [ "${1:-}" = "--menu" ]; then
    exit 0
fi

echo "Access to /dev/uinput (sudo asks for your password):"
sudo install -m 644 "$here/99-airmouse-uinput.rules" /etc/udev/rules.d/99-airmouse-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/airmouse-uinput.conf > /dev/null
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput
sudo usermod -aG input "$USER"
echo "Done. If AirMouse still cannot move the mouse, log out and back in."
