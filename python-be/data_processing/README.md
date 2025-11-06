# Data Processing Scripts

This directory contains scripts responsible for processing raw data and generating structured metadata used in the video automation pipeline.

## Files:

- [`generate_scene_map.py`](python-be/data_processing/generate_scene_map.py): This script generates a structured scene map from an SRT transcript. It consolidates timing, topical tags, highlight heuristics, CTA flags, and motion cue candidates. This output is crucial for downstream planners (LLM or deterministic rules) to orchestrate B-roll, SFX, and animations consistently.

- [`generate_sfx_catalog.py`](python-be/data_processing/generate_sfx_catalog.py): This script discovers all SFX (sound effect) files within the `assets/sfx` directory and generates a TypeScript catalog (`remotion-app/src/data/sfxCatalog.ts`) that can be consumed by the Remotion frontend.
### Sync knowledge base

Generate structured knowledge assets and embeddings from the curated markdown/JSON repository:

```bash
python data_processing/sync_knowledge_base.py --rebuild-vectors
```

This command parses markdown metadata, validates schemas, and outputs artefacts under `outputs/knowledge/` for downstream consumers.


### Prepare training windows

Transform an SRT transcript into JSON windows enriched with knowledge snippets:

```bash
python data_processing/prepare_training_windows.py outputs/stage1_cut.srt outputs/training_windows.json
```

