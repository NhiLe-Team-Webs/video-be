# AI Planning Knowledge Base

This repository serves as the central knowledge base for the AI-driven video plan generation pipeline. It contains all essential reference materials, including rules, definitions, workflows, quality criteria, examples, and asset references. This knowledge base is critical for supporting the training, inference, and evaluation phases of the AI model, ensuring that generated video plans are accurate, consistent, and aligned with production standards.

Central repository of reference materials that support training, inference, and evaluation of the video plan-generation pipeline.

## Scope
- Consolidates rules, definitions, workflows, criteria, examples, and asset references derived from:
  - `AI_Training_Plan.md`
  - `transcript_video_1.txt` / `video1.json`
  - `transcript_video_2.txt` / `video2.json`
  - Asset catalogs under `assets/`
- Goal: guide the model to place highlights, b-roll, sound effects, overlays, and motion cues with high accuracy and narrative relevance.

## Directory Map
- `data_sources.md` - provenance and key takeaways from transcripts, timelines, and catalogs.
- `training_pipeline.md` - end-to-end preparation and modelling process.
- `element_definitions.md` - glossary for element types, layers, and default behaviours.
- `element_schema.json` - machine-readable schema describing required fields, enumerations, and validation constraints.
- `planning_guidelines.md` - actionable rules for proposing timeline elements with cross-references.
- `quality_criteria.md` - success metrics and acceptance checkpoints.
- `glossary.md` - domain terminology used across the knowledge base.
- `asset_catalogs.md` - how to incorporate `broll`, `sfx`, `motion`, and context catalogs into modelling.
- `examples/` - qualitative (`patterns.md`) and structured (`patterns.json`) editing exemplars.
- `videos/` - narrative blueprints for each reference video (summary, audience, themes, cue suggestions).
- `CHANGELOG.md` - tracked updates to maintain version history.

## Usage Guidance
1. Review `data_sources.md` to understand raw inputs and supporting catalogs.
2. Align feature engineering and targets using `training_pipeline.md`, `element_definitions.md`, and `element_schema.json`.
3. During plan generation, enforce `planning_guidelines.md` and validate against `quality_criteria.md`.
4. Leverage `asset_catalogs.md` alongside the JSON catalogs to ensure selected assets exist and honour motion rules.
5. Consult `videos/` and `examples/` for grounded samples (positive and negative) before crafting prompts, labels, or rule-based validators.
6. Log any documentation changes in `CHANGELOG.md` so training runs can reference the correct knowledge base version.
