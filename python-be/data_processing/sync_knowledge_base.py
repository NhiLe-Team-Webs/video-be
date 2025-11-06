from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from knowledge_base import KnowledgeBaseIngestor, sync_knowledge_base
from knowledge_base.repository import KnowledgeRepository


def main(rebuild_vectors: bool = False) -> None:
    documents = sync_knowledge_base()
    if rebuild_vectors:
        # Force reload of vector store to ensure downstream consumers see fresh data.
        repo = KnowledgeRepository()
        _ = repo.vector_store  # property access triggers rebuild
    print(
        json.dumps(
            {
                "markdown_docs": len(documents["markdown"]),
                "json_docs": len(documents["json"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronise knowledge base assets.")
    parser.add_argument(
        "--rebuild-vectors",
        action="store_true",
        help="Force rebuild of vector store after ingestion.",
    )
    args = parser.parse_args()
    main(rebuild_vectors=args.rebuild_vectors)
