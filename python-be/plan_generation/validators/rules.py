from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from knowledge_base.models import ValidationIssue
from knowledge_base.paths import KNOWLEDGE_BASE_ROOT


MOTION_RULES_PATH = KNOWLEDGE_BASE_ROOT.parent / "assets" / "motion_rules.json"
SFX_CATALOG_PATH = KNOWLEDGE_BASE_ROOT.parent / "assets" / "sfx_catalog.json"
CONTEXT_RULES_PATH = KNOWLEDGE_BASE_ROOT.parent / "assets" / "context_rules.json"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_plan_rules(plan: Dict[str, Any]) -> Iterable[ValidationIssue]:
    issues: List[ValidationIssue] = []
    elements = plan if isinstance(plan, list) else plan.get("elements", [])

    motion_rules = {rule["action"]: rule for rule in _load_json(MOTION_RULES_PATH).get("rules", [])}
    sfx_catalog = {item["id"]: item for item in _load_json(SFX_CATALOG_PATH).get("items", [])}
    context_rules = {rule["context"]: rule for rule in _load_json(CONTEXT_RULES_PATH).get("rules", [])}

    last_action_time: Dict[str, float] = defaultdict(lambda: -1e9)
    last_overlay_time: float = -1e9

    for element in elements:
        timestamp = float(element.get("timestamp", 0))
        elem_type = element.get("type")

        if elem_type == "effect":
            action = element.get("action")
            if action and action in motion_rules:
                min_spacing = motion_rules[action].get("minSpacing", 0)
                if timestamp - last_action_time[action] < min_spacing:
                    issues.append(
                        ValidationIssue(
                            code="rule.motion.spacing",
                            message=f"Effect '{action}' violates min spacing of {min_spacing}s",
                            severity="warning",
                            context={"timestamp": timestamp},
                        )
                    )
                last_action_time[action] = timestamp

        if elem_type == "text_overlay":
            if timestamp - last_overlay_time < 0.3:
                issues.append(
                    ValidationIssue(
                        code="rule.overlay.spacing",
                        message="Overlays should be staggered by at least 0.3s",
                        severity="warning",
                        context={"timestamp": timestamp},
                    )
                )
            last_overlay_time = timestamp

            context = element.get("context")
            if context:
                expected = context_rules.get(context, {})
                tags = expected.get("recommendedSfxTags", [])
                sound = element.get("sound")
                if sound and sound in sfx_catalog:
                    sound_tags = sfx_catalog[sound].get("tags", [])
                    if tags and not any(tag in sound_tags for tag in tags):
                        issues.append(
                            ValidationIssue(
                                code="rule.overlay.sfx_context",
                                message=f"Sound '{sound}' does not match recommended tags for context '{context}'",
                                severity="warning",
                                context={"timestamp": timestamp},
                            )
                        )

    return issues
