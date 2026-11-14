#!/usr/bin/env bash
# Builds dist/AirMouse/AirMouse and dist/AirMouse-linux-x64.tar.gz on Linux (build.bat does it on Windows).
# Needs Python 3.12 or newer with Tk and venv (Debian, Ubuntu: sudo apt install python3-venv python3-tk).
set -euo pipefail
cd "$(dirname "$0")"

download() {
    if [ ! -f "$1" ]; then
        echo "Downloading $1..."
        mkdir -p "$(dirname "$1")"
        curl -fsSL -o "$1" "$2"
    fi
}
download models/hand_landmarker.task \
    https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
download models/face_landmarker.task \
    https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

if [ ! -x .venv/bin/python ]; then
    "${PYTHON:-python3}" -m venv .venv
fi
if ! .venv/bin/python -c "import tkinter" 2>/dev/null; then
    echo "Python has no Tk: install it (Debian, Ubuntu: sudo apt install python3-tk) and run build.sh again."
    exit 1
fi
# requirements.txt pins everything AirMouse needs (python-xlib only on Linux), so it installs without dependencies.
.venv/bin/python -m pip install -q --no-deps -r requirements.txt
.venv/bin/python -m pip install -q pyinstaller==6.22.3

# python-xlib loads its extensions (SHAPE, XTEST) by name, so they are collected explicitly.
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name AirMouse \
    --add-data "models:models" \
    --add-data "assets/airmouse.ico:assets" \
    --collect-binaries mediapipe \
    --copy-metadata mediapipe \
    --collect-data sv_ttk \
    --collect-submodules Xlib \
    --exclude-module matplotlib \
    --exclude-module sounddevice \
    --exclude-module PIL.AvifImagePlugin --exclude-module PIL._avif \
    --exclude-module PIL.WebPImagePlugin --exclude-module PIL._webp \
    --exclude-module PIL.ImageCms --exclude-module PIL._imagingcms \
    --exclude-module ssl --exclude-module _ssl --exclude-module _hashlib \
    main.py

# Not used at run time: the time zones of Tcl (600 small files).
rm -rf dist/AirMouse/_internal/_tcl_data/tzdata

# Next to the program: the menu entry and access to /dev/uinput (install.sh), and the icon.
cp linux/install.sh linux/99-airmouse-uinput.rules dist/AirMouse/
.venv/bin/python -c "from PIL import Image; Image.open('assets/airmouse.ico').save('dist/AirMouse/airmouse.png')"
tar -C dist -czf dist/AirMouse-linux-x64.tar.gz AirMouse

echo
echo "Done: dist/AirMouse/AirMouse and dist/AirMouse-linux-x64.tar.gz"
