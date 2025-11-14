from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import auto_editor_runner, exporter, ingest, planner_llm, transcriber
from .config import DEFAULT_SOURCE_VIDEO, ensure_runtime_directories
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import slugify, timestamp_slug

LOGGER = logging.getLogger(__name__)


def run_pipeline(
    source: Path,
    *,
    slug: str | None = None,
    plan_model: str | None = None,
    plan_max_entries: int | None = None,
    plan_extra: str | None = None,
    plan_scene_map: Path | None = None,
    plan_dry_run: bool = False,
    whisper_model: str = "small",
    whisper_language: str | None = None,
) -> ProjectPaths:
    ensure_runtime_directories()
    slug = slug or timestamp_slug(source.stem)
    slug = slugify(slug)
    project = ProjectPaths.from_slug(slug, source)
    setup_logging(project.log_file)

    LOGGER.info("=== Pipeline start | slug=%s ===", project.slug)
    ingest_project = ingest.ingest_video(source, slug=project.slug)
    auto_editor_runner.run_auto_editor(ingest_project)
    LOGGER.info("=== Starting transcription ===")
    transcriber.transcribe_video(
        ingest_project,
        model=whisper_model,
        language=whisper_language,
    )
    LOGGER.info("=== Transcription completed ===")
    planner_llm.generate_plan(
        ingest_project,
        model=plan_model,
        max_entries=plan_max_entries,
        extra_instructions=plan_extra,
        scene_map=plan_scene_map,
        dry_run=plan_dry_run,
    )
    exporter.export_artifacts(ingest_project)
    LOGGER.info("=== Pipeline completed | slug=%s ===", project.slug)
    return ingest_project


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full local pipeline.")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_VIDEO,
        help="Source video file. Default: %(default)s",
    )
    parser.add_argument("--slug", help="Optional slug (default: auto based on timestamp).")
    parser.add_argument(
        "--plan-model",
        help="Gemini model override for plan_generation.make_plan.py.",
    )
    parser.add_argument(
        "--plan-max-entries",
        type=int,
        help="Limit number of SRT rows passed to the planner.",
    )
    parser.add_argument(
        "--plan-extra",
        help="Extra instruction string appended to the planner prompt.",
    )
    parser.add_argument(
        "--plan-scene-map",
        type=Path,
        help="Optional path to scene_map.json.",
    )
    parser.add_argument(
        "--plan-dry-run",
        action="store_true",
        help="Only print the prompt (no Gemini call).",
    )
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-language")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    run_pipeline(
        args.source,
        slug=args.slug,
        plan_model=args.plan_model,
        plan_max_entries=args.plan_max_entries,
        plan_extra=args.plan_extra,
        plan_scene_map=args.plan_scene_map,
        plan_dry_run=args.plan_dry_run,
        whisper_model=args.whisper_model,
        whisper_language=args.whisper_language,
    )


if __name__ == "__main__":
    main()
