# Python Backend Toolkit

Automation scripts for preparing video transcripts, scene analysis, AI-generated plans, and Remotion-ready assets.

## Quick Start

```bash
cd python-be
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Optional `.env` overrides:

```dotenv
# Silence thresholds (milliseconds) that gate transition placement
TRANSITIONS_MIN_PAUSE_MS=700
MIN_PAUSE_MS=700

# Default transition fallback (cut | fadeCamera | slideWhoosh)
DEFAULT_TRANSITION_TYPE=fadeCamera

# Gemini configuration (if using LLM planning)
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-pro
```

## End-to-End Workflow

```bash
# macOS/Linux
./run_all.sh path/to/video.mp4

# Windows
run_all.bat path\to\video.mp4
```

The script:

1. Syncs the knowledge base (`data_processing/sync_knowledge_base.py`).
2. Trims silence via Auto-Editor (`outputs/stage1_cut.mp4`).
3. Generates an SRT transcript with Whisper (`outputs/stage1_cut.srt`).
4. Builds a scene map (`outputs/scene_map.json`) and training windows (`outputs/training_windows.json`).
5. Calls the Gemini planner (`outputs/plan.json`).
6. Enriches the plan with motion/B-roll metadata (`outputs/plan_enriched.json`).
7. Copies the trimmed video and enriched plan to `../public/input/`.

## Key Scripts

| Script | Description |
| ------ | ----------- |
| `data_processing/generate_scene_map.py` | Derives topics, highlight scores, and CTA flags from the transcript. |
| `data_processing/sync_knowledge_base.py` | Parses Markdown/JSON docs into structured data and embeddings. |
| `data_processing/prepare_training_windows.py` | Converts SRT entries into training samples enriched with knowledge snippets. |
| `plan_generation/make_plan_gemini.py` | Prompts Gemini using transcript + scene map + knowledge snippets. |
| `plan_generation/enrich_plan.py` | Adds B-roll, motion cues, and CTA safeguards to the generated plan. |
| `plan_generation/validators/` | Schema and rule validations for any plan before export. |

## Generated Artifacts

| Path | Purpose |
| ---- | ------- |
| `outputs/stage1_cut.mp4` | Silence-trimmed video (source for Remotion). |
| `outputs/stage1_cut.srt` | Transcript produced by Whisper. |
| `outputs/scene_map.json` | Per-segment analysis (topics, scores, CTA marks). |
| `outputs/training_windows.json` | AI training samples aligned to the transcript. |
| `outputs/plan.json` | Raw Gemini output. |
| `outputs/plan_enriched.json` | Finalised plan with motion/B-roll metadata. |
| `outputs/knowledge/` | Cached structured docs and embeddings. |

## Knowledge Base Integration

- Curated content lives in `../knowledge-base/` (see that README for structure).
- Python utilities in `knowledge_base/` provide ingestion, vector search, and validation helpers.
- `make_plan_gemini.py` automatically retrieves relevant guideline snippets once the cache is synced.
- Use `KnowledgeService.validate_plan(plan_dict)` to combine schema and rule checks before shipping a plan.

## Remotion Rendering

```bash
cd ../remotion-app
npm install
npm run render   # outputs out/final.mp4
```

The Remotion project expects `public/input/input.mp4` and `public/input/plan.json` (copied by the run script). Segment transitions, highlights, SFX, and B-roll placeholders are all driven by the enriched plan.

## Troubleshooting

- **Missing Whisper output**: ensure `pip install -r requirements.txt` completed and you have the necessary FFmpeg codecs.
- **Gemini errors**: confirm `GEMINI_API_KEY` is set; use `--dry-run --print-prompt` to inspect the constructed prompt.
- **Validation failures**: run the validators manually to inspect issues.
  ```python
  from plan_generation.validators import validate_plan_schema, validate_plan_rules
  issues = [*validate_plan_schema(plan), *validate_plan_rules(plan)]
  ```
- **Remotion render issues**: check that every SFX path referenced in the plan exists under `../assets/sfx/` and that the plan matches `src/data/planSchema.ts`.

## Additional Documentation

- `knowledge_base/README.md` – ingestion and retrieval internals.
- `plan_generation/validators/README.md` – schema/rule validation details.
- `outputs/knowledge/README.md` – description of cached artifacts.
- `../knowledge-base/README.md` – curated training materials and schemas.

Keep all new documentation and inline comments in English. Update the relevant README whenever you add new scripts or change the workflow to keep onboarding friction low.
