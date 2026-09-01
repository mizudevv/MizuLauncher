@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Building MizuLauncher with PyInstaller...
python -m PyInstaller --noconfirm --clean --onedir --windowed --name MizuLauncher --add-data "VERSION.txt;." --add-data "assets;assets" main.py
if errorlevel 1 (
  echo PyInstaller failed.
  exit /b 1
)

echo [2/3] Writing integrity manifest...
python tools\write_exe_manifest.py dist\MizuLauncher\MizuLauncher.exe
if errorlevel 1 (
  echo Integrity manifest failed.
  exit /b 1
)

echo [3/3] Build complete.
echo Folder: dist\MizuLauncher\
echo EXE:    dist\MizuLauncher\MizuLauncher.exe
endlocal
