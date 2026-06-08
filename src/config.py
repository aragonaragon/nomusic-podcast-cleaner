"""
Central configuration for NoMusic Podcast Cleaner.

Keeping all paths, constants and "magic numbers" here makes the rest of the
code easy to read and tweak.
"""

from pathlib import Path

# --- Project paths -----------------------------------------------------------
# config.py lives in:  <project>/src/config.py
# so the project root is two levels up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
TEMP_DIR = PROJECT_ROOT / "temp"

# Create the working folders on import so the app never crashes because a
# directory is missing.
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# --- Supported input formats -------------------------------------------------
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}

# --- Audio settings ----------------------------------------------------------
SAMPLE_RATE = 44100
# Process and export in MONO. Speech doesn't need stereo, and mono roughly
# halves both memory use and separation time — a big win on mid-range machines.
CHANNELS = 1

# EBU R128 loudness normalization targets (gentle, broadcast-friendly).
LOUDNORM_I = -16.0    # integrated loudness (LUFS)
LOUDNORM_TP = -1.5    # true peak (dBTP)
LOUDNORM_LRA = 11.0   # loudness range

# --- Strength settings -------------------------------------------------------
# Each strength maps to a source-separation model. Names are the model filenames
# understood by `python-audio-separator`, which downloads them automatically
# on first use.
#
# Trade-off: Demucs (htdemucs_ft) is the cleanest but slowest; MDX-Net models
# are much faster and good enough for speech.
SEPARATION_MODES = {
    "Fast": "Kim_Vocal_2.onnx",             # quick MDX pass — good for previews
    "Balanced": "UVR-MDX-NET-Voc_FT.onnx",  # solid vocals, reasonable speed
    "Strong": "htdemucs_ft.yaml",           # Demucs fine-tuned, slowest/cleanest
}

# Short plain-language hint shown next to each strength in the UI.
MODE_HINTS = {
    "Fast": "Quickest. Good enough for a quick check.",
    "Balanced": "Recommended. Good quality, reasonable speed.",
    "Strong": "Best music removal. Slowest.",
}

DEFAULT_MODE = "Balanced"

# Final cleaned-audio base name (extensions added later).
CLEANED_BASENAME = "cleaned_speech"

# --- Preview mode ------------------------------------------------------------
# Length (seconds) used when the user enables the quick test.
PREVIEW_SECONDS = 30

# --- Heavy-music warning -----------------------------------------------------
# Rough heuristic: after separation we compare how loud the music part is
# versus the speech part. If the speech isn't at least this many dB louder than
# the leftover music, we warn that the source had a lot of music mixed in and
# the result may still contain some.
MUSIC_HEAVY_DB_GAP = 6.0

# --- Long-file handling (chunking) -------------------------------------------
# Files longer than this are processed in chunks so memory stays bounded on
# mid-range machines (no GPU, ~8 GB RAM). Shorter files run in a single pass.
LONG_FILE_THRESHOLD_SECONDS = 12 * 60   # 12 minutes
CHUNK_SECONDS = 10 * 60                  # target chunk length (10 minutes)

# Files longer than this trigger a gentle "this will take a while" note.
SLOW_WARNING_SECONDS = 20 * 60          # 20 minutes

# Silence-aware splitting: instead of cutting at an exact 10:00 mark (which can
# leave a faint click at the seam), we look for a quiet moment near the target
# and cut there. Keeps total length identical, so audio/video stay in sync.
SILENCE_NOISE_DB = -30          # below this level counts as "quiet"
SILENCE_MIN_DURATION = 0.30     # seconds of quiet needed to qualify as a gap
SILENCE_SEARCH_WINDOW = 60      # look this many seconds around the target cut

# --- Optional light noise reduction ------------------------------------------
# Gentle FFT denoise applied to the cleaned speech when the user enables it.
# Kept light on purpose so voices don't sound robotic.
DENOISE_AMOUNT = 12             # afftdn noise reduction in dB (gentle)

# --- Housekeeping ------------------------------------------------------------
# On startup, leftover scratch files older than this are deleted automatically.
TEMP_MAX_AGE_HOURS = 24
