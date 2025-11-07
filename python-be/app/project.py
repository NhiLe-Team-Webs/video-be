from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict

from .config import (
    INPUT_DIR,
    LOGS_DIR,
    OUTPUTS_DIR,
    PLANS_DIR,
    PROCESSED_DIR,
    TRANSCRIPTS_DIR,
)


@dataclass
class ProjectPaths:
    slug: str
    source_video: Path
    ingested_video: Path
    processed_video: Path
    processed_metadata: Path
    transcript_json: Path
    transcript_text: Path
    transcript_srt: Path
    plan_json: Path
    metadata_file: Path
    log_file: Path
    export_dir: Path

    @classmethod
    def from_slug(cls, slug: str, source_video: Path) -> "ProjectPaths":
        ingested = INPUT_DIR / f"{slug}.mp4"
        processed = PROCESSED_DIR / f"{slug}_ae.mp4"
        return cls(
            slug=slug,
            source_video=source_video,
            ingested_video=ingested,
            processed_video=processed,
            processed_metadata=processed.with_suffix(".metadata.json"),
            transcript_json=TRANSCRIPTS_DIR / f"{slug}.json",
            transcript_text=TRANSCRIPTS_DIR / f"{slug}.txt",
            transcript_srt=TRANSCRIPTS_DIR / f"{slug}.srt",
            plan_json=PLANS_DIR / f"{slug}.json",
            metadata_file=LOGS_DIR / f"{slug}_ingest.json",
            log_file=LOGS_DIR / f"{slug}.log",
            export_dir=OUTPUTS_DIR / slug,
        )

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {key: str(value) if isinstance(value, Path) else value for key, value in data.items()}
