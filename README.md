# Python Backend Toolkit

Local-first automation scripts that ingest raw footage, trim silence, generate Whisper transcripts, build an AI-assisted scene plan, and export artifacts ready for FE tooling.

## Quick start

```bash
cd python-be
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Runtime directories

The pipeline writes everything under `python-be/data/` and copies the final artifacts to `python-be/outputs/<slug>/`.

```
data/
 ├─ input/         # ingested footage per slug
 ├─ processed/     # auto-editor output
 ├─ transcripts/   # Whisper JSON + TXT
 ├─ plans/         # plan_<slug>.json
 └─ logs/          # module + metadata logs
```

## Run the full flow

```bash
# macOS/Linux
./run_all.sh path/to/video.mp4

# Windows
run_all.bat path\to\video.mp4
```

> Nếu không truyền tham số, script mặc định đọc `python-be/data/input/footage.mp4`. Chỉ cần thả video vào đó và chạy `run_all.bat`.

Environment overrides:

| Variable | Meaning | Example |
| -------- | ------- | ------- |
| `PIPELINE_SLUG` | Force a slug (else timestamp) | `PIPELINE_SLUG=ke-ai-demo` |
| `PLAN_MODEL` | Gemini model override passed to `make_plan.py` | `PLAN_MODEL=gemini-1.5-pro` |
| `PLAN_MAX_ENTRIES` | Cap SRT rows sent to Gemini | `PLAN_MAX_ENTRIES=140` |
| `PLAN_EXTRA` | Extra prompt instructions | `PLAN_EXTRA="ưu tiên hook đầu video"` |
| `PLAN_SCENE_MAP` | Path to `scene_map.json` (optional) | `PLAN_SCENE_MAP=data/plans/scene_map.json` |
| `PLAN_DRY_RUN` | `1/true` to only print the prompt | `PLAN_DRY_RUN=1` |
| `WHISPER_MODEL` | Whisper model size | `WHISPER_MODEL=base` |
| `WHISPER_LANGUAGE` | Optional ISO language hint | `WHISPER_LANGUAGE=vi` |
| `VENV_PYTHON` | Explicit Python binary for scripts | `VENV_PYTHON=.venv\Scripts\python.exe` |

> 💡 Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) in your environment or `.env` before running the planner.

`run_all` executes `python -m app.orchestrator ...`, which performs:

1. **Ingest** – registers the provided footage path (default `data/input/footage.mp4`) and derives a slug.
2. **Auto-Editor** – trims silence and stores the cut clip in `data/processed/<slug>_ae.mp4`.
3. **Whisper** – writes JSON, TXT, and SRT transcripts in `data/transcripts/`.
4. **Planner** – shells out to `plan_generation/make_plan.py` (Gemini) to create `data/plans/<slug>.json`.
5. **Exporter** – copies the processed video + transcript + plan into `outputs/<slug>/` along with a `manifest.json`.

## Run modules individually

Each module is a CLI so you can rerun specific steps:

```bash
python -m app.ingest --source data/input/demo-slug.mp4 --slug demo-slug
python -m app.auto_editor_runner --slug demo-slug
python -m app.transcriber --slug demo-slug --model small --language en
python -m app.planner_llm --slug demo-slug --model gemini-1.5-pro
python -m app.exporter --slug demo-slug
```

## LLM planner

- Planning is delegated to `plan_generation/make_plan.py`, which already contains the Gemini prompt, fallback configs, and KnowledgeService glue.
- Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) in `.env` or the environment so `google-generativeai` can authenticate.
- Reuse the module directly:

```bash
python -m app.planner_llm --slug demo-slug --model gemini-1.5-pro
```

- Planner output schema:

```jsonc
{
  "project_slug": "demo-slug",
  "created_at": "2025-11-07T12:00:00Z",
  "generator": {"provider": "gemini", "model": "gemini-1.5-pro"},
  "video": {"processed_video": "data/processed/demo-slug_ae.mp4"},
  "scenes": [
    {
      "scene_id": "scene-001",
      "start": 0.0,
      "end": 18.4,
      "summary": "...",
      "transcript_excerpt": "..."
    }
  ]
}
```

## Generated artifacts

| Path | Description |
| ---- | ----------- |
| `data/input/<slug>.mp4` | User-managed footage path consumed by the pipeline. |
| `data/processed/<slug>_ae.mp4` | Silence-trimmed clip from Auto-Editor. |
| `data/transcripts/<slug>.json` | Raw Whisper JSON (segments + timing). |
| `data/transcripts/<slug>.txt` | Plain-text transcript for prompts. |
| `data/transcripts/<slug>.srt` | Subtitle file consumed by `make_plan.py`. |
| `data/plans/<slug>.json` | Scene plan consumed by FE. |
| `outputs/<slug>/manifest.json` | Export summary + relative paths. |

## Troubleshooting

- **Auto-Editor not found** → install via `pip install auto-editor` (already in `requirements.txt`) and ensure FFmpeg is available on PATH.
- **Whisper fails** → confirm `openai-whisper` package is installed; this implicitly depends on FFmpeg codecs.
- **LLM errors** → confirm `GEMINI_API_KEY` is set and `plan_generation/make_plan.py` can reach the Gemini API.
- **Permission issues** → delete stale files inside `data/` (they are ignored via `.gitignore`) if a previous run was interrupted.

All documentation and code comments remain English-first, while `ke_hoach_local.md` tracks the Vietnamese planning notes for the local deployment.
