# Asset Catalog Integration

This document details how asset catalogs are integrated into the video automation pipeline. It ensures that the AI model's outputs can be directly mapped to available production assets, guaranteeing the generation of actionable and feasible video plans.

Connect model outputs with available production assets to guarantee actionable plans.

## Catalog Overview

| File | Purpose | Key Fields |
| ---- | ------- | ---------- |
| `assets/broll_catalog.json` | Inventory of stills and footage for b-roll replacement shots. | `id`, `title`, `file`, `mediaType`, `orientation`, `tags`, `mood`, `usageExamples`. |
| `assets/sfx_catalog.json` | Library of sound effects indexed by mood and cue type. | `id`, `file`, `length`, `intensity`, `tags`, `recommendedContexts`. |
| `assets/motion_rules.json` | Allowed transitions and motion presets with usage rules. | `id`, `action`, `layer`, `minSpacing`, `pairings`. |
| `assets/context_rules.json` | Mapping from narrative contexts to preferred asset tags. | `context`, `recommendedBrollTags`, `recommendedSfxTags`, `notes`. |

## Usage Guidelines

1. **Match by Context Tags** - ensure each generated element includes `context` (see `element_schema.json`). Use it to query `context_rules.json` and retrieve permitted `broll` or `sfx` tags.
2. **Validate Asset Availability** - before finalising a plan, confirm `description` or `sound` values map to existing `id`s in the relevant catalog; log fallback suggestions when no exact match is found.
3. **Respect Motion Constraints** - defer to `motion_rules.json` for allowable sequences (for example, minimum 0.5 s spacing between identical zooms).
4. **Enrich Training Examples** - augment training data with catalog metadata (for example, embed `mood` vectors) so the model learns to pick assets aligned with emotional tone.
5. **Keep Catalogs Synced** - update version numbers and regeneration timestamps when assets change; propagate updates to downstream caches.

## Integration Touchpoints

- **Feature Engineering** - include catalog tags as additional inputs when predicting `description` or `sound`.
- **Inference** - post-process model outputs by selecting the closest matching `id` using cosine similarity between description embeddings and catalog tags.
- **Evaluation** - add assertions in `quality_criteria.md` to confirm selected assets exist and comply with `motion_rules.json`.

Refer back to `knowledge-base/data_sources.md` for provenance and to `planning_guidelines.md` for contextual placement rules.
