@echo off
setlocal enabledelayedexpansion
title NoMusic Podcast Cleaner (Portable)
cd /d "%~dp0"

echo ============================================
echo   NoMusic Podcast Cleaner  (Portable)
echo   No separate Python install needed.
echo ============================================
echo.

set "PY=%~dp0python\python.exe"
if not exist "%PY%" (
  echo [X] Bundled Python is missing. This package looks incomplete.
  echo     Please get a fresh copy of the package.
  pause
  exit /b 1
)

REM --- FFmpeg: use the bundled copy --------------------------------------
if exist "%~dp0bin\ffmpeg.exe" (
  set "PATH=%~dp0bin;!PATH!"
) else (
  echo [!] Bundled FFmpeg is missing. Cleaning may not work.
  echo.
)

REM --- Install components on first run -----------------------------------
if not exist "%~dp0python\.installed" (
  echo Installing components ^(first run only - needs internet, a few minutes^)...
  echo.
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [X] Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  echo done> "%~dp0python\.installed"
  echo.
  echo Components installed.
  echo.
)

REM --- Launch (browser opens automatically) -----------------------------
echo Starting... your browser will open in a moment.
echo Keep this window open while you use the app. Close it to stop.
echo.
"%PY%" app.py

echo.
echo App stopped.
pause
