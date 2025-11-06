# Planning Guidelines

This document outlines the operational rules and best practices for proposing timeline elements that align with the reference videos. These guidelines are crucial for ensuring that AI-generated video plans are consistent, high-quality, and adhere to established production standards. Cross-reference [element_definitions.md](element_definitions.md) for detailed layer behavior and [quality_criteria.md](quality_criteria.md) for validation thresholds.

## Narrative Alignment
- Anchor every element to a transcript clause; avoid floating overlays with no spoken support. *Rationale:* Maintains coherence with dialogue and prevents disjointed visuals.
- Track signal phrases ("Part 1", "Stage 2", "Option 3", "Here's why") to justify section headers or text overlays. *Rationale:* Reinforces structural beats described in [videos/video1_outline.md](videos/video1_outline.md) and [videos/video2_outline.md](videos/video2_outline.md).
- Align stories and analogies with metaphorical b-roll using `context` hints or tag matches from [asset_catalogs.md](asset_catalogs.md). *Rationale:* Visualises abstract concepts for faster comprehension.

## B-Roll Selection
- Pick b-roll that literalises or metaphorically echoes the spoken idea (for example, trash bin for "mistakes", instruments for "learning analogies", skyline for "market scale"). *Rationale:* Supports narrative cues in transcripts.
- Match tone and pacing: fast cuts for energetic lists, steadier shots for reflective segments. *Rationale:* Mood tags in `broll_catalog.json` help maintain emotional alignment.
- Let each clip play until another `video` layer element arrives; smooth abrupt switches with `effect` actions defined in [element_schema.json](element_schema.json). *Rationale:* Avoids jarring cuts while respecting defaults in [element_definitions.md](element_definitions.md#element-families).

## Text & Animated Overlays
- Use `highlighted_background` as the default for key facts, comparisons, and definitions. *Rationale:* Brand-consistent and legible (see `style` enum in `element_schema.json`).
- Build progressive lists for frameworks; each new point appends to the previous overlay. *Rationale:* Mirrors positive examples in [examples/patterns.md](examples/patterns.md#video-1---how-i-would-learn-digital-marketing).
- Apply `text_animation` presets when narration references numbers climbing (`count_up`) or typing/flow (`typing_effect`, `flow_chart`). *Rationale:* Motion choices should support narrative metaphors; guardrails defined in `motion_rules.json`.
- Keep copy concise and faithful to the transcript; default to title case for readability. *Rationale:* Preserves voice and aligns with guidance in [glossary.md](glossary.md).
- Surface highlight keywords as 1–2 word noun or verb phrases that retain meaning together; drop conversational fillers (`uh`, `oh`, `you know`) before publishing. *Rationale:* Keeps on-screen knowledge base text signal-rich and purposeful.

## Sound Effects
- Pair new terms or section changes with subtle SFX (`ui_pop`, `whoosh_standard`). *Rationale:* Audio cues boost recall and correspond to assets in `sfx_catalog.json`.
- Reserve `money`, `success`, or `achievement` sounds for monetary claims or milestones. *Rationale:* Prevents semantic drift and keeps the acoustic palette purposeful.
- Use `typing` sounds only when animations or narration mention writing or typing. *Rationale:* Maintains cohesive audiovisual storytelling.

## Motion & Transitions
- Trigger `zoom_in` on turning points or emphasised statements ("this is the key", "here's the mistake"). *Rationale:* Heightens focus; validated by examples in [examples/patterns.json](examples/patterns.json).
- Deploy `zoom_out` to release tension or provide wider context after a focal point. *Rationale:* Restores viewer orientation.
- Space identical effects by at least 0.5 s unless narrative urgency demands otherwise. *Rationale:* Enforced by `motion_rules.json`; avoids viewer fatigue (see negative cases in `patterns.json`).

## Layer & Timing Hygiene
- Do not overlap full-screen overlays at the same timestamp; offset by at least 0.3 s or merge copy. *Rationale:* Respects the stack hierarchy defined in [element_definitions.md](element_definitions.md#layer-stack).
- When the `video` layer is active (b-roll), overlays may occupy full width; otherwise keep margins to protect speaker visibility. *Rationale:* Preserves essential facial expressions.
- End SFX before the next major beat and cap overlay visibility at 6-8 s unless the segment is static. *Rationale:* Aligns with [quality_criteria.md](quality_criteria.md#timing) to prevent lingering elements.

## Content Consistency
- Use canonical terminology ("digital marketing", "traditional marketing", "B2B/B2C", "feature vs benefit"). *Rationale:* Vocabulary centralised in [glossary.md](glossary.md) ensures consistent messaging.
- Keep tone authoritative, instructional, and encouraging as reflected in both transcripts. *Rationale:* Matches target audience described in video outlines.
- Maintain chronological order in lists (for example, "Stage 1 -> Stage 2 -> Stage 3"). *Rationale:* Prevents cognitive dissonance and supports pedagogy.
