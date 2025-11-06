# Quality Criteria

This document defines the benchmarks and standards used for reviewing both AI model outputs and human-labelled video plans. Adhering to these criteria ensures the consistency, accuracy, and overall quality of the generated video content, facilitating effective evaluation and continuous improvement of the AI system.

Benchmarks for reviewing model outputs and human-labelled plans.

## Timing
- **Timestamp error** <= 0.5 s for overlays and SFX, <= 1.0 s for b-roll and transitions.
- **Duration consistency** - no element persists past the next conflicting cue; default to metadata rules in `element_definitions.md`.

## Coverage
- Every major section (see `videos/*.md`) contains at least one supporting visual element.
- No unaddressed transcript peaks: stories, statistics, frameworks, and comparisons must trigger at least a text overlay or b-roll.

## Layer Integrity
- Only one element per layer at any instant (exceptions: audio layer can stack ambience plus SFX if mix-tested).
- Transitions do not collide with overlays unless intentionally coordinated.

## Content Accuracy
- On-screen text mirrors transcript wording or summarises it accurately without introducing new facts.
- B-roll descriptions are actionable for editors (clear subject, action, mood).
- Sound choices reinforce the message rather than distract.

## Style Consistency
- `highlighted_background` used for high-importance text across videos unless brand guidelines dictate otherwise.
- Animation choices match narrative intent (for example, `typing_effect` only when typing is implied).
- Colour, tone, and energy remain aligned with the source videos' instructional style.

## Review Workflow
- Automated checks: compare predicted elements to ground truth with metrics (F1, MAE).
- Human review: run through transcripts while watching the plan, verifying that each cue feels natural.
- Regression guardrail: maintain a curated library of "golden" plan outputs; new models must meet or exceed their scores.
