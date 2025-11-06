#!/usr/bin/env python3
"""Enrich an existing Gemini plan with B-roll assignments, motion cues and CTA highlights.

This post-processor consumes:
  - plan.json produced by make_plan_gemini.py
  - scene_map.json generated from the transcript
  - asset catalogs (B-roll, SFX) and motion rules

It augments each segment with:
  * `kind` (defaults to "normal")
  * `broll` metadata referencing items from assets/broll_catalog.json when appropriate
  * `motionCue` in camelCase respecting configured frequency limits
  * optional `notes` describing auto decisions (useful for debugging)

It also:
  * appends a CTA highlight if the scene map flagged any CTA segment but the plan lacks one
  * reports timing gaps between consecutive segments
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import nltk  # type: ignore
    from nltk.corpus import stopwords  # type: ignore
    from nltk.tokenize import word_tokenize  # type: ignore
    from nltk.tag import pos_tag  # type: ignore
except ImportError:
    nltk = None  # type: ignore[assignment]
    stopwords = None  # type: ignore[assignment]
    word_tokenize = None  # type: ignore[assignment]
    pos_tag = None  # type: ignore[assignment]


def ensure_nltk_resource(resource_path: str, download_name: str) -> None:
    if nltk is None:
        raise ImportError(
            "NLTK is required for highlight keyword extraction. "
            "Install it via 'pip install nltk'."
        )
    try:
        nltk.data.find(resource_path)
    except LookupError:
        nltk.download(download_name)


if nltk is not None:
    ensure_nltk_resource('tokenizers/punkt', 'punkt')
    ensure_nltk_resource('taggers/averaged_perceptron_tagger', 'averaged_perceptron_tagger')
    ensure_nltk_resource('corpora/stopwords', 'stopwords')

_ALLOWED_CONNECTORS = {"OF", "FOR", "AND", "&", "IN", "ON", "VS", "VERSUS", "TO", "WITH"}
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
    "make",
    "makes",
    "making",
    "made",
    "watch",
    "watches",
    "watching",
    "interact",
    "interacts",
    "interacting",
    "discuss",
    "discusses",
    "discussing",
    "explain",
    "explains",
    "explaining",
    "stand",
    "stands",
    "standing",
    "tell",
    "tells",
    "telling",
    "catch",
    "catches",
    "catching",
    "let",
    "lets",
    "letting",
    "take",
    "takes",
    "taking",
    "know",
    "knows",
    "knowing",
    "think",
    "thinks",
    "thinking",
    "feel",
    "feels",
    "feeling",
    "see",
    "sees",
    "seeing",
    "talk",
    "talks",
    "talking",
    "say",
    "says",
    "saying",
    "look",
    "looks",
    "looking",
    "get",
    "gets",
    "getting",
    "give",
    "gives",
    "giving",
    "keep",
    "keeps",
    "keeping",
    "want",
    "wants",
    "wanting",
    "need",
    "needs",
    "needing",
    "allow",
    "allows",
    "allowing",
    "may",
    "might",
    "should",
    "could",
    "would",
    "will",
    "can",
    "now",
    "today",
    "tonight",
    "already",
    "maybe",
    "just",
}

_TOKEN_SANITIZER = re.compile(r"\s+")
_ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")
_COMMON_VERB_TOKENS_LOWER = {token.lower() for token in _COMMON_VERB_TOKENS}


@lru_cache(maxsize=1)
def _ensure_pos_tagger() -> bool:
    if nltk is None or pos_tag is None:
        return False
    resources = [
        ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
        ("taggers/averaged_perceptron_tagger", "averaged_perceptron_tagger"),
    ]
    for resource_path, download_name in resources:
        try:
            nltk.data.find(resource_path)  # type: ignore[union-attr]
            return True
        except LookupError:
            try:
                nltk.download(download_name, quiet=True)  # type: ignore[union-attr]
                nltk.data.find(resource_path)  # type: ignore[union-attr]
                return True
            except Exception:
                continue
    return False


def _clean_token(token: str) -> str:
    return _TOKEN_SANITIZER.sub(" ", token.strip())


def _trim_edge_connectors(tokens: List[str]) -> List[str]:
    result = list(tokens)
    while result and result[0].upper() in _ALLOWED_CONNECTORS:
        result.pop(0)
    while result and result[-1].upper() in _ALLOWED_CONNECTORS:
        result.pop()
    return result


def _has_noun(tag_map: Dict[int, str], indices: range) -> bool:
    for idx in indices:
        if tag_map.get(idx, "").startswith("NN"):
            return True
    return False


def _filter_with_pos(tokens: List[str]) -> List[str]:
    if not _ensure_pos_tagger():
        return []

    taggable_indices: List[int] = []
    taggable_tokens: List[str] = []
    for idx, token in enumerate(tokens):
        cleaned = re.sub(r"[^A-Za-z0-9'-]+", "", token)
        if not cleaned:
            continue
        if cleaned.upper() in _ALLOWED_CONNECTORS:
            continue
        taggable_indices.append(idx)
        taggable_tokens.append(cleaned.lower())

    if not taggable_tokens:
        return []

    tagged = pos_tag(taggable_tokens)
    index_to_tag = {taggable_indices[i]: tag.upper() for i, (_, tag) in enumerate(tagged)}

    selected: List[str] = []
    total = len(tokens)
    for idx, token in enumerate(tokens):
        normalized = _clean_token(token)
        if not normalized:
            continue
        upper_token = normalized.upper()
        if upper_token in _ALLOWED_CONNECTORS:
            if _has_noun(index_to_tag, range(0, idx)) and _has_noun(index_to_tag, range(idx + 1, total)):
                selected.append(upper_token)
            continue

        tag = index_to_tag.get(idx, "")
        if not tag:
            continue
        if tag.startswith("NN"):
            selected.append(normalized)
        elif tag.startswith("JJ") or tag == "CD":
            if _has_noun(index_to_tag, range(idx + 1, total)):
                selected.append(normalized)

    return _trim_edge_connectors(selected)


def _fallback_filter(tokens: List[str]) -> List[str]:
    selected: List[str] = []
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
        upper_token = normalized.upper()
        lower_token = normalized.lower()
        if upper_token in _ALLOWED_CONNECTORS:
            if selected and _has_future_content(idx + 1):
                selected.append(upper_token)
            continue
        if lower_token in _COMMON_VERB_TOKENS_LOWER:
            continue
        if not _ALNUM_PATTERN.search(normalized):
            continue
        selected.append(normalized)

    return _trim_edge_connectors(selected)


def filter_tokens_to_noun_phrase(tokens: List[str], max_tokens: int | None = None) -> List[str]:
    cleaned = [_clean_token(token) for token in tokens if _clean_token(token)]
    if not cleaned:
        return []

    filtered = _filter_with_pos(cleaned)
    if not filtered:
        filtered = _fallback_filter(cleaned)
    if not filtered:
        filtered = cleaned

    if max_tokens is not None and max_tokens > 0:
        limited: List[str] = []
        content_count = 0
        for token in filtered:
            limited.append(token)
            if token.upper() not in _ALLOWED_CONNECTORS:
                content_count += 1
            if content_count >= max_tokens:
                break
        filtered = _trim_edge_connectors(limited) or filtered

    return filtered


DEFAULT_STOP_WORDS = {
    "a",
    "about",
    "after",
    "again",
    "against",
    "all",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "but",
    "by",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "im",
    "ive",
    "hes",
    "shes",
    "youre",
    "theyre",
    "weve",
    "thats",
    "theres",
    "whats",
    "gonna",
    "wanna",
    "lets",
}
STOP_WORDS = set(stopwords.words('english')) if stopwords else set()
if STOP_WORDS:
    STOP_WORDS.update(DEFAULT_STOP_WORDS)
else:
    STOP_WORDS = set(DEFAULT_STOP_WORDS)
IMPORTANT_SHORT_TOKENS = {"ai", "ms", "ebv", "cta"}
BLACKLIST_PHRASES = {
    "thanks for watching",
    "thank you for watching",
    "see you in the next",
    "see you next",
    "i hope you enjoyed",
    "bye",
    "goodbye",
}
FILLER_WORDS = {
    "uh",
    "um",
    "uhh",
    "umm",
    "oh",
    "ah",
    "er",
    "hmm",
    "huh",
    "yeah",
    "yep",
    "nope",
    "okay",
    "ok",
    "alright",
    "ahead",
}
FILLER_PHRASES = {
    "you know",
    "i mean",
    "kind of",
    "sort of",
    "yeah yeah",
    "oh okay",
}
MIN_KEYWORD_LENGTH = 3
MAX_KEYWORD_TOKENS = 3
MAX_SRT_AUTO_HIGHLIGHTS = 6
MAX_TOTAL_HIGHLIGHTS = 20
SECTION_TITLE_SUFFIXES: tuple[str, ...] = (
    "Overview",
    "Insights",
    "Focus",
    "Spotlight",
    "Framework",
    "Recap",
    "Summary",
)
GENERIC_SKIP_TOKENS = {
    "GET",
    "WANT",
    "THINK",
    "GO",
    "COME",
    "MAKE",
    "TAKE",
    "DO",
    "DOING",
    "SAY",
    "SAYS",
    "SAYING",
    "ASK",
    "ASKING",
    "TRY",
    "TRYING",
    "TRIES",
    "SEE",
    "SEES",
    "LOOK",
    "LOOKS",
    "LOOKING",
    "NEED",
    "NEEDS",
    "JUST",
    "RIGHT",
    "OKAY",
    "OK",
    "WELL",
    "FIRST",
    "SECOND",
    "THIRD",
    "ONE",
    "TWO",
    "THREE",
    "ANYTHING",
    "ANYONE",
    "ANYBODY",
    "EVERYTHING",
    "EVERYONE",
    "THING",
    "THINGS",
    "STUFF",
    "AHEAD",
    "GONNA",
    "WANNA",
    "CAN",
    "CANT",
    "GOING",
    "KNOW",
    "NEXT",
    "ALWAYS",
    "PRETTY",
    "ACTUALLY",
    "DAY",
    "LOT",
    "EVEN",
    "MADE",
    "BASICALLY",
    "SAID",
    "DONT",
    "DON",
    "DIDNT",
    "AWESOME",
    "AWAY",
    "BACK",
    "LATE",
    "BEGINNING",
    "LONG",
    "HAPPY",
    "WINDING",
    "HELPED",
    "GROW",
    "CAMERA",
    "PART",
    "MESSAGE",
    "MORNING",
    "BALANCED",
    "SIT",
    "SLEEP",
    "SOMEHOW",
    "SOMETHING",
    "FEEL",
    "FREE",
    "INTERVIEWS",
    "JIM",
    "HOME",
    "FACT",
    "HOURS",
    "BUILDING",
    "INDUSTRY",
    "SIX",
    "QUESTIONS",
    "SORRY",
    "FINE",
    "FORWARD",
    "STARTED",
    "BOTTOM",
    "MIGHT",
    "SPARK",
    "SPEND",
    "TIME",
    "REALLY",
    "SURE",
    "TOUGH",
    "KIND",
    "LIKE",
    "SCREW",
    "ELSE",
    "PICK",
    "WORD",
    "WORDS",
    "MEAN",
    "MEANS",
    "MEANT",
    "QUESTION",
    "ANSWER",
    "ASKED",
    "SAYED",
    "I",
    "ME",
    "MY",
    "MINE",
    "WE",
    "US",
    "OUR",
    "OURS",
    "YOU",
    "YOUR",
    "YOURS",
    "HE",
    "HIM",
    "HIS",
    "SHE",
    "HER",
    "HERS",
    "THEY",
    "THEM",
    "THEIR",
    "THEIRS",
    "HES",
    "SHES",
    "IM",
    "IVE",
    "YOURE",
    "THEYRE",
    "WEVE",
    "ITS",
    "IT",
    "S",
    "GOT",
    "GIVE",
    "GIVING",
    "TAKES",
    "TAKEN",
}

PRONOUN_TOKENS = {
    "I",
    "YOU",
    "WE",
    "THEY",
    "HE",
    "SHE",
    "IT",
    "ME",
    "HIM",
    "HER",
    "THEM",
    "US",
    "YOUR",
    "OUR",
    "THEIR",
    "MY",
    "YOURSELF",
    "OURSELVES",
    "THEMSELVES",
}

ADJECTIVE_SUFFIXES = (
    "IVE",
    "OUS",
    "FUL",
    "LESS",
    "ING",
    "ED",
    "ABLE",
    "IBLE",
    "ANT",
    "ENT",
    "LIKE",
    "ISH",
    "AL",
    "ARY",
    "ERY",
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> Dict[str, Any]:
    """
    Loads a JSON file from the given path.

    Args:
        path: The path to the JSON file.

    Returns:
        A dictionary containing the JSON data.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(data: Dict[str, Any], path: Path) -> None:
    """
    Writes a dictionary to a JSON file with pretty-printing.
    Ensures the parent directory exists.

    Args:
        data: The dictionary to write.
        path: The path to the output JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def camel_case_motion(name: str) -> str:
    """
    Converts a string to camelCase, typically used for motion cue names.
    E.g., "zoom-in" -> "zoomIn", "slide up" -> "slideUp".

    Args:
        name: The input string.

    Returns:
        The camelCase version of the string.
    """
    normalized = name.strip().replace("-", "_").replace(" ", "_").lower()
    parts = [part for part in normalized.split("_") if part]
    if not parts:
        return ""
    first, *rest = parts
    return first + "".join(part.title() for part in rest)


def overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """
    Calculates the overlap duration in seconds between two time intervals.

    Args:
        a_start: Start time of interval A.
        a_end: End time of interval A.
        b_start: Start time of interval B.
        b_end: End time of interval B.

    Returns:
        The duration of the overlap in seconds. Returns 0.0 if there is no overlap.
    """
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def parse_timestamp_to_seconds(value: Any) -> Optional[float]:
    """
    Converts a timestamp string (e.g. "12:34") or numeric value into seconds.
    Supports "MM:SS" and "HH:MM:SS" formats.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric >= 0 else None

    if not isinstance(value, str):
        return None

    token = value.strip()
    if not token:
        return None

    parts = token.split(':')
    try:
        numeric_parts = [float(part) for part in parts]
    except ValueError:
        return None

    if len(numeric_parts) == 1:
        seconds = numeric_parts[0]
    elif len(numeric_parts) == 2:
        minutes, seconds = numeric_parts
        seconds += minutes * 60
    elif len(numeric_parts) == 3:
        hours, minutes, seconds = numeric_parts
        seconds += minutes * 60 + hours * 3600
    else:
        return None

    return seconds if seconds >= 0 else None


