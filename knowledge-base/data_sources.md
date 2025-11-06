# Data Sources

This document provides a comprehensive overview of all data sources utilized in the AI video automation pipeline. Understanding these sources is crucial for comprehending how the AI learns, generates, and validates video plans. Each source plays a distinct role in the overall process, from raw transcripts to structured asset catalogs.


| Source | Role in pipeline | Notable details |
| ------ | ---------------- | --------------- |
| `AI_Training_Plan.md` | Master plan for curating datasets, extracting features, training and evaluating models. | Written in Vietnamese; covers nine stages from data auditing to deployment and includes risk mitigation notes. |
| `transcript_video_1.txt` | Full transcript with timestamps for *How I Would Learn Digital Marketing (If I Could Start Over)*. | Highlights speaker journey, three-part learning framework, practice principles, and career path discussion. |
| `video1.json` | Annotated timeline aligned to `transcript_video_1.txt`. | 188 timestamp entries plus `video_metadata` with element glossaries, layering rules, editing patterns, and AI-specific notes. |
| `transcript_video_2.txt` | Transcript and timing for *Digital Marketing 101 (A Beginner's Guide to Marketing)*. | Explains foundational marketing concepts, channel definitions, and comparison frameworks (digital vs. traditional, B2B vs. B2C, products vs. services). |
| `video2.json` | Timeline annotations for `transcript_video_2.txt`. | Emphasis on text overlays with highlighted backgrounds, frequent zoom transitions, and context fields describing intent of each element. |
| Asset catalogs (`assets/*.json`) | Authoritative source for available b-roll, motion, and SFX assets. | Documented in detail inside [asset_catalogs.md](asset_catalogs.md); include tags, moods, and usage constraints used during inference. |

### Extraction Reminders

- Keep transcript timestamps in `M:SS` and convert to seconds during preprocessing.
- Preserve `context`, `style`, `animation`, and `sound` attributes; they contain supervision signals even when absent from transcripts.
- When augmenting data, cross-link transcript spans to timeline entries via timestamp proximity (+/- 1 second window works for both videos).
- Track narrative sections (e.g., `Part 1`, `B2B vs B2C`) to help the model learn context-aware element placement.
- Synchronise with asset catalogs so generated descriptions map to real `id`s and comply with motion spacing rules.
