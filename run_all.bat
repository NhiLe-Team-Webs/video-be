@echo off
setlocal ENABLEEXTENSIONS

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not "%VENV_PYTHON%"=="" (
  set "PYTHON=%VENV_PYTHON%"
) else (
  set "PYTHON=python"
)

set "SOURCE_VIDEO=%~1"
if "%SOURCE_VIDEO%"=="" (
  set "SOURCE_VIDEO=%SCRIPT_DIR%data\input\footage.mp4"
)

set "SLUG_OVERRIDE=%~2"
if "%SLUG_OVERRIDE%"=="" (
  set "SLUG_TARGET=%PIPELINE_SLUG%"
) else (
  set "SLUG_TARGET=%SLUG_OVERRIDE%"
)

if "%SLUG_TARGET%"=="" (
  set "SLUG_ARG="
) else (
  set "SLUG_ARG=--slug %SLUG_TARGET%"
)

set "PLAN_MODEL_ARG="
if not "%PLAN_MODEL%"=="" (
  set "PLAN_MODEL_ARG=--plan-model \"%PLAN_MODEL%\""
)

set "PLAN_MAX_ARG="
if not "%PLAN_MAX_ENTRIES%"=="" (
  set "PLAN_MAX_ARG=--plan-max-entries %PLAN_MAX_ENTRIES%"
)

set "PLAN_EXTRA_ARG="
if not "%PLAN_EXTRA%"=="" (
  set "PLAN_EXTRA_ARG=--plan-extra \"%PLAN_EXTRA%\""
)

set "PLAN_SCENE_MAP_ARG="
if not "%PLAN_SCENE_MAP%"=="" (
  set "PLAN_SCENE_MAP_ARG=--plan-scene-map \"%PLAN_SCENE_MAP%\""
)

set "PLAN_DRY_RUN_ARG="
if /I "%PLAN_DRY_RUN%"=="1" set "PLAN_DRY_RUN_ARG=--plan-dry-run"
if /I "%PLAN_DRY_RUN%"=="true" set "PLAN_DRY_RUN_ARG=--plan-dry-run"

set "WHISPER_MODEL_ARG="
if not "%WHISPER_MODEL%"=="" (
  set "WHISPER_MODEL_ARG=--whisper-model %WHISPER_MODEL%"
)

set "WHISPER_LANG_ARG="
if not "%WHISPER_LANGUAGE%"=="" (
  set "WHISPER_LANG_ARG=--whisper-language %WHISPER_LANGUAGE%"
)

echo [INFO] Starting local pipeline
echo        Source     : %SOURCE_VIDEO%
if not "%SLUG_TARGET%"=="" (
  echo        Slug override: %SLUG_TARGET%
)

%PYTHON% -m app.orchestrator --source "%SOURCE_VIDEO%" %SLUG_ARG% %PLAN_MODEL_ARG% %PLAN_MAX_ARG% %PLAN_EXTRA_ARG% %PLAN_SCENE_MAP_ARG% %PLAN_DRY_RUN_ARG% %WHISPER_MODEL_ARG% %WHISPER_LANG_ARG%
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Pipeline failed (%EXIT_CODE%).
  exit /b %EXIT_CODE%
)

echo [DONE] Pipeline finished successfully.
exit /b 0
