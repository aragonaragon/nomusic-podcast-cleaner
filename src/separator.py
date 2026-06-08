"""
Source separation wrapper.

Strategy:
  1. Prefer `python-audio-separator` (PyPI package name: `audio-separator`).
     It auto-downloads UVR / MDX-Net / Demucs models and exposes a simple API.
  2. If that package is unavailable, fall back to running Demucs via the CLI
     (`python -m demucs ...`) if it is installed.
  3. If neither is available, raise a clear, actionable error.

In every case the public function `separate_vocals()` returns the path to a
single WAV file containing the isolated speech/vocals stem, copied to
`<temp>/cleaned_speech.wav`.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from . import config


class SeparationError(RuntimeError):
    """Raised when no separation backend is available or separation fails."""


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _pick_vocals_file(candidates: list[Path]) -> Path | None:
    """From a list of stem files, return the one that looks like vocals/speech."""
    for p in candidates:
        name = p.name.lower()
        if "vocal" in name or "speech" in name:
            return p
    return None


def _pick_instrumental_file(candidates: list[Path]) -> Path | None:
    """From a list of stem files, return the music/instrumental one (if any)."""
    for p in candidates:
        name = p.name.lower()
        if "instrument" in name or "no_vocals" in name or "music" in name:
            return p
    return None


# --- Backend 1: python-audio-separator ---------------------------------------
def _separate_with_audio_separator(
    input_wav: Path,
    model_filename: str,
    temp_dir: Path,
    log,
) -> tuple[Path, Path | None]:
    from audio_separator.separator import Separator  # imported lazily

    work_dir = temp_dir / "separation"
    work_dir.mkdir(parents=True, exist_ok=True)

    separator = Separator(output_dir=str(work_dir), output_format="WAV")

    # Try the mode's preferred model; fall back to the library default if that
    # specific model can't be loaded (e.g. name changed or download failed).
    try:
        log(f"Loading separation model: {model_filename}")
        separator.load_model(model_filename=model_filename)
    except Exception as exc:  # noqa: BLE001 - we want any failure to fall back
        log(f"Could not load '{model_filename}' ({exc}). Falling back to default model.")
        separator.load_model()

    log("Separating speech from music… (first run downloads the model)")
    output_files = separator.separate(str(input_wav))

    # Returned names may be relative to the output dir — resolve both ways.
    produced: list[Path] = []
    for f in output_files:
        p = Path(f)
        produced.append(p if p.is_absolute() else work_dir / p)

    vocals = _pick_vocals_file(produced)
    if vocals is None or not vocals.exists():
        raise SeparationError(
            "Separation finished but no vocals stem could be identified. "
            f"Produced files: {[p.name for p in produced]}"
        )
    instrumental = _pick_instrumental_file(produced)
    return vocals, instrumental


# --- Backend 2: Demucs CLI ---------------------------------------------------
def _separate_with_demucs_cli(input_wav: Path, temp_dir: Path, log) -> tuple[Path, Path | None]:
    work_dir = temp_dir / "demucs"
    work_dir.mkdir(parents=True, exist_ok=True)

    log("Running Demucs (this can be slow on CPU)…")
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",   # only vocals vs. the rest
        "-o", str(work_dir),
        str(input_wav),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise SeparationError(f"Demucs failed:\n{tail}")

    # Demucs writes: <work_dir>/<model>/<track>/vocals.wav (and no_vocals.wav)
    matches = list(work_dir.rglob("vocals.wav"))
    if not matches:
        raise SeparationError("Demucs ran but no vocals.wav was produced.")
    vocals = matches[0]
    instrumental = vocals.with_name("no_vocals.wav")
    return vocals, (instrumental if instrumental.exists() else None)


# --- Public API --------------------------------------------------------------
def separate_vocals(
    input_wav: Path,
    mode: str,
    temp_dir: Path,
    log=print,
    out_name: str = config.CLEANED_BASENAME,
) -> tuple[Path, Path | None]:
    """
    Isolate the speech/vocals stem from `input_wav`.

    Args:
        input_wav:  working WAV file (speech + music).
        mode:       one of config.SEPARATION_MODES keys.
        temp_dir:   scratch directory.
        log:        callable used to report progress (defaults to print).
        out_name:   base name for the copied result (lets callers keep many
                    chunk results side by side without collisions).

    Returns:
        (speech_wav, music_wav_or_None) — speech is copied to
        `<temp_dir>/<out_name>.wav`; the music stem (if the backend produced
        one) is copied to `<temp_dir>/<out_name>_music.wav` for later checks.
    """
    model_filename = config.SEPARATION_MODES.get(mode, config.SEPARATION_MODES[config.DEFAULT_MODE])

    if _has_module("audio_separator"):
        vocals, instrumental = _separate_with_audio_separator(input_wav, model_filename, temp_dir, log)
    elif shutil.which("demucs") or _has_module("demucs"):
        vocals, instrumental = _separate_with_demucs_cli(input_wav, temp_dir, log)
    else:
        raise SeparationError(
            "No source-separation backend is installed.\n\n"
            "Install the recommended one with:\n"
            "    pip install \"audio-separator[cpu]\"\n\n"
            "or, for GPU (CUDA):\n"
            "    pip install \"audio-separator[gpu]\"\n\n"
            "Alternatively install Demucs:\n"
            "    pip install demucs"
        )

    # Normalize the result location/name regardless of backend.
    cleaned = temp_dir / f"{out_name}.wav"
    if cleaned.exists():
        cleaned.unlink()
    shutil.copy2(vocals, cleaned)

    music_copy: Path | None = None
    if instrumental is not None and Path(instrumental).exists():
        music_copy = temp_dir / f"{out_name}_music.wav"
        if music_copy.exists():
            music_copy.unlink()
        shutil.copy2(instrumental, music_copy)

    log("Speech stem ready.")
    return cleaned, music_copy
