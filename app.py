"""
NoMusic Podcast Cleaner — Gradio MVP.

Run with:
    python app.py

Everything is processed locally. No login, no cloud, no uploads.
Designed to work on ordinary (mid-range) machines: audio is processed in mono
and long files are handled in chunks so memory stays bounded.
"""

from __future__ import annotations

import threading
from pathlib import Path

import gradio as gr

from src import config
from src.media_utils import (
    FFmpegError,
    check_setup,
    cleanup_temp,
    find_ffmpeg,
    get_duration,
    get_media_type,
    rebuild_video,
    timestamp,
)
from src.pipeline import Cancelled, clean_file
from src.separator import SeparationError
from src.audio_postprocess import assess_music_residue, export_cleaned_audio


APP_TITLE = "NoMusic Podcast Cleaner"
APP_DESCRIPTION = (
    "Remove or reduce background music from podcasts, interviews, and talking "
    "videos while keeping speech as clear as possible."
)

# Shared stop flag. The Stop button sets it; the pipeline checks it between
# chunks and between files, then halts at the next safe point.
_cancel_event = threading.Event()


def _request_stop():
    _cancel_event.set()
    return "Stopping… will halt at the next safe point."


def _as_path_list(files) -> list[Path]:
    """Normalize the gr.File value (None / str / list) into a list of Paths."""
    if files is None:
        return []
    if isinstance(files, (str, Path)):
        return [Path(files)]
    return [Path(f) for f in files]


def process(files, mode, preview, normalize, denoise, export_audio, export_video,
            progress=gr.Progress()):
    """
    Main pipeline. A generator so the UI updates live; handles one or many files.

    Yields tuples matching the output components:
        (status, warning, logs, downloads, audio_preview, video_preview)
    """
    _cancel_event.clear()

    no_audio = gr.update(value=None, visible=False)
    no_video = gr.update(value=None, visible=False)
    no_warning = gr.update(value="", visible=False)
    no_files = gr.update(value=None, visible=False)

    log_lines: list[str] = []
    outputs: list[str] = []          # all produced file paths (for the downloads list)
    warnings: list[str] = []         # per-file heavy-music notes

    def log(msg: str):
        log_lines.append(str(msg))

    def files_update():
        return gr.update(value=outputs, visible=True) if outputs else no_files

    def warn_update():
        if not warnings:
            return no_warning
        body = "\n".join(f"- {w}" for w in warnings)
        return gr.update(value=f"⚠️ **Heads up**\n{body}", visible=True)

    def emit(status, *, audio=no_audio, video=no_video):
        return status, warn_update(), "\n".join(log_lines), files_update(), audio, video

    # --- Validate inputs -----------------------------------------------------
    paths = _as_path_list(files)
    if not paths:
        yield emit("Please select one or more files first.")
        return

    valid: list[tuple[Path, str]] = []
    for p in paths:
        if not p.exists():
            log(f"Skipped (not found): {p.name}")
            continue
        mt = get_media_type(p)
        if mt is None:
            log(f"Skipped (unsupported type '{p.suffix}'): {p.name}")
            continue
        valid.append((p, mt))

    if not valid:
        yield emit("No supported files to process — see logs.")
        return

    if not export_audio and not export_video:
        yield emit("Nothing to export — pick at least one output option.")
        return

    n_files = len(valid)
    if n_files > 1:
        log(f"Batch: {n_files} files queued.")

    try:
        find_ffmpeg()  # fail early with a friendly message if FFmpeg is missing

        for idx, (input_path, media_type) in enumerate(valid):
            if _cancel_event.is_set():
                raise Cancelled()

            prefix = f"[{idx + 1}/{n_files}] " if n_files > 1 else ""
            log(f"\n{prefix}{input_path.name}")
            yield emit(f"Working… {prefix}{input_path.name}")

            # Long-file heads-up (full runs only).
            if not preview:
                dur = get_duration(input_path)
                if dur and dur > config.SLOW_WARNING_SECONDS:
                    log(f"  ~{dur / 60:.0f} min long — this will take a while.")

            # Per-file progress mapped into the overall bar.
            def report(frac, desc="", _i=idx):
                progress((_i + frac) / n_files, desc=f"{prefix}{desc}")

            result = clean_file(
                input_path, mode, preview,
                log=log, progress=report, should_cancel=_cancel_event.is_set,
            )

            # Heavy-music check.
            residue_msg = assess_music_residue(result.speech_wav, result.music_wav)
            if residue_msg:
                warnings.append(f"**{input_path.name}** — {residue_msg}")
                log("  " + residue_msg)

            # Export audio.
            run_id = timestamp()
            suffix = "_preview" if preview else ""
            base_name = f"{input_path.stem}_nomusic{suffix}_{run_id}"
            log(f"  Exporting (normalize={'on' if normalize else 'off'}, "
                f"denoise={'on' if denoise else 'off'})…")
            yield emit(f"Working… exporting {prefix}".strip())
            wav_out, mp3_out = export_cleaned_audio(
                result.speech_wav, config.OUTPUTS_DIR, base_name,
                normalize=normalize, denoise=denoise,
            )

            this_audio = no_audio
            if export_audio:
                outputs.extend([str(mp3_out), str(wav_out)])
                this_audio = gr.update(value=str(mp3_out), visible=(n_files == 1))
            log(f"  Saved: {mp3_out.name}, {wav_out.name}")

            # Rebuild video if requested and applicable.
            this_video = no_video
            if media_type == "video" and export_video:
                log("  Rebuilding video…")
                yield emit(f"Working… rebuilding video {prefix}".strip(), audio=this_audio)
                video_out = config.OUTPUTS_DIR / f"{base_name}.mp4"
                rebuild_video(input_path, wav_out, video_out)
                outputs.append(str(video_out))
                this_video = gr.update(value=str(video_out), visible=(n_files == 1))
                log(f"  Saved: {video_out.name}")

            yield emit(f"Working… {prefix}done", audio=this_audio, video=this_video)

        progress(1.0, desc="Done")
        log(f"\nDone! Files are in: {config.OUTPUTS_DIR}")
        done = f"Done ✅  {len(outputs)} file(s) saved."
        if preview:
            done += " (preview only — uncheck Quick test for the full file)"
        # Show preview for single-file runs.
        last_audio = no_audio
        last_video = no_video
        if n_files == 1 and outputs:
            last_audio = gr.update(value=outputs[0], visible=True)
            if any(o.endswith(".mp4") for o in outputs):
                last_video = gr.update(value=next(o for o in outputs if o.endswith(".mp4")), visible=True)
        yield emit(done, audio=last_audio, video=last_video)

    except Cancelled:
        log("\nStopped by user.")
        msg = f"Stopped ⏹  {len(outputs)} file(s) finished before stopping."
        yield emit(msg)
    except (FFmpegError, SeparationError) as exc:
        log(f"\nERROR: {exc}")
        yield emit("Something went wrong — see logs below.")
    except Exception as exc:  # noqa: BLE001 - never crash the UI
        log(f"\nUnexpected error: {exc}")
        yield emit("Something went wrong — see logs below.")


