#!/usr/bin/env python3
"""Generate a structured scene map from an SRT transcript.

The output consolidates timing, topical tags, highlight heuristics, CTA flags,
and motion cue candidates so downstream planners (LLM or deterministic rules)
can orchestrate B-roll, SFX, and animations consistently.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TIMECODE_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})$"
)
TOKEN_RE = re.compile(r"[A-Za-zÀ-ỹ0-9]+" , re.UNICODE)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class SrtEntry:
    """
    Represents a single entry in an SRT (SubRip) transcript file.

    Attributes:
        index: The sequential index of the SRT entry.
        start: The start timecode of the subtitle (HH:MM:SS,mmm).
        end: The end timecode of the subtitle (HH:MM:SS,mmm).
        text: The raw text content of the subtitle, potentially multi-line.
    """
    index: int
    start: str
    end: str
    text: str

    @property
    def text_one_line(self) -> str:
        """Returns the subtitle text as a single line, stripping extra whitespace."""
        return " ".join(line.strip() for line in self.text.splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def parse_timecode(value: str) -> float:
    """
    Parses an SRT timecode string (HH:MM:SS,mmm) into total seconds (float).

    Args:
        value: The timecode string.

    Returns:
        The total time in seconds as a float.
    """
    hours, minutes, remainder = value.split(":")
    seconds, millis = remainder.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000
    )


def parse_srt(path: Path) -> List[SrtEntry]:
    """
    Parses an SRT file and extracts subtitle entries.

    Args:
        path: The path to the SRT file.

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
        time_match = TIMECODE_RE.match(lines[1])
        if not time_match:
            continue

        # The rest of the lines form the text
        text = "\n".join(lines[2:]) if len(lines) > 2 else ""
        entries.append(
            SrtEntry(
                index=idx,
                start=time_match.group("start"),
                end=time_match.group("end"),
                text=text,
            )
        )

    return entries


