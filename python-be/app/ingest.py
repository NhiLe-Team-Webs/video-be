from __future__ import annotations

import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_SOURCE_VIDEO, ensure_runtime_directories
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import dump_json, slugify, timestamp_slug

LOGGER = logging.getLogger(__name__)


def ingest_video(source: Path, slug: str | None = None) -> ProjectPaths:
    ensure_runtime_directories()
    if not source.exists():
        raise FileNotFoundError(f"Source video not found: {source}")

    slug = slug or timestamp_slug(source.stem)
    project = ProjectPaths.from_slug(slug, source_video=source)

    project.ingested_video.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != project.ingested_video.resolve():
        shutil.copy2(source, project.ingested_video)
    else:
        LOGGER.info("Source already located at %s, skipping copy.", project.ingested_video)

    metadata = {
        "slug": project.slug,
        "source": str(source),
        "ingested_video": str(project.ingested_video),
        "copied_at": datetime.utcnow().isoformat() + "Z",
        "size_bytes": project.ingested_video.stat().st_size,
    }
    dump_json(metadata, project.metadata_file)
    LOGGER.info("Ingested %s -> %s", source, project.ingested_video)
    return project


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest a raw video into the pipeline.")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_VIDEO,
        help="Path to the source footage (default: %(default)s)",
    )
    parser.add_argument(
        "--slug",
        type=str,
        help="Optional slug. If omitted a timestamp slug will be generated.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    slug = slugify(args.slug) if args.slug else None
    project = ProjectPaths.from_slug(slug or timestamp_slug(args.source.stem), args.source)
    setup_logging(project.log_file)
    ingest_video(args.source, slug=project.slug)


if __name__ == "__main__":
    main()
