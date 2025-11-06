# Editing Patterns

This document provides qualitative descriptions and examples of common editing patterns used in the video automation pipeline. These patterns serve as concrete exemplars for the AI model, demonstrating how different video elements should be combined and sequenced to achieve specific narrative and visual effects. For machine-readable, structured examples, refer to `patterns.json`.

## Video 1 - How I Would Learn Digital Marketing

### Introduction & Hook
-   **Pattern**: Speaker intro with a bold, engaging question.
-   **Elements**: `speaker_intro` (main layer), `text_overlay` (overlay layer) with `bold_emphasis` style.
-   **Rationale**: Immediately captures viewer attention and sets the stage for the video's core topic.

### Three-Part Learning Framework
-   **Pattern**: Progressive list reveal for a multi-stage framework.
-   **Elements**: Series of `text_overlay` elements with `fade_in_list` animation, each adding a new point to the previous one.
-   **Rationale**: Visually reinforces the structured learning path, making it easy for viewers to follow.

### Practice Principles
-   **Pattern**: Iconography with brief text overlays for key principles.
-   **Elements**: `icon` (overlay layer) with relevant `content` (e.g., lightbulb for "innovation"), accompanied by `text_overlay` with `clean_minimal` style.
-   **Rationale**: Provides quick visual cues for abstract concepts, enhancing comprehension and retention.

### Career Path Discussion
-   **Pattern**: B-roll footage illustrating career growth or industry trends.
-   **Elements**: `broll` (video layer) with `description` matching the spoken content (e.g., "modern office", "digital network").
-   **Rationale**: Breaks up speaker footage, adds visual interest, and metaphorically supports the narrative.

## Video 2 - Digital Marketing 101

### Foundational Concepts
-   **Pattern**: Highlighted definitions with `highlighted_background` style.
-   **Elements**: `text_overlay` (overlay layer) with `highlighted_background` style for key terms and their definitions.
-   **Rationale**: Ensures critical vocabulary is clearly presented and easily digestible.

### Channel Definitions
-   **Pattern**: Split-column text overlay for comparing different channels.
-   **Elements**: `text_overlay` (overlay layer) with `split_column` style, presenting two or more channels side-by-side.
-   **Rationale**: Facilitates direct comparison and highlights distinctions between various digital marketing channels.

### Digital vs. Traditional Marketing
-   **Pattern**: Animated flow chart or progression arrow for comparative analysis.
-   **Elements**: `text_animation` (overlay layer) with `flow_chart` or `progression_arrow` animation, illustrating the differences and evolution.
-   **Rationale**: Visually explains complex comparisons and shows relationships between concepts.

### B2B vs. B2C
-   **Pattern**: Callout box with concise summaries for business models.
-   **Elements**: `text_overlay` (overlay layer) with `callout_box` style, providing bullet points or short descriptions for each model.
-   **Rationale**: Offers a clear, encapsulated summary of distinct business approaches.

### Feature vs. Benefit
-   **Pattern**: Icon effect with a subtle sound cue for emphasis.
-   **Elements**: `icon` (overlay layer) appearing with a `ui_pop` `sound_effect` (audio layer) when a feature or benefit is introduced.
-   **Rationale**: Draws attention to the distinction and reinforces the learning point with an auditory cue.

## General Principles for Pattern Application

-   **Contextual Relevance**: Always ensure the chosen pattern aligns with the narrative intent and emotional tone of the spoken content.
-   **Pacing**: Adjust the duration and animation speed of elements to match the speaker's pace and the overall rhythm of the video.
-   **Clarity**: Prioritize clear communication. Overlays should be concise, and visuals should directly support the message without distraction.
-   **Brand Consistency**: Adhere to established brand guidelines for styles, colors, and animations.
-   **Layer Management**: Avoid visual clutter by respecting the layer stack hierarchy and ensuring elements do not overlap unnecessarily.
-   **Sound Reinforcement**: Use sound effects judiciously to enhance emphasis and transitions, not to overwhelm the viewer.

## Purpose

The `patterns.json` file provides machine-readable examples that complement the qualitative descriptions in `patterns.md`. It helps the AI model learn:

-   **Correct sequencing**: How elements like `text_overlay`, `broll`, and `sound_effect` should follow each other.
-   **Contextual application**: When to use specific styles, animations, or sound effects based on the narrative context.
-   **Constraint adherence**: Examples that demonstrate compliance with rules defined in `element_schema.json` and `motion_rules.json`.

## Structure

The `patterns.json` file is an array of objects, where each object represents a specific editing pattern. Each pattern typically includes:

-   **`name`**: A descriptive name for the pattern.
-   **`description`**: A brief explanation of the pattern's intent and usage.
-   **`elements`**: An array of video elements, each conforming to the `element_schema.json`, demonstrating the pattern. These elements include `timestamp`, `type`, `layer`, and other relevant properties.
-   **`notes`**: Additional qualitative notes or rationale for the pattern.

## Usage

-   **Training**: Used as structured training data to teach the AI model how to generate valid and effective video plans.
-   **Validation**: Provides concrete test cases for validating the AI's output against known good examples.
-   **Debugging**: Helps in understanding and debugging unexpected behaviors in the AI's plan generation by comparing outputs to these reference patterns.

Refer to `knowledge-base/examples/patterns.md` for qualitative descriptions and further context on these editing patterns.