def load_json(path: Path) -> Dict[str, Any]:
    """
    Loads a JSON file from the given path. Returns an empty dict if file not found.

    Args:
        path: The path to the JSON file.

    Returns:
        A dictionary containing the JSON data, or an empty dictionary if the file
        does not exist.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_topic_index(broll_catalog: Dict[str, Any]) -> Dict[str, Iterable[str]]:
    """
    Builds an index of topics and their associated keywords from the B-roll catalog.
    This index is used to detect topics within SRT entries.

    Args:
        broll_catalog: The dictionary representing the B-roll catalog.

    Returns:
        A dictionary where keys are normalized topics and values are sets of keywords
        associated with that topic.
    """
    topic_map: Dict[str, set[str]] = defaultdict(set)

    for item in broll_catalog.get("items", []):
        topics = item.get("topics") or []
        keywords = item.get("keywords") or []
        title = item.get("title", "")
        for topic in topics:
            topic_lower = topic.lower()
            # Add the topic itself as a keyword
            topic_map[topic_lower].add(topic_lower)
            # Add individual words from the topic as keywords
            for word in TOKEN_RE.findall(topic_lower):
                topic_map[topic_lower].add(word)
            # Add keywords from the item
            for keyword in keywords:
                for word in TOKEN_RE.findall(keyword.lower()):
                    topic_map[topic_lower].add(word)
            # Add words from the item's title
            for word in TOKEN_RE.findall(title.lower()):
                topic_map[topic_lower].add(word)

    return topic_map


def normalize_text(text: str) -> str:
    """
    Normalizes text by converting it to lowercase.

    Args:
        text: The input string.

    Returns:
        The lowercase version of the string.
    """
    return text.lower()


def tokenize(text: str) -> List[str]:
    """
    Tokenizes a given text into a list of lowercase words/tokens.

    Args:
        text: The input string.

    Returns:
        A list of lowercase tokens.
    """
    return [token.lower() for token in TOKEN_RE.findall(text)]


def detect_topics(text_tokens: List[str], topic_index: Dict[str, Iterable[str]]) -> Tuple[List[str], Dict[str, int]]:
    """
    Detects relevant topics in a list of text tokens using a pre-built topic index.

    Args:
        text_tokens: A list of lowercase tokens from the text.
        topic_index: A dictionary mapping topics to their associated keywords.

    Returns:
        A tuple containing:
        - A list of the top 5 detected topics (strings).
        - A dictionary mapping all detected topics to their scores.
    """
    counter: Dict[str, int] = {}
    text_token_set = Counter(text_tokens) # Count occurrences of each token in the text

    for topic, keywords in topic_index.items():
        # Score a topic based on how many of its keywords appear in the text
        score = sum(text_token_set.get(keyword, 0) for keyword in keywords)
        if score:
            counter[topic] = score

    # Sort topics by score in descending order
    sorted_topics = sorted(counter.items(), key=lambda item: item[1], reverse=True)
    return [topic for topic, _ in sorted_topics[:5]], counter


def detect_emotion(text: str) -> Tuple[str, List[str]]:
    """
    Detects the dominant emotion in a given text based on predefined keywords.

    Args:
        text: The input string.

    Returns:
        A tuple containing:
        - The detected dominant emotion ("hype", "confidence", "urgent", "serious", "informative", "surprise", or "neutral").
        - A list of keywords that triggered the emotion detection.
    """
    emotion_keywords = {
        "hype": ["amazing", "incredible", "thành công", "bứt phá", "đột phá", "celebrate", "thành tựu"],
        "confidence": ["tin tưởng", "chắc chắn", "đảm bảo", "guarantee", "bảo chứng"],
        "urgent": ["ngay", "ngay lập tức", "đừng bỏ lỡ", "right now", "deadline"],
        "serious": ["thách thức", "khó khăn", "trở ngại", "challenge"],
        "informative": ["thống kê", "số liệu", "data", "analytics"],
        "surprise": ["bất ngờ", "shock", "surprise", "không ngờ"],
    }

    hits: Dict[str, List[str]] = defaultdict(list)
    lowered = text.lower()
    for emotion, keywords in emotion_keywords.items():
        for keyword in keywords:
            if keyword in lowered:
                hits[emotion].append(keyword)

    if not hits:
        return "neutral", []

    # Determine the best emotion by the one with the most keyword hits
    best_emotion = max(hits.items(), key=lambda item: len(item[1]))[0]
    # Collect all triggered keywords
    all_hits = [kw for kws in hits.values() for kw in kws]
    return best_emotion, all_hits


def compute_highlight_score(text: str) -> Tuple[float, List[str]]:
    """
    Computes a highlight score for a given text based on keywords, numbers, and exclamations.

    Args:
        text: The input string.

    Returns:
        A tuple containing:
        - The calculated highlight score (float, clamped between 0.0 and 1.0).
        - A list of triggers (keywords, numbers) that contributed to the score.
    """
    highlight_keywords = [
        "quan trọng", "key", "điểm chính", "đặc biệt", "chìa khóa", "kết quả",
        "giải pháp", "lợi ích", "đột phá", "chiến lược", "số liệu", "target",
        "goal", "kêu gọi", "nhớ", "focus", "highlight",
    ]
    lowered = text.lower()
    hits = [kw for kw in highlight_keywords if kw in lowered]
    numbers = re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text) # Detect numbers (e.g., 10, 1.5, 20%)
    exclamations = lowered.count("!") + lowered.count("!!!") # Count exclamation marks

    score = 0.0
    score += min(len(hits) * 0.18, 0.6) # Max 0.6 from keywords
    score += min(len(numbers) * 0.15, 0.3) # Max 0.3 from numbers
    score += min(exclamations * 0.1, 0.2) # Max 0.2 from exclamations

    return min(score, 1.0), hits + numbers


def detect_cta(text: str) -> Tuple[bool, List[str]]:
    """
    Detects if a given text contains Call-to-Action (CTA) keywords.

    Args:
        text: The input string.

    Returns:
        A tuple containing:
        - A boolean indicating whether a CTA was detected.
        - A list of CTA keywords that were found.
    """
    cta_keywords = [
        "đăng ký", "subscribe", "theo dõi", "liên hệ", "đăng nhập", "đăng ký kênh",
        "call to action", "cta", "kêu gọi", "sign up", "subscribe now", "hành động ngay",
    ]
    lowered = text.lower()
    triggers = [kw for kw in cta_keywords if kw in lowered]
    return bool(triggers), triggers


def load_motion_rules(root: Path) -> Dict[str, Any]:
    """
    Loads motion rules from 'assets/motion_rules.json' and preprocesses motion keywords.

    Args:
        root: The root path of the repository.

    Returns:
        A dictionary containing motion rules, with an added '_motion_keywords' entry
        for quick lookup.
    """
    motion_path = root / "assets" / "motion_rules.json"
    motion_rules = load_json(motion_path)
    motion_keywords: Dict[str, List[str]] = {}

    for key, value in motion_rules.items():
        if key.endswith("_keywords") and isinstance(value, list):
            cue = key.replace("_keywords", "")
            motion_keywords[cue] = [item.lower() for item in value]

    motion_rules["_motion_keywords"] = motion_keywords
    return motion_rules


def detect_motion_cues(text: str, motion_rules: Dict[str, Any]) -> List[str]:
    """
    Detects potential motion cues in a given text based on predefined motion rules.

    Args:
        text: The input string.
        motion_rules: Dictionary containing motion cue rules, including preprocessed keywords.

    Returns:
        A list of detected motion cue names.
    """
    lowered = text.lower()
    candidates: List[str] = []
    motion_keywords: Dict[str, List[str]] = motion_rules.get("_motion_keywords", {})
    for cue, keywords in motion_keywords.items():
        if any(keyword in lowered for keyword in keywords):
            candidates.append(cue)
    return candidates


def detect_sfx_hints(text: str, highlight_score: float, cta_flag: bool) -> List[str]:
    """
    Detects potential SFX (sound effect) hints in a given text based on keywords,
    highlight score, and CTA flag.

    Args:
        text: The input string.
        highlight_score: The highlight score of the text.
        cta_flag: A boolean indicating if the text contains a CTA.

    Returns:
        A sorted list of unique SFX hint categories.
    """
    lowered = text.lower()
    hints: List[str] = []
    if highlight_score >= 0.55:
        hints.append("emphasis")
    if any(word in lowered for word in ["wow", "whoa", "bất ngờ", "surprise"]):
        hints.append("whoosh")
    if any(word in lowered for word in ["chúc mừng", "celebrate", "thành công", "chiến thắng"]):
        hints.append("emotion")
    if any(word in lowered for word in ["click", "nhấp", "button", "giao diện", "ứng dụng"]):
        hints.append("ui")
    if any(word in lowered for word in ["công nghệ", "ai", "digital", "robot"]):
        hints.append("tech")
    if cta_flag:
        hints.append("cta")
    if not hints and "?" in text:
        hints.append("question")
    return sorted(set(hints))


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------


def generate_scene_map(
    entries: List[SrtEntry],
    *,
    topic_index: Dict[str, Iterable[str]],
    motion_rules: Dict[str, Any],
    fps: float,
) -> Dict[str, Any]:
    """
    Generates a structured scene map from a list of SRT entries.
    Each scene in the map includes timing, topics, emotion, highlight scores,
    CTA flags, motion candidates, and SFX hints.

    Args:
        entries: A list of SrtEntry objects.
        topic_index: A pre-built index of topics and their keywords.
        motion_rules: Dictionary containing motion cue rules.
        fps: The frame rate of the video, used to calculate frame counts.

    Returns:
        A dictionary representing the complete scene map.
    """
    scenes: List[Dict[str, Any]] = []
    topic_totals: Counter[str] = Counter()
    highlight_count = 0
    cta_count = 0

    parallax_enabled = bool(motion_rules.get("parallax"))
    motion_frequency = float(motion_rules.get("motion_frequency", 0.0))
    highlight_rate = float(motion_rules.get("highlight_rate", 0.0))

    for entry in entries:
        text_one_line = entry.text_one_line
        text_tokens = tokenize(text_one_line)
        
        # Detect various metadata for the scene
        topics, topic_scores = detect_topics(text_tokens, topic_index)
        emotion, emotion_hits = detect_emotion(text_one_line)
        highlight_score, highlight_hits = compute_highlight_score(text_one_line)
        cta_flag, cta_hits = detect_cta(text_one_line)
        motion_candidates = detect_motion_cues(text_one_line, motion_rules)
        sfx_hints = detect_sfx_hints(text_one_line, highlight_score, cta_flag)

        # Calculate timing in seconds and frames
        start_seconds = parse_timecode(entry.start)
        end_seconds = parse_timecode(entry.end)
        duration = max(end_seconds - start_seconds, 0.0)

        start_frame = int(round(start_seconds * fps))
        end_frame = int(round(end_seconds * fps))

        # Update overall summary counts
        topic_totals.update(topics)
        if highlight_score >= highlight_rate:
            highlight_count += 1
        if cta_flag:
            cta_count += 1

        # Append the structured scene data
        scenes.append(
            {
                "id": entry.index,
                "start": start_seconds,
                "end": end_seconds,
                "duration": duration,
                "startFrame": start_frame,
                "endFrame": end_frame,
                "text": entry.text,
                "textOneLine": text_one_line,
                "tokens": text_tokens,
                "topics": topics,
                "topicScores": topic_scores,
                "emotion": emotion,
                "emotionTriggers": emotion_hits,
                "highlightScore": round(highlight_score, 4),
                "highlightTriggers": highlight_hits,
                "cta": cta_flag,
                "ctaTriggers": cta_hits,
                "motionCandidates": motion_candidates,
                "parallaxEligible": parallax_enabled and highlight_score >= highlight_rate,
                "sfxHints": sfx_hints,
                "rawTextLength": len(text_one_line),
            }
        )

    # Calculate total duration and build summary statistics
    total_duration = entries[-1].end if entries else "00:00:00,000"
    summary = {
        "totalSegments": len(scenes),
        "estimatedDurationSeconds": parse_timecode(total_duration) if entries else 0.0,
        "highlightSegments": highlight_count,
        "ctaSegments": cta_count,
        "motionFrequencyConfig": motion_frequency,
        "highlightRateConfig": highlight_rate,
        "topTopics": [
            {"topic": topic, "count": count}
            for topic, count in topic_totals.most_common(8)
        ],
    }

    # Return the complete scene map structure
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "fps": fps,
        "motionRules": {
            "parallax": parallax_enabled,
            "motion_frequency": motion_frequency,
            "highlight_rate": highlight_rate,
        },
        "segments": scenes,
        "summary": summary,
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def resolve_repo_root() -> Path:
    """
    Walk upwards from this file to locate the repository root.
    The repo root is identified by the first ancestor containing an `assets` directory.
    """
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "assets").exists():
            return candidate
    return current


def resolve_output_path(input_path: Path, output_arg: Path | None) -> Path:
    """
    Resolves the output path for the scene map JSON file.
    If an output argument is provided, it uses that; otherwise, it derives a path
    from the input SRT file (e.g., 'input.srt.scene_map.json').
    Ensures the parent directory for the output path exists.

    Args:
        input_path: The path to the input SRT file.
        output_arg: Optional. The user-specified output path.

    Returns:
        The resolved Path object for the output JSON file.
    """
    if output_arg:
        target = output_arg
    else:
        target = input_path.with_suffix(".scene_map.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def main(argv: List[str] | None = None) -> int:
    """
    Main entry point for the script. Parses arguments, loads SRT,
    generates the scene map, and writes it to a JSON file.

    Args:
        argv: Optional. A list of command-line arguments. Defaults to sys.argv.

    Returns:
        An exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(description="Generate scene_map.json from SRT transcript.")
    parser.add_argument("srt_path", type=Path, help="Input SRT file")
    parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        type=Path,
        help="Destination JSON path (default: alongside SRT)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Frame rate used to derive frame counts (default: 30)",
    )

    args = parser.parse_args(argv)
    
    # Validate SRT input path
    if not args.srt_path.exists():
        parser.error(f"SRT file not found: {args.srt_path}")

    # Parse SRT and validate entries
    entries = parse_srt(args.srt_path)
    if not entries:
        parser.error("No valid entries found in SRT")

    # Resolve repository root and load catalogs/rules
    repo_root = resolve_repo_root()
    broll_catalog = load_json(repo_root / "assets" / "broll_catalog.json")
    topic_index = build_topic_index(broll_catalog)

    motion_rules = load_motion_rules(repo_root)

    # Generate the scene map
    scene_map = generate_scene_map(
        entries,
        topic_index=topic_index,
        motion_rules=motion_rules,
        fps=args.fps,
    )

    # Add source and catalog information to the scene map
    scene_map["source"] = str(args.srt_path)
    scene_map["catalogs"] = {
        "broll": bool(broll_catalog),
        "motionRules": bool(motion_rules),
    }

    # Resolve and write the output scene map
    output_path = resolve_output_path(args.srt_path, args.output_path)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(scene_map, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"[SCENE MAP] Saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