def sanitize_text(value: Any) -> Optional[str]:
    """Returns a trimmed string if available, otherwise None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def ensure_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def derive_duration_seconds(entry: Dict[str, Any], element: Dict[str, Any], fallback: float = 3.0) -> float:
    """
    Resolves a duration in seconds from element or entry metadata, with dynamic adjustments.
    Accepts common keys like 'duration', 'length', or 'duration_seconds'.
    """
    base_duration = fallback
    for container in (element, entry):
        for key in ('duration_seconds', 'duration', 'length'):
            candidate = container.get(key)
            if isinstance(candidate, (int, float)) and candidate > 0:
                base_duration = float(candidate)
                break
        if base_duration != fallback:
            break

    # Dynamic adjustment based on text length
    text_content = sanitize_text(element.get('content')) or sanitize_text(entry.get('text'))
    if text_content:
        word_count = len(text_content.split())
        # Adjust duration: 0.5 seconds per word, min 1.5s, max 5.0s
        dynamic_duration = max(1.5, min(word_count * 0.5, 5.0))
        return max(base_duration, dynamic_duration)

    return base_duration


def condense_text(value: str, max_words: int = 2, max_chars: int = 42) -> str:
    """
    Condenses text into an uppercase keyword phrase while filtering filler terms.
    Returns the first `max_words` tokens (default 2) that are not stop words or filler.
    """
    phrase = select_keyword_phrase(
        value,
        max_tokens=min(max_words, MAX_KEYWORD_TOKENS),
        max_chars=max_chars,
    )
    return phrase or ""


def _clean_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9']+", "", token or "")


def keyword_is_meaningful(text: str) -> bool:
    tokens = [token.upper() for token in re.findall(r"[A-Za-z0-9]+", text or "") if token]
    if not tokens:
        return False
    if tokens == ["FIRST", "ONE"]:
        return False
    if all(token in GENERIC_SKIP_TOKENS for token in tokens):
        return False
    if any(token.lower() in _COMMON_VERB_TOKENS_LOWER for token in tokens):
        return False
    content_tokens = [token for token in tokens if token.upper() not in _ALLOWED_CONNECTORS]
    if len(content_tokens) == 1 and len(content_tokens[0]) < 5:
        return False
    return True


def select_keyword_phrase(
    text: str,
    max_tokens: int = MAX_KEYWORD_TOKENS,
    max_chars: int = 42,
) -> Optional[str]:
    if not text:
        return None

    tokens = re.findall(r"[A-Za-z0-9']+", text)
    raw_candidates: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = re.sub(r"[^a-z0-9]", "", token.lower())
        if not normalized:
            continue
        if normalized in FILLER_WORDS:
            continue
        if normalized in STOP_WORDS and normalized not in IMPORTANT_SHORT_TOKENS:
            continue
        if normalized.upper() in GENERIC_SKIP_TOKENS:
            continue
        if len(normalized) < MIN_KEYWORD_LENGTH and normalized not in IMPORTANT_SHORT_TOKENS:
            continue
        candidate_upper = token.upper()
        if candidate_upper in seen:
            continue
        seen.add(candidate_upper)
        raw_candidates.append(token)
        if len(raw_candidates) >= max_tokens * 3:
            break

    if not raw_candidates:
        return None

    filtered_tokens = filter_tokens_to_noun_phrase(raw_candidates, max_tokens=max_tokens)
    if not filtered_tokens:
        filtered_tokens = raw_candidates[:max_tokens]

    keywords = [token.upper() for token in filtered_tokens if token]
    if not keywords:
        return None

    phrase = " ".join(keywords[:max_tokens])
    if not keyword_is_meaningful(phrase):
        filtered = [kw for kw in keywords if keyword_is_meaningful(kw)]
        if not filtered:
            return None
        phrase = filtered[0] if len(filtered) == 1 else " ".join(filtered[:max_tokens])
        if not keyword_is_meaningful(phrase):
            return None

    if len(phrase) > max_chars:
        phrase = phrase[: max_chars - 1].rstrip() + "..."
    return phrase


def ensure_highlight_keyword(fields: Dict[str, Any]) -> bool:
    keyword = fields.get("keyword")
    if isinstance(keyword, str) and keyword and keyword_is_meaningful(keyword):
        return True
    text_value = fields.get("text")
    if isinstance(text_value, str) and text_value and keyword_is_meaningful(text_value):
        fields["keyword"] = text_value
        return True
    return False


def extract_meaningful_phrases(
    text: str,
    max_phrases: int = 1,
    max_chars_per_phrase: int = 42,
) -> List[str]:
    phrase = select_keyword_phrase(text, max_tokens=MAX_KEYWORD_TOKENS, max_chars=max_chars_per_phrase)
    return [phrase] if phrase else []


def normalize_phrase(words: List[str], max_words: int, max_chars: int = 48) -> str:
    """Normalizes a list of words into a concise keyword phrase."""
    joined = " ".join(words)
    phrases = extract_meaningful_phrases(joined, max_phrases=1, max_chars_per_phrase=max_chars)
    if phrases:
        return phrases[0]
    return condense_text(joined, max_words=min(max_words, MAX_KEYWORD_TOKENS), max_chars=max_chars)


def split_words_for_supporting(words: List[str]) -> Tuple[List[str], List[str]]:
    if len(words) <= 3:
        return words, []

    split_tokens = {"and", "but", "versus", "vs", "while", "because", "so", "then", "what", "that", "which", "where", "who"}
    for idx, token in enumerate(words):
        if token.lower() in split_tokens and 2 <= idx <= len(words) - 3:
            return words[:idx], words[idx:]

    midpoint = max(2, len(words) // 2)
    return words[:midpoint], words[midpoint:]


def collect_scene_window(
    scene_segments: Iterable[Dict[str, Any]],
    start: float,
    end: float,
    *,
    min_overlap: float = 0.06,
) -> List[Dict[str, Any]]:
    """
    Return transcript entries overlapping the given time window.
    """
    window: List[Dict[str, Any]] = []
    for entry in scene_segments:
        seg_start = float(entry.get("start", 0.0))
        seg_end = float(entry.get("end", seg_start))
        if seg_end <= seg_start:
            continue
        if overlap_seconds(start, end, seg_start, seg_end) >= min_overlap:
            window.append(entry)
    window.sort(key=lambda item: float(item.get("start", 0.0)))
    return window


def derive_phrase_from_window(
    window: List[Dict[str, Any]],
    *,
    max_tokens: int = MAX_KEYWORD_TOKENS + 2,
) -> Optional[str]:
    """
    Build a noun phrase from a transcript window.
    """
    if not window:
        return None

    text_parts: List[str] = []
    tokens: List[str] = []
    for entry in window:
        text_value = entry.get("textOneLine") or entry.get("text") or ""
        if text_value:
            text_parts.append(str(text_value))
        segment_tokens = entry.get("tokens") or []
        if isinstance(segment_tokens, list):
            tokens.extend(str(token) for token in segment_tokens if token)

    blob = " ".join(part.strip() for part in text_parts if part).strip()
    if blob:
        phrase = select_keyword_phrase(blob, max_tokens=max_tokens, max_chars=48)
        if phrase:
            return phrase

    if tokens:
        filtered_tokens = filter_tokens_to_noun_phrase(tokens, max_tokens=max_tokens)
        if filtered_tokens:
            fallback_phrase = " ".join(token.upper() for token in filtered_tokens if token)
            if keyword_is_meaningful(fallback_phrase):
                return fallback_phrase

    return None


def snap_highlights_to_transcript(
    plan: Dict[str, Any],
    scene_segments: Iterable[Dict[str, Any]],
    *,
    min_overlap: float = 0.06,
    min_duration: float = 0.6,
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Snap highlights to the transcript timeline and return the windows used.
    """
    highlights = plan.get("highlights", [])
    if not highlights:
        return {}

    scene_segments_list = list(scene_segments)
    if not scene_segments_list:
        return {}

    highlight_windows: Dict[int, List[Dict[str, Any]]] = {}

    for idx, highlight in enumerate(highlights):
        start = highlight.get("start")
        duration = highlight.get("duration")
        if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
            continue

        start = float(start)
        duration = float(duration) if duration else min_duration
        if duration <= 0:
            duration = min_duration
        end = start + duration
        if end <= start:
            end = start + min_duration

        window = collect_scene_window(scene_segments_list, start, end, min_overlap=min_overlap)
        if not window:
            best_entry: Optional[Dict[str, Any]] = None
            best_overlap = 0.0
            for entry in scene_segments_list:
                seg_start = float(entry.get("start", 0.0))
                seg_end = float(entry.get("end", seg_start))
                if seg_end <= seg_start:
                    continue
                ov = overlap_seconds(start, end, seg_start, seg_end)
                if ov > best_overlap:
                    best_overlap = ov
                    best_entry = entry
            if best_entry:
                window = [best_entry]

        if not window:
            continue

        snapped_start = float(window[0].get("start", start))
        snapped_end = float(window[-1].get("end", end))
        if snapped_end <= snapped_start:
            continue

        highlight["start"] = round(snapped_start, 2)
        highlight["duration"] = round(max(min_duration, snapped_end - snapped_start), 2)
        highlight_windows[idx] = window

    if highlight_windows:
        plan["highlights"] = sorted(highlights, key=lambda item: item.get("start", 0.0) or 0.0)

    return highlight_windows


