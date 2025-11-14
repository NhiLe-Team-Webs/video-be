"""Generate a flexible edit plan via Gemini LLM."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

try:
    from .knowledge import KnowledgeService
except Exception:  # pragma: no cover - optional dependency at runtime
    KnowledgeService = None  # type: ignore[assignment]

TIMECODE_RE = re.compile(r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})$")
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

SFX_EXTENSIONS = {".mp3", ".wav", ".ogg"}

MAX_SCENE_CONTEXT_ITEMS = 32
MAX_BROLL_SUMMARY_ITEMS = 20
MAX_SFX_ITEMS_PER_CATEGORY = 5

HIGHLIGHT_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "so",
    "yet",
    "nor",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "without",
    "into",
    "onto",
    "about",
    "around",
    "over",
    "under",
    "after",
    "before",
    "between",
    "among",
    "through",
    "during",
    "within",
    "across",
    "against",
    "toward",
    "towards",
    "upon",
    "via",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
    "then",
    "than",
    "when",
    "where",
    "while",
    "because",
    "since",
    "if",
    "though",
    "although",
    "unless",
    "until",
    "very",
    "really",
    "just",
    "maybe",
    "perhaps",
    "quite",
    "rather",
    "some",
    "any",
    "each",
    "every",
    "either",
    "neither",
    "both",
    "many",
    "much",
    "few",
    "little",
    "more",
    "most",
    "less",
    "least",
    "own",
    "same",
    "such",
    "i",
    "me",
    "my",
    "mine",
    "myself",
    "we",
    "us",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "who",
    "whom",
    "whose",
    "which",
    "what",
    "whatever",
    "whoever",
    "whichever",
    "someone",
    "something",
    "anyone",
    "anything",
    "everyone",
    "everything",
    "not",
    "no",
    "yes",
    "ok",
    "okay",
    "uh",
    "um",
    "hmm",
    "ve",
    "re",
    "ll",
    "d",
    "s",
    "m",
}

_ALLOWED_CONNECTORS = {"of", "for", "and", "&", "in", "on", "vs", "versus", "to", "with"}
_COMMON_VERB_TOKENS = {
    "be",
    "am",
    "is",
    "are",
    "was",
    "were",
    "being",
    "been",
    "do",
    "does",
    "did",
    "doing",
    "have",
    "has",
    "had",
    "having",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    "need",
}

_TOKEN_SANITIZER = re.compile(r"\s+")
_ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")
_COMMON_VERB_TOKENS_LOWER = {token.lower() for token in _COMMON_VERB_TOKENS}
SRT_HIGHLIGHT_ID_RE = re.compile(r"^srt-(\d+)$", re.IGNORECASE)
SECTION_TITLE_SUFFIXES: tuple[str, ...] = (
    "Overview",
    "Insights",
    "Focus",
    "Spotlight",
    "Framework",
    "Recap",
    "Summary",
)


def format_section_title(highlight_id: str, base_phrase: str, *, fallback: str = "Key Theme") -> tuple[str, str]:
    """
    Returns a tuple of (display_text, keyword) for section titles, ensuring the visible
    text includes a descriptor so it will not mirror B-roll labels verbatim.
    """
    sanitized = sanitize_highlight_text(base_phrase) if base_phrase else ""
    if not sanitized:
        sanitized = fallback
    suffix_index = sum(ord(ch) for ch in highlight_id) if highlight_id else 0
    suffix = SECTION_TITLE_SUFFIXES[suffix_index % len(SECTION_TITLE_SUFFIXES)]
    lower_phrase = sanitized.lower()
    if suffix.lower() not in lower_phrase:
        display = f"{sanitized} {suffix}"
    else:
        display = sanitized
    keyword = display.upper()
    return display, keyword


def _clean_token(token: str) -> str:
    return _TOKEN_SANITIZER.sub(" ", token.strip())


def _trim_edge_connectors(tokens: list[str]) -> list[str]:
    result = list(tokens)
    while result and result[0].lower() in _ALLOWED_CONNECTORS:
        result.pop(0)
    while result and result[-1].lower() in _ALLOWED_CONNECTORS:
        result.pop()
    return result


def _filter_tokens_to_noun_phrase(tokens: list[str]) -> list[str]:
    selected: list[str] = []
    total = len(tokens)

    def _has_future_content(start: int) -> bool:
        for future_idx in range(start, total):
            candidate = tokens[future_idx].strip()
            if not candidate:
                continue
            lower = candidate.lower()
            if lower in _COMMON_VERB_TOKENS_LOWER:
                continue
            if not _ALNUM_PATTERN.search(candidate):
                continue
            return True
        return False

    for idx, token in enumerate(tokens):
        normalized = _clean_token(token)
        if not normalized:
            continue
        lower_token = normalized.lower()
        if lower_token in _ALLOWED_CONNECTORS:
            if selected and _has_future_content(idx + 1):
                selected.append(lower_token)
            continue
        if lower_token in _COMMON_VERB_TOKENS_LOWER:
            continue
        if not _ALNUM_PATTERN.search(normalized):
            continue
        selected.append(normalized)

    return _trim_edge_connectors(selected)


def filter_tokens_to_noun_phrase(tokens: list[str], max_tokens: int | None = None) -> list[str]:
    cleaned = [_clean_token(token) for token in tokens if _clean_token(token)]
    if not cleaned:
        return []

    filtered = _filter_tokens_to_noun_phrase(cleaned)
    if not filtered:
        filtered = cleaned

    if max_tokens is not None and max_tokens > 0:
        limited: list[str] = []
        content_count = 0
        for token in filtered:
            limited.append(token)
            if token.lower() not in _ALLOWED_CONNECTORS:
                content_count += 1
            if content_count >= max_tokens:
                break
        filtered = _trim_edge_connectors(limited) or filtered

    return filtered


def resolve_repo_root(start: Path | None = None) -> Path:
    """
    Walk upwards from the provided path (or this file) to find the repository root.
    The root is identified as the first ancestor containing an `assets` directory.
    """
    current = (start or Path(__file__)).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "assets").exists():
            return candidate
    return current


def load_json_if_exists(path: Path | None) -> Dict[str, Any]:
    """
    Loads a JSON file from the given path if it exists, otherwise returns an empty dictionary.
    Handles JSON decoding and OS errors gracefully.

    Args:
        path: The path to the JSON file.

    Returns:
        A dictionary containing the JSON data, or an empty dictionary if the file
        does not exist or cannot be parsed/read.
    """
    if not path:
        return {}
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        print(f"[WARN] Could not parse JSON file: {path}", file=sys.stderr)
    except OSError:
        print(f"[WARN] Could not read JSON file: {path}", file=sys.stderr)
    return {}


def sanitize_highlight_text(value: str) -> str:
    """
    Reduce highlight text to a compact noun phrase by removing filler words and verbs.
    Fallback to the original string if aggressive filtering would produce an empty result.
    """
    if not value:
        return value

    original = " ".join(value.strip().split())
    if not original:
        return original

    tokens = re.findall(r"[A-Za-z0-9\u00C0-\u017F]+", original)
    if not tokens:
        return original

    filtered = [token for token in tokens if token.lower() not in HIGHLIGHT_STOPWORDS]
    candidate_tokens = filtered if filtered else tokens
    noun_tokens = filter_tokens_to_noun_phrase(candidate_tokens, max_tokens=6)
    if noun_tokens:
        candidate_tokens = noun_tokens

    if len(candidate_tokens) < 2 and tokens:
        fallback_tokens = [
            token for token in tokens if token.lower() not in {"uh", "um", "ok", "okay", "hmm"}
        ]
        if len(fallback_tokens) >= 2:
            candidate_tokens = fallback_tokens[:4]
        elif tokens:
            candidate_tokens = tokens[:4]

    phrase = " ".join(candidate_tokens).strip()
    if not phrase:
        phrase = original

    if not phrase:
        return value.strip()

    # Keep original casing for acronyms, otherwise title-case for readability
    if phrase.isupper():
        return phrase

    words = phrase.split()
    normalized = " ".join(word if word.isupper() else word.capitalize() for word in words)
    if len(normalized) <= 1:
        return original
    if len(normalized.split()) == 1 and len(original.split()) >= 2:
        fallback = " ".join(token.capitalize() for token in tokens[:2])
        return fallback or normalized
    return normalized


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely converts a value to a float. If conversion fails, returns a default value.

    Args:
        value: The value to convert.
        default: The default value to return if conversion fails.

    Returns:
        The float representation of the value, or the default if conversion fails.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _humanize_sfx_description(relative_path: Path) -> str:
    """
    Generates a human-readable description for an SFX asset based on its relative path.
    For example, 'ui/pop.mp3' becomes 'UI: Pop'.

    Args:
        relative_path: The Path object representing the SFX asset's relative path.

    Returns:
        A human-readable string description of the SFX.
    """
    # Determine the category from the parent directory name
    category = relative_path.parent.name if relative_path.parent != Path(".") else "mix"
    # Extract the base name and replace separators with spaces
    base = relative_path.stem.replace("-", " ").replace("_", " ")
    # Capitalize category and base for better readability
    category_title = category.replace("-", " ").replace("_", " ").title()
    base_title = base.title()
    return f"{category_title}: {base_title}"


def discover_available_sfx() -> Dict[str, str]:
    """
    Discovers all available SFX files in the 'assets/sfx' directory and creates
    a dictionary mapping their relative paths (and prefixed paths) to human-readable descriptions.

    Returns:
        A dictionary where keys are SFX paths (e.g., 'ui/pop.mp3', 'assets/sfx/ui/pop.mp3')
        and values are their descriptions.
    """
    # Resolve the root directory of the repository
    root_dir = resolve_repo_root()
    sfx_dir = root_dir / "assets" / "sfx"
    available: Dict[str, str] = {}

    # If the SFX directory does not exist, return an empty dictionary
    if not sfx_dir.exists():
        return available

    # Iterate over all files in the SFX directory and its subdirectories
    for asset in sorted(sfx_dir.rglob("*")):
        # Skip if it's not a file or if the extension is not a recognized SFX extension
        if not asset.is_file() or asset.suffix.lower() not in SFX_EXTENSIONS:
            continue
        # Get the path relative to the SFX directory
        relative_path = asset.relative_to(sfx_dir)
        # Use POSIX-style path for consistency
        key = relative_path.as_posix()
        # Generate a human-readable description
        description = _humanize_sfx_description(relative_path)
        # Add both the relative path and the full prefixed path to the available SFX
        available[key] = description
        prefixed_key = f"assets/sfx/{key}"
        available[prefixed_key] = description

    return available


AVAILABLE_SFX: Dict[str, str] = discover_available_sfx() or {
    "ui/pop.mp3": "UI: Pop punchy nhấn mạnh",
    "whoosh/whoosh.mp3": "Whoosh chuyển cảnh mượt",
    "emphasis/ding.mp3": "Ding sạch cho số liệu quan trọng",
    "emotion/applause.mp3": "Applause nhanh cho thành tựu",
    "tech/camera-click.mp3": "Tiếng chụp ảnh nhấn mạnh demo",
}


def _build_sfx_lookup() -> Dict[str, str]:
    """
    Builds a lookup dictionary for SFX assets, allowing retrieval by various normalized keys
    (e.g., full path, filename, stem). This helps in robustly matching SFX names from LLM output.

    Returns:
        A dictionary mapping normalized SFX keys to their canonical paths.
    """
    lookup: Dict[str, str] = {}
    for key in AVAILABLE_SFX.keys():
        # Store the original key in lowercase
        lower_key = key.lower()
        lookup.setdefault(lower_key, key)
        # Store by filename (lowercase)
        name = Path(key).name.lower()
        lookup.setdefault(name, key)
        # Store by filename stem (lowercase, without extension)
        stem = Path(key).stem.lower()
        lookup.setdefault(stem, key)
    return lookup


SFX_LOOKUP = _build_sfx_lookup()
TRANSITION_TYPES = ["cut", "crossfade", "slide", "zoom", "scale", "rotate", "blur"]
TRANSITION_DIRECTIONS = ["left", "right", "up", "down"]
HIGHLIGHT_POSITIONS = ["bottom", "center"]
HIGHLIGHT_ANIMATIONS = [
    "fade",
    "zoom",
    "slide",
    "bounce",
    "float",
    "flip",
    "typewriter",
    "pulse",
    "spin",
    "pop",
]
HIGHLIGHT_VARIANTS = ["callout", "blurred", "brand", "cutaway", "typewriter"]
MAX_HIGHLIGHTS = 18
DEFAULT_HIGHLIGHT_DURATION = 2.6


@dataclass
class SrtEntry:
    index: int
    start: str
    end: str
    text: str

    @property
    def text_one_line(self) -> str:
        return " ".join(line.strip() for line in self.text.splitlines() if line.strip())


def seconds_from_timecode(value: str) -> float:
    """
    Converts an SRT timecode string (HH:MM:SS,mmm) into total seconds (float).

    Args:
        value: The timecode string.

    Returns:
        The total time in seconds as a float.
    """
    # Split the timecode into hours, minutes, and the remaining part (seconds,milliseconds)
    hours, minutes, remainder = value.split(":")
    # Split the remainder into seconds and milliseconds
    seconds, millis = remainder.split(",")
    # Calculate total seconds
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_srt(path: Path, *, max_entries: int | None = None) -> List[SrtEntry]:
    """
    Parses an SRT file and extracts subtitle entries.

    Args:
        path: The path to the SRT file.
        max_entries: Optional. The maximum number of entries to parse.

    Returns:
        A list of SrtEntry objects.
    """
    content = path.read_text(encoding="utf-8")
    # Split the content into blocks based on double newlines
    blocks = re.split(r"\n\s*\n", content.strip())
    entries: List[SrtEntry] = []
    for block in blocks:
        # Filter out empty lines from the block
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            # A valid SRT block needs at least an index and a timecode line
            continue
        try:
            # The first line is usually the index
            idx = int(lines[0])
        except ValueError:
            # Fallback to sequential index if parsing fails
            idx = len(entries) + 1
        # The second line is the timecode
        match = TIMECODE_RE.match(lines[1])
        if not match:
            continue
        # The rest of the lines form the text
        text = "\n".join(lines[2:]) if len(lines) > 2 else ""
        entries.append(SrtEntry(index=idx, start=match.group("start"), end=match.group("end"), text=text))
        # Stop parsing if max_entries limit is reached
        if max_entries and len(entries) >= max_entries:
            break
    return entries


def _format_available(values: Iterable[str]) -> str:
    """
    Formats an iterable of strings into a comma-separated string.

    Args:
        values: An iterable of strings.

    Returns:
        A single string with values joined by ", ".
    """
    return ", ".join(values)


def summarize_scene_map(scene_map: Dict[str, Any], limit: int = MAX_SCENE_CONTEXT_ITEMS) -> str:
    """
    Generates a concise summary of the scene map, including overall statistics and
    details for a limited number of initial segments. This summary is used to provide
    context to the LLM.

    Args:
        scene_map: The dictionary representing the scene map.
        limit: The maximum number of segments to include in the detailed summary.

    Returns:
        A formatted string summarizing the scene map.
    """
    segments = scene_map.get("segments") or []
    if not segments:
        return ""

    lines: List[str] = []
    summary = scene_map.get("summary") or {}
    summary_parts: List[str] = []

    # Add overall summary statistics
    total_segments = summary.get("totalSegments")
    if total_segments is not None:
        summary_parts.append(f"segments={total_segments}")
    duration = summary.get("estimatedDurationSeconds")
    if duration is not None:
        summary_parts.append(f"duration~{_safe_float(duration):.1f}s")
    highlight_segments = summary.get("highlightSegments")
    if highlight_segments is not None:
        summary_parts.append(f"highlight>=threshold={highlight_segments}")
    cta_segments = summary.get("ctaSegments")
    if cta_segments is not None:
        summary_parts.append(f"cta={cta_segments}")
    motion_freq = summary.get("motionFrequencyConfig")
    if motion_freq is not None:
        summary_parts.append(f"motion_frequency={_safe_float(motion_freq):.2f}")
    highlight_rate = summary.get("highlightRateConfig")
    if highlight_rate is not None:
        summary_parts.append(f"highlight_rate={_safe_float(highlight_rate):.2f}")

    top_topics = summary.get("topTopics") or []
    if top_topics:
        topic_summary = ", ".join(
            f"{topic_entry.get('topic','?')}({topic_entry.get('count',0)})"
            for topic_entry in top_topics[:6]
        )
        summary_parts.append(f"top_topics={topic_summary}")

    if summary_parts:
        lines.append("Summary: " + " | ".join(summary_parts))

    # Add detailed summary for individual segments (up to limit)
    for idx, segment in enumerate(segments[:limit], start=1):
        seg_id = segment.get("id", idx)
        start = _safe_float(segment.get("start"))
        end = _safe_float(segment.get("end"))
        topics = ", ".join(segment.get("topics", [])[:3]) or "-"
        emotion = segment.get("emotion", "neutral")
        highlight_score = _safe_float(segment.get("highlightScore"))
        motion_candidates = ", ".join(segment.get("motionCandidates", [])[:3]) or "-"
        sfx_hints = ", ".join(segment.get("sfxHints", [])[:3]) or "-"
        flags: List[str] = []
        if segment.get("cta"):
            flags.append("cta")
        if segment.get("parallaxEligible"):
            flags.append("parallax")
        flag_suffix = f" | flags={','.join(flags)}" if flags else ""
        lines.append(
            f"{seg_id}: {start:.2f}-{end:.2f}s | topics={topics} | emotion={emotion} "
            f"| highlight={highlight_score:.2f} | motion={motion_candidates} | sfx={sfx_hints}{flag_suffix}"
        )

    # Indicate if more segments are omitted
    remaining = len(segments) - limit
    if remaining > 0:
        lines.append(f"... {remaining} additional segments omitted")

    return "\n".join(lines)


def summarize_broll_catalog(catalog: Dict[str, Any], limit: int = MAX_BROLL_SUMMARY_ITEMS) -> str:
    """
    Generates a concise summary of the B-roll catalog, including details for a
    limited number of initial items. This summary is used to provide context to the LLM.

    Args:
        catalog: The dictionary representing the B-roll catalog.
        limit: The maximum number of B-roll items to include in the summary.

    Returns:
        A formatted string summarizing the B-roll catalog.
    """
    items = catalog.get("items") or []
    if not items:
        return ""

    lines: List[str] = []
    for item in items[:limit]:
        item_id = item.get("id", "?")
        media_type = item.get("mediaType", "video")
        orientation = item.get("orientation", "landscape")
        topics = ", ".join(item.get("topics", [])[:3]) or "-"
        mood = ", ".join(item.get("mood", [])[:2]) or "-"
        usage = ", ".join(item.get("recommendedUsage", [])[:2]) or "-"
        lines.append(
            f"{item_id}: {media_type}/{orientation} | topics={topics} | mood={mood} | usage={usage}"
        )

    remaining = len(items) - limit
    if remaining > 0:
        lines.append(f"... {remaining} additional B-roll items available")

    return "\n".join(lines)


def summarize_sfx_catalog(catalog: Dict[str, Any], max_items: int = MAX_SFX_ITEMS_PER_CATEGORY) -> str:
    """
    Generates a concise summary of the SFX catalog, categorizing SFX and listing
    a limited number of items per category. This summary is used to provide context to the LLM.

    Args:
        catalog: The dictionary representing the SFX catalog.
        max_items: The maximum number of SFX items to list per category.

    Returns:
        A formatted string summarizing the SFX catalog.
    """
    categories = catalog.get("categories") or []
    if not categories:
        return ""

    lines: List[str] = []
    for category in categories:
        label = category.get("label") or category.get("id") or "misc"
        items = category.get("items") or []
        if not items:
            continue

        entries: List[str] = []
        for item in items[:max_items]:
            item_id = item.get("id", "?")
            usage = item.get("usage") or []
            usage_text = "/".join(usage[:2]) if usage else ""
            if usage_text:
                entries.append(f"{item_id} ({usage_text})")
            else:
                entries.append(item_id)

        remaining = len(items) - max_items
        if remaining > 0:
            entries.append(f"+{remaining} more")

        lines.append(f"{label}: {', '.join(entries)}")

    return "\n".join(lines)


def summarize_motion_rules(motion_rules: Dict[str, Any]) -> str:
    """
    Generates a concise summary of the motion rules, including target frequencies
    and highlight thresholds. This summary is used to provide context to the LLM.

    Args:
        motion_rules: The dictionary representing the motion rules.

    Returns:
        A formatted string summarizing the motion rules.
    """
    if not motion_rules:
        return ""

    lines: List[str] = []
    motion_freq = motion_rules.get("motion_frequency")
    highlight_rate = motion_rules.get("highlight_rate")
    if motion_freq is not None:
        lines.append(f"Target motion frequency <= {motion_freq}")
    if highlight_rate is not None:
        lines.append(f"Highlight threshold >= {highlight_rate}")

    # Summarize motion cue keywords
    for key, value in motion_rules.items():
        if key.endswith("_keywords") and isinstance(value, list):
            cue = key.replace("_keywords", "").replace("_", " ")
            lines.append(f"{cue}: {', '.join(value)}")

    return "\n".join(lines)


def build_prompt(
    entries: Iterable[SrtEntry],
    *,
    extra_instructions: str | None = None,
    scene_map: Dict[str, Any] | None = None,
    broll_catalog: Dict[str, Any] | None = None,
    sfx_catalog: Dict[str, Any] | None = None,
    motion_rules: Dict[str, Any] | None = None,
    client_manifest: Dict[str, Any] | None = None,
    knowledge_service: Optional["KnowledgeService"] = None,
) -> str:
    """
    Constructs the full prompt for the Gemini LLM, including transcript segments,
    schema hints, rules, and supplemental context from various catalogs.

    Args:
        entries: An iterable of SrtEntry objects representing the transcript.
        extra_instructions: Optional. Additional free-form instructions from the user.
        scene_map: Optional. Dictionary containing scene metadata.
        broll_catalog: Optional. Dictionary containing B-roll asset catalog.
        sfx_catalog: Optional. Dictionary containing SFX asset catalog.
        motion_rules: Optional. Dictionary containing motion cue rules.
        client_manifest: Optional. Dictionary containing frontend templates/effects.

    Returns:
        A formatted string representing the complete prompt for the LLM.
    """
    # Format transcript entries into a readable section
    timeline_lines = [
        f"{entry.index}. [{entry.start} -> {entry.end}] {entry.text_one_line}"
        for entry in entries
    ]
    transcript_section = "\n".join(timeline_lines)

    # Define a schema hint to guide the LLM's output structure
    schema_hint = {
        "segments": [
            {
                "id": "intro",
                "sourceStart": 0.0,
                "duration": 6.4,
                "transitionOut": {"type": "crossfade", "duration": 0.6},
            },
            {
                "id": "demo",
                "sourceStart": 6.4,
                "duration": 9.1,
                "transitionIn": {"type": "crossfade", "duration": 0.6},
                "transitionOut": {"type": "slide", "duration": 0.5, "direction": "left"},
            },
        ],
        "highlights": [
            {
                "id": "hook",
                "text": "KEY IDEA: Stay consistent",
                "start": 2.4,
                "duration": 2.6,
                "position": "center",
                "animation": "zoom",
                "sfx": "ui/pop.mp3",
                "volume": 0.75,
            }
        ],
    }

    schema_hint_json = json.dumps(schema_hint, indent=2)

    # Format available options for rules section
    sfx_names = _format_available(sorted(AVAILABLE_SFX.keys()))
    sfx_notes = "; ".join(f"{name}: {desc}" for name, desc in AVAILABLE_SFX.items())
    transition_types = _format_available(TRANSITION_TYPES)
    transition_directions = _format_available(TRANSITION_DIRECTIONS)
    highlight_positions = _format_available(HIGHLIGHT_POSITIONS)
    highlight_animations = _format_available(HIGHLIGHT_ANIMATIONS)

    # Base instruction for the LLM
    instruction_text = (
        "You are a detail-oriented video editor. Build a Remotion JSON plan with concise segments, smooth transitions, and purposeful highlights/SFX. "
        "Maintain a cinematic rhythm and avoid overusing effects."
    )
    if extra_instructions:
        instruction_text += f" Extra guidance from user: {extra_instructions.strip()}"

    # Define a list of rules for the LLM to follow
    rules_lines = [
        "- `segments` describe consecutive portions of the trimmed video with `sourceStart` (seconds) and `duration`. Use `label` for short context if helpful.",
        f"- `transitionIn`/`transitionOut` types may be: {transition_types}; slides can add `direction` ({transition_directions}); zoom/scale/rotate/blur may include `intensity` between 0.1 and 0.35.",
        "- Trim or merge sentences when silence exceeds ~0.7s unless a pause is intentionally required.",
        f"- Aim for up to {MAX_HIGHLIGHTS} standout highlights; keep each roughly 2-4 seconds and anchor every one to a crisp verb-free noun phrase from the transcript.",
        "- Maintain breathing room—skip filler chatter, but don't hesitate to capture each meaningful beat the speaker emphasises.",
        f"- Populate `highlights` with `type` (noteBox/typewriter/sectionTitle/icon/etc.), `text`, `start`, `duration`, plus `position` ({highlight_positions}) and `animation` ({highlight_animations}). Icons may sit centre; all large text callouts stay `position: \"bottom\"`.",
        "- Keep highlight placements to three slots: a bold bottom banner for the key noun phrase, plus optional concise supporting phrases at `supportingTexts.topLeft` and `supportingTexts.topRight`.",
        "- For textual highlights, keep `text`/`keyword` to a meaningful noun phrase (no verbs, no conjunction lists). Favour compact 2-3 word noun clusters; if you cannot form one, skip the highlight. Always anchor the main phrase at the bottom centre using `layout: \"bottom\"` (or set `layout` to `left`/`right`/`dual` with `supportingTexts.topLeft`/`supportingTexts.topRight` while keeping the bottom text).",
        "- When emitting `sectionTitle` entries, append a high-level descriptor (Overview/Insights/Focus/etc.) so the visible text never duplicates a raw clip name or B-roll label.",
        "- Only surface language that actually appears in the transcript (allowing singular/plural variations); extract noun phrases from the spoken sentence and avoid invented wording.",
        "- If you cannot find a clear noun phrase for a candidate moment, skip the highlight instead of forcing one.",
        "- Align every highlight `start` and `duration` to the transcript timestamps—snap to the underlying SRT entries and leave at least 0.2s between independent highlights so different positions never overlap simultaneously.",
        "- When both left and right supporting texts are present, ensure the right side appears second by leaving the left stagger at 0 and adding `staggerRight: 2` (seconds).",
        "- Insert centre-screen `sectionTitle` cards at major topic shifts (roughly every big idea). Give them an `overlay` tint (for example `{ \"tint\": \"#030303\", \"opacity\": 0.72 }`) and a short SFX accent from the catalog.",
        "- Provide `motionCue` (zoomIn/zoomOut) on segments that carry high-impact numbers, definitions, or section cards so the camera reinforces emphasis.",
        "- For `type: \"icon\"` include `name` (short label) and optional icon/colors/animation; attach SFX when it enhances energy.",
        "- When assigning B-roll, set `mode: \"full\"` so footage fills the frame beneath overlays and animations.",
        f"- Always pick SFX from `assets/sfx` with relative paths (for example assets/sfx/ui/pop.mp3). Available options: {sfx_names}. Key notes: {sfx_notes}.",
        "- When highlights include SFX, align `start` with the moment and set `volume` between 0-1 if needed.",
        "- Match B-roll subjects to the spoken context. Favour catalog IDs where keywords overlap the transcript tokens inside the same time range.",
        "- Segments must touch end-to-start with no gaps in the source timeline.",
        "- Respond with JSON inside a single fenced code block.",
    ]

    # Add conditional rules based on provided context
    highlight_rate_value = None
    if motion_rules:
        highlight_rate_value = motion_rules.get("highlight_rate")
        rules_lines.append("- Motion cues must follow the keywords and frequency found in the motion rules context.")
    if highlight_rate_value is not None:
        rules_lines.append(
            f"- Treat segments with `highlightScore` >= {highlight_rate_value} as prime candidates for visual emphasis, B-roll, and SFX."
        )
    if scene_map:
        rules_lines.append("- Use the scene map insights below to align B-roll, CTA moments, motion cues, and SFX hints per segment.")
    if broll_catalog:
        rules_lines.append("- Choose B-roll IDs from the catalog context, matching topics/mood and keeping framing consistent.")
    if client_manifest:
        rules_lines.append(
            "- Align segments with the FE templates and effects listed in the client manifest when recommending overlays, typography, or decorative assets."
        )

    # Build supplemental context sections
    context_sections: List[str] = []
    if scene_map:
        scene_summary = summarize_scene_map(scene_map)
        if scene_summary:
            context_sections.append("Scene map insights:\n" + scene_summary)
    if broll_catalog:
        broll_summary = summarize_broll_catalog(broll_catalog)
        if broll_summary:
            context_sections.append("B-roll catalog (id / media / topics):\n" + broll_summary)
    if motion_rules:
        motion_summary = summarize_motion_rules(motion_rules)
        if motion_summary:
            context_sections.append("Motion cue rules:\n" + motion_summary)
    if sfx_catalog:
        sfx_summary = summarize_sfx_catalog(sfx_catalog)
        if sfx_summary:
            context_sections.append("SFX catalog overview:\n" + sfx_summary)
    if client_manifest:
        templates = client_manifest.get("templates", [])[:5]
        effects = client_manifest.get("effects", {})
        audio = client_manifest.get("audio", {})
        audio_lines: List[str] = []
        if audio.get("bgm"):
            audio_lines.append(f"BGM preference: {audio['bgm']}")
        if audio.get("sfxFallback"):
            audio_lines.append(f"SFX fallback: {audio['sfxFallback']}")
        if templates:
            template_lines = []
            for template in templates:
                template_lines.append(
                    f"{template.get('id','?')}: {template.get('name','')} - {template.get('description','')}"
                )
            context_sections.append(
                "FE templates (id / name / description):\n" + "\n".join(template_lines)
            )
        if effects:
            effect_keys = ", ".join(list(effects.keys())[:12])
            context_sections.append("Available FE effects keys:\n" + effect_keys)
        if audio_lines:
            context_sections.append("Audio guidance from client manifest:\n" + "\n".join(audio_lines))

    # Assemble all parts of the prompt
    prompt_parts = [
        instruction_text,
        "Use this schema template (update with real values):",
        schema_hint_json,
        "Rules:",
        "\n".join(rules_lines),
    ]
    knowledge_snippets: List[str] = []
    if knowledge_service is not None:
        transcript_excerpt = " ".join(entry.text_one_line for entry in entries)[:1500]
        knowledge_snippets = knowledge_service.guideline_summaries(
            transcript_excerpt, top_k=5
        )
    if knowledge_snippets:
        context_sections.append(
            "Knowledge base guidelines:\n" + "\n".join(f"- {snippet}" for snippet in knowledge_snippets)
        )

    context_block = "\n\n".join(context_sections)

    if context_block:
        prompt_parts.append("Supplemental context:\n" + context_block)
    prompt_parts.append("Transcript segments (ordered):\n" + transcript_section)

    # Join prompt parts and ensure a trailing newline
    prompt = "\n\n".join(part for part in prompt_parts if part) + "\n"
    return prompt


def extract_plan_json(text: str) -> dict:
    """
    Extracts a JSON object from a given text, typically an LLM response.
    It looks for JSON within fenced code blocks first, then attempts to parse the raw text.

    Args:
        text: The input string, potentially containing a JSON block.

    Returns:
        The parsed JSON dictionary.

    Raises:
        ValueError: If no valid JSON can be extracted from the text.
    """
    candidates: List[str] = []
    # Search for JSON within fenced code blocks (```json ... ```)
    for match in JSON_BLOCK_RE.finditer(text):
        candidates.append(match.group(1).strip())
    if not candidates:
        # If no fenced block is found, assume the entire text might be JSON
        candidates.append(text.strip())

    last_error: Exception | None = None
    for candidate in candidates:
        # Try parsing with and without carriage returns
        for cleaned in (candidate, candidate.replace("\r", "")):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
    # Strip markdown code block delimiters
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON from LLM response: {exc}")


def ensure_float(value: Any, default: float = 0.0) -> float:
    """
    Ensures a value is a float, providing a default if conversion fails.

    Args:
        value: The value to convert.
        default: The default float value to return on failure.

    Returns:
        The converted float or the default value.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ensure_bool(value: Any, default: bool = False) -> bool:
    """
    Ensures a value is a boolean, handling various string/numeric representations.

    Args:
        value: The value to convert.
        default: The default boolean value to return on failure or empty string.

    Returns:
        The converted boolean or the default value.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return default
    return bool(value) if value is not None else default


def normalize_segment_kind(value: Any) -> str | None:
    """
    Normalizes a segment 'kind' value to a standard string ('broll' or 'normal').

    Args:
        value: The raw segment kind value.

    Returns:
        "broll", "normal", or None if the input is invalid.
    """
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        if not normalized:
            return None
        if normalized in {"broll", "brollplaceholder", "placeholderbroll"}:
            return "broll"
        # If "broll" is part of the normalized string, assume it's a broll segment
        return "broll" if "broll" in normalized else "normal"
    return "normal"


def normalize_sfx_name(value: Any) -> str | None:
    """
    Normalizes an SFX name from various input formats to a canonical path
    (e.g., 'assets/sfx/ui/pop.mp3') using the SFX_LOOKUP.

    Args:
        value: The raw SFX name or path.

    Returns:
        The normalized SFX path or None if no match is found.
    """
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    # Normalize path separators and remove leading './'
    candidate_normalized = candidate.replace("\\", "/").lstrip("./")
    # Remove 'assets/' or 'sfx/' prefixes if present
    if candidate_normalized.startswith("assets/"):
        candidate_normalized = candidate_normalized[7:]
    if candidate_normalized.startswith("sfx/"):
        candidate_normalized = candidate_normalized[4:]

    # Check various forms of the candidate against the SFX lookup
    checks = [
        candidate_normalized.lower(),  # Full normalized path
        Path(candidate_normalized).name.lower(),  # Filename only
        Path(candidate_normalized).stem.lower(),  # Filename stem (without extension)
    ]

    for key in checks:
        if not key:
            continue
        match = SFX_LOOKUP.get(key)
        if match:
            return match

    return None


def normalize_camera_movement(value: Any) -> str | None:
    """
    Normalizes camera movement descriptions to standard values ("zoomIn", "zoomOut").

    Args:
        value: The raw camera movement description.

    Returns:
        "zoomIn", "zoomOut", or None if no match.
    """
    if value is None:
        return None
    normalized = str(value).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if normalized in {"zoomin", "pushin", "push"}:
        return "zoomIn"
    if normalized in {"zoomout", "pullback", "pull"}:
        return "zoomOut"
    return None


def normalize_transition(value: Any) -> Dict[str, Any] | None:
    """
    Normalizes a raw transition definition into a structured dictionary.
    Handles various input formats for type, direction, duration, and intensity.

    Args:
        value: The raw transition definition (string or dictionary).

    Returns:
        A dictionary representing the normalized transition, or None if the input is invalid.
    """
    if value is None:
        return None

    transition_type = None
    direction = None
    duration_value = None
    intensity_value = None

    if isinstance(value, str):
        transition_type = value.lower()
    elif isinstance(value, dict):
        transition_type = (value.get("type") or value.get("style") or "").lower()
        direction = (value.get("direction") or value.get("dir") or "").lower() or None
        duration_value = ensure_float(value.get("duration", value.get("length", 0.0)), 0.0)
        intensity_value = ensure_float(value.get("intensity", value.get("strength", 0.0)), 0.0)
    else:
        return None

    # Map common transition aliases to standard types
    if transition_type in {"fade", "dissolve"}:
        transition_type = "crossfade"
    elif transition_type in {"slide-left", "slide-right", "slide-up", "slide-down"}:
        for candidate in TRANSITION_DIRECTIONS:
            if candidate in transition_type:
                direction = candidate
                break
        transition_type = "slide"
    elif transition_type in {"zoom-in", "zoom-out", "push", "push-in", "push-out", "punch", "punch-in", "punch-out"}:
        transition_type = "zoom"
    elif transition_type in {"scale-up", "scale-down", "grow", "shrink"}:
        transition_type = "scale"
    elif transition_type in {"spin", "twist", "turn"}:
        transition_type = "rotate"
    elif transition_type in {"focus", "defocus", "dream", "soft-focus", "soften"}:
        transition_type = "blur"

    # Default to "cut" if the type is not recognized
    if transition_type not in TRANSITION_TYPES:
        transition_type = "cut"

    # "cut" transitions don't need further properties
    if transition_type == "cut":
        return {"type": "cut"}

    # Set default and clamp duration
    duration_value = duration_value if duration_value and duration_value > 0 else 0.6
    duration_value = max(0.1, min(duration_value, 3.0))

    # Clamp and round intensity if provided
    if intensity_value is not None and intensity_value <= 0:
        intensity_value = None
    if intensity_value is not None:
        intensity_value = round(max(0.05, min(float(intensity_value), 0.6)), 3)

    transition: Dict[str, Any] = {
        "type": transition_type,
        "duration": round(duration_value, 3),
    }

    # Add direction for slide transitions
    if transition_type == "slide" and direction in TRANSITION_DIRECTIONS:
        transition["direction"] = direction

    # Add intensity for specific transition types
    if transition_type in {"zoom", "scale", "rotate", "blur"} and intensity_value:
        transition["intensity"] = intensity_value

    return transition


def normalize_highlight_item(
    raw: Dict[str, Any],
    index: int,
    srt_lookup: Dict[int, SrtEntry] | None = None,
) -> Dict[str, Any] | None:
    """
    Normalizes a raw highlight item definition into a structured dictionary.
    Handles various input formats for type, text, timing, position, animation, and other properties.

    Args:
        raw: The raw highlight item dictionary.
        index: The index of the highlight, used for generating a default ID.
        srt_lookup: Optional mapping of SRT indices to entries for snapping timing/text.

    Returns:
        A dictionary representing the normalized highlight item, or None if the input is invalid.
    """
    if not isinstance(raw, dict):
        return None

    highlight_id = str(raw.get("id") or f"highlight-{index + 1:02d}")

    highlight_type_raw = raw.get("type") or raw.get("kind")
    highlight_type: str | None = None
    if isinstance(highlight_type_raw, str):
        type_key = highlight_type_raw.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        type_map = {
            "highlight": "noteBox",
            "caption": "noteBox",
            "callout": "noteBox",
            "notebox": "noteBox",
            "notecard": "noteBox",
            "quote": "noteBox",
            "typewriter": "typewriter",
            "section": "sectionTitle",
            "sectiontitle": "sectionTitle",
            "titlecard": "sectionTitle",
            "chapter": "sectionTitle",
            "icon": "icon",
            "iconhighlight": "icon",
        }
        highlight_type = type_map.get(type_key, highlight_type_raw.strip())

    # Extract and strip various text fields
    text_raw = (raw.get("text") or raw.get("caption") or "").strip()
    title_raw = (raw.get("title") or "").strip()
    subtitle_raw = (raw.get("subtitle") or "").strip()
    badge_raw = (raw.get("badge") or "").strip()
    name_raw = (raw.get("name") or raw.get("label") or "").strip()
    icon_value = (raw.get("icon") or raw.get("iconName") or "").strip()

    srt_entry: SrtEntry | None = None
    if srt_lookup:
        match = SRT_HIGHLIGHT_ID_RE.match(highlight_id.lower())
        if match:
            try:
                srt_idx = int(match.group(1))
            except ValueError:
                srt_idx = None
            if srt_idx is not None:
                srt_entry = srt_lookup.get(srt_idx)

    srt_text = srt_entry.text_one_line.strip() if srt_entry else ""

    # Determine if it's an icon type if not explicitly set
    has_icon_marker = bool(icon_value or (name_raw and not highlight_type))
    resolved_highlight_type = highlight_type or ("icon" if has_icon_marker else None)

    # If no content is provided, this is not a valid highlight
    if not any([text_raw, title_raw, subtitle_raw, badge_raw, name_raw, icon_value, srt_text]):
        return None
    if not text_raw and srt_text:
        text_raw = srt_text

    # Normalize start time
    start = ensure_float(raw.get("start", raw.get("time", 0.0)), 0.0)
    start = max(0.0, start)

    # Normalize duration, with fallback and clamping
    duration = ensure_float(raw.get("duration", raw.get("length", 0.0)), DEFAULT_HIGHLIGHT_DURATION)
    if duration <= 0:
        end_time = ensure_float(raw.get("end"))
        if end_time > start:
            duration = end_time - start
    if duration <= 0:
        duration = DEFAULT_HIGHLIGHT_DURATION
    duration = max(1.5, min(duration, 5.0))

    if srt_entry:
        srt_start = seconds_from_timecode(srt_entry.start)
        srt_end = seconds_from_timecode(srt_entry.end)
        srt_duration = max(0.0, srt_end - srt_start)
        if srt_duration > 0:
            start = srt_start
            duration = srt_duration
            duration = max(1.5, min(duration, 5.0))
    start = max(0.0, start)

    # Determine highlight positioning defaults
    is_icon_highlight = resolved_highlight_type == "icon"
    default_position = "center" if is_icon_highlight else "bottom"
    position = (raw.get("position") or raw.get("placement") or default_position).lower()
    if position not in HIGHLIGHT_POSITIONS or not is_icon_highlight:
        position = default_position

    # Normalize animation, with default based on type
    animation_raw = raw.get("animation") or raw.get("style") or raw.get("motion")
    animation_default = "pop" if resolved_highlight_type == "icon" else "fade"
    animation_key = ""
    if isinstance(animation_raw, str):
        animation_key = animation_raw.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    animation_map = {
        "fade": "fade", "fadein": "fade",
        "zoom": "zoom", "zoomin": "zoom",
        "punch": "pop", "punchin": "pop", "pop": "pop", "popin": "pop",
        "bounce": "bounce",
        "float": "float", "floating": "float",
        "flip": "flip",
        "spin": "spin", "rotate": "spin",
        "typewriter": "typewriter",
        "pulse": "pulse", "breath": "pulse", "beat": "pulse",
        "slide": "slide", "slideup": "slide", "slidedown": "slide", "slideleft": "slide", "slideright": "slide",
    }
    animation = animation_map.get(animation_key, animation_default)

    # Construct the base highlight dictionary
    sanitized_text = ""
    if not is_icon_highlight:
        keyword_raw = raw.get("keyword")
        keyword_text = keyword_raw.strip() if isinstance(keyword_raw, str) else ""
        primary_candidates = [
            text_raw,
            srt_text,
            keyword_text,
            title_raw,
            subtitle_raw,
        ]
        for candidate in primary_candidates:
            if not candidate:
                continue
            sanitized_candidate = sanitize_highlight_text(candidate)
            if sanitized_candidate:
                sanitized_text = sanitized_candidate
                break

    highlight: Dict[str, Any] = {
        "id": highlight_id,
        "start": round(start, 3),
        "duration": round(duration, 3),
        "position": position,
        "animation": animation,
    }

    assigned_type = resolved_highlight_type or ("icon" if is_icon_highlight else None)
    if not assigned_type:
        if sanitized_text:
            assigned_type = "noteBox"
        elif text_raw:
            assigned_type = "noteBox"

    if assigned_type:
        highlight["type"] = assigned_type

    if assigned_type == "noteBox":
        if not sanitized_text:
            return None
        highlight["text"] = sanitized_text
        highlight["keyword"] = sanitized_text
        importance_raw = raw.get("importance")
        if isinstance(importance_raw, str) and importance_raw.strip():
            highlight["importance"] = importance_raw.strip().lower()
        else:
            highlight.setdefault("importance", "primary")
        highlight["showBottom"] = True
        highlight.setdefault("safeBottom", 0.18)
        highlight.setdefault("safeInsetHorizontal", 0.08)
    elif assigned_type == "sectionTitle":
        base_phrase = title_raw or text_raw or keyword_text or sanitized_text or srt_text
        display_text, keyword_value = format_section_title(highlight_id, base_phrase or "")
        highlight["text"] = display_text
        highlight["keyword"] = keyword_value
    elif assigned_type == "icon" and text_raw:
        highlight["text"] = text_raw

    if title_raw:
        highlight["title"] = title_raw
    if subtitle_raw:
        highlight["subtitle"] = subtitle_raw
    if badge_raw:
        highlight["badge"] = badge_raw
    if name_raw:
        highlight["name"] = name_raw
    if icon_value:
        highlight["icon"] = icon_value

    # Add asset path if present
    asset = (raw.get("asset") or raw.get("media") or "").strip()
    if asset:
        highlight["asset"] = asset

    # Normalize and add variant
    variant_raw = raw.get("variant") or raw.get("styleVariant")
    if variant_raw:
        variant_key = str(variant_raw).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
        variant_map = {
            "callout": "callout", "default": "callout", "bubble": "callout",
            "blur": "blurred", "blurred": "blurred", "blurredbackdrop": "blurred",
            "brand": "brand", "brandpanel": "brand",
            "cutaway": "cutaway", "black": "cutaway",
            "typewriter": "typewriter",
        }
        normalized_variant = variant_map.get(variant_key)
        if normalized_variant in HIGHLIGHT_VARIANTS:
            highlight["variant"] = normalized_variant

    # Normalize and add SFX
    sfx_value = raw.get("sfx") or raw.get("asset") or raw.get("sound")
    sfx_name = normalize_sfx_name(sfx_value)
    if sfx_name:
        # Ensure SFX path is prefixed correctly
        if not sfx_name.lower().startswith("assets/"):
            if sfx_name.lower().startswith("sfx/"):
                sfx_name = f"assets/{sfx_name}"
            else:
                sfx_name = f"assets/sfx/{sfx_name}"
        highlight["sfx"] = sfx_name

    # Add color properties if present
    accent_color = raw.get("accentColor") or raw.get("accent")
    if isinstance(accent_color, str) and accent_color.strip():
        highlight["accentColor"] = accent_color.strip()

    background_color = raw.get("backgroundColor") or raw.get("background") or raw.get("bg")
    if isinstance(background_color, str) and background_color.strip():
        highlight["backgroundColor"] = background_color.strip()

    icon_color = raw.get("iconColor") or raw.get("iconColour")
    if isinstance(icon_color, str) and icon_color.strip():
        highlight["iconColor"] = icon_color.strip()

    # Normalize supporting text layout for dual highlights
    supporting_texts: Dict[str, str] = {}

    def coerce_supporting(value: Any) -> str | None:
        if isinstance(value, str):
            cleaned = sanitize_highlight_text(value.strip())
            return cleaned or None
        return None

    raw_supporting = raw.get("supportingTexts")
    if isinstance(raw_supporting, dict):
        left_candidate = (
            raw_supporting.get("topLeft")
            or raw_supporting.get("top_left")
            or raw_supporting.get("left")
            or raw_supporting.get("primary")
        )
        right_candidate = (
            raw_supporting.get("topRight")
            or raw_supporting.get("top_right")
            or raw_supporting.get("right")
            or raw_supporting.get("secondary")
        )
        left_text = coerce_supporting(left_candidate)
        right_text = coerce_supporting(right_candidate)
        if left_text:
            supporting_texts["topLeft"] = left_text
        if right_text:
            supporting_texts["topRight"] = right_text

    # Support alternate schemas (items array, side-specific keys)
    if not supporting_texts:
        items = raw.get("items")
        if isinstance(items, list):
            if len(items) > 0:
                left_text = coerce_supporting(items[0])
                if left_text:
                    supporting_texts["topLeft"] = left_text
            if len(items) > 1:
                right_text = coerce_supporting(items[1])
                if right_text:
                    supporting_texts["topRight"] = right_text

    left_fallback = (
        raw.get("supportingLeft")
        or raw.get("supportLeft")
        or raw.get("supporting")
        or raw.get("keywordSecondary")
        or raw.get("left")
    )
    right_fallback = raw.get("supportingRight") or raw.get("supportRight") or raw.get("right")
    left_text = coerce_supporting(left_fallback)
    right_text = coerce_supporting(right_fallback)

    if left_text:
        supporting_texts.setdefault("topLeft", left_text)
    if right_text:
        supporting_texts.setdefault("topRight", right_text)

    if supporting_texts:
        highlight["supportingTexts"] = supporting_texts

    layout_raw = raw.get("layout") or raw.get("arrangement") or raw.get("alignment")
    layout_value: str | None = None
    if isinstance(layout_raw, str):
        layout_candidate = layout_raw.strip().lower()
        if layout_candidate in {"left", "right", "dual", "bottom"}:
            layout_value = layout_candidate
        elif layout_candidate in {"pair", "split"}:
            layout_value = "dual"

    if not layout_value:
        if "topLeft" in supporting_texts and "topRight" in supporting_texts:
            layout_value = "dual"
        elif "topLeft" in supporting_texts:
            layout_value = "left"
        elif "topRight" in supporting_texts:
            layout_value = "right"
        elif not is_icon_highlight and sanitized_text:
            layout_value = "bottom"

    if layout_value:
        highlight["layout"] = layout_value
        if layout_value in {"left", "right", "dual"} and sanitized_text:
            highlight["showBottom"] = True

    # Add side alignment (legacy support)
    side = (raw.get("side") or "").strip().lower()
    if side in {"top", "bottom", "left", "right"}:
        highlight["side"] = side

    if supporting_texts:
        highlight.setdefault("staggerLeft", 0.0)
        if "topRight" in supporting_texts:
            highlight["staggerRight"] = ensure_float(raw.get("staggerRight"), 2.0) or 2.0


    # Add radius if valid
    radius = raw.get("radius")
    if radius is not None:
        try:
            radius_float = float(radius)
        except (TypeError, ValueError):
            radius_float = None
        if radius_float is not None and radius_float > 0:
            highlight["radius"] = round(radius_float, 3)

    # Add volume if valid
    volume = raw.get("volume")
    if volume is not None:
        try:
            volume_float = float(volume)
        except (TypeError, ValueError):
            volume_float = None
        if volume_float is not None:
            volume_float = max(0.0, min(volume_float, 1.0))
            highlight["volume"] = round(volume_float, 3)

    return highlight


def normalize_plan(
    plan: Dict[str, Any],
    *,
    srt_entries: Iterable[SrtEntry] | None = None,
) -> Dict[str, Any]:
    """
    Normalizes the entire plan dictionary, processing segments and highlights.
    This function ensures consistency and applies default values where necessary.

    Args:
        plan: The raw plan dictionary from the LLM.
        srt_entries: Optional collection of parsed SRT entries used for snapping highlight timing.

    Returns:
        A normalized plan dictionary.

    Raises:
        ValueError: If the input plan is not a dictionary.
    """
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object.")

    srt_lookup: Dict[int, SrtEntry] = {}
    if srt_entries:
        srt_lookup = {
            entry.index: entry
            for entry in srt_entries
            if isinstance(entry, SrtEntry)
        }

    segment_items: List[tuple[float, Dict[str, Any]]] = []
    raw_segments = plan.get("segments")
    if isinstance(raw_segments, list):
        for index, raw_segment in enumerate(raw_segments):
            if not isinstance(raw_segment, dict):
                continue
            
            # Normalize sourceStart and duration
            source_start = ensure_float(
                raw_segment.get("sourceStart", raw_segment.get("start", 0.0)),
                0.0,
            )
            duration = ensure_float(raw_segment.get("duration"))
            if duration <= 0:
                end_value = ensure_float(raw_segment.get("end"))
                start_value = ensure_float(raw_segment.get("start", source_start))
                if end_value > start_value:
                    duration = end_value - start_value
            if duration <= 0:
                length_value = ensure_float(raw_segment.get("length"))
                if length_value > 0:
                    duration = length_value
            if duration <= 0:
                continue

            segment_plan: Dict[str, Any] = {
                "id": str(raw_segment.get("id") or f"segment-{index + 1:02d}"),
                "sourceStart": round(source_start, 3),
                "duration": round(duration, 3),
            }

            # Tạm thời vô hiệu hóa gắn nhãn segment `broll` để tránh chèn placeholder B-roll.
            # if "kind" in raw_segment:
            #     kind_value = normalize_segment_kind(raw_segment.get("kind"))
            #     if kind_value:
            #         segment_plan["kind"] = kind_value

            # Add label if present
            label = (raw_segment.get("label") or raw_segment.get("title") or "").strip()
            if label:
                segment_plan["label"] = label

            # Add title if present
            title_value = raw_segment.get("title")
            if isinstance(title_value, str):
                title_clean = title_value.strip()
                if title_clean:
                    segment_plan["title"] = title_clean

            # Normalize silenceAfter property
            silence_after_raw = None
            for key in ("silenceAfter", "silence_after"):
                if key in raw_segment:
                    silence_after_raw = raw_segment.get(key)
                    break
            if silence_after_raw is not None:
                segment_plan["silenceAfter"] = ensure_bool(silence_after_raw)
            else:
                segment_plan["silenceAfter"] = False

            # Normalize gapAfter property
            gap_after_raw = None
            for key in ("gapAfter", "gap_after"):
                if key in raw_segment:
                    gap_after_raw = raw_segment.get(key)
                    break
            if gap_after_raw is not None:
                segment_plan["gapAfter"] = ensure_bool(gap_after_raw)

            # Normalize playbackRate
            playback_raw = raw_segment.get("playbackRate", raw_segment.get("speed"))
            if playback_raw is not None:
                playback_rate = ensure_float(playback_raw, 1.0)
                if playback_rate <= 0:
                    playback_rate = 1.0
                if abs(playback_rate - 1.0) > 1e-3:
                    segment_plan["playbackRate"] = round(playback_rate, 3)

            # Normalize transitionIn
            transition_in = normalize_transition(
                raw_segment.get("transitionIn")
                or raw_segment.get("transition_in")
                or raw_segment.get("enterTransition")
            )
            if transition_in:
                segment_plan["transitionIn"] = transition_in

            # Normalize transitionOut
            transition_out = normalize_transition(
                raw_segment.get("transitionOut")
                or raw_segment.get("transition_out")
                or raw_segment.get("exitTransition")
            )
            if transition_out:
                segment_plan["transitionOut"] = transition_out

            # Normalize cameraMovement
            metadata_raw = raw_segment.get("metadata")
            metadata_camera = metadata_raw.get("cameraMovement") if isinstance(metadata_raw, dict) else None
            camera_movement = normalize_camera_movement(
                raw_segment.get("cameraMovement")
                or raw_segment.get("camera_movement")
                or metadata_camera
            )
            if camera_movement:
                segment_plan["cameraMovement"] = camera_movement

            # Add metadata if present
            if isinstance(metadata_raw, dict) and metadata_raw:
                segment_plan["metadata"] = metadata_raw

            # Store timeline start for sorting
            timeline_start = ensure_float(
                raw_segment.get("timelineStart", raw_segment.get("timeline_start")),
                source_start,
            )
            segment_items.append((timeline_start, segment_plan))

    # Sort segments by timeline start and source start
    segment_items.sort(key=lambda item: (item[0], item[1]["sourceStart"]))
    normalized_segments = [item[1] for item in segment_items]

    # Process raw highlights
    raw_highlights: List[Any] = []
    if isinstance(plan.get("highlights"), list):
        raw_highlights = list(plan["highlights"])
    elif isinstance(plan.get("actions"), list): # Support older "actions" key
        for action in plan.get("actions", []):
            if not isinstance(action, dict):
                continue
            action_type = (action.get("type") or action.get("kind") or "").lower()
            if action_type in {"caption", "highlight", "icon", "notebox", "typewriter", "section", "sectiontitle"}:
                raw_highlights.append(action)

    normalized_highlights: List[Dict[str, Any]] = []
    for idx, raw_highlight in enumerate(raw_highlights):
        normalized = normalize_highlight_item(raw_highlight, idx, srt_lookup=srt_lookup)
        if normalized:
            normalized_highlights.append(normalized)
        if len(normalized_highlights) >= MAX_HIGHLIGHTS:
            break

    # Sort highlights by start time
    normalized_highlights.sort(key=lambda item: item.get("start", 0.0))

    normalized_plan: Dict[str, Any] = {
        "segments": normalized_segments,
        "highlights": normalized_highlights,
    }

    # Add meta information if present
    if "meta" in plan:
        normalized_plan["meta"] = plan["meta"]

    return normalized_plan


def configure_client(model_name: str | None = None) -> genai.GenerativeModel:
    """
    Configures and returns a Gemini GenerativeModel client.
    Loads API key from .env file or environment variables.

    Args:
        model_name: Optional. The name of the Gemini model to use. Defaults to "gemini-1.5-flash".

    Returns:
        A configured google.generativeai.GenerativeModel instance.

    Raises:
        RuntimeError: If GEMINI_API_KEY is not found.
    """
    # Load environment variables from .env files
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")
    load_dotenv()  # load defaults if present

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY. Add it to .env or environment variables.")

    genai.configure(api_key=api_key)
    resolved_model = model_name or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return genai.GenerativeModel(resolved_model)


def dump_plan(plan: dict, output_path: Path) -> None:
    """
    Dumps the generated plan to a JSON file with pretty-printing.
    Ensures the output directory exists.

    Args:
        plan: The plan dictionary to save.
        output_path: The path to the output JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2)
        handle.write("\n")


