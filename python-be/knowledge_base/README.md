# Knowledge Base Module

This module (`python-be/knowledge_base/`) provides the core runtime utilities for interacting with the AI planning knowledge base. Its primary functions include parsing raw documentation assets (Markdown and JSON), validating their structure, and enabling efficient retrieval of knowledge for various AI pipeline stages. This module acts as an interface between the raw knowledge assets and the AI models that consume them.

Runtime utilities for parsing, validating, and retrieving documentation from the `knowledge-base/` repository.

## Folder Layout

| File | Purpose |
| ---- | ------- |
| `__init__.py` | Exposes high-level entry points (`KnowledgeBaseIngestor`, `KnowledgeRepository`, `sync_knowledge_base`). |
| `ingestion.py` | Converts Markdown/JSON assets into structured documents and embedding chunks. |
| `markdown_parser.py` | Handles CommonMark parsing, heading extraction, and front-matter metadata. |
| `models.py` | Pydantic models and dataclasses shared by the ingestion and retrieval logic. |
| `paths.py` | Centralised path definitions for knowledge assets and cached outputs. |
| `repository.py` | Loads cached documents, provides vector search, validation helpers, and graph construction. |
| `vector_store.py` | Embedding encoder and in-memory cosine similarity search implementation. |
| `graph.py` | Builds a lightweight NetworkX graph linking documents to sections. |

## Typical Workflow

1. **Synchronise assets**  
   ```bash
   python data_processing/sync_knowledge_base.py --rebuild-vectors
   ```
   This command populates `outputs/knowledge/structured.json`, `embeddings.json`, and `schema_cache.json`.

2. **Load at runtime**  
   ```python
   from knowledge_base import KnowledgeRepository

   repo = KnowledgeRepository()
   docs = repo.documents["markdown"]
   results = repo.search("zoom transition pacing", top_k=3)
   ```

3. **Validation utilities**  
   The repository exposes `validation_report` that converts iterables of `ValidationIssue` into a structured response. The plan validators in `plan_generation/validators/` rely on this helper.

## Extending the Module

- Add new Pydantic models in `models.py` so they can be reused across ingestion and consumers.
- Keep ingestion side-effect free: new parsers should return models, not write files directly.
- Always update this README (and `knowledge-base/README.md`) when new responsibilities or scripts are introduced.

For details on the curated knowledge assets themselves, see `../knowledge-base/README.md`.
