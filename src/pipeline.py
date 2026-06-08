"""
High-level cleaning pipeline.

This is where long-file handling lives. The goal is for it to "just work" on
mid-range machines (no GPU, ~8 GB RAM):

  * Everything is converted to MONO (see config.CHANNELS) to halve memory/time.
  * Files longer than config.LONG_FILE_THRESHOLD_SECONDS are processed in
    chunks so memory stays bounded no matter how long the file is.
  * Per-chunk results are cached in a job folder, so if a long run crashes or
    is restarted, already-finished chunks are skipped (basic resume).
  * On success the job folder is cleaned up; only the final outputs remain.

The caller (app.py) just receives the finished speech stem and an optional
music stem (used for the heavy-music warning).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import config
from .media_utils import (
    compute_silence_cut_points,
    concat_audios,
    get_duration,
    split_audio,
    timestamp,
    to_working_wav,
)
from .separator import separate_vocals


class Cancelled(Exception):
    """Raised when the user stops a job in progress."""


@dataclass
class CleanResult:
    speech_wav: Path
    music_wav: Path | None
    duration: float | None
    chunked: bool


def _noop_progress(fraction: float, desc: str = "") -> None:  # default callback
    pass


def _never_cancel() -> bool:
    return False


def _job_key(input_path: Path, mode: str) -> str:
    """Stable folder name for resume, tied to the file, its size, and the mode."""
    size = input_path.stat().st_size
    safe = "".join(c for c in input_path.stem if c.isalnum() or c in "-_")[:40] or "job"
    return f"{safe}_{size}_{mode}"


def _cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def clean_file(
    input_path: Path,
    mode: str,
    preview: bool,
    log=print,
    progress=_noop_progress,
    should_cancel=_never_cancel,
) -> CleanResult:
    """
    Produce a cleaned (music-removed) mono speech WAV from an audio/video file.

    Returns a CleanResult with the speech stem and (when available) the music
    stem for the heavy-music check. `should_cancel` is checked between chunks;
    if it returns True, a Cancelled exception is raised.
    """
    temp = config.TEMP_DIR

    # --- Preview: small, fast, no caching -----------------------------------
    if preview:
        progress(0.05, "Preparing audio")
        log(f"Quick test — first {config.PREVIEW_SECONDS}s only.")
        work = to_working_wav(input_path, temp / f"preview_{timestamp()}.wav", config.PREVIEW_SECONDS)
        progress(0.25, "Removing music")
        speech, music = separate_vocals(work, mode, temp, log=log, out_name=config.CLEANED_BASENAME)
        progress(1.0, "Done")
        return CleanResult(speech, music, duration=None, chunked=False)

    # --- Full run: resume-friendly job folder -------------------------------
    job_dir = temp / "jobs" / _job_key(input_path, mode)
    job_dir.mkdir(parents=True, exist_ok=True)

    source = job_dir / "source.wav"
    if source.exists():
        log("Reusing prepared audio from a previous run.")
    else:
        progress(0.03, "Preparing audio")
        log("Preparing audio (converting to mono)…")
        to_working_wav(input_path, source)

    duration = get_duration(source)
    needs_chunk = duration is not None and duration > config.LONG_FILE_THRESHOLD_SECONDS

    final_speech = temp / f"{config.CLEANED_BASENAME}.wav"
    final_music = temp / f"{config.CLEANED_BASENAME}_music.wav"

    # --- Short file: single pass --------------------------------------------
    if not needs_chunk:
        progress(0.2, "Removing music")
        speech, music = separate_vocals(source, mode, job_dir, log=log, out_name="speech_full")
        shutil.copy2(speech, final_speech)
        out_music = None
        if music is not None and Path(music).exists():
            shutil.copy2(music, final_music)
            out_music = final_music
        _cleanup(job_dir)
        progress(1.0, "Done")
        return CleanResult(final_speech, out_music, duration=duration, chunked=False)

    # --- Long file: split → process each chunk → stitch ---------------------
    minutes = duration / 60 if duration else 0
    chunk_min = config.CHUNK_SECONDS // 60
    log(f"Long file (~{minutes:.0f} min). Processing in {chunk_min}-minute chunks to stay light on memory.")

    chunks_dir = job_dir / "chunks"
    chunk_files = sorted(chunks_dir.glob("part_*.wav")) if chunks_dir.exists() else []
    if not chunk_files:
        progress(0.06, "Splitting into chunks")
        # Cut at quiet moments near each boundary so seams aren't audible.
        cut_times = compute_silence_cut_points(source, config.CHUNK_SECONDS)
        if cut_times:
            log("Splitting at quiet moments to keep seams seamless.")
        chunk_files = split_audio(source, config.CHUNK_SECONDS, chunks_dir, segment_times=cut_times or None)
    n = len(chunk_files)
    log(f"{n} chunks total.")

    voc_dir = job_dir / "vocals"
    mus_dir = job_dir / "music"
    voc_dir.mkdir(exist_ok=True)
    mus_dir.mkdir(exist_ok=True)

    voc_parts: list[Path] = []
    mus_parts: list[Path] = []

    for i, chunk in enumerate(chunk_files):
        if should_cancel():
            raise Cancelled()

        name = f"chunk_{i:03d}"
        voc_path = voc_dir / f"{name}.wav"
        mus_path = mus_dir / f"{name}.wav"
        frac = 0.10 + 0.80 * (i / max(n, 1))

        if voc_path.exists():
            log(f"Chunk {i + 1}/{n}: already done — skipping.")
        else:
            progress(frac, f"Removing music — chunk {i + 1} of {n}")
            log(f"Chunk {i + 1}/{n}: removing music…")
            # Quiet inner logging to avoid flooding; separate_vocals writes
            # the result straight into voc_dir as <name>.wav.
            _, music = separate_vocals(chunk, mode, voc_dir, log=lambda *_: None, out_name=name)
            if music is not None and Path(music).exists():
                shutil.copy2(music, mus_path)
            # Tidy the per-chunk music copy separate_vocals left in voc_dir.
            (voc_dir / f"{name}_music.wav").unlink(missing_ok=True)

        voc_parts.append(voc_path)
        if mus_path.exists():
            mus_parts.append(mus_path)

    progress(0.92, "Stitching chunks back together")
    log("Joining cleaned chunks into one file…")
    concat_audios(voc_parts, final_speech, temp)

    out_music = None
    if len(mus_parts) == n:  # only meaningful if every chunk produced music
        concat_audios(mus_parts, final_music, temp)
        out_music = final_music

    _cleanup(job_dir)
    progress(1.0, "Done")
    return CleanResult(final_speech, out_music, duration=duration, chunked=True)
