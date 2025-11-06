#!/usr/bin/env python
"""Upload Whisper transcript text to Google Sheets via Apps Script."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    """Load environment variables from the project .env if present."""
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    load_dotenv()


def _read_transcript(srt_path: Path) -> str:
    """Convert an SRT file into plain text."""
    if not srt_path.exists():
        raise FileNotFoundError(f"Transcript file not found: {srt_path}")

    text_lines: list[str] = []
    for raw_line in srt_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        text_lines.append(line)

    transcript = "\n".join(text_lines).strip()
    if not transcript:
        raise ValueError(f"Transcript file {srt_path} produced empty text.")
    return transcript


def _upload_transcript(transcript: str, url: str, timeout: int = 30) -> tuple[int, str]:
    """Send the transcript text to the Apps Script endpoint."""
    payload = json.dumps({"transcript": transcript}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
            return status_code, body
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach endpoint: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a Whisper transcript as plain text to Google Sheets.",
    )
    parser.add_argument(
        "srt_path",
        type=Path,
        help="Path to the Whisper-generated SRT file.",
    )
    parser.add_argument(
        "--url",
        dest="url_override",
        help="Apps Script endpoint URL. Overrides GOOGLE_APPS_SCRIPT_API_URL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout (seconds) for the upload request. Default: 30.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env()

    endpoint_url = args.url_override
    if not endpoint_url:
        # Delay importing os until after dotenv runs so env vars are available.
        import os

        endpoint_url = os.getenv("GOOGLE_APPS_SCRIPT_API_URL", "").strip()

    if not endpoint_url:
        raise RuntimeError(
            "GOOGLE_APPS_SCRIPT_API_URL is not configured. "
            "Set it in python-be/.env or pass --url."
        )

    transcript_text = _read_transcript(Path(args.srt_path))
    status_code, response_body = _upload_transcript(
        transcript_text, endpoint_url, timeout=args.timeout
    )

    print(f"[INFO] Uploaded transcript (status {status_code}).")
    if response_body:
        print(f"[DEBUG] Response: {response_body}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
