# Training Pipeline Blueprint

This document serves as the authoritative blueprint for the AI video plan generation training pipeline. It details the end-to-end process, from data preparation and feature engineering to model strategy, training routines, evaluation, and deployment. This blueprint is derived from the `AI_Training_Plan.md` (Vietnamese source) and should be used as the primary reference when preparing datasets, developing new models, or evolving the existing model stack.

Derived from `AI_Training_Plan.md` (Vietnamese source). Use this as the authoritative workflow when preparing datasets or evolving the model stack.

## 1. Audit Existing Data & Targets
- Understand transcript structure, narration pace, and how timeline annotations map to speech.
- Catalogue every element attribute that must be predicted: `timestamp`, `duration`, `type`, `layer`, `content/description`, `style`, `animation`, `sound`, `action`, optional `context` and `confidence` (see [element_schema.json](element_schema.json)).
- Confirm ingestion coverage for both transcripts and JSON timelines; flag missing sections or inconsistent timestamps.

## 2. Preprocess & Align
- Merge transcript text with timeline entries by timestamp, producing windows (5-10 seconds) that give sufficient context.
- Normalize timestamps to seconds for easier maths and modelling.
- Segment transcripts into sentences or clauses; tokenise and build embeddings (Sentence-BERT or equivalent).
- Encode video elements: one-hot for categorical fields, embeddings for text-heavy attributes (`description`, `content`); ensure categorical vocab matches [element_schema.json](element_schema.json).

## 3. Feature Engineering
- Transcript features: semantic vectors, sentence length, relative position within the video, keyword flags (for example, "Part 1", "mistake", "option").
- Audio/tempo proxies: estimate speaking rate via word counts per window.
- Timeline context: distance to previous/next elements, element type history, context tags (aligned to `context_rules.json`).
- Style cues: reuse `context` labels to signal metaphors, comparisons, or emphasis needs.
- Asset compatibility: embed catalog metadata (for example, `tags`, `mood`, `intensity`) from `broll_catalog.json` and `sfx_catalog.json` for recommendation scoring.

## 4. Model Strategy
- Treat timestamp and duration predictions as regression; element presence and type as multi-label or multi-class classification.
- Consider hierarchical modelling: first detect whether an element occurs, then specialise by element family.
- Explore sequence-to-sequence or encoder-decoder approaches for generating ordered element lists.
- Reserve capacity for generative text (for example, overlay copy) via template libraries or conditional generation models.

## 5. Training Routine
- Split data by video to avoid leakage (train on one video, validate on another, rotate as more data arrives).
- Use curriculum: start with type/layer predictions, then add auxiliary heads (content, style).
- Apply class balancing (oversampling rare elements like `achievement_highlight`).
- Monitor convergence per head; early-stop if accuracy plateaus but loss diverges.

## 6. Evaluation
- Quantitative: accuracy/F1 for type classification, MAE for timestamps, BLEU/ROUGE for generated text.
- Qualitative: human review against `quality_criteria.md` with focus on narrative fit and layer conflicts.
- Stress tests: long speaking segments without elements, rapid-fire sections with many overlays, sections requiring metaphors.

## 7. Deployment Checklist
- Package preprocessing scripts, model weights, `element_schema.json`, and inference pipeline.
- Provide fallbacks when confidence is low (for example, default overlays or prompts for manual review).
- Log predictions with timestamps and context for downstream auditing.

## 8. Maintenance Cadence
- Quarterly data refresh to incorporate new annotated videos.
- Monthly error analysis session targeting repeated failure modes (mis-timed SFX, incorrect layer stacking).
- Capture feedback from editors to expand context tags and example catalogues.

## 9. Risk Controls
- Mitigate noisy timestamps by smoothing predictions and enforcing minimum separation thresholds defined in `motion_rules.json`.
- Prevent style drift by constraining `style` predictions to allowed set per brand guide.
- Document assumptions about transcript accuracy; include fallbacks when speech deviates from script.
