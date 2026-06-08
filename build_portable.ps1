# Builds a PORTABLE package of NoMusic Podcast Cleaner.
#
# The package bundles a private copy of Python (embeddable) AND FFmpeg, so the
# person you share with needs NOTHING pre-installed. They just double-click
# "Run NoMusic (Portable).bat". The first run installs the Python components
# into the bundled Python (needs internet once).
#
# Output:  dist\NoMusic Podcast Cleaner Portable\
#          dist\NoMusic-Podcast-Cleaner-Portable.zip
#
# Run from this folder:
#   powershell -ExecutionPolicy Bypass -File build_portable.ps1

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$pyVer  = "3.11.9"
$root   = $PSScriptRoot
$dist   = Join-Path $root "dist"
$name   = "NoMusic Podcast Cleaner Portable"
$pkg    = Join-Path $dist $name
$pyDir  = Join-Path $pkg "python"

Write-Host "Building PORTABLE package (bundles Python $pyVer + FFmpeg)..." -ForegroundColor Cyan

# --- 1) Fresh package folder -------------------------------------------------
if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
New-Item -ItemType Directory -Force -Path $pyDir | Out-Null

# --- 2) Download + extract embeddable Python --------------------------------
$embedUrl = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-amd64.zip"
$embedZip = Join-Path $dist "python-embed.zip"
Write-Host "  Downloading embeddable Python..."
Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip
Expand-Archive -Path $embedZip -DestinationPath $pyDir -Force
Remove-Item $embedZip -Force

# --- 3) Enable site-packages so pip works -----------------------------------
# The embeddable build ships with a ._pth file that disables site imports.
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
@(
    "python311.zip",
    ".",
    "Lib\site-packages",
    "",
    "import site"
) | Set-Content -Path $pth.FullName -Encoding ASCII
Write-Host "  Configured $($pth.Name) for pip."

# --- 4) Bootstrap pip --------------------------------------------------------
Write-Host "  Bootstrapping pip..."
$getpip = Join-Path $pyDir "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
& (Join-Path $pyDir "python.exe") $getpip --no-warn-script-location | Out-Null
Remove-Item $getpip -Force

# --- 5) Copy application files -----------------------------------------------
foreach ($f in @("app.py", "requirements.txt", "README.md", "README.en.md")) {
    Copy-Item (Join-Path $root $f) (Join-Path $pkg $f)
}
Copy-Item (Join-Path $root "Run NoMusic (Portable).bat") (Join-Path $pkg "Run NoMusic.bat")

$srcDst = Join-Path $pkg "src"
New-Item -ItemType Directory -Force -Path $srcDst | Out-Null
Get-ChildItem (Join-Path $root "src") -Filter *.py | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $srcDst $_.Name)
}
foreach ($d in @("outputs", "temp")) {
    $p = Join-Path $pkg $d
    New-Item -ItemType Directory -Force -Path $p | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $p ".gitkeep") | Out-Null
}

# --- 6) Bundle FFmpeg --------------------------------------------------------
function Find-Tool($t) {
    $c = Get-Command $t -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $h = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "$t.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($h) { return $h.FullName }
    return $null
}
$bin = Join-Path $pkg "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null
$ffmpeg = Find-Tool "ffmpeg"; $ffprobe = Find-Tool "ffprobe"
if ($ffmpeg -and $ffprobe) {
    Copy-Item $ffmpeg  (Join-Path $bin "ffmpeg.exe")
    Copy-Item $ffprobe (Join-Path $bin "ffprobe.exe")
    Write-Host "  Bundled FFmpeg." -ForegroundColor Green
} else {
    Write-Host "  [!] FFmpeg not found to bundle." -ForegroundColor Yellow
}

# --- 7) Recipient note -------------------------------------------------------
@"
NoMusic Podcast Cleaner (Portable)
==================================

Nothing to install. Just double-click  "Run NoMusic.bat"

- The FIRST run downloads the components it needs (needs internet, a few minutes).
- After that it starts in seconds and opens your browser.
- Drop in audio/video files, click "Start cleaning".
  Results are saved in the "outputs" folder.

Everything runs on your own computer. Nothing is uploaded.
"@ | Set-Content -Path (Join-Path $pkg "START HERE.txt") -Encoding UTF8

Write-Host ""
Write-Host "Scaffold ready: $pkg" -ForegroundColor Cyan
Write-Host "Next: zip it (after optional pre-install) - see build output."
