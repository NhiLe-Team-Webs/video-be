@echo off
setlocal ENABLEEXTENSIONS

REM ---------------------------------------------------------------------------
REM Resolve script directory and move there so relative imports work.
REM ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM ---------------------------------------------------------------------------
REM Input / output configuration
REM ---------------------------------------------------------------------------
set "SOURCE_VIDEO=%~1"
if "%SOURCE_VIDEO%"=="" set "SOURCE_VIDEO=%SCRIPT_DIR%..\public\input\input.mp4"

set "OUTPUT_DIR=%SCRIPT_DIR%outputs"
set "PUBLIC_ROOT=%SCRIPT_DIR%..\public"
set "PUBLIC_INPUT=%PUBLIC_ROOT%\input"
if not defined HIGHLIGHT_CATALOG (
  set "HIGHLIGHT_CATALOG="
)

set "AUTO_EDITOR_OUTPUT=%OUTPUT_DIR%\stage1_cut.mp4"
set "WHISPER_SRT=%OUTPUT_DIR%\stage1_cut.srt"
set "PLAN_TMP=%OUTPUT_DIR%\plan.json"
set "PLAN_ENRICHED=%OUTPUT_DIR%\plan_enriched.json"
set "SCENE_MAP=%OUTPUT_DIR%\scene_map.json"
set "TRAINING_WINDOWS=%OUTPUT_DIR%\training_windows.json"
if not defined HIGHLIGHT_SRT (
  set "HIGHLIGHT_SRT=%WHISPER_SRT%"
)

set "PYTHON=python"

if not exist "%SOURCE_VIDEO%" (
  echo [ERROR] Missing input video: %SOURCE_VIDEO%
  exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if not exist "%PUBLIC_INPUT%" mkdir "%PUBLIC_INPUT%"

REM ---------------------------------------------------------------------------
REM Sync knowledge base (structured docs + embeddings)
REM ---------------------------------------------------------------------------
echo [STEP] Sync knowledge base assets
%PYTHON% data_processing\sync_knowledge_base.py
if errorlevel 1 (
  echo [ERROR] Knowledge-base sync failed.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM Auto-Editor – remove silence
REM ---------------------------------------------------------------------------
echo [STEP] Auto-Editor => %AUTO_EDITOR_OUTPUT%
%PYTHON% -m auto_editor "%SOURCE_VIDEO%" -o "%AUTO_EDITOR_OUTPUT%" ^
  --edit audio:threshold=0.06 ^
  --margin "0.75s,1s" ^
  --silent-speed 4 ^
  --video-speed 1 ^
  --video-codec libx264 ^
  --audio-codec aac ^
  --quiet

REM ---------------------------------------------------------------------------
REM Whisper – generate transcript
REM ---------------------------------------------------------------------------
echo [STEP] Whisper => %WHISPER_SRT%
%PYTHON% -m whisper "%AUTO_EDITOR_OUTPUT%" ^
  --model small ^
  --language en ^
  --task transcribe ^
  --output_format srt ^
  --output_dir "%OUTPUT_DIR%"

if not exist "%WHISPER_SRT%" (
  echo [ERROR] Whisper did not produce %WHISPER_SRT%.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM Upload transcript to Google Sheets
REM ---------------------------------------------------------------------------
echo [STEP] Upload transcript to Google Sheet
%PYTHON% -m data_processing.upload_transcript "%WHISPER_SRT%"
if errorlevel 1 (
  echo [ERROR] Transcript upload failed.
  exit /b 1
)

if defined HIGHLIGHT_CATALOG (
  if not exist "%HIGHLIGHT_CATALOG%" set "HIGHLIGHT_CATALOG="
)
if defined HIGHLIGHT_SRT (
  if not exist "%HIGHLIGHT_SRT%" set "HIGHLIGHT_SRT="
)

REM ---------------------------------------------------------------------------
REM Derive scene map + training windows
REM ---------------------------------------------------------------------------
echo [STEP] Scene map => %SCENE_MAP%
%PYTHON% -m data_processing.generate_scene_map "%WHISPER_SRT%" -o "%SCENE_MAP%"

echo [STEP] Training windows => %TRAINING_WINDOWS%
%PYTHON% -m data_processing.prepare_training_windows "%WHISPER_SRT%" "%TRAINING_WINDOWS%"

REM ---------------------------------------------------------------------------
REM Generate plan with Gemini (knowledge-aware)
REM ---------------------------------------------------------------------------
echo [STEP] Gemini plan => %PLAN_TMP%
%PYTHON% -m plan_generation.make_plan_gemini "%WHISPER_SRT%" "%PLAN_TMP%" --scene-map "%SCENE_MAP%"
if errorlevel 1 (
  echo [ERROR] Gemini plan generation failed.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM Enrich plan with assets + motion cues
REM ---------------------------------------------------------------------------
echo [STEP] Enrich plan => %PLAN_ENRICHED%
set ENRICH_ARGS=--scene-map "%SCENE_MAP%"
if defined HIGHLIGHT_CATALOG (
  set ENRICH_ARGS=%ENRICH_ARGS% --highlight-catalog "%HIGHLIGHT_CATALOG%"
)
if defined HIGHLIGHT_SRT (
  set ENRICH_ARGS=%ENRICH_ARGS% --highlight-srt "%HIGHLIGHT_SRT%"
)
%PYTHON% -m plan_generation.enrich_plan "%PLAN_TMP%" "%PLAN_ENRICHED%" %ENRICH_ARGS%
if errorlevel 1 (
  echo [ERROR] Plan enrichment failed.
  exit /b 1
)

REM ---------------------------------------------------------------------------
REM Copy outputs for Remotion
REM ---------------------------------------------------------------------------
copy /Y "%AUTO_EDITOR_OUTPUT%" "%PUBLIC_INPUT%\input.mp4" >nul
copy /Y "%PLAN_ENRICHED%" "%PUBLIC_INPUT%\plan.json" >nul

echo [DONE] Copied artifacts to public\input\
echo        - Video: public\input\input.mp4
echo        - Plan : public\input\plan.json
exit /b 0
