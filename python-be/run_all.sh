#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve script directory and move there so relative imports work.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Input / output configuration
# ---------------------------------------------------------------------------
SOURCE_VIDEO="${1:-$SCRIPT_DIR/../public/input/input.mp4}"
OUTPUT_DIR="$SCRIPT_DIR/outputs"
PUBLIC_ROOT="$SCRIPT_DIR/../public"
PUBLIC_INPUT="$PUBLIC_ROOT/input"
HIGHLIGHT_CATALOG="${HIGHLIGHT_CATALOG:-}"

AUTO_EDITOR_OUTPUT="$OUTPUT_DIR/stage1_cut.mp4"
WHISPER_SRT="$OUTPUT_DIR/stage1_cut.srt"
PLAN_TMP="$OUTPUT_DIR/plan.json"
PLAN_ENRICHED="$OUTPUT_DIR/plan_enriched.json"
SCENE_MAP="$OUTPUT_DIR/scene_map.json"
TRAINING_WINDOWS="$OUTPUT_DIR/training_windows.json"
HIGHLIGHT_SRT="${HIGHLIGHT_SRT:-$WHISPER_SRT}"

PYTHON=${PYTHON:-python}

if [[ -n "$HIGHLIGHT_CATALOG" && ! -f "$HIGHLIGHT_CATALOG" ]]; then
  HIGHLIGHT_CATALOG=""
fi
if [[ -n "$HIGHLIGHT_SRT" && ! -f "$HIGHLIGHT_SRT" ]]; then
  HIGHLIGHT_SRT=""
fi

if [[ ! -f "$SOURCE_VIDEO" ]]; then
  echo "[ERROR] Missing input video: $SOURCE_VIDEO" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR" "$PUBLIC_INPUT"

# ---------------------------------------------------------------------------
# Sync knowledge base (structured docs + embeddings)
# ---------------------------------------------------------------------------
echo "[STEP] Sync knowledge base assets"
$PYTHON data_processing/sync_knowledge_base.py

# ---------------------------------------------------------------------------
# Auto-Editor – remove silence
# ---------------------------------------------------------------------------
echo "[STEP] Auto-Editor => $AUTO_EDITOR_OUTPUT"
$PYTHON -m auto_editor "$SOURCE_VIDEO" -o "$AUTO_EDITOR_OUTPUT" \
  --edit audio:threshold=0.06 \
  --margin "0.75s,1s" \
  --silent-speed 4 \
  --video-speed 1 \
  --video-codec libx264 \
  --audio-codec aac \
  --quiet

# ---------------------------------------------------------------------------
# Whisper – generate transcript
# ---------------------------------------------------------------------------
echo "[STEP] Whisper => $WHISPER_SRT"
$PYTHON -m whisper "$AUTO_EDITOR_OUTPUT" \
  --model small \
  --language en \
  --task transcribe \
  --output_format srt \
  --output_dir "$OUTPUT_DIR"

if [[ ! -f "$WHISPER_SRT" ]]; then
  echo "[ERROR] Whisper did not produce $WHISPER_SRT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Upload transcript to Google Sheets
# ---------------------------------------------------------------------------
echo "[STEP] Upload transcript to Google Sheet"
if ! $PYTHON -m data_processing.upload_transcript "$WHISPER_SRT"; then
  echo "[ERROR] Transcript upload failed." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Derive scene map + training windows
# ---------------------------------------------------------------------------
echo "[STEP] Scene map => $SCENE_MAP"
$PYTHON -m data_processing.generate_scene_map "$WHISPER_SRT" -o "$SCENE_MAP"

echo "[STEP] Training windows => $TRAINING_WINDOWS"
$PYTHON -m data_processing.prepare_training_windows "$WHISPER_SRT" "$TRAINING_WINDOWS"

# ---------------------------------------------------------------------------
# Generate plan with Gemini (knowledge-aware)
# ---------------------------------------------------------------------------
echo "[STEP] Gemini plan => $PLAN_TMP"
if ! $PYTHON -m plan_generation.make_plan_gemini "$WHISPER_SRT" "$PLAN_TMP" --scene-map "$SCENE_MAP"; then
  echo "[ERROR] Gemini plan generation failed." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Enrich plan with assets + motion cues
# ---------------------------------------------------------------------------
echo "[STEP] Enrich plan => $PLAN_ENRICHED"
ENRICH_CMD=("$PYTHON" -m plan_generation.enrich_plan "$PLAN_TMP" "$PLAN_ENRICHED" --scene-map "$SCENE_MAP")
if [[ -n "$HIGHLIGHT_CATALOG" && -f "$HIGHLIGHT_CATALOG" ]]; then
  ENRICH_CMD+=(--highlight-catalog "$HIGHLIGHT_CATALOG")
fi
if [[ -n "$HIGHLIGHT_SRT" && -f "$HIGHLIGHT_SRT" ]]; then
  ENRICH_CMD+=(--highlight-srt "$HIGHLIGHT_SRT")
fi
"${ENRICH_CMD[@]}"

# ---------------------------------------------------------------------------
# Copy outputs for Remotion
# ---------------------------------------------------------------------------
cp "$AUTO_EDITOR_OUTPUT" "$PUBLIC_INPUT/input.mp4"
cp "$PLAN_ENRICHED" "$PUBLIC_INPUT/plan.json"

echo "[DONE] Copied artifacts to public/input/"
echo "       - Video: public/input/input.mp4"
echo "       - Plan : public/input/plan.json"
echo "[NEXT] Run: cd ../remotion-app && npm install && npm run render"