def refresh_highlight_phrases(
    plan: Dict[str, Any],
    highlight_windows: Dict[int, List[Dict[str, Any]]],
) -> None:
    """
    Replace highlight keyword/text with transcript-derived noun phrases when needed.
    """
    highlights = plan.get("highlights", [])
    if not highlights or not highlight_windows:
        return

    refreshed: List[Dict[str, Any]] = []

    for idx, highlight in enumerate(highlights):
        window = highlight_windows.get(idx)
        if not window:
            highlight_type = (highlight.get("type") or "").lower()
            if highlight_type == "sectiontitle" or keyword_is_meaningful(str(highlight.get("keyword") or highlight.get("text") or "")):
                refreshed.append(highlight)
            continue
        highlight_id = str(highlight.get("id") or "")
        if highlight_id.startswith("cta_"):
            refreshed.append(highlight)
            continue

        candidate_phrase = derive_phrase_from_window(window)
        if not candidate_phrase:
            if (highlight.get("type") or "").lower() == "sectiontitle":
                refreshed.append(highlight)
            elif keyword_is_meaningful(str(highlight.get("keyword") or "")) or keyword_is_meaningful(str(highlight.get("text") or "")):
                refreshed.append(highlight)
            continue

        transcript_tokens = {
            token.upper()
            for entry in window
            for token in entry.get("tokens") or []
            if isinstance(token, str) and token
        }

        def needs_override(value: Any) -> bool:
            if not isinstance(value, str) or not value.strip():
                return True
            words = {token.upper() for token in re.findall(r"[A-Za-z0-9']+", value)}
            if not words:
                return True
            if transcript_tokens and not words.issubset(transcript_tokens):
                return True
            return False

        highlight_type = (highlight.get("type") or "").lower()
        if highlight_type == "icon":
            continue

        if needs_override(highlight.get("keyword")):
            highlight["keyword"] = candidate_phrase
        if highlight_type == "sectiontitle":
            if needs_override(highlight.get("text")):
                highlight["text"] = candidate_phrase.title()
        else:
            if needs_override(highlight.get("text")):
                highlight["text"] = candidate_phrase

        keyword_value = highlight.get("keyword") or highlight.get("text")
        if not isinstance(keyword_value, str) or not keyword_is_meaningful(keyword_value):
            continue

        refreshed.append(highlight)

    plan["highlights"] = refreshed


def decorate_section_highlights(plan: Dict[str, Any]) -> None:
    """
    Ensures sectionTitle highlights present a decorated phrase so their text
    never mirrors raw B-roll labels or plain transcript snippets.
    """
    highlights = plan.get("highlights", [])
    if not highlights:
        return

    used_texts: set[str] = set()
    suffix_count = len(SECTION_TITLE_SUFFIXES)
    if suffix_count == 0:
        return

    for highlight in highlights:
        if (highlight.get("type") or "").lower() != "sectiontitle":
            continue
        base_source = (
            highlight.get("keyword")
            or highlight.get("text")
            or ""
        )
        base_phrase = (
            select_keyword_phrase(str(base_source), max_tokens=MAX_KEYWORD_TOKENS + 1, max_chars=48)
            or condense_text(str(base_source), max_words=MAX_KEYWORD_TOKENS + 1, max_chars=48)
            or "Key Theme"
        )
        highlight_id = str(highlight.get("id") or "")
        seed = sum(ord(ch) for ch in highlight_id)
        base_title = base_phrase.title()

        attempt = 0
        chosen_text = ""
        while attempt < suffix_count * 2:
            suffix = SECTION_TITLE_SUFFIXES[(seed + attempt) % suffix_count]
            if suffix.lower() in base_title.lower():
                candidate = base_title
            else:
                candidate = f"{base_title} {suffix}"
            normalized = candidate.strip()
            if normalized.lower() not in used_texts:
                chosen_text = normalized
                break
            attempt += 1
        if not chosen_text:
            chosen_text = base_title.strip() or "Key Theme Overview"

        highlight["text"] = chosen_text
        highlight["keyword"] = chosen_text.upper()
        used_texts.add(chosen_text.lower())


def enforce_highlight_spacing(
    plan: Dict[str, Any],
    *,
    min_gap: float = 0.2,
    min_duration: float = 0.6,
) -> None:
    """
    Prevent overlapping highlight windows by trimming or prioritising key beats.
    """
    highlights = plan.get("highlights", [])
    if not highlights:
        return

    ordered = sorted(highlights, key=lambda item: item.get("start", 0.0) or 0.0)
    filtered: List[Dict[str, Any]] = []

    for current in ordered:
        start = current.get("start")
        duration = current.get("duration")
        if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
            continue
        start = float(start)
        duration = max(min_duration, float(duration))

        while filtered:
            previous = filtered[-1]
            prev_start = float(previous.get("start", 0.0))
            prev_duration = max(min_duration, float(previous.get("duration", min_duration)))
            prev_end = prev_start + prev_duration
            if start >= prev_end + min_gap:
                break

            available = start - min_gap - prev_start
            current_is_section = (current.get("type") or "").lower() == "sectiontitle"
            previous_is_section = (previous.get("type") or "").lower() == "sectiontitle"

            if available >= min_duration:
                previous["duration"] = round(available, 2)
                break

            if current_is_section and not previous_is_section:
                filtered.pop()
                continue

            if not current_is_section and previous_is_section:
                break

            if available > 0.4:
                previous["duration"] = round(max(min_duration, available), 2)
                break

            if duration > prev_duration:
                filtered.pop()
                continue

            break  # drop current highlight

        if filtered:
            prev_last = filtered[-1]
            prev_end = float(prev_last.get("start", 0.0)) + float(prev_last.get("duration", min_duration))
            if start < prev_end + min_gap:
                continue

        current["start"] = round(start, 2)
        current["duration"] = round(duration, 2)
        filtered.append(current)

    plan["highlights"] = filtered


def prune_highlights(
    plan: Dict[str, Any],
    *,
    max_total: int = MAX_TOTAL_HIGHLIGHTS,
) -> None:
    """
    Reduces highlight count to a manageable number, preferring noun-rich,
    numerically significant, or section-title moments.
    """
    highlights = plan.get("highlights", [])
    if not highlights or len(highlights) <= max_total:
        return

    def score_highlight(item: Dict[str, Any]) -> float:
        base = 0.0
        h_type = (item.get("type") or "").lower()
        if h_type == "sectiontitle":
            base += 120
        elif h_type == "icon":
            base += 40
        elif h_type == "cta":
            base += 80

        if (item.get("importance") or "").lower() == "primary":
            base += 12

        text = str(item.get("keyword") or item.get("text") or "")
        tokens = re.findall(r"[A-Za-z0-9]+", text)
        if not tokens:
            return base - 25.0
        content_tokens = [token for token in tokens if token.upper() not in _ALLOWED_CONNECTORS]
        noun_like = sum(1 for token in content_tokens if token.lower() not in _COMMON_VERB_TOKENS_LOWER)
        base += min(noun_like * 4, 20)

        if any(char.isdigit() for char in text):
            base += 10

        duration = float(item.get("duration") or 0.0)
        base += min(duration, 5.0)

        start = float(item.get("start") or 0.0)
        # Slight preference for earlier highlights to maintain pacing
        base += max(0.0, 8.0 - start * 0.05)

        # Reward compact multi-word noun clusters; penalize single short words
        if len(content_tokens) >= 2:
            base += 10
        elif len(content_tokens) == 1:
            if len(content_tokens[0]) >= 6:
                base += 2
            else:
                base -= 12

        return base

    scored = [
        (score_highlight(item), float(item.get("start") or 0.0), idx, item)
        for idx, item in enumerate(highlights)
    ]
    scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
    retained = {entry[3].get("id") for entry in scored[:max_total]}

    plan["highlights"] = [item for item in highlights if item.get("id") in retained]
    plan["highlights"].sort(key=lambda item: item.get("start", 0.0) or 0.0)


