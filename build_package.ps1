# Builds a shareable package of NoMusic Podcast Cleaner.
#
# Output:  dist\NoMusic Podcast Cleaner\   (the folder to share)
#          dist\NoMusic-Podcast-Cleaner.zip (zipped, ready to send)
#
# The package bundles FFmpeg, so the person you share with only needs Python.
# First launch installs the Python components automatically (needs internet once).
#
# Run from this folder:   powershell -ExecutionPolicy Bypass -File build_package.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dist = Join-Path $root "dist"
$pkgName = "NoMusic Podcast Cleaner"
$pkg = Join-Path $dist $pkgName

Write-Host "Building package..." -ForegroundColor Cyan

# --- 1) Fresh package folder -------------------------------------------------
if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
New-Item -ItemType Directory -Force -Path $pkg | Out-Null

# --- 2) Copy application files ------------------------------------------------
foreach ($f in @("app.py", "requirements.txt", "README.md", "Run NoMusic.bat")) {
    Copy-Item (Join-Path $root $f) (Join-Path $pkg $f)
}

# src\ without caches
$srcDst = Join-Path $pkg "src"
New-Item -ItemType Directory -Force -Path $srcDst | Out-Null
Get-ChildItem (Join-Path $root "src") -Filter *.py | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $srcDst $_.Name)
}

# empty working folders
foreach ($d in @("outputs", "temp")) {
    $p = Join-Path $pkg $d
    New-Item -ItemType Directory -Force -Path $p | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $p ".gitkeep") | Out-Null
}

# --- 3) Bundle FFmpeg (ffmpeg.exe + ffprobe.exe) -----------------------------
function Find-Tool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "$name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

$bin = Join-Path $pkg "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null
$ffmpeg = Find-Tool "ffmpeg"
$ffprobe = Find-Tool "ffprobe"
if ($ffmpeg -and $ffprobe) {
    Copy-Item $ffmpeg (Join-Path $bin "ffmpeg.exe")
    Copy-Item $ffprobe (Join-Path $bin "ffprobe.exe")
    Write-Host "  Bundled FFmpeg from: $ffmpeg" -ForegroundColor Green
} else {
    Write-Host "  [!] FFmpeg not found to bundle. The package will rely on the user installing it." -ForegroundColor Yellow
}

# --- 4) A plain-language note for the recipient ------------------------------
$readme = @"
NoMusic Podcast Cleaner — how to start
======================================

1. Make sure Python 3.11 or newer is installed.
   Get it from https://www.python.org/downloads/ and tick
   "Add Python to PATH" during setup.

2. Double-click  "Run NoMusic.bat"

   - The FIRST time, it installs what it needs automatically.
     This takes a few minutes and needs an internet connection.
   - After that it starts in seconds and opens your browser.

3. Drop in your audio/video files, click "Start cleaning".
   Results are saved in the "outputs" folder.

What you need:
- Windows 64-bit, Python 3.11+
- About 3 GB of free disk space
- 8 GB RAM recommended (4 GB minimum; it just runs slower)
- Internet on the first run (to download components and the audio model)
- A graphics card is NOT required.

Everything runs on your own computer. Nothing is uploaded.
"@
Set-Content -Path (Join-Path $pkg "START HERE.txt") -Value $readme -Encoding UTF8

# --- 5) Zip it ---------------------------------------------------------------
$zip = Join-Path $dist "NoMusic-Podcast-Cleaner.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $pkg -DestinationPath $zip

$zipMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
Write-Host "  Folder: $pkg"
Write-Host "  Zip:    $zip  ($zipMB MB)"
