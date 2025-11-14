from __future__ import annotations

import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .config import INPUT_DIR
from .logging_utils import setup_logging
from .project import ProjectPaths
from .utils import dump_json

LOGGER = logging.getLogger(__name__)


def export_artifacts(project: ProjectPaths) -> Path:
    project.export_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "slug": project.slug,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "processed_video": None,
        "transcript_srt": None,
        "plan": None,
    }

    if project.processed_video.exists():
        processed_target = project.export_dir / project.processed_video.name
        shutil.copy2(project.processed_video, processed_target)
        manifest["processed_video"] = str(processed_target)

    if project.transcript_srt.exists():
        srt_target = project.export_dir / project.transcript_srt.name
        shutil.copy2(project.transcript_srt, srt_target)
        manifest["transcript_srt"] = str(srt_target)

    if project.plan_json.exists():
        plan_target = project.export_dir / "plan.json"
        shutil.copy2(project.plan_json, plan_target)
        manifest["plan"] = str(plan_target)

    manifest_path = project.export_dir / "manifest.json"
    dump_json(manifest, manifest_path)
    LOGGER.info("Artifacts exported to %s", project.export_dir)
    return project.export_dir


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export plan + assets for FE consumption.")
    parser.add_argument("--slug", required=True)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    source_video = INPUT_DIR / f"{args.slug}.mp4"
    project = ProjectPaths.from_slug(args.slug, source_video)
    setup_logging(project.log_file)
    export_artifacts(project)


if __name__ == "__main__":
    main()