THEME = gr.themes.Soft(
    primary_hue="violet",
    secondary_hue="purple",
    neutral_hue="slate",
    radius_size="lg",
)

CUSTOM_CSS = """
.gradio-container {max-width: 1060px !important; margin: 0 auto !important;}
#hero {text-align: center; padding: 30px 22px; border-radius: 20px; color: #fff;
  background: linear-gradient(135deg, #7c3aed 0%, #9333ea 45%, #c026d3 100%);
  box-shadow: 0 12px 32px rgba(147, 51, 234, .28); margin-bottom: 20px;}
#hero .emoji {font-size: 2.6rem; line-height: 1;}
#hero h1 {color: #fff !important; font-size: 2rem; margin: .25em 0 .15em; font-weight: 800;}
#hero p {color: rgba(255, 255, 255, .92); max-width: 640px; margin: 0 auto; font-size: 1.02rem;}
#hero .pills {margin-top: 14px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;}
#hero .pill {background: rgba(255, 255, 255, .18); color: #fff; padding: 4px 12px;
  border-radius: 999px; font-size: .82rem; font-weight: 600;}
.card {border-radius: 18px !important; box-shadow: 0 4px 18px rgba(2, 6, 23, .06);
  border: 1px solid rgba(2, 6, 23, .07); padding: 16px 18px !important;}
.card-title {font-weight: 700; font-size: 1.05rem; margin: 0 0 12px;}
#start-btn {font-weight: 800;}
#footer {text-align: center; opacity: .7; font-size: .9rem; margin-top: 16px;}
.setup-warn {border-left: 4px solid #f59e0b; background: #fff7ed;
  padding: 12px 16px; border-radius: 12px; color: #7c2d12;}
"""

