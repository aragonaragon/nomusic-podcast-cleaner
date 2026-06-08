"""
Light post-processing of the isolated speech stem.

V1 keeps this intentionally gentle: just EBU R128 loudness normalization via
FFmpeg's `loudnorm` filter so the output is comfortable to listen to. We avoid
aggressive noise reduction on purpose — preserving speech clarity matters more
than squeezing out every last bit of music.

Exports the cleaned speech as both WAV and MP3.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .media_utils import measure_mean_volume, run_ffmpeg


def _loudnorm_filter() -> str:
    return (
        f"loudnorm=I={config.LOUDNORM_I}"
        f":TP={config.LOUDNORM_TP}"
        f":LRA={config.LOUDNORM_LRA}"
    )


def _build_filter_chain(normalize: bool, denoise: bool) -> list[str]:
    """
    Assemble the -af argument from the enabled steps (order matters: denoise
    first, then loudness). Returns [] when nothing is enabled.
    """
    steps: list[str] = []
    if denoise:
        # Gentle FFT denoiser; light setting preserves speech naturalness.
        steps.append(f"afftdn=nr={config.DENOISE_AMOUNT}")
    if normalize:
        steps.append(_loudnorm_filter())
    return ["-af", ",".join(steps)] if steps else []


def export_wav(input_wav: Path, out_path: Path, normalize: bool = True, denoise: bool = False) -> Path:
    """Write a WAV file, optionally denoising and/or evening out the volume."""
    run_ffmpeg([
        "-y",
        "-i", str(input_wav),
        *_build_filter_chain(normalize, denoise),
        "-ar", str(config.SAMPLE_RATE),
        "-ac", str(config.CHANNELS),
        str(out_path),
    ])
    return out_path


def export_mp3(input_wav: Path, out_path: Path, normalize: bool = True, denoise: bool = False) -> Path:
    """Write an MP3 file (LAME, ~190 kbps VBR), optionally denoising/normalizing."""
    run_ffmpeg([
        "-y",
        "-i", str(input_wav),
        *_build_filter_chain(normalize, denoise),
        "-ar", str(config.SAMPLE_RATE),
        "-ac", str(config.CHANNELS),
        "-codec:a", "libmp3lame",
        "-q:a", "2",
        str(out_path),
    ])
    return out_path


def export_cleaned_audio(
    speech_wav: Path,
    out_dir: Path,
    base_name: str,
    normalize: bool = True,
    denoise: bool = False,
) -> tuple[Path, Path]:
    """
    Produce both formats from the cleaned speech stem.

    Returns (wav_path, mp3_path).
    """
    wav_path = out_dir / f"{base_name}.wav"
    mp3_path = out_dir / f"{base_name}.mp3"
    export_wav(speech_wav, wav_path, normalize=normalize, denoise=denoise)
    export_mp3(speech_wav, mp3_path, normalize=normalize, denoise=denoise)
    return wav_path, mp3_path


def assess_music_residue(speech_wav: Path, music_wav: Path | None) -> str | None:
    """
    Rough check of how much music was mixed into the speech.

    Compares the loudness of the separated speech vs. the leftover music. If the
    speech isn't clearly louder than the music, the source was music-heavy and
    the result may still contain some — so we return a plain-language warning.
    Returns None when there's nothing to flag (or it can't be measured).
    """
    if music_wav is None or not Path(music_wav).exists():
        return None

    speech_db = measure_mean_volume(speech_wav)
    music_db = measure_mean_volume(music_wav)
    if speech_db is None or music_db is None:
        return None

    gap = speech_db - music_db  # how much louder speech is than the music
    if gap < config.MUSIC_HEAVY_DB_GAP:
        return (
            "Heads up: this file has a lot of music mixed into the speech, so "
            "some music may still be audible in the result. Try the 'Strong' "
            "setting for a cleaner cut."
        )
    return None
