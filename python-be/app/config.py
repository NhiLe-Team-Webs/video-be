from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
PROCESSED_DIR = DATA_DIR / "processed"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
PLANS_DIR = DATA_DIR / "plans"
LOGS_DIR = DATA_DIR / "logs"
OUTPUTS_DIR = BASE_DIR / "outputs"

DEFAULT_SOURCE_VIDEO = INPUT_DIR / "footage.mp4"


def ensure_runtime_directories() -> None:
    """Create folders required by the pipeline."""
    for path in (
        DATA_DIR,
        INPUT_DIR,
        PROCESSED_DIR,
        TRANSCRIPTS_DIR,
        PLANS_DIR,
        LOGS_DIR,
        OUTPUTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def get_env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean flag from environment variables."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
