# 🎙️ NoMusic Podcast Cleaner

**🌐 [العربية](README.md) · English**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Local only](https://img.shields.io/badge/Privacy-100%25%20local%20%C2%B7%20no%20upload-brightgreen)

Remove or reduce background music from podcasts, interviews, lectures, and
talking videos — while keeping the **speech as clear as possible**.

Everything runs **locally** on your machine. No login, no account, no cloud
upload. Your files never leave your computer.

> **Easiest start (Windows):** double-click `Run NoMusic.bat` — it sets
> everything up on first run and opens in your browser.

---

## What it does

1. You drop in a **video** or **audio** file.
2. It detects the type automatically.
3. It separates the **speech/vocals** from the music using an AI source-separation
   model.
4. It lightly normalizes loudness so the result is comfortable to listen to.
5. It exports:
   - A **cleaned speech-only** file as **MP3 and WAV**.
   - If the input was a video, a new **MP4** with the original picture and the
     cleaned audio.

Output files are saved to the `outputs/` folder.

## What it can **not** guarantee

- It is **not** perfect music removal. AI separation reduces music and often
  removes it well, but faint artifacts or residual music can remain — especially
  when music and speech overlap heavily.
- Singing, heavy sound effects, or speech buried under loud music are the hardest
  cases.
- This V1 favors **speech clarity over extreme music removal**. It does not apply
  aggressive noise reduction (that tends to make voices sound robotic).
- Quality depends on the chosen mode and the source recording.

---

## Requirements

- **Python 3.11+**
- **FFmpeg** installed and available on your `PATH` (used to extract and rebuild
  audio/video). FFmpeg is **not** a pip package.

### Installing FFmpeg

- **Windows:** download from <https://www.gyan.dev/ffmpeg/builds/> (or
  `winget install Gyan.FFmpeg`), then ensure `ffmpeg` works in a new terminal.
- **macOS:** `brew install ffmpeg`
- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`

Verify with:

```bash
ffmpeg -version
```

---

## Installation

```bash
cd nomusic-podcast-cleaner

# (recommended) create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

> **GPU users:** the requirements install the CPU build of the separator.
> For an NVIDIA GPU, install the GPU extra instead for a big speed-up:
> `pip install "audio-separator[gpu]"`

---

## How to run

### Easiest: one click (Windows)

Just **double-click `Run NoMusic.bat`**.

- The **first run** sets up a local environment and installs everything
  automatically (this takes a few minutes — only happens once).
- Every run after that starts in seconds and **opens your browser
  automatically**.
- It even finds FFmpeg installed via `winget` without needing a restart.
- Keep the black window open while you use the app; close it to stop.

> Tip: right-click `Run NoMusic.bat` → **Send to → Desktop (create shortcut)** to
> launch it from your desktop.

### Manual (any OS)

```bash
python app.py
```

Gradio prints a local URL (usually `http://127.0.0.1:7860`) and opens it in your
browser.

1. Drop in **one or more** files (or click to browse). Multiple files are
   processed one after another (batch).
2. Pick a **Strength**.
3. (Optional) tick **Quick test** to process only the first 30 seconds — handy
   for trying a long file before committing to the whole thing.
4. (Optional) leave **Even out the volume** on for a comfortable, consistent
   listening level.
5. (Optional) tick **Reduce background noise (light)** to gently clean up
   residual hiss.
6. Click **Start cleaning**. Use **Stop** to halt a long job — it finishes the
   current chunk/file, then stops (anything already done is kept).
7. Watch the **Status** line and progress bar; open the **Logs** panel for
   detail. Download results from **Cleaned files** — they're also saved in
   `outputs/`.

If a file has a lot of music mixed into the speech, you'll see a friendly
**warning** that some music may remain (with a suggestion to try **Strong**).

### Strength

| Strength     | Backend model        | Speed      | Best for |
|--------------|----------------------|------------|----------|
| **Fast**     | Kim_Vocal_2 (MDX)    | Fastest    | Quick checks / previews |
| **Balanced** | UVR-MDX-NET-Voc_FT   | Medium     | Recommended everyday use |
| **Strong**   | Demucs (htdemucs_ft) | Slowest    | Tough music, best quality |

> The first time you use a strength, the model is **downloaded automatically**
> (a few hundred MB). Later runs reuse the cached model.

---

## Supported formats

- **Video:** `.mp4 .mov .mkv .avi .webm .m4v .flv`
- **Audio:** `.mp3 .wav .m4a .aac .flac .ogg .opus .wma`

Output: cleaned audio as **MP3 + WAV**, cleaned video as **MP4**.

---

## Long files & mid-range machines

This tool is built to run on **ordinary laptops** (no GPU, ~8 GB RAM), even for
long recordings:

- **Mono processing** — audio is converted to a single channel before
  separation. Speech doesn't need stereo, and this roughly **halves memory use
  and processing time**. Output is mono.
- **Automatic chunking** — files longer than ~12 minutes are split into
  ~10-minute pieces, cleaned one at a time, then stitched back together. Memory
  stays bounded no matter how long the file is (a 2-hour podcast works the same
  as a 5-minute one).
- **Crash-safe resume** — finished chunks are cached during a run. If a long job
  is interrupted, restarting it **skips the chunks already done** instead of
  starting over. On success the cache is cleaned up automatically.
- **Quick test** — tick it to process only the first 30 seconds, so you can
  sanity-check a 2-hour file in seconds before committing.
- **Seamless seams** — chunk boundaries are placed on quiet moments (silence
  detection), so joins aren't audible and total length is preserved (audio/video
  stay in sync).
- **Auto-cleanup** — leftover scratch files older than a day are removed on
  startup, so the `temp/` folder never grows out of control.

## Performance notes (GPU/CPU)

- On **CPU**, separation is the slow part — expect roughly **0.5×–3× the audio
  length** depending on strength and machine (Fast is quickest, Strong/Demucs is
  slowest). A 2-hour file can take a while — start it and walk away.
- On a supported **NVIDIA GPU** (install `audio-separator[gpu]`), separation is
  several times faster.
- FFmpeg steps (extract / split / stitch / rebuild) are fast; rebuilding video
  **copies** the original video stream, so there is no quality loss.

---

## Project structure

```
nomusic-podcast-cleaner/
  app.py                 # Gradio UI + pipeline orchestration
  requirements.txt
  README.md
  src/
    config.py            # paths, constants, mode → model map, chunk settings
    media_utils.py       # file-type detection + all FFmpeg calls (split/concat/probe)
    pipeline.py          # orchestration: mono prep, chunking, resume, stitching
    separator.py         # speech/vocals isolation (audio-separator / Demucs)
    audio_postprocess.py # loudness normalization + MP3/WAV export + music check
  outputs/               # results land here
  temp/                  # scratch files (safe to delete)
```

---

## Troubleshooting

- **"FFmpeg was not found"** — install FFmpeg and reopen your terminal.
- **"No source-separation backend is installed"** — run
  `pip install "audio-separator[cpu]"`.
- **First run is slow / seems stuck** — it's downloading the model. Subsequent
  runs are much faster.
- **Out of memory** — try **Fast draft** mode, or close other apps.
