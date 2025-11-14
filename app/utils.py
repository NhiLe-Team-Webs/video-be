from __future__ import annotations

import json
import logging
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

LOGGER = logging.getLogger(__name__)


def slugify(value: str) -> str:
    """Convert an arbitrary string into a filesystem-safe slug."""
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_"}:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    return "-".join(filter(None, slug.split("-"))) or "project"


def timestamp_slug(prefix: str = "project") -> str:
    """Generate a time-based slug with the provided prefix."""
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_prefix = slugify(prefix)
    return f"{safe_prefix}-{stamp}"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def format_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    logger: logging.Logger | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute a shell command and log stdout/stderr."""
    log = logger or LOGGER
    log.debug("Running command: %s", format_command(command))
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if capture:
        if completed.stdout:
            log.debug("[stdout]\n%s", completed.stdout.strip())
        if completed.stderr:
            log.debug("[stderr]\n%s", completed.stderr.strip())
    if completed.returncode != 0:
        error_message = f"Command failed ({completed.returncode}): {format_command(command)}"
        log.error(error_message)
        raise RuntimeError(error_message) from None
    return completed


def summarize_segments_text(segments: Iterable[dict], max_chars: int = 220) -> str:
    """Take a list of transcript segments and return a short text excerpt."""
    combined = " ".join(seg.get("text", "").strip() for seg in segments)
    combined = " ".join(combined.split())
    if len(combined) <= max_chars:
        return combined
    return combined[: max_chars - 3].rstrip() + "..."
