@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Installer build completed.
pause
endlocal
