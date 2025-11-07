from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from .config import INPUT_DIR, TRANSCRIPTS_DIR, ensure_runtime_directories
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import dump_json, run_command

LOGGER = logging.getLogger(__name__)


def transcribe_video(
    project: ProjectPaths,
    *,
    model: str = "small",
    language: str | None = None,
    task: str = "transcribe",
) -> Dict[str, Any]:
    ensure_runtime_directories()
    if not project.processed_video.exists():
        raise FileNotFoundError(f"Processed video missing: {project.processed_video}")

    command = [
        sys.executable,
        "-m",
        "whisper",
        str(project.processed_video),
        "--model",
        model,
        "--task",
        task,
        "--output_format",
        "all",
        "--output_dir",
        str(TRANSCRIPTS_DIR),
    ]
    if language:
        command.extend(["--language", language])

    run_command(command, logger=LOGGER)

    raw_output = TRANSCRIPTS_DIR / f"{project.processed_video.stem}.json"
    if not raw_output.exists():
        matches = sorted(TRANSCRIPTS_DIR.glob(f"{project.processed_video.stem}*.json"))
        if not matches:
            raise FileNotFoundError(
                f"Whisper output not found for stem {project.processed_video.stem}"
            )
        raw_output = matches[-1]

    with raw_output.open("r", encoding="utf-8") as handle:
        transcript_data = json.load(handle)

    dump_json(transcript_data, project.transcript_json)
    text = transcript_data.get("text", "").strip()
    project.transcript_text.write_text(text, encoding="utf-8")

    srt_source = _resolve_whisper_artifact(project, "srt")
    shutil.copy2(srt_source, project.transcript_srt)
    LOGGER.info("Transcript saved to %s", project.transcript_json)
    return transcript_data


def _resolve_whisper_artifact(project: ProjectPaths, extension: str) -> Path:
    candidate = TRANSCRIPTS_DIR / f"{project.processed_video.stem}.{extension}"
    if candidate.exists():
        return candidate
    matches = sorted(TRANSCRIPTS_DIR.glob(f"{project.processed_video.stem}*.{extension}"))
    if matches:
        return matches[-1]
    raise FileNotFoundError(
        f"Whisper output not found for stem {project.processed_video.stem} ({extension})"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Whisper transcript for a slug.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", help="Optional language hint, e.g. en or vi.")
    parser.add_argument("--task", default="transcribe")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    source_video = INPUT_DIR / f"{args.slug}.mp4"
    project = ProjectPaths.from_slug(args.slug, source_video)
    setup_logging(project.log_file)
    transcribe_video(
        project,
        model=args.model,
        language=args.language,
        task=args.task,
    )


if __name__ == "__main__":
    main()