def inject_section_cards(
    plan: Dict[str, Any],
    segment_summaries: Iterable[Tuple[Dict[str, Any], SceneSummary]],
    scene_segments: Iterable[Dict[str, Any]],
    *,
    max_cards: int = 4,
    min_gap_seconds: float = 18.0,
) -> List[Dict[str, Any]]:
    """
    Inject centred sectionTitle highlights for major topic pivots.
    """
    segment_summaries = list(segment_summaries)
    if not segment_summaries:
        return []

    highlights = plan.setdefault("highlights", [])
    existing_sections = [
        float(item.get("start", 0.0))
        for item in highlights
        if isinstance(item, dict) and (item.get("type") or "").lower() == "sectiontitle"
    ]
    existing_sections.sort()

    inserted: List[Dict[str, Any]] = []
    last_section = existing_sections[-1] if existing_sections else -float("inf")

    for segment, summary in segment_summaries:
        if len(inserted) >= max_cards:
            break
        if summary.highlight_score < 0.65:
            continue
        if summary.duration < 3.0:
            continue
        start_time = float(summary.start)
        if start_time < 5.0:
            continue
        if start_time < last_section + min_gap_seconds:
            continue
        if any(abs(start_time - existing) < min_gap_seconds * 0.5 for existing in existing_sections):
            continue

        window = collect_scene_window(scene_segments, summary.start, summary.end, min_overlap=0.4)
        if not window:
            continue

        phrase = derive_phrase_from_window(window, max_tokens=MAX_KEYWORD_TOKENS + 2)
        if not phrase:
            continue

        raw_id = segment.get("id") or f"{len(highlights) + len(inserted)}"
        highlight_id = f"section_{raw_id}"

        section_highlight = {
            "id": highlight_id,
            "type": "sectionTitle",
            "start": round(float(window[0].get("start", summary.start)), 2),
            "duration": round(min(max(summary.duration, 3.2), 5.2), 2),
            "text": phrase.title(),
            "keyword": phrase,
            "position": "center",
            "animation": "float",
            "variant": "brand",
            "overlay": {"tint": "#050607", "opacity": 0.72, "blendMode": "multiply"},
            "sfx": "assets/sfx/ui/swipe.mp3",
            "volume": 0.55,
            "importance": "primary",
        }

        highlights.append(section_highlight)
        inserted.append(section_highlight)
        existing_sections.append(section_highlight["start"])
        existing_sections.sort()
        last_section = section_highlight["start"]

    if inserted:
        highlights.sort(key=lambda item: item.get("start", 0.0) or 0.0)

    return inserted


def parse_srt_timestamp(value: str) -> Optional[float]:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", value)
    if not match:
        return None
    hours, minutes, seconds, milliseconds = match.groups()
    total_seconds = (
        int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000
    )
    return total_seconds


def parse_srt_file(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        raw = handle.read()

    raw = raw.replace("\ufeff", "").strip()
    if not raw:
        return []

    entries: List[Dict[str, Any]] = []
    blocks = re.split(r"\r?\n\r?\n", raw)
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        index_str = lines[0]
        time_line = lines[1]
        text_lines = lines[2:] if len(lines) > 2 else []

        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})", time_line
        )
        if not time_match:
            continue

        start_seconds = parse_srt_timestamp(time_match.group(1))
        end_seconds = parse_srt_timestamp(time_match.group(2))
        if start_seconds is None or end_seconds is None or end_seconds <= start_seconds:
            continue

        try:
            index = int(index_str)
        except ValueError:
            index = len(entries) + 1

        text = " ".join(text_lines).strip()
        if not text:
            continue

        entries.append(
            {
                "index": index,
                "start": start_seconds,
                "end": end_seconds,
                "duration": end_seconds - start_seconds,
                "text": text,
            }
        )

    return entries


