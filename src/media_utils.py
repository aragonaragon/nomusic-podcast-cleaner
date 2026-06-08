"""
Media helpers: file-type detection and all FFmpeg interactions.

Every FFmpeg call goes through `run_ffmpeg`, which uses a plain argument list
(never shell=True) so file names with spaces or odd characters are safe.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import config


class FFmpegError(RuntimeError):
    """Raised when FFmpeg is missing or a command fails."""


# Platform-specific install hint, shown when FFmpeg can't be found.
def _install_hint() -> str:
    system = platform.system()
    if system == "Windows":
        return "Windows:  winget install Gyan.FFmpeg   (then open a NEW terminal)"
    if system == "Darwin":
        return "macOS:    brew install ffmpeg"
    return "Linux:    sudo apt install ffmpeg   (or your distro's package manager)"


def find_ffmpeg() -> str:
    """Return the ffmpeg executable path or raise a clear, actionable error."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegError(
            "FFmpeg is required but was not found.\n\n"
            "FFmpeg handles reading/writing audio and video. Install it, then "
            "restart this app:\n\n"
            f"  {_install_hint()}\n\n"
            "After installing, run `ffmpeg -version` in a new terminal to "
            "confirm it works."
        )
    return ffmpeg


def check_setup() -> tuple[bool, str]:
    """
    Non-raising setup probe for the UI.

    Returns (ok, message). `ok` is False if FFmpeg is missing.
    """
    try:
        find_ffmpeg()
        return True, "FFmpeg detected — ready to go."
    except FFmpegError as exc:
        return False, str(exc)


def run_ffmpeg(args: list[str]) -> None:
    """
    Run an FFmpeg command safely.

    `args` is the part *after* the executable, e.g. ["-y", "-i", "in.mp4", ...].
    Raises FFmpegError with the captured stderr if the command fails.
    """
    ffmpeg = find_ffmpeg()
    cmd = [ffmpeg, *args]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        # Keep the tail of stderr — that's where FFmpeg explains what broke.
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise FFmpegError(f"FFmpeg failed:\n{tail}")


def timestamp() -> str:
    """A filesystem-safe timestamp for unique file names."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_media_type(path: Path) -> str | None:
    """Return 'video', 'audio', or None based on the file extension."""
    ext = path.suffix.lower()
    if ext in config.VIDEO_EXTENSIONS:
        return "video"
    if ext in config.AUDIO_EXTENSIONS:
        return "audio"
    return None


def _maybe_limit(max_seconds: int | None) -> list[str]:
    """FFmpeg args to cap duration (used by preview mode); empty if no limit."""
    return ["-t", str(max_seconds)] if max_seconds else []


def extract_audio(input_path: Path, temp_dir: Path, max_seconds: int | None = None) -> Path:
    """
    Extract the audio track from a video into a clean WAV file.

    ffmpeg -y -i input.mp4 -vn -ac 2 -ar 44100 [-t N] temp/<name>_audio.wav
    """
    out_path = temp_dir / f"{input_path.stem}_{timestamp()}_audio.wav"
    run_ffmpeg([
        "-y",
        "-i", str(input_path),
        "-vn",                       # drop the video stream
        "-ac", str(config.CHANNELS),
        "-ar", str(config.SAMPLE_RATE),
        *_maybe_limit(max_seconds),
        str(out_path),
    ])
    return out_path


def convert_to_wav(input_path: Path, temp_dir: Path, max_seconds: int | None = None) -> Path:
    """
    Convert any audio file to a standard working WAV so the separator gets a
    predictable input. If it's already a matching WAV we still re-encode for
    consistency — it's cheap and avoids edge cases.
    """
    out_path = temp_dir / f"{input_path.stem}_{timestamp()}_work.wav"
    run_ffmpeg([
        "-y",
        "-i", str(input_path),
        "-ac", str(config.CHANNELS),
        "-ar", str(config.SAMPLE_RATE),
        *_maybe_limit(max_seconds),
        str(out_path),
    ])
    return out_path


def to_working_wav(input_path: Path, out_path: Path, max_seconds: int | None = None) -> Path:
    """
    Convert any audio OR video file to a standard mono working WAV.

    `-vn` (drop video) is harmless for audio-only inputs, so this one helper
    covers both cases. Writing to an explicit `out_path` lets the pipeline cache
    it deterministically for resume.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-y",
        "-i", str(input_path),
        "-vn",
        "-ac", str(config.CHANNELS),
        "-ar", str(config.SAMPLE_RATE),
        *_maybe_limit(max_seconds),
        str(out_path),
    ])
    return out_path


