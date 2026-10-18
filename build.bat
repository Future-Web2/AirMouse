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
.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller || goto :error

.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name AirMouse ^
    --icon assets\airmouse.ico ^
    --add-data "models;models" ^
    --add-data "assets\airmouse.ico;assets" ^
    --collect-all mediapipe ^
    --collect-data sv_ttk ^
    main.py || goto :error

echo.
echo Done: dist\AirMouse\AirMouse.exe
exit /b 0

:error
echo Build failed.
exit /b 1