def main(argv: List[str] | None = None) -> int:
    """
    Main entry point for the script. Parses arguments, builds the prompt,
    calls the Gemini LLM, normalizes the response, and saves the plan.

    Args:
        argv: Optional. A list of command-line arguments. Defaults to sys.argv.

    Returns:
        An exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(description="Generate edit plan with Gemini")
    parser.add_argument("srt_path", type=Path, help="Input SRT transcript")
    parser.add_argument("output_plan", type=Path, help="Destination JSON plan file")
    parser.add_argument("--model", dest="model_name", help="Override Gemini model name")
    parser.add_argument(
        "--max-entries",
        type=int,
        default=160,
        help="Limit number of SRT entries sent to Gemini",
    )
    parser.add_argument(
        "--extra",
        dest="extra_instructions",
        help="Optional free-form instructions appended to the prompt",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling Gemini",
    )
    parser.add_argument(
        "--scene-map",
        dest="scene_map_path",
        type=Path,
        help="Optional scene_map.json to enrich the prompt with precomputed metadata",
    )
    parser.add_argument(
        "--client-manifest",
        dest="client_manifest_path",
        type=Path,
        help="Optional clientManifest.json with frontend templates and effects",
    )

    args = parser.parse_args(argv)

    # Validate SRT input path
    if not args.srt_path.exists():
        parser.error(f"SRT file not found: {args.srt_path}")

    # Parse SRT and validate entries
    entries = parse_srt(args.srt_path, max_entries=args.max_entries)
    if not entries:
        parser.error("No valid entries found in SRT")

    # Load optional scene map data
    scene_map_data: Dict[str, Any] | None = None
    if args.scene_map_path:
        if not args.scene_map_path.exists():
            parser.error(f"Scene map not found: {args.scene_map_path}")
        scene_map_data = load_json_if_exists(args.scene_map_path)
        if not scene_map_data:
            print(f"[WARN] Scene map is empty or invalid: {args.scene_map_path}", file=sys.stderr)
            scene_map_data = None

    # Load optional client manifest data
    client_manifest: Dict[str, Any] | None = None
    if args.client_manifest_path:
        if not args.client_manifest_path.exists():
            parser.error(f"Client manifest not found: {args.client_manifest_path}")
        client_manifest = load_json_if_exists(args.client_manifest_path)
        if not client_manifest:
            print(
                f"[WARN] Client manifest is empty or invalid: {args.client_manifest_path}",
                file=sys.stderr,
            )
            client_manifest = None

    # Resolve repository root and load asset catalogs/motion rules
    repo_root = resolve_repo_root()
    broll_catalog = load_json_if_exists(repo_root / "assets" / "broll_catalog.json") or None
    sfx_catalog = load_json_if_exists(repo_root / "assets" / "sfx_catalog.json") or None
    motion_rules = load_json_if_exists(repo_root / "assets" / "motion_rules.json") or None

    # Initialize KnowledgeService
    knowledge_service: Optional[KnowledgeService] = None
    if KnowledgeService is not None:
        try:
            knowledge_service = KnowledgeService()
        except Exception as exc:
            print(f"[WARN] Could not initialize KnowledgeService: {exc}", file=sys.stderr)

    base_include_scene_map = bool(scene_map_data)
    has_catalogs = any([broll_catalog, sfx_catalog, motion_rules])
    base_include_catalogs = has_catalogs

    # Build the default prompt for dry-run or first attempt
    prompt_cache: Dict[tuple[int, bool, bool], str] = {}
    base_key = (len(entries), base_include_scene_map, base_include_catalogs)
    prompt_cache[base_key] = build_prompt(
        entries,
        extra_instructions=args.extra_instructions,
        scene_map=scene_map_data if base_include_scene_map else None,
        broll_catalog=broll_catalog if base_include_catalogs else None,
        sfx_catalog=sfx_catalog if base_include_catalogs else None,
        motion_rules=motion_rules if base_include_catalogs else None,
        client_manifest=client_manifest,
        knowledge_service=knowledge_service,
    )

    # If dry-run, print prompt and exit
    if args.dry_run:
        print(prompt_cache[base_key])
        return 0

    # Prepare fallback configurations to mitigate Gemini timeouts
    configs: List[Dict[str, Any]] = []
    seen_configs: set[tuple[int, bool, bool]] = set()

    def register_config(limit: int, include_scene: bool, include_catalogs: bool, label: str) -> None:
        limit = max(1, min(limit, len(entries)))
        include_scene = include_scene and base_include_scene_map
        include_catalogs_flag = include_catalogs and base_include_catalogs
        key = (limit, include_scene, include_catalogs_flag)
        if key in seen_configs:
            return
        seen_configs.add(key)
        configs.append(
            {
                "limit": limit,
                "include_scene_map": include_scene,
                "include_catalogs": include_catalogs_flag,
                "label": label,
            }
        )

    register_config(len(entries), True, True, "full prompt")
    if len(entries) > 140:
        register_config(140, True, True, "140 entries")
    if len(entries) > 120:
        register_config(120, True, True, "120 entries")
    register_config(min(len(entries), 90), False, True, "no scene map")
    register_config(min(len(entries), 70), False, False, "minimal context")

    # Configure Gemini client
    try:
        model = configure_client(args.model_name)
    except Exception as exc:  # noqa: BLE001 - surface friendly message
        print(f"[ERROR] {exc}")
        return 1

    raw_text: Optional[str] = None
    used_entries: List[SrtEntry] = entries
    last_error: Optional[Exception] = None

    for config in configs:
        entry_limit = config["limit"]
        include_scene_map = config["include_scene_map"]
        include_catalogs_flag = config["include_catalogs"]
        label = config["label"]

        subset_entries = entries[:entry_limit]
        cache_key = (entry_limit, include_scene_map, include_catalogs_flag)
        if cache_key not in prompt_cache:
            prompt_cache[cache_key] = build_prompt(
                subset_entries,
                extra_instructions=args.extra_instructions,
                scene_map=scene_map_data if include_scene_map else None,
                broll_catalog=broll_catalog if include_catalogs_flag else None,
                sfx_catalog=sfx_catalog if include_catalogs_flag else None,
                motion_rules=motion_rules if include_catalogs_flag else None,
                client_manifest=client_manifest,
                knowledge_service=knowledge_service,
            )
        attempt_prompt = prompt_cache[cache_key]

        try:
            response = model.generate_content(attempt_prompt)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            error_text = str(exc)
            print(
                f"[WARN] Gemini attempt failed ({label}, entries={entry_limit}): {error_text}"
            )
            error_text_lower = error_text.lower()
            if "deadline" in error_text_lower or "504" in error_text_lower:
                continue
            break

        raw_text = getattr(response, "text", None)
        if not raw_text:
            last_error = RuntimeError("Empty response from Gemini")  # type: ignore[assignment]
            print(f"[WARN] Empty response from Gemini ({label})")
            raw_text = None
            continue

        used_entries = subset_entries
        break

    if raw_text is None:
        if last_error is not None:
            print(f"[ERROR] Gemini request failed after retries: {last_error}")
        else:
            print("[ERROR] Gemini request failed: unknown error")
        return 1

    # Extract and normalize the plan from LLM response
    try:
        plan = extract_plan_json(raw_text)
        plan = normalize_plan(plan, srt_entries=used_entries)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        debug_path = args.output_plan.parent / f"{args.output_plan.stem}.raw_response.txt"
        try:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(raw_text, encoding="utf-8")
            print(f"[INFO] Raw Gemini response saved to {debug_path}")
        except OSError as write_exc:
            print(f"[WARN] Could not persist Gemini response for inspection: {write_exc}", file=sys.stderr)
        return 1

    # Dump the final plan to output file
    dump_plan(plan, args.output_plan)
    print(f"[PLAN] Saved Gemini plan to {args.output_plan}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