def build_highlight_from_overlay(
    entry_index: int,
    entry: Dict[str, Any],
    element_index: int,
    element: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Converts a single text overlay element into a HighlightPlan-compatible dictionary.
    """
    if element.get('type') != 'text_overlay':
        return None

    timestamp = parse_timestamp_to_seconds(entry.get('timestamp'))
    if timestamp is None:
        return None

    content = element.get('content')
    main_text: Optional[str] = None
    supporting: Dict[str, str] = {}

    if isinstance(content, str):
        main_text = sanitize_text(content)
    elif isinstance(content, dict):
        main_text = (
            sanitize_text(content.get('keyword'))
            or sanitize_text(content.get('title'))
            or sanitize_text(content.get('heading'))
            or sanitize_text(content.get('label'))
        )

        items = content.get('items')
        if isinstance(items, list) and items:
            first = sanitize_text(items[0])
            second = sanitize_text(items[1]) if len(items) > 1 else None
            if first and not supporting.get('topLeft'):
                supporting['topLeft'] = first
            if second and not supporting.get('topRight'):
                supporting['topRight'] = second
            if not main_text:
                main_text = sanitize_text(items[-1]) or first

        for source_key, target_key in (
            ('top_left', 'topLeft'),
            ('topLeft', 'topLeft'),
            ('left', 'topLeft'),
            ('primary', 'topLeft'),
            ('top_right', 'topRight'),
            ('topRight', 'topRight'),
            ('right', 'topRight'),
            ('secondary', 'topRight'),
            ('top_center', 'topCenter'),
            ('topCenter', 'topCenter'),
        ):
            value = sanitize_text(content.get(source_key))
            if value and target_key not in supporting:
                supporting[target_key] = value
    else:
        main_text = sanitize_text(entry.get('script'))

    if not main_text:
        main_text = sanitize_text(entry.get('script'))
    if not main_text:
        return None

    supporting_cleaned: Dict[str, str] = {}
    for key, value in supporting.items():
        if not value:
            continue
        phrases = extract_meaningful_phrases(value, max_phrases=1, max_chars_per_phrase=32)
        if phrases:
            supporting_cleaned[key] = phrases[0]

    duration = derive_duration_seconds(entry, element)

    supporting_final: Dict[str, str] = {}
    left_value = supporting_cleaned.get('topLeft') or supporting_cleaned.get('topCenter')
    right_value = supporting_cleaned.get('topRight') or supporting_cleaned.get('topCenter')

    if left_value:
        supporting_final['topLeft'] = left_value
    if right_value and right_value != left_value:
        supporting_final['topRight'] = right_value

    main_phrases = extract_meaningful_phrases(main_text, max_phrases=1, max_chars_per_phrase=42)
    if not main_phrases:
        return None
    primary_keyword = main_phrases[0]
    if not keyword_is_meaningful(primary_keyword):
        return None

    highlight: Dict[str, Any] = {
        'id': f'kb-{entry_index:03d}-{element_index:02d}',
        'type': 'noteBox',
        'start': round(timestamp, 2),
        'duration': round(duration, 2),
        'position': 'bottom',
        'layout': 'bottom',
        'importance': 'primary',
        'showBottom': True,
        'safeBottom': 0.18,
        'safeInsetHorizontal': 0.08,
        'text': primary_keyword,
        'keyword': primary_keyword,
    }

    if supporting_final:
        highlight['supportingTexts'] = supporting_final
        both_sides = 'topLeft' in supporting_final and 'topRight' in supporting_final
        if both_sides:
            highlight['layout'] = 'dual'
            highlight['staggerLeft'] = 0.0
            highlight['staggerRight'] = 2.0
        elif 'topLeft' in supporting_final:
            highlight['layout'] = 'left'
            highlight['staggerLeft'] = 0.0
        elif 'topRight' in supporting_final:
            highlight['layout'] = 'right'
            highlight['staggerRight'] = 0.0

    return highlight




DEFAULT_BROLL_DURATION = 6.0

BROLL_RULES: List[Tuple[set[str], str]] = [
    (set(["digital marketing", "marketing", "online marketing"]), "creative_brainstorm"),
    (set(["strategy", "tactics", "plan", "framework"]), "presentation_speaker"),
    (set(["seo", "search engine optimization"]), "data_analysis"),
    (set(["social media", "facebook", "instagram", "linkedin"]), "remote_call"),
    (set(["ppc", "paid ads", "google ads"]), "data_analysis"),
    (set(["email marketing", "email campaigns"]), "typing_laptop"),
    (set(["web optimization", "website", "landing page"]), "coding_screen"),
    (set(["audience", "segmentation", "target", "customer"]), "teamwork_meeting"),
    (set(["learning", "education", "course", "training"]), "training_workshop"),
    (set(["caffeine", "coffee", "cup of coffee"]), "typing_laptop"),
    (set(["career", "job", "growth", "specialise"]), "office_motion"),
    (set(["credibility", "authority", "expert"]), "presentation_speaker"),
    (set(["data", "analytics", "metrics", "insights"]), "data_analysis"),
    (set(["content", "blog", "video", "post"]), "creative_brainstorm"),
    (set(["organic", "paid", "promotion"]), "data_analysis"),
    (set(["brand awareness", "direct response"]), "presentation_speaker"),
    (set(["products", "services"]), "office_motion"),
    (set(["b2b", "b2c", "business to business", "business to consumer"]), "teamwork_meeting"),
    (set(["loyal", "loyalty", "loyal clients"]), "handshake_success"),
    (set(["sweet", "honest", "heartwarming"]), "celebration_success"),
    (set(["favorite memory", "favourite memory", "memory", "family", "grandkids"]), "celebration_success"),
    (set(["high school", "sweetheart", "sweethearts"]), "training_workshop"),
    (set(["clientele", "clients", "client"]), "teamwork_meeting"),
    (set(["partnership", "still with", "day one"]), "office_motion"),
    (set(["relationship", "relationships", "friendships"]), "startup_team"),
    (set(["consistency", "consistent"]), "office_motion"),
    (set(["mail room", "mailroom"]), "office_motion"),
    (set(["industry", "business owner", "company"]), "startup_team"),
    (set(["personality", "psychology", "traits", "introvert", "extrovert"]), "training_workshop"),
    (set(["mind", "brain", "thought", "thinking"]), "digital_brain"),
    (set(["people", "audience", "social", "crowd", "group"]), "teamwork_meeting"),
]

BROLL_NOTES = {
    "handshake_success": "B-roll: handshake_success underscores loyalty anecdote.",
    "celebration_success": "B-roll: celebration_success adds warmth during character description.",
    "training_workshop": "B-roll: training_workshop illustrates the high-school group setup.",
    "teamwork_meeting": "B-roll: teamwork_meeting spotlights established clientele.",
    "presentation_speaker": "B-roll: presentation_speaker fits the talk-style explanation.",
    "creative_brainstorm": "B-roll: creative_brainstorm adds energetic collaboration context.",
    "data_analysis": "B-roll: data_analysis visualises metric-heavy commentary.",
    "remote_call": "B-roll: remote_call reinforces digital social interaction.",
    "typing_laptop": "B-roll: typing_laptop underscores analytical focus.",
    "coding_screen": "B-roll: coding_screen mirrors technical optimisation themes.",
    "digital_brain": "B-roll: digital_brain supports references to cognitive science.",
    "startup_team": "B-roll: startup_team reinforces loyal friendships with clients.",
    "office_motion": "B-roll: office_motion underscores consistent client relationships.",
}

BROLL_REASONS = {
    "handshake_success": ["Handshake moment reinforces loyalty description."],
    "celebration_success": ["Celebration visual supports the heartfelt moment."],
    "training_workshop": ["Group setting mirrors the meeting story energy."],
    "teamwork_meeting": ["Team huddle echoes long-term client relationships."],
    "presentation_speaker": ["Stage speaker visual reinforces the narrated insight."],
    "creative_brainstorm": ["Creative session footage keeps the discussion lively."],
    "data_analysis": ["Analytics dashboard imagery matches the metric-focused commentary."],
    "remote_call": ["Video call vignette highlights social/audience engagement."],
    "typing_laptop": ["Typing closeup mirrors detailed analytical thinking."],
    "coding_screen": ["Code view emphasises technical problem solving."],
    "digital_brain": ["Digital brain animation echoes cognitive references in the script."],
    "startup_team": ["Collaborative workspace visualises loyal friendships with clients."],
    "office_motion": ["Office walkthrough mirrors consistent client presence."],
}

BROLL_FULL_IDS = {
    "handshake_success",
    "celebration_success",
    "training_workshop",
    "teamwork_meeting",
    "startup_team",
    "office_motion",
    "presentation_speaker",
    "creative_brainstorm",
    "data_analysis",
    "remote_call",
    "typing_laptop",
    "coding_screen",
    "digital_brain",
}

MAX_BROLL_REUSE = 2


MOTION_ZOOM_IN_KEYWORDS = {
    "loyal",
    "loyalty",
    "sweet",
    "honest",
    "memory",
    "favorite memory",
    "favourite memory",
    "sweetheart",
    "sweethearts",
    "clientele",
    "client",
    "clients",
    "relationship",
    "relationships",
    "consistency",
    "consistent",
}

MOTION_ANIMATION_HINTS = {"zoom", "pulse", "bounce", "fade"}
ALLOWED_MOTIONS = {"zoomIn", "zoomOut"}


HIGHLIGHT_SFX_RULES = [
    {"keywords": {"sweet", "honest"}, "sfx": "assets/sfx/emotion/applause.mp3", "gain": -2.5},
    {"keywords": {"high school", "sweetheart", "sweethearts"}, "sfx": "assets/sfx/ui/pop.mp3", "gain": -2.5},
    {"keywords": {"clientele", "client", "clients"}, "sfx": "assets/sfx/ui/pop.mp3", "gain": -2.5},
    {"keywords": {"loyalty", "day one"}, "sfx": "assets/sfx/emphasis/ding.mp3", "gain": -2.5},
    {"keywords": {"relationship", "relationships"}, "sfx": "assets/sfx/ui/bubble-pop.mp3", "gain": -3.0},
    {"keywords": {"consistency", "consistent"}, "sfx": "assets/sfx/emphasis/ding.mp3", "gain": -3.0},
]


def match_broll_candidates(text: str) -> List[str]:
    lowered = text.lower()
    matches: List[str] = []
    for keywords, broll_id in BROLL_RULES:
        if any(keyword in lowered for keyword in keywords):
            matches.append(broll_id)
    return matches


def ensure_broll_from_highlights(
    plan: Dict[str, Any],
    broll_catalog: Dict[str, Any] | None,
) -> None:
    if not broll_catalog:
        return

    catalog_items = {item.get("id"): item for item in broll_catalog.get("items", [])}
    if not catalog_items:
        return

    segments = plan.get("segments", [])
    if not segments:
        return

    highlights = plan.get("highlights", [])
    if not highlights:
        return
    def locate_segment(timecode: float) -> Optional[Dict[str, Any]]:
        for segment in segments:
            start = float(segment.get("sourceStart", 0.0))
            end = start + float(segment.get("duration", 0.0))
            if start <= timecode <= end:
                return segment
        return None

    assigned_counts: defaultdict[str, int] = defaultdict(int)
    section_locked_segments: set[str] = set()
    for highlight in highlights:
        if (highlight.get("type") or "").lower() != "sectiontitle":
            continue
        start = highlight.get("start")
        if not isinstance(start, (int, float)):
            continue
        segment = locate_segment(start)
        if segment and segment.get("id"):
            section_locked_segments.add(segment["id"])

    for highlight in highlights:
        start = highlight.get("start")
        if not isinstance(start, (int, float)):
            continue

        segment = locate_segment(start)
        if not segment or segment.get("broll"):
            continue
        segment_id = segment.get("id")
        if isinstance(segment_id, str) and segment_id in section_locked_segments:
            continue

        highlight_type = (highlight.get("type") or "").lower()
        if highlight_type == "sectiontitle":
            continue

        text_sources = [highlight.get("keyword") or ""]
        supporting = highlight.get("supportingTexts") or {}
        text_sources.extend(supporting.values())
        label = segment.get("label") or segment.get("title")
        if label:
            text_sources.append(label)
        full_text = " ".join(filter(None, text_sources))
        if not full_text:
            continue

        candidates = match_broll_candidates(full_text)
        if not candidates:
            continue

        chosen_item = None
        chosen_id = None
        for candidate_id in sorted(candidates, key=lambda cid: (assigned_counts[cid], cid)):
            item = catalog_items.get(candidate_id)
            if not item:
                continue
            file_path = str(item.get("file") or "")
            media_type = (item.get("mediaType") or "").lower()
            if media_type and media_type != "video" and not file_path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mpg", ".mpeg")):
                continue
            if assigned_counts[candidate_id] >= MAX_BROLL_REUSE:
                continue
            chosen_item = item
            chosen_id = candidate_id
            break

        if not chosen_item or not chosen_id:
            continue

        file_path = str(chosen_item.get("file") or "")
        media_type = (chosen_item.get("mediaType") or "").lower()
        if media_type and media_type != "video" and not file_path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mpg", ".mpeg")):
            continue

        mode = "full"
        reasons = BROLL_REASONS.get(chosen_item.get("id")) or ["Highlight keyword match"]
        duration_hint = float(chosen_item.get("durationHintSeconds") or DEFAULT_BROLL_DURATION)
        max_duration = round(min(duration_hint, float(segment.get("duration", duration_hint))), 3)

        segment["broll"] = {
            "id": chosen_item.get("id"),
            "file": chosen_item.get("file"),
            "mode": mode,
            "confidence": 3.0,
            "reasons": reasons,
            "duration": max_duration,
        }
        notes = [
            note
            for note in segment.get("notes", [])
            if not note.lower().startswith("no b-roll match")
        ]
        note_text = BROLL_NOTES.get(chosen_item.get("id")) or f"B-roll injected via highlight keyword: {chosen_item.get('id')}"
        if note_text not in notes:
            notes.append(note_text)
        segment["notes"] = notes
        assigned_counts[chosen_id] += 1


def ensure_motion_from_highlights(
    plan: Dict[str, Any],
    motion_rules: Dict[str, Any] | None,
) -> None:
    if not motion_rules:
        motion_rules = {}

    segments = plan.get("segments", [])
    highlights = plan.get("highlights", [])
    if not segments or not highlights:
        return

    def locate_segment(timecode: float) -> Optional[Dict[str, Any]]:
        for segment in segments:
            start = float(segment.get("sourceStart", 0.0))
            end = start + float(segment.get("duration", 0.0))
            if start <= timecode <= end:
                return segment
        return None

    max_motions = max(1, math.ceil(len(segments) * float(motion_rules.get("motion_frequency", 0.5))))
    assigned = sum(1 for segment in segments if segment.get("motionCue"))
    last_motion: Optional[str] = None

    for highlight in highlights:
        start = highlight.get("start")
        if not isinstance(start, (int, float)):
            continue

        segment = locate_segment(start)
        if not segment:
            continue
        existing_cue = segment.get("motionCue")
        if assigned >= max_motions and not existing_cue:
            break

        text_parts = [highlight.get("keyword") or ""]
        supporting = highlight.get("supportingTexts") or {}
        text_parts.extend(supporting.values())
        combined_text = " ".join(filter(None, text_parts)).lower()

        motion: Optional[str] = None
        animation_hint = (highlight.get("animation") or "").lower()
        zoom_out_keywords = motion_rules.get("zoom_out_keywords", [])
        zoom_out_hit = any(word in combined_text for word in zoom_out_keywords)

        has_number = any(ch.isdigit() for ch in combined_text)

        if highlight.get("importance") == "primary":
            if zoom_out_hit and last_motion == "zoomIn":
                motion = "zoomOut"
            elif has_number:
                motion = "zoomIn"
            elif last_motion == "zoomIn":
                motion = "zoomOut"
            else:
                motion = "zoomIn"
        elif has_number:
            motion = "zoomIn"
        elif any(keyword in combined_text for keyword in MOTION_ZOOM_IN_KEYWORDS):
            motion = "zoomIn"
        elif animation_hint in MOTION_ANIMATION_HINTS:
            motion = "zoomIn"
        elif zoom_out_hit:
            motion = "zoomOut"
        else:
            if existing_cue in ALLOWED_MOTIONS:
                motion = existing_cue
            else:
                motion = "zoomOut" if last_motion == "zoomIn" else "zoomIn"

        if not motion:
            continue
        if existing_cue:
            if existing_cue == motion:
                continue
            if existing_cue not in ALLOWED_MOTIONS and motion in ALLOWED_MOTIONS:
                pass
            elif existing_cue in ALLOWED_MOTIONS and motion != existing_cue:
                segment["motionCue"] = motion
            else:
                continue

        notes = [
            note
            for note in segment.get("notes", [])
            if not note.lower().startswith("motion cue assigned")
        ]
        description = (
            highlight.get("text")
            or highlight.get("keyword")
            or highlight.get("title")
            or ""
        ).strip()
        gist = f"\"{description}\"" if description else "highlight context"
        note_text = f"Motion cue: {motion} emphasises {gist}."
        if note_text not in notes:
            notes.append(note_text)
        segment["notes"] = notes
        segment["motionCue"] = motion
        if not existing_cue:
            assigned += 1
        last_motion = motion


def ensure_highlight_sfx(
    plan: Dict[str, Any],
    sfx_catalog: Dict[str, Any] | None,
) -> None:
    highlights = plan.get("highlights", [])
    if not highlights:
        return

    available: set[str] = set()
    if sfx_catalog:
        for item in sfx_catalog.get("items", []):
            if not isinstance(item, dict):
                continue
            path = item.get("file") or item.get("id")
            if isinstance(path, str):
                available.add(path.lower())

    for highlight in highlights:
        if highlight.get("sfx"):
            continue

        text_parts = [
            highlight.get("text"),
            highlight.get("keyword"),
            highlight.get("title"),
        ]
        combined = " ".join(filter(None, text_parts)).lower()
        if not combined:
            continue

        for rule in HIGHLIGHT_SFX_RULES:
            if any(keyword in combined for keyword in rule["keywords"]):
                sfx_path = rule["sfx"]
                if available and sfx_path.lower() not in available:
                    continue
                highlight["sfx"] = sfx_path
                highlight["gain"] = rule.get("gain", -3.0)
                metadata = highlight.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata.setdefault("audio", "auto")
                break


def trim_highlights_to_segments(plan: Dict[str, Any], margin: float = 0.25) -> None:
    segments = plan.get("segments", [])
    highlights = plan.get("highlights", [])
    if not segments or not highlights:
        return

    latest_end = 0.0
    for segment in segments:
        try:
            start = float(segment.get("sourceStart", 0.0))
            duration = float(segment.get("duration", 0.0))
        except (TypeError, ValueError):
            continue
        latest_end = max(latest_end, start + max(0.0, duration))

    cutoff = latest_end + margin
    trimmed = [
        highlight
        for highlight in highlights
        if isinstance(highlight.get("start"), (int, float)) and highlight["start"] <= cutoff
    ]
    trimmed.sort(key=lambda item: item.get("start", 0.0))
    plan["highlights"] = trimmed
def augment_highlights_from_catalog(
    plan: Dict[str, Any],
    catalog: Dict[str, Any],
    min_gap: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Generates additional highlight entries from a structured catalog (e.g., video2.json)
    and appends them to the plan while avoiding duplicates.
    """
    timeline = catalog.get('video_timeline') or catalog.get('timeline') or []
    if not isinstance(timeline, list) or not timeline:
        return []

    highlights = plan.setdefault('highlights', [])
    existing_starts = [h.get('start') for h in highlights if isinstance(h.get('start'), (int, float))]

    injected: List[Dict[str, Any]] = []
    side_toggle = False
    for entry_index, entry in enumerate(timeline):
        elements = entry.get('elements') or []
        if not isinstance(elements, list):
            continue

        for element_index, element in enumerate(elements):
            highlight = build_highlight_from_overlay(entry_index, entry, element_index, element)
            if not highlight:
                continue

            start_time = highlight.get('start')
            if start_time is None:
                continue

            duplicate = any(abs(start_time - existing) <= min_gap for existing in existing_starts)
            if duplicate:
                continue

            layout = highlight.get('layout') or 'bottom'
            highlight['position'] = 'bottom'
            highlight['showBottom'] = True
            highlight['importance'] = (highlight.get('importance') or 'primary').lower()

            supporting_texts = highlight.get('supportingTexts')
            if layout in {'left', 'right'} and isinstance(supporting_texts, dict):
                desired = 'left' if not side_toggle else 'right'
                value = (
                    supporting_texts.get('topLeft')
                    if desired == 'left'
                    else supporting_texts.get('topRight')
                )
                fallback_value = supporting_texts.get('topLeft') or supporting_texts.get('topRight')
                final_value = value or fallback_value
                if desired == 'left' and final_value:
                    highlight['supportingTexts'] = {'topLeft': final_value}
                    highlight['layout'] = 'left'
                    highlight['staggerLeft'] = 0.0
                    highlight.pop('staggerRight', None)
                elif desired == 'right' and final_value:
                    highlight['supportingTexts'] = {'topRight': final_value}
                    highlight['layout'] = 'right'
                    highlight['staggerRight'] = 0.0
                    highlight.pop('staggerLeft', None)
                else:
                    highlight['layout'] = desired
                side_toggle = not side_toggle
            elif layout == 'dual':
                if isinstance(supporting_texts, dict):
                    highlight['layout'] = 'dual'
                    highlight['staggerLeft'] = 0.0
                    highlight['staggerRight'] = max(
                        2.0,
                        ensure_float(highlight.get('staggerRight'), 2.0),
                    )
            else:
                highlight['layout'] = 'bottom'
                highlight.pop('supportingTexts', None)
                highlight.pop('staggerLeft', None)
                highlight.pop('staggerRight', None)

            highlight.pop('side', None)
            highlights.append(highlight)
            injected.append(highlight)
            existing_starts.append(start_time)

    if injected:
        highlights.sort(key=lambda item: item.get('start', 0.0) or 0.0)

    return injected






def build_highlight_override(entry: Dict[str, Any], text_lower: str, start: float, duration: float) -> Optional[Dict[str, Any]]:
    highlight_id = f'srt-{entry["index"]:04d}'
    if 'epstein-barr' in text_lower:
        right = '32X MS RISK' if '32' in text_lower else ('THE KISSING DISEASE' if 'kissing' in text_lower else 'MONONUCLEOSIS')
        return {
            'id': highlight_id,
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'importance': 'primary',
            'position': 'bottom',
            'layout': 'dual',
            'text': 'EPSTEIN-BARR VIRUS',
            'keyword': 'EPSTEIN-BARR VIRUS',
            'showBottom': True,
            'staggerLeft': 0.0,
            'staggerRight': 2.0,
            'supportingTexts': {
                'topLeft': 'EPSTEIN-BARR VIRUS',
                'topRight': right,
            },
        }
    if "didn't know what caused" in text_lower:
        return {
            'id': highlight_id,
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'importance': 'primary',
            'position': 'bottom',
            'layout': 'dual',
            'text': 'UNKNOWN CAUSE',
            'keyword': 'UNKNOWN CAUSE',
            'showBottom': True,
            'staggerLeft': 0.0,
            'staggerRight': 2.0,
            'supportingTexts': {
                'topLeft': 'UNKNOWN CAUSE',
                'topRight': 'HARD TO TREAT',
            },
        }
    if '10 million' in text_lower and '20 year' in text_lower:
        return {
            'id': highlight_id,
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'importance': 'primary',
            'position': 'bottom',
            'layout': 'dual',
            'safeBottom': 0.18,
            'safeInsetHorizontal': 0.08,
            'text': '10 MILLION PEOPLE',
            'keyword': '10 MILLION PEOPLE',
            'showBottom': True,
            'staggerLeft': 0.0,
            'staggerRight': 2.0,
            'supportingTexts': {
                'topLeft': '10 MILLION PEOPLE',
                'topRight': '20 YEARS',
            },
        }
    if 'direct link' in text_lower and 'multiple sclerosis' in text_lower:
        return {
            'id': highlight_id,
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'importance': 'primary',
            'position': 'bottom',
            'layout': 'bottom',
            'safeBottom': 0.18,
            'safeInsetHorizontal': 0.08,
            'text': 'DIRECT LINK: EBV ? MS',
            'keyword': 'DIRECT LINK: EBV ? MS',
            'showBottom': True,
        }
    if 'multiple sclerosis' in text_lower and '32' in text_lower:
        return {
            'id': highlight_id,
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'importance': 'primary',
            'position': 'bottom',
            'layout': 'bottom',
            'safeBottom': 0.18,
            'safeInsetHorizontal': 0.08,
            'text': '32X MS RISK',
            'keyword': '32X MS RISK',
            'showBottom': True,
        }
    return None
def augment_highlights_from_srt(
    plan: Dict[str, Any],
    srt_path: Path,
    min_gap: float = 0.5,
) -> List[Dict[str, Any]]:
    entries = parse_srt_file(srt_path)
    if not entries:
        return []

    highlights = plan.setdefault('highlights', [])
    highlights.sort(key=lambda h: h.get('start', 0.0))

    def has_conflict(start_time: float, duration_time: float) -> bool:
        end_time = start_time + duration_time
        for existing in highlights:
            existing_start = existing.get('start')
            existing_duration = existing.get('duration') or 0.0
            if not isinstance(existing_start, (int, float)):
                continue
            existing_end = existing_start + float(existing_duration)
            if overlap_seconds(start_time, end_time, existing_start, existing_end) > 0.0:
                return True
            if abs(existing_start - start_time) <= min_gap:
                return True
        return False

    injected: List[Dict[str, Any]] = []
    side_toggle = False
    recent_phrases: set[str] = set()

    for entry in entries:
        if len(injected) >= MAX_SRT_AUTO_HIGHLIGHTS:
            break
        if len(highlights) >= MAX_TOTAL_HIGHLIGHTS:
            break

        start = max(0.0, entry['start'])
        duration = derive_duration_seconds(entry, entry)

        if start < 0.6 or has_conflict(start, duration):
            continue

        raw_text = entry['text']
        text_lower = raw_text.lower()
        if any(phrase in text_lower for phrase in BLACKLIST_PHRASES):
            continue

        clean = re.sub(r"[^A-Za-z0-9\s'%-]", " ", raw_text)
        words = [w for w in clean.split() if w]
        if not words:
            continue

        normalized_sentence = " ".join(words).lower()
        if normalized_sentence in recent_phrases:
            continue
        recent_phrases.add(normalized_sentence)

        override = build_highlight_override(entry, text_lower, start, duration)
        if override:
            if ensure_highlight_keyword(override):
                highlights.append(override)
                injected.append(override)
            continue

        primary_text = normalize_phrase(words, max_words=4, max_chars=40)
        if not primary_text or not keyword_is_meaningful(primary_text):
            continue

        left_words, right_words = split_words_for_supporting(words)
        left_text = normalize_phrase(left_words, max_words=4, max_chars=32)
        right_text = normalize_phrase(right_words, max_words=4, max_chars=32) if right_words else ""

        highlight: Dict[str, Any] = {
            'id': f"srt-{entry['index']:04d}",
            'type': 'noteBox',
            'start': round(start, 2),
            'duration': round(duration, 2),
            'position': 'bottom',
            'layout': 'bottom',
            'importance': 'primary',
            'showBottom': True,
            'safeBottom': 0.18,
            'safeInsetHorizontal': 0.08,
            'text': primary_text,
            'keyword': primary_text,
        }

        supporting_candidates: List[Tuple[str, str]] = []
        if left_text and keyword_is_meaningful(left_text) and left_text != primary_text:
            supporting_candidates.append(('left', left_text))
        if right_text and keyword_is_meaningful(right_text) and right_text not in {primary_text, left_text}:
            supporting_candidates.append(('right', right_text))

        supporting_texts: Dict[str, str] = {}
        if len(supporting_candidates) >= 2:
            supporting_texts['topLeft'] = supporting_candidates[0][1]
            supporting_texts['topRight'] = supporting_candidates[1][1]
            highlight['layout'] = 'dual'
            highlight['staggerLeft'] = 0.0
            highlight['staggerRight'] = 2.0
        elif len(supporting_candidates) == 1:
            desired_side = 'left' if not side_toggle else 'right'
            _, phrase = supporting_candidates[0]
            final_side = desired_side
            if final_side == 'left':
                supporting_texts['topLeft'] = phrase
                highlight['layout'] = 'left'
                highlight['staggerLeft'] = 0.0
            else:
                supporting_texts['topRight'] = phrase
                highlight['layout'] = 'right'
                highlight['staggerRight'] = 0.0
            side_toggle = not side_toggle

        if supporting_texts:
            highlight['supportingTexts'] = supporting_texts

        if not ensure_highlight_keyword(highlight):
            continue

        hl_duration = float(highlight.get('duration', duration) or duration)
        window_end = start + duration
        max_start = max(start, window_end - hl_duration)
        desired = start + duration * 0.55
        highlight['start'] = round(min(max(desired, start), max_start), 2)

        highlights.append(highlight)
        injected.append(highlight)

    if injected:
        highlights.sort(key=lambda item: item.get('start', 0.0) or 0.0)

    return injected

def strip_non_section_sfx(plan: Dict[str, Any]) -> None:
    """
    Removes sound effect metadata from non-section highlights to keep overlays subtle.
    """
    for highlight in plan.get('highlights', []):
        if highlight.get('type') == 'sectionTitle':
            continue
        metadata = highlight.get('metadata')
        preserve = isinstance(metadata, dict) and metadata.get('audio') in {'auto', 'keep', 'accent'}
        if preserve:
            continue
        highlight.pop('sfx', None)
        highlight.pop('gain', None)
        highlight.pop('ducking', None)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SceneSummary:
    """
    Represents a summary of a scene, aggregating various metadata from scene map segments.

    Attributes:
        start: The start time of the scene segment in seconds.
        end: The end time of the scene segment in seconds.
        topics: A list of dominant topics in the scene.
        highlight_score: A numerical score indicating the highlight potential of the scene.
        motion_candidates: A list of potential motion cues for the scene.
        tokens: A list of important tokens/keywords from the scene's transcript.
        text: The combined transcript text for the scene.
        cta: A boolean flag indicating if the scene contains a Call-to-Action.
        sfx_hints: A list of suggested SFX categories for the scene.
    """
    start: float
    end: float
    topics: List[str]
    highlight_score: float
    motion_candidates: List[str]
    tokens: List[str]
    text: str
    cta: bool
    sfx_hints: List[str]

    @property
    def duration(self) -> float:
        """Calculates the duration of the scene summary."""
        return max(0.0, self.end - self.start)


# ---------------------------------------------------------------------------
# Scene aggregation
# ---------------------------------------------------------------------------


def aggregate_scene_for_segment(
    plan_segment: Dict[str, Any], scene_segments: Iterable[Dict[str, Any]]
) -> SceneSummary | None:
    start = float(plan_segment.get("sourceStart", 0.0))
    end = start + float(plan_segment.get("duration", 0.0))
    if end <= start:
        return None

    topics_counter: Counter[str] = Counter()
    motion_candidates: List[str] = []
    tokens_counter: Counter[str] = Counter()
    sfx_hints_counter: Counter[str] = Counter()

    highlight_score_total = 0.0
    total_weight = 0.0
    texts: List[str] = []
    cta_flag = False

    for scene in scene_segments:
        scene_start = float(scene.get("start", 0.0))
        scene_end = float(scene.get("end", scene_start))
        weight = overlap_seconds(start, end, scene_start, scene_end)
        if weight <= 0:
            continue

        topics_counter.update(scene.get("topics") or [])
        for candidate in scene.get("motionCandidates") or []:
            motion_name = camel_case_motion(candidate)
            if motion_name and motion_name not in motion_candidates:
                motion_candidates.append(motion_name)
        tokens_counter.update(scene.get("tokens") or [])
        sfx_hints_counter.update(scene.get("sfxHints") or [])

        highlight_score = float(scene.get("highlightScore", 0.0))
        highlight_score_total += highlight_score * weight
        total_weight += weight

        if scene.get("textOneLine"):
            texts.append(scene["textOneLine"])
        cta_flag = cta_flag or bool(scene.get("cta"))

    if total_weight == 0:
        return None

    combined_text = " ".join(texts)
    averaged_highlight = highlight_score_total / total_weight if total_weight else 0.0

    tokens_sorted = [token for token, _ in tokens_counter.most_common(24)]
    sfx_hints = [hint for hint, _ in sfx_hints_counter.most_common(8)]

    return SceneSummary(
        start=start,
        end=end,
        topics=[topic for topic, _ in topics_counter.most_common(6)],
        highlight_score=averaged_highlight,
        motion_candidates=motion_candidates,
        tokens=tokens_sorted,
        text=combined_text,
        cta=cta_flag,
        sfx_hints=sfx_hints,
    )


# ---------------------------------------------------------------------------
# B-roll selection
# ---------------------------------------------------------------------------


def score_broll_item(item: Dict[str, Any], scene: SceneSummary) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []

    item_topics = [topic.lower() for topic in item.get("topics") or []]
    scene_topics = [topic.lower() for topic in scene.topics]
    topic_overlap = set(item_topics) & set(scene_topics)
    if topic_overlap:
        score += 2.5 * len(topic_overlap)
        reasons.append(f"topics match {sorted(topic_overlap)}")

    keywords = [kw.lower() for kw in item.get("keywords") or []]
    token_hits = set(scene.tokens) & set(keywords)
    if token_hits:
        score += 1.0 * len(token_hits)
        reasons.append(f"keywords hit {sorted(token_hits)}")

    moods = [m.lower() for m in item.get("mood") or []]
    if scene.highlight_score >= 0.7 and moods:
        score += 0.4
        reasons.append("highlight scene prefers mood assets")

    if item.get("mediaType") == "video":
        score += 0.3
    if item.get("orientation") == "landscape":
        score += 0.1

    if not reasons:
        reasons.append("fallback")
    return score, reasons


def select_broll(scene: SceneSummary, catalog: Dict[str, Any], threshold: float) -> Dict[str, Any] | None:
    items = catalog.get("items") or []
    if not items:
        return None

    # Filter out items that are too short for the scene duration
    filtered_items = [item for item in items if float(item.get("duration", 0.0)) >= scene.duration * 0.8]
    if not filtered_items:
        return None

    best_item: Optional[Dict[str, Any]] = None
    best_score = 0.0
    best_reasons: List[str] = []

    for item in filtered_items:
        score, reasons = score_broll_item(item, scene)
        if score > best_score:
            best_item = item
            best_score = score
            best_reasons = reasons

    # Only select b-roll if the score is above the threshold and it's a high-impact scene
    if not best_item or best_score < threshold or scene.highlight_score < 0.6:
        return None

    return {
        "id": best_item.get("id"),
        "file": best_item.get("file"),
        "confidence": round(best_score, 2),
        "reasons": best_reasons,
        "mediaType": best_item.get("mediaType"),
        "orientation": best_item.get("orientation"),
    }


# ---------------------------------------------------------------------------
# Motion cue selection
# ---------------------------------------------------------------------------


def select_motion_cue(
    scene: SceneSummary,
    *,
    motion_rules: Dict[str, Any],
    assigned_so_far: int,
    total_segments: int,
) -> str | None:
    frequency = float(motion_rules.get("motion_frequency", 0.0))
    max_segments = math.ceil(total_segments * frequency) if frequency > 0 else total_segments
    if assigned_so_far >= max_segments:
        return None

    candidate = None
    # Prioritize explicit motion candidates from scene map
    if scene.motion_candidates:
        candidate = scene.motion_candidates[0]
    # Assign zoomIn for high-impact scenes (high highlight score)
    elif scene.highlight_score >= float(motion_rules.get("highlight_rate", 0.0)):
        candidate = "zoomIn"
    # Assign pan for scenes with moderate highlight score and longer duration
    elif scene.highlight_score >= 0.4 and scene.duration > 5.0:
        candidate = "pan"
    # Assign zoomOut for scenes with lower highlight score or as a contrast to zoomIn
    elif scene.highlight_score < 0.4 and scene.duration > 3.0:
        candidate = "zoomOut"

    return candidate


# ---------------------------------------------------------------------------
# CTA highlight logic
# ---------------------------------------------------------------------------


def ensure_cta_highlight(
    plan: Dict[str, Any],
    cta_candidates: List[Tuple[Dict[str, Any], SceneSummary]],
    sfx_catalog: Dict[str, Any] | None,
) -> None:
    highlights = plan.setdefault("highlights", [])
    if any("cta" in (h.get("id") or "").lower() or (h.get("type") == "cta") for h in highlights):
        return

    if not cta_candidates:
        return

    # pick the last CTA candidate (usually near outro)
    segment, scene = cta_candidates[-1]
    start = max(scene.start, segment.get("sourceStart", 0.0))
    duration = max(2.5, min(5.0, segment.get("duration", 4.0)))
    highlight_start = max(start, start + segment.get("duration", duration) - 3.0)

    applause_sfx = None
    if sfx_catalog:
        for category in sfx_catalog.get("categories", []):
            for item in category.get("items", []):
                if "applause" in (item.get("id") or ""):
                    applause_sfx = item.get("file") or f"assets/sfx/{category.get('id')}/{item.get('id')}"
                    break
            if applause_sfx:
                break

    highlights.append(
        {
            "id": "cta_subscribe",
            "type": "sectionTitle",
            "text": "Dang ky kenh de nhan video moi!",
            "start": round(highlight_start, 2),
            "duration": round(duration, 2),
            "position": "center",
            "animation": "float",
            "variant": "brand",
            "sfx": applause_sfx or "assets/sfx/emotion/applause.mp3",
            "volume": 0.7,
        }
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def compute_timing_warnings(segments: List[Dict[str, Any]], tolerance: float = 0.05) -> List[str]:
    warnings: List[str] = []
    for prev, current in zip(segments, segments[1:]):
        prev_end = float(prev.get("sourceStart", 0.0)) + float(prev.get("duration", 0.0))
        gap = float(current.get("sourceStart", 0.0)) - prev_end
        if gap > tolerance:
            warnings.append(
                f"Gap of {gap:.2f}s between {prev.get('id')} and {current.get('id')}; consider extending previous duration."
            )
        elif gap < -tolerance:
            warnings.append(
                f"Overlap of {-gap:.2f}s between {prev.get('id')} and {current.get('id')}; verify segment timings."
            )
    return warnings


# ---------------------------------------------------------------------------
# Main enrichment workflow
# ---------------------------------------------------------------------------


def enrich_plan(
    plan: Dict[str, Any],
    scene_map: Dict[str, Any],
    *,
    broll_catalog: Dict[str, Any] | None,
    sfx_catalog: Dict[str, Any] | None,
    motion_rules: Dict[str, Any] | None,
    broll_threshold: float = 1.5,
) -> Tuple[Dict[str, Any], List[str]]:
    segments = plan.get("segments") or []
    scene_segments = list(scene_map.get("segments") or [])
    motion_rules = motion_rules or {}

    total_segments = len(segments)
    assigned_motion = 0
    cta_candidates: List[Tuple[Dict[str, Any], SceneSummary]] = []
    warnings: List[str] = []
    segment_summary_pairs: List[Tuple[Dict[str, Any], SceneSummary]] = []

    for segment in segments:
        segment.setdefault("kind", "normal")

        scene_summary = aggregate_scene_for_segment(segment, scene_segments)
        if not scene_summary:
            segment.setdefault(
                "notes",
                []
            ).append("No matching scene metadata; skipped B-roll and motion cue.")
            continue

        notes: List[str] = []

        if broll_catalog:
            broll = select_broll(scene_summary, broll_catalog, broll_threshold)
            if broll:
                segment["broll"] = {
                    "id": broll["id"],
                    "file": broll["file"],
                    "mode": "full",
                    "confidence": broll["confidence"],
                    "reasons": broll["reasons"],
                }
                notes.append(f"B-roll assigned: {broll['id']} ({', '.join(broll['reasons'])})")
            else:
                notes.append("No B-roll match above threshold.")

        if motion_rules:
            motion_cue = select_motion_cue(
                scene_summary,
                motion_rules=motion_rules,
                assigned_so_far=assigned_motion,
                total_segments=total_segments,
            )
            if motion_cue:
                segment["motionCue"] = motion_cue
                assigned_motion += 1
                notes.append(f"Motion cue assigned: {motion_cue}")

        if scene_summary.cta:
            cta_candidates.append((segment, scene_summary))

        if scene_summary.sfx_hints and "sfxHints" not in segment:
            segment["sfxHints"] = scene_summary.sfx_hints
            notes.append(f"SFX hints propagated: {', '.join(scene_summary.sfx_hints)}")

        if notes:
            segment.setdefault("notes", []).extend(notes)

        segment_summary_pairs.append((segment, scene_summary))

    ensure_cta_highlight(plan, cta_candidates, sfx_catalog)
    inserted_sections = inject_section_cards(plan, segment_summary_pairs, scene_segments)
    if inserted_sections:
        meta = plan.setdefault("meta", {})
        generated = meta.setdefault("generatedSections", 0)
        try:
            meta["generatedSections"] = int(generated) + len(inserted_sections)
        except Exception:
            meta["generatedSections"] = len(inserted_sections)

    warnings.extend(compute_timing_warnings(segments))
    if warnings:
        plan.setdefault("meta", {}).setdefault("warnings", warnings)
    return plan, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: List[str] | None = None) -> int:
    """
    Main entry point for the script. Parses arguments, loads data,
    enriches the plan, and writes the output.

    Args:
        argv: Optional. A list of command-line arguments. Defaults to sys.argv.

    Returns:
        An exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(description="Enrich plan.json with B-roll and motion cues.")
    parser.add_argument("plan_path", type=Path, help="Input plan.json from Gemini")
    parser.add_argument("output_path", type=Path, help="Output path for enriched plan")
    parser.add_argument(
        "--scene-map",
        dest="scene_map_path",
        type=Path,
        required=True,
        help="scene_map.json generated by generate_scene_map.py",
    )
    parser.add_argument(
        "--broll-catalog",
        dest="broll_catalog_path",
        type=Path,
        default=Path("assets/broll_catalog.json"),
        help="Path to broll_catalog.json (default: repo_root/assets/broll_catalog.json)",
    )
    parser.add_argument(
        "--sfx-catalog",
        dest="sfx_catalog_path",
        type=Path,
        default=Path("assets/sfx_catalog.json"),
        help="Path to sfx_catalog.json (default: repo_root/assets/sfx_catalog.json)",
    )
    parser.add_argument(
        "--motion-rules",
        dest="motion_rules_path",
        type=Path,
        default=Path("assets/motion_rules.json"),
        help="Path to motion_rules.json (default: repo_root/assets/motion_rules.json)",
    )
    parser.add_argument(
        "--highlight-catalog",
        dest="highlight_catalog_path",
        type=Path,
        help="Optional path to a structured text highlight catalog (e.g., video2.json)",
    )
    parser.add_argument(
        "--highlight-srt",
        dest="highlight_srt_path",
        type=Path,
        help="Optional path to an SRT file used to generate highlight captions",
    )
    parser.add_argument(
        "--broll-threshold",
        dest="broll_threshold",
        type=float,
        default=1.5,
        help="Minimum score required to attach B-roll (default: 1.5)",
    )

    args = parser.parse_args(argv)

    # Load input plan and scene map
    plan = load_json(args.plan_path)
    scene_map = load_json(args.scene_map_path)

    # Resolve repository root for loading catalogs
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    def resolve(path: Path) -> Path:
        """Helper to resolve absolute or relative paths against the repository root."""
        return path if path.is_absolute() else (repo_root / path)

    # Load optional catalogs and rules
    broll_catalog = load_json(resolve(args.broll_catalog_path)) if args.broll_catalog_path else None
    sfx_catalog = load_json(resolve(args.sfx_catalog_path)) if args.sfx_catalog_path else None
    motion_rules = load_json(resolve(args.motion_rules_path)) if args.motion_rules_path else None
    highlight_catalog = (
        load_json(resolve(args.highlight_catalog_path))
        if args.highlight_catalog_path
        else None
    )
    highlight_srt_path = (
        resolve(args.highlight_srt_path)
        if args.highlight_srt_path
        else None
    )

    # Enrich the plan
    enriched_plan, warnings = enrich_plan(
        plan,
        scene_map,
        broll_catalog=broll_catalog,
        sfx_catalog=sfx_catalog,
        motion_rules=motion_rules,
        broll_threshold=args.broll_threshold,
    )

    if highlight_catalog:
        injected = augment_highlights_from_catalog(enriched_plan, highlight_catalog)
        if injected:
            enriched_plan.setdefault("meta", {}).setdefault(
                "highlightCatalog",
                str(args.highlight_catalog_path),
            )
            print(
                f"[INFO] Injected {len(injected)} highlight(s) from {args.highlight_catalog_path}"
            )

    if highlight_srt_path and highlight_srt_path.exists():
        injected_srt = augment_highlights_from_srt(enriched_plan, highlight_srt_path)
        if injected_srt:
            enriched_plan.setdefault("meta", {}).setdefault(
                "highlightSrt",
                str(highlight_srt_path),
            )
            print(
                f"[INFO] Injected {len(injected_srt)} SRT highlight(s) from {highlight_srt_path}"
            )

    scene_segments_for_alignment = list(scene_map.get("segments") or [])
    highlight_windows = snap_highlights_to_transcript(
        enriched_plan,
        scene_segments_for_alignment,
    )
    refresh_highlight_phrases(enriched_plan, highlight_windows)
    decorate_section_highlights(enriched_plan)
    enforce_highlight_spacing(enriched_plan)
    prune_highlights(enriched_plan)
    trim_highlights_to_segments(enriched_plan)
    ensure_broll_from_highlights(enriched_plan, broll_catalog)
    ensure_motion_from_highlights(enriched_plan, motion_rules)
    ensure_highlight_sfx(enriched_plan, sfx_catalog)
    strip_non_section_sfx(enriched_plan)

    # Write the enriched plan to output
    write_json(enriched_plan, args.output_path)

    # Report any warnings
    if warnings:
        print("[WARN] Issues detected:")
        for warning in warnings:
            print(f"  - {warning}")
    print(f"[PLAN] Enriched plan written to {args.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


