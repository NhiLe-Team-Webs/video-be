from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from knowledge_base.paths import KNOWLEDGE_BASE_ROOT
from knowledge_base.repository import KnowledgeRepository
from knowledge_base.models import ValidationIssue


SCHEMA_PATH = KNOWLEDGE_BASE_ROOT / "element_schema.json"


def _load_schema() -> Dict[str, Any]:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_plan_schema(plan: Dict[str, Any]) -> Iterable[ValidationIssue]:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(plan), key=lambda e: e.path):
        yield ValidationIssue(
            code="schema.validation",
            message=error.message,
            severity="error",
            context={"path": list(error.path)},
        )
