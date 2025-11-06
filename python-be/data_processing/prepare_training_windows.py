from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from plan_generation.knowledge import KnowledgeService  # noqa: E402
from plan_generation.make_plan_gemini import load_json_if_exists # noqa: E402


SRT_BLOCK_RE = re.compile(
    r"(?P<index>\d+)\s+"
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s-->\s(?P<end>\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<text>.+?)(?=\n\n|\Z)",
    re.DOTALL,
)


def parse_timecode(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def _get_schema_enums(schema: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Extracts all enum values for relevant properties from the element schema."""
    enums: Dict[str, Set[str]] = {}
    properties = schema.get("properties", {})
    for prop_name in ["type", "layer", "style", "animation", "sound", "action"]:
        if prop_name in properties and "enum" in properties[prop_name]:
            enums[prop_name] = set(properties[prop_name]["enum"])
    return enums


def _encode_element_features(
    elements: List[Dict[str, Any]], schema_enums: Dict[str, Set[str]]
) -> Dict[str, Any]:
    """
    Encodes a list of plan elements into a feature vector for a training window.
    This is a simplified encoding for demonstration purposes.
    """
    features: Dict[str, Any] = {
        "num_elements": len(elements),
        "avg_element_duration": 0.0,
    }

    if not elements:
        return features

    total_duration = 0.0
    present_types: Set[str] = set()
    present_layers: Set[str] = set()

    for element in elements:
        total_duration += element.get("duration", 0.0)
        if "type" in element and element["type"] in schema_enums.get("type", set()):
            present_types.add(element["type"])
        if "layer" in element and element["layer"] in schema_enums.get("layer", set()):
            present_layers.add(element["layer"])

    if elements:
        features["avg_element_duration"] = total_duration / len(elements)

    # One-hot encode presence of element types
    for element_type in schema_enums.get("type", set()):
        features[f"has_type_{element_type}"] = element_type in present_types

    # One-hot encode presence of layers
    for layer_type in schema_enums.get("layer", set()):
        features[f"has_layer_{layer_type}"] = layer_type in present_layers

    return features


def _encode_text_features(
    text: str, context_rules: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Encodes text features for a training window, including sentence length and keyword flags.
    """
    features: Dict[str, Any] = {
        "text_length": len(text),
        "sentence_count": len(re.split(r'[.!?]', text)) - 1, # Simple sentence count
        "word_count": len(text.split()),
        "relative_position": 0.0, # Placeholder, will be calculated later if needed
    }

    if context_rules and "rules" in context_rules:
        for rule in context_rules["rules"]:
            if "conditions" in rule and "keywords" in rule["conditions"]:
                rule_keywords = rule["conditions"]["keywords"]
                for keyword in rule_keywords:
                    # Simple keyword presence flag
                    features[f"has_keyword_{keyword.lower().replace(' ', '_')}"] = \
                        keyword.lower() in text.lower()

    return features


def _encode_audio_features(text_features: Dict[str, Any], duration: float) -> Dict[str, Any]:
    """
    Encodes audio-related features for a training window, specifically speaking rate.
    """
    features: Dict[str, Any] = {
        "speaking_rate_wps": 0.0,
    }

    word_count = text_features.get("word_count", 0)
    if duration > 0:
        features["speaking_rate_wps"] = round(word_count / duration, 2)

    return features


@dataclass
class TrainingWindow:
    index: int
    start: float
    end: float
    duration: float
    text: str
    guideline_snippets: List[str]
    plan_elements: List[Dict[str, Any]]
    encoded_features: Dict[str, Any]
    text_features: Dict[str, Any]
    audio_features: Dict[str, Any]


def parse_srt(
    path: Path,
    plan_data: Optional[Dict[str, Any]] = None,
    element_schema: Optional[Dict[str, Any]] = None,
    context_rules: Optional[Dict[str, Any]] = None,
) -> List[TrainingWindow]:
    content = path.read_text(encoding="utf-8").strip()
    service: Optional[KnowledgeService]
    try:
        service = KnowledgeService()
    except Exception:
        service = None

    windows: List[TrainingWindow] = []
    
    schema_enums: Dict[str, Set[str]] = {}
    if element_schema:
        schema_enums = _get_schema_enums(element_schema)
    else:
        print("[WARN] Element schema not provided for encoding.", file=sys.stderr)

    for match in SRT_BLOCK_RE.finditer(content):
        index = int(match.group("index"))
        start = parse_timecode(match.group("start"))
        end = parse_timecode(match.group("end"))
        text = re.sub(r"\s+", " ", match.group("text")).strip()
        guideline_snippets: List[str] = []
        if service is not None and text:
            guideline_snippets = service.guideline_summaries(text, top_k=3)

        aligned_plan_elements: List[Dict[str, Any]] = []
        if plan_data:
            # Simple alignment: check if element's start/end falls within the SRT window
            # This will be refined in the next steps
            for segment in plan_data.get("segments", []):
                seg_start = segment.get("sourceStart", 0.0)
                seg_duration = segment.get("duration", 0.0)
                seg_end = seg_start + seg_duration
                if (start <= seg_start < end) or (start < seg_end <= end) or \
                   (seg_start <= start < seg_end) or (seg_start < end <= seg_end):
                    aligned_plan_elements.append(segment)
            for highlight in plan_data.get("highlights", []):
                hl_start = highlight.get("start", 0.0)
                hl_duration = highlight.get("duration", 0.0)
                hl_end = hl_start + hl_duration
                if (start <= hl_start < end) or (start < hl_end <= end) or \
                   (hl_start <= start < hl_end) or (hl_start < end <= hl_end):
                    aligned_plan_elements.append(highlight)

        text_features = _encode_text_features(text, context_rules)
        audio_features = _encode_audio_features(text_features, max(end - start, 0.0))
        encoded_features = _encode_element_features(aligned_plan_elements, schema_enums)

        windows.append(
            TrainingWindow(
                index=index,
                start=start,
                end=end,
                duration=max(end - start, 0.0),
                text=text,
                guideline_snippets=guideline_snippets,
                plan_elements=aligned_plan_elements,
                encoded_features=encoded_features,
                text_features=text_features,
                audio_features=audio_features,
            )
        )
    return windows


def main(input_srt: Path, output_json: Path, input_plan: Optional[Path] = None) -> None:
    plan_data: Optional[Dict[str, Any]] = None
    if input_plan:
        plan_data = load_json_if_exists(input_plan)
        if not plan_data:
            print(f"[WARN] Could not load or parse plan file: {input_plan}", file=sys.stderr)

    element_schema_path = Path(__file__).resolve().parents[2] / "knowledge-base" / "element_schema.json"
    element_schema_data = load_json_if_exists(element_schema_path)
    if not element_schema_data:
        print(f"[ERROR] Could not load element schema from {element_schema_path}", file=sys.stderr)
        sys.exit(1)

    context_rules_path = Path(__file__).resolve().parents[2] / "assets" / "context_rules.json"
    context_rules_data = load_json_if_exists(context_rules_path)
    if not context_rules_data:
        print(f"[WARN] Could not load context rules from {context_rules_path}", file=sys.stderr)
        context_rules_data = None

    windows = parse_srt(input_srt, plan_data, element_schema_data, context_rules_data)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps([asdict(window) for window in windows], indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(windows)} windows to {output_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert an SRT transcript into training windows enriched with knowledge-base snippets."
    )
    parser.add_argument("input_srt", type=Path, help="Path to the source SRT file.")
    parser.add_argument(
        "output_json", type=Path, help="Destination JSON file for training windows."
    )
    parser.add_argument(
        "--input-plan",
        type=Path,
        help="Optional path to a JSON plan file to align with SRT entries.",
    )
    args = parser.parse_args()
    main(args.input_srt, args.output_json, args.input_plan)
