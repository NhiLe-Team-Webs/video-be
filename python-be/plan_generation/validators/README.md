# Plan Validators

Schema and rule enforcement utilities for AI-generated Remotion plans.

## Components

| File | Purpose |
| ---- | ------- |
| `__init__.py` | Re-exports the public validation functions. |
| `schema.py` | Validates plans against `knowledge-base/element_schema.json` using `jsonschema`. |
| `rules.py` | Applies domain rules (motion spacing, SFX alignment, context tags) leveraging the curated asset catalogs. |

## Usage

```python
from plan_generation.validators import validate_plan_schema, validate_plan_rules
from knowledge_base.repository import KnowledgeRepository

issues = list(validate_plan_schema(plan_dict))
issues += list(validate_plan_rules(plan_dict))

repo = KnowledgeRepository()
report = repo.validation_report(issues)
print(report.is_valid, report.issues)
```

Integrate these checks after generating a plan—either inside the pipeline (e.g., `make_plan_gemini.py`) or before exporting JSON to the Remotion app.

## Maintenance Notes

- Keep `rules.py` aligned with assets under `assets/` (`motion_rules.json`, `sfx_catalog.json`, `context_rules.json`).
- When the JSON schema evolves, run `python data_processing/sync_knowledge_base.py` so cached hashes stay in sync.
- Document any new validations here and in high-level workflow docs (`python-be/README.md`) to help future contributors.
