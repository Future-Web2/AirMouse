@echo off
rem Builds dist\AirMouse\AirMouse.exe
setlocal
cd /d "%~dp0"

if not exist models\hand_landmarker.task (
    echo Downloading the hand model...
    curl.exe -sSL --create-dirs -o models\hand_landmarker.task ^
        https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task || goto :error
)
if not exist models\face_landmarker.task (
    echo Downloading the face model...
    curl.exe -sSL --create-dirs -o models\face_landmarker.task ^
        https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task || goto :error
)
if not exist .venv\Scripts\python.exe (
    python -m venv .venv || goto :error
)
rem requirements.txt pins everything AirMouse needs, so it installs without dependencies.
rem A .venv from an older build has the full OpenCV in place of the headless one: swap it.
.venv\Scripts\python.exe -m pip show -q opencv-contrib-python >nul 2>&1 && (
    .venv\Scripts\python.exe -m pip uninstall -q -y opencv-contrib-python matplotlib sounddevice || goto :error
    .venv\Scripts\python.exe -m pip install -q --no-deps --force-reinstall -r requirements.txt || goto :error
)
.venv\Scripts\python.exe -m pip install -q --no-deps -r requirements.txt || goto :error
.venv\Scripts\python.exe -m pip install -q pyinstaller==6.22.3 || goto :error

rem Left out: matplotlib and sounddevice (mediapipe extras), image formats and TLS that nothing opens.
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name AirMouse ^
    --icon assets\airmouse.ico ^
    --add-data "models;models" ^
    --add-data "assets\airmouse.ico;assets" ^
    --collect-binaries mediapipe ^
    --copy-metadata mediapipe ^
    --collect-data sv_ttk ^
    --exclude-module matplotlib ^
    --exclude-module sounddevice ^
    --exclude-module PIL.AvifImagePlugin --exclude-module PIL._avif ^
    --exclude-module PIL.WebPImagePlugin --exclude-module PIL._webp ^
    --exclude-module PIL.ImageCms --exclude-module PIL._imagingcms ^
    --exclude-module ssl --exclude-module _ssl --exclude-module _hashlib ^
    main.py || goto :error

rem Not used at run time: FFmpeg (only for video files; the camera goes through
rem DirectShow / Media Foundation) and the time zones of Tcl (600 small files).
del /q dist\AirMouse\_internal\cv2\opencv_videoio_ffmpeg*.dll 2>nul
rmdir /s /q dist\AirMouse\_internal\_tcl_data\tzdata 2>nul

echo.
echo Done: dist\AirMouse\AirMouse.exe
exit /b 0

:error
echo Build failed.
exit /b 1
