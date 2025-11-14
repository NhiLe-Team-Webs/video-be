from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import CLIENT_MANIFEST_PATH, INPUT_DIR
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import run_command

LOGGER = logging.getLogger(__name__)
MAKE_PLAN_MODULE = "plan_generation.make_plan"


def generate_plan(
    project: ProjectPaths,
    *,
    model: str | None = None,
    max_entries: int | None = None,
    extra_instructions: str | None = None,
    scene_map: Path | None = None,
    client_manifest: Path | None = None,
    dry_run: bool = False,
) -> Path:
    if not project.transcript_srt.exists():
        raise FileNotFoundError(f"SRT transcript missing: {project.transcript_srt}")

    command = [
        sys.executable,
        "-m",
        MAKE_PLAN_MODULE,
        str(project.transcript_srt),
        str(project.plan_json),
    ]
    if model:
        command.extend(["--model", model])
    if max_entries:
        command.extend(["--max-entries", str(max_entries)])
    if extra_instructions:
        command.extend(["--extra", extra_instructions])
    if scene_map:
        command.extend(["--scene-map", str(scene_map)])
    if client_manifest:
        command.extend(["--client-manifest", str(client_manifest)])
    if dry_run:
        command.append("--dry-run")

    LOGGER.info("Running plan_generation.make_plan for %s", project.slug)
    run_command(command, logger=LOGGER, capture=False)
    return project.plan_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run plan_generation.make_plan for a slug.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--model", help="Override Gemini model name.")
    parser.add_argument("--max-entries", type=int, help="Limit number of SRT entries in the prompt.")
    parser.add_argument("--extra", help="Extra instructions appended to the prompt.")
    parser.add_argument(
        "--scene-map",
        type=Path,
        help="Optional path to scene_map.json to enrich the prompt.",
    )
    parser.add_argument(
        "--client-manifest",
        type=Path,
        help="Path to clientManifest.json with frontend resources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling Gemini.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    source_video = INPUT_DIR / f"{args.slug}.mp4"
    project = ProjectPaths.from_slug(args.slug, source_video)
    setup_logging(project.log_file)
    generate_plan(
        project,
        model=args.model,
        max_entries=args.max_entries,
        extra_instructions=args.extra,
        scene_map=args.scene_map,
        client_manifest=args.client_manifest or CLIENT_MANIFEST_PATH,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