def measure_mean_volume(path: Path) -> float | None:
    """
    Return the mean volume (dBFS, negative number) of an audio file using
    FFmpeg's volumedetect. Returns None if it can't be measured.

    Used only for the rough "heavy music" heuristic — not for processing.
    """
    ffmpeg = find_ffmpeg()
    null_out = "NUL" if platform.system() == "Windows" else "/dev/null"
    result = subprocess.run(
        [ffmpeg, "-i", str(path), "-af", "volumedetect", "-f", "null", null_out],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    return float(match.group(1)) if match else None


def get_duration(path: Path) -> float | None:
    """
    Return media duration in seconds using ffprobe, or None if unavailable.

    ffprobe ships with FFmpeg; if it's missing we just skip duration-based
    features (chunking still works via a safe default).
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return None


def _detect_silences(wav_path: Path) -> list[tuple[float, float]]:
    """
    Return a list of (start, end) silent intervals using FFmpeg's silencedetect.
    Empty list if none found or it can't be measured.
    """
    ffmpeg = find_ffmpeg()
    null_out = "NUL" if platform.system() == "Windows" else "/dev/null"
    flt = f"silencedetect=noise={config.SILENCE_NOISE_DB}dB:d={config.SILENCE_MIN_DURATION}"
    result = subprocess.run(
        [ffmpeg, "-i", str(wav_path), "-af", flt, "-f", "null", null_out],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)", result.stderr)]
    return list(zip(starts, ends))


def compute_silence_cut_points(wav_path: Path, chunk_seconds: int) -> list[float]:
    """
    Pick chunk boundaries that fall on quiet moments, so seams aren't audible.

    Strategy: walk forward in `chunk_seconds` steps; for each target time, snap
    to the middle of the nearest silence within SILENCE_SEARCH_WINDOW. Falls
    back to the exact target time if no nearby silence exists.

    Returns a sorted list of cut times (seconds), excluding 0 and the end.
    """
    duration = get_duration(wav_path)
    if not duration or duration <= chunk_seconds:
        return []

    silences = _detect_silences(wav_path)
    # Candidate cut instants = midpoints of each silent gap.
    midpoints = [(s + e) / 2 for s, e in silences]

    cuts: list[float] = []
    target = float(chunk_seconds)
    window = config.SILENCE_SEARCH_WINDOW
    while target < duration - 1:
        near = [m for m in midpoints if abs(m - target) <= window and m > (cuts[-1] if cuts else 0)]
        cut = min(near, key=lambda m: abs(m - target)) if near else target
        # Avoid zero-length or out-of-order segments.
        if cut > (cuts[-1] if cuts else 0) + 1 and cut < duration - 1:
            cuts.append(round(cut, 3))
            target = cut + chunk_seconds
        else:
            target += chunk_seconds
    return cuts


def split_audio(
    wav_path: Path,
    chunk_seconds: int,
    out_dir: Path,
    segment_times: list[float] | None = None,
) -> list[Path]:
    """
    Split a WAV file into chunks for low-memory processing.

    If `segment_times` is given, cut at exactly those instants (silence-aware);
    otherwise fall back to fixed `chunk_seconds` intervals. Stream copy — fast
    and lossless. Returns the chunk paths in order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "part_%03d.wav"
    split_args = (
        ["-segment_times", ",".join(str(t) for t in segment_times)]
        if segment_times
        else ["-segment_time", str(chunk_seconds)]
    )
    run_ffmpeg([
        "-y",
        "-i", str(wav_path),
        "-f", "segment",
        *split_args,
        "-segment_format", "wav",
        "-reset_timestamps", "1",
        "-c", "copy",
        str(pattern),
    ])
    return sorted(out_dir.glob("part_*.wav"))


def cleanup_temp(temp_dir: Path, max_age_hours: float) -> None:
    """
    Delete scratch files/folders older than `max_age_hours`.

    Keeps recent items so an interrupted long job can still resume. Never
    touches `.gitkeep`. Best-effort: ignores files in use or permission issues.
    """
    import time

    cutoff = time.time() - max_age_hours * 3600
    for item in temp_dir.iterdir():
        if item.name == ".gitkeep":
            continue
        try:
            if item.stat().st_mtime < cutoff:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
        except OSError:
            pass


def concat_audios(parts: list[Path], out_path: Path, temp_dir: Path) -> Path:
    """
    Join WAV chunks back into one file using FFmpeg's concat demuxer.

    The chunks share the same format, so this is a fast stream copy.
    """
    list_file = temp_dir / f"concat_{timestamp()}.txt"
    # The concat demuxer wants `file '<path>'`; forward slashes are safe on all
    # platforms and avoid backslash-escaping headaches on Windows.
    lines = [f"file '{Path(p).resolve().as_posix()}'" for p in parts]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    try:
        run_ffmpeg([
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ])
    finally:
        list_file.unlink(missing_ok=True)
    return out_path


def rebuild_video(original_video: Path, cleaned_audio: Path, out_path: Path) -> Path:
    """
    Mux the original (untouched) video stream with the cleaned audio.

    ffmpeg -y -i input.mp4 -i cleaned.wav -map 0:v:0 -map 1:a:0 \
           -c:v copy -c:a aac -shortest output.mp4

    The video is copied (no re-encode) so this step is fast and lossless.
    """
    run_ffmpeg([
        "-y",
        "-i", str(original_video),
        "-i", str(cleaned_audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ])
    return out_path
