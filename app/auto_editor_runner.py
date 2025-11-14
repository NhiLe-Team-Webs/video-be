from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import INPUT_DIR, ensure_runtime_directories
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import dump_json, run_command

LOGGER = logging.getLogger(__name__)


def run_auto_editor(
    project: ProjectPaths,
    *,
    silence_threshold: float = 0.06,
    margin: str = "0.2s,0.4s",
    silent_speed: float = 1.5,
    video_speed: float = 1.0,
) -> Path:
    ensure_runtime_directories()
    if not project.ingested_video.exists():
        raise FileNotFoundError(f"Ingested video missing: {project.ingested_video}")

    command = [
        sys.executable,
        "-m",
        "auto_editor",
        str(project.ingested_video),
        "-o",
        str(project.processed_video),
        "--edit",
        f"audio:threshold={silence_threshold}",
        "--margin",
        margin,
        "--silent-speed",
        str(silent_speed),
        "--video-speed",
        str(video_speed),
        "--video-codec",
        "libx264",
        "--audio-codec",
        "aac",
    ]
    run_command(command, logger=LOGGER, capture=False)
    metadata = {
        "slug": project.slug,
        "input": str(project.ingested_video),
        "output": str(project.processed_video),
        "silence_threshold": silence_threshold,
        "margin": margin,
        "silent_speed": silent_speed,
        "video_speed": video_speed,
    }
    dump_json(metadata, project.processed_metadata)
    LOGGER.info("Auto-Editor output saved to %s", project.processed_video)
    return project.processed_video


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Auto-Editor for a project slug.")
    parser.add_argument("--slug", required=True, help="Project slug to process.")
    parser.add_argument("--silence-threshold", type=float, default=0.06)
    parser.add_argument("--margin", default="0.2s,0.4s")
    parser.add_argument("--silent-speed", type=float, default=1.5)
    parser.add_argument("--video-speed", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    source_video = INPUT_DIR / f"{args.slug}.mp4"
    project = ProjectPaths.from_slug(args.slug, source_video)
    setup_logging(project.log_file)
    run_auto_editor(
        project,
        silence_threshold=args.silence_threshold,
        margin=args.margin,
        silent_speed=args.silent_speed,
        video_speed=args.video_speed,
    )


if __name__ == "__main__":
    main()
