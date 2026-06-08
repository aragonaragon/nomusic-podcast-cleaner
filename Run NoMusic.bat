@echo off
setlocal enabledelayedexpansion
title NoMusic Podcast Cleaner

REM Always run from the folder this file lives in.
cd /d "%~dp0"

echo ============================================
echo   NoMusic Podcast Cleaner
echo ============================================
echo.

REM --- 1) Make sure Python exists -------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python was not found.
  echo     Install Python 3.11+ from https://www.python.org/downloads/
  echo     and tick "Add Python to PATH" during setup.
  echo.
  pause
  exit /b 1
)

REM --- 2) Make sure FFmpeg is reachable -------------------------------------
REM Prefer the copy bundled with this package (folder: bin\).
if exist "%~dp0bin\ffmpeg.exe" (
  set "PATH=%~dp0bin;!PATH!"
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  REM Otherwise try the FFmpeg that winget installs, even before a shell restart.
  set "FFDIR="
  for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
    for /d %%B in ("%%D\ffmpeg-*") do (
      if exist "%%B\bin\ffmpeg.exe" set "FFDIR=%%B\bin"
    )
  )
  if defined FFDIR (
    set "PATH=!FFDIR!;!PATH!"
  ) else (
    echo [!] FFmpeg was not found. The app will open but cleaning will not work.
    echo     Install it with:  winget install Gyan.FFmpeg
    echo     then close and run this file again.
    echo.
  )
)

REM --- 3) Create the virtual environment on first run ----------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creating a local environment ^(first run only^)...
  python -m venv .venv
  if errorlevel 1 (
    echo [X] Could not create the environment.
    pause
    exit /b 1
  )
)

set "PY=.venv\Scripts\python.exe"

REM --- 4) Install dependencies once (marker file tracks completion) ---------
if not exist ".venv\.installed" (
  echo Installing components ^(first run only - this can take several minutes^)...
  echo.
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [X] Installation failed. See the messages above.
    pause
    exit /b 1
  )
  echo done> ".venv\.installed"
  echo.
  echo Components installed.
  echo.
)

REM --- 5) Launch (the browser opens automatically) -------------------------
echo Starting... your browser will open in a moment.
echo Keep this window open while you use the app. Close it to stop.
echo.
"%PY%" app.py

echo.
echo App stopped.
pause
