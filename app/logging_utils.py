from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(log_file: Path | None = None) -> None:
    """Configure root logger once per process."""
    log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    if root_logger.handlers:
        if log_file:
            _ensure_file_handler(root_logger, log_file, level=log_level)
        return

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        handlers=handlers,
    )


def _ensure_file_handler(logger: logging.Logger, log_file: Path, level: str) -> None:
    existing = [
        handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)
    ]
    if any(Path(handler.baseFilename) == log_file for handler in existing):
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fh.setLevel(getattr(logging, level, logging.INFO))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s | %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
