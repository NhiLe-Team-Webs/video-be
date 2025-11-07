#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${VENV_PYTHON:-python}"
SOURCE_VIDEO="${1:-$SCRIPT_DIR/data/input/footage.mp4}"
PIPELINE_SLUG="${PIPELINE_SLUG:-}"
WHISPER_MODEL="${WHISPER_MODEL:-small}"
WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-}"
PLAN_MODEL="${PLAN_MODEL:-}"
PLAN_MAX_ENTRIES="${PLAN_MAX_ENTRIES:-}"
PLAN_EXTRA="${PLAN_EXTRA:-}"
PLAN_SCENE_MAP="${PLAN_SCENE_MAP:-}"
PLAN_DRY_RUN="${PLAN_DRY_RUN:-}"

SLUG_ARGS=()
[[ -n "$PIPELINE_SLUG" ]] && SLUG_ARGS+=(--slug "$PIPELINE_SLUG")

PLAN_MODEL_ARGS=()
[[ -n "$PLAN_MODEL" ]] && PLAN_MODEL_ARGS+=(--plan-model "$PLAN_MODEL")

PLAN_MAX_ARGS=()
[[ -n "$PLAN_MAX_ENTRIES" ]] && PLAN_MAX_ARGS+=(--plan-max-entries "$PLAN_MAX_ENTRIES")

PLAN_EXTRA_ARGS=()
[[ -n "$PLAN_EXTRA" ]] && PLAN_EXTRA_ARGS+=(--plan-extra "$PLAN_EXTRA")

PLAN_SCENE_MAP_ARGS=()
[[ -n "$PLAN_SCENE_MAP" ]] && PLAN_SCENE_MAP_ARGS+=(--plan-scene-map "$PLAN_SCENE_MAP")

PLAN_DRY_RUN_ARGS=()
case "${PLAN_DRY_RUN,,}" in
  1|true|yes) PLAN_DRY_RUN_ARGS+=(--plan-dry-run) ;;
esac

WHISPER_LANG_ARGS=()
[[ -n "$WHISPER_LANGUAGE" ]] && WHISPER_LANG_ARGS+=(--whisper-language "$WHISPER_LANGUAGE")

echo "[INFO] Starting local pipeline"
echo "       Source      : $SOURCE_VIDEO"
[[ -n "$PIPELINE_SLUG" ]] && echo "       Slug        : $PIPELINE_SLUG"

"$PYTHON_BIN" -m app.orchestrator \
  --source "$SOURCE_VIDEO" \
  --whisper-model "$WHISPER_MODEL" \
  "${SLUG_ARGS[@]}" \
  "${PLAN_MODEL_ARGS[@]}" \
  "${PLAN_MAX_ARGS[@]}" \
  "${PLAN_EXTRA_ARGS[@]}" \
  "${PLAN_SCENE_MAP_ARGS[@]}" \
  "${PLAN_DRY_RUN_ARGS[@]}" \
  "${WHISPER_LANG_ARGS[@]}"

echo "[DONE] Pipeline finished successfully."