HERO_HTML = """
<div id="hero">
  <div class="emoji">🎙️</div>
  <h1>NoMusic Podcast Cleaner</h1>
  <p>Remove background music from podcasts, interviews, and talking videos —
     and keep the speech crystal clear.</p>
  <div class="pills">
    <span class="pill">🔒 100% local</span>
    <span class="pill">🚫 No upload</span>
    <span class="pill">🎬 Audio + video</span>
    <span class="pill">🆓 Free &amp; open source</span>
  </div>
</div>
"""


def build_ui() -> gr.Blocks:
    # Best-effort housekeeping so the temp folder doesn't grow forever.
    try:
        cleanup_temp(config.TEMP_DIR, config.TEMP_MAX_AGE_HOURS)
    except Exception:  # noqa: BLE001 - never block startup on cleanup
        pass

    ffmpeg_ok, ffmpeg_msg = check_setup()

    with gr.Blocks(title=APP_TITLE, theme=THEME, css=CUSTOM_CSS) as demo:
        gr.HTML(HERO_HTML)

        if not ffmpeg_ok:
            gr.Markdown(
                "### ⚠️ Setup needed\n\n"
                "```\n" + ffmpeg_msg + "\n```\n"
                "You can still open this page, but cleaning won't work until "
                "FFmpeg is installed and you restart the app.",
                elem_classes="setup-warn",
            )

        with gr.Row(equal_height=False):
            with gr.Column(scale=1):
                with gr.Group(elem_classes="card"):
                    gr.Markdown("### 1 · Add files & choose options", elem_classes="card-title")
                    file_input = gr.File(
                        label="🎬 Drop video or audio files here (one or many)",
                        file_count="multiple",
                        type="filepath",
                    )
                    mode = gr.Radio(
                        choices=list(config.SEPARATION_MODES.keys()),
                        value=config.DEFAULT_MODE,
                        label="Strength",
                        info=" · ".join(f"{k}: {v}" for k, v in config.MODE_HINTS.items()),
                    )
                    preview = gr.Checkbox(
                        value=False,
                        label=f"⚡ Quick test (only the first {config.PREVIEW_SECONDS} seconds)",
                        info="Great for trying a long file fast before committing.",
                    )
                    normalize = gr.Checkbox(value=True, label="🔊 Even out the volume (recommended)")
                    denoise = gr.Checkbox(value=False, label="✨ Reduce background noise (light)")
                    export_audio = gr.Checkbox(value=True, label="💾 Save cleaned audio (MP3 + WAV)")
                    export_video = gr.Checkbox(
                        value=True,
                        label="🎞️ Save cleaned video (only for video inputs)",
                    )
                    with gr.Row():
                        start_btn = gr.Button("✨ Start cleaning", variant="primary",
                                              scale=3, elem_id="start-btn")
                        stop_btn = gr.Button("⏹ Stop", scale=1)

            with gr.Column(scale=1):
                with gr.Group(elem_classes="card"):
                    gr.Markdown("### 2 · Results", elem_classes="card-title")
                    status = gr.Textbox(
                        label="Status", lines=1, interactive=False, placeholder="Ready.",
                    )
                    warning = gr.Markdown(visible=False)
                    downloads = gr.Files(label="⬇️ Cleaned files (download)", visible=False)
                    audio_out = gr.Audio(label="Preview — cleaned audio", visible=False)
                    video_out = gr.Video(label="Preview — cleaned video", visible=False)
                    with gr.Accordion("📋 Logs", open=False):
                        logs = gr.Textbox(
                            label=None, lines=12, interactive=False,
                            placeholder="Detailed step-by-step messages will appear here…",
                            show_copy_button=True,
                        )

        run_event = start_btn.click(
            fn=process,
            inputs=[file_input, mode, preview, normalize, denoise, export_audio, export_video],
            outputs=[status, warning, logs, downloads, audio_out, video_out],
        )
        # Stop sets the flag AND cancels the running event.
        stop_btn.click(fn=_request_stop, inputs=None, outputs=status, cancels=[run_event])

        gr.HTML(
            "<div id='footer'>All processing happens locally on your machine. "
            "Long files are handled in chunks. Output files are saved to the "
            "<code>outputs</code> folder.</div>"
        )

    return demo


if __name__ == "__main__":
    app = build_ui()
    # Bound to localhost; not shared publicly. Opens the browser automatically.
    app.launch(inbrowser=True)
