"""
Convenience layer for loading cached knowledge documents and running retrieval/validation helpers.

This module provides the `KnowledgeRepository` class, which acts as a central access point
for all processed knowledge base data. It handles loading structured documents and
vector embeddings from cached files, provides search capabilities, and offers utilities
for validation and graph construction.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

import json  # For loading JSON data from cached files
from pathlib import Path  # For object-oriented filesystem paths
from typing import Dict, Iterable, List, Optional  # Type hinting utilities

from .graph import build_knowledge_graph  # Function to build a knowledge graph
from .models import KnowledgeDocument, ValidationReport, ValidationIssue  # Data models
from .paths import (  # File path configurations
    EMBEDDINGS_DATA_PATH,
    OUTPUT_ROOT,
    STRUCTURED_DATA_PATH,
    ensure_output_dirs,
)
from .vector_store import InMemoryVectorStore, Vectoriser, VectorSearchResult  # Vector store components


class KnowledgeRepository:
    """
    A repository for accessing and querying the processed knowledge base.

    This class provides methods to:
    - Load structured knowledge documents (Markdown and JSON).
    - Access an in-memory vector store for semantic search.
    - Perform searches against the vectorized knowledge.
    - Retrieve specific types of documents (e.g., planning guidelines).
    - Generate validation reports.
    - Construct a graph representation of the knowledge base.
    """

    def __init__(self, output_root: Path | None = None) -> None:
        """
        Initializes the KnowledgeRepository.

        Args:
            output_root: The root directory where processed knowledge outputs are stored.
                         Defaults to `OUTPUT_ROOT` if not provided.
        """
        self.output_root = output_root or OUTPUT_ROOT
        ensure_output_dirs()  # Ensure output directories exist before attempting to load
        self._documents: Dict[str, List[KnowledgeDocument]] | None = None  # Cache for loaded documents
        self._vector_store: Optional[InMemoryVectorStore] = None  # Cache for the vector store
        self._vectoriser = Vectoriser()  # Initialize the vectorizer for encoding queries

    @property
    def documents(self) -> Dict[str, List[KnowledgeDocument]]:
        """
        Lazily loads and returns all structured knowledge documents.

        If documents are not already loaded, it reads `structured.json` and
        deserializes them into `KnowledgeDocument` objects.

        Returns:
            A dictionary containing lists of `KnowledgeDocument` objects,
            categorized by "markdown" and "json".

        Raises:
            FileNotFoundError: If the structured knowledge data file is not found.
        """
        if self._documents is None:
            if not STRUCTURED_DATA_PATH.exists():
                raise FileNotFoundError(
                    "Structured knowledge data not found. Run sync_knowledge_base first."
                )
            raw = json.loads(STRUCTURED_DATA_PATH.read_text(encoding="utf-8"))
            self._documents = {
                key: [KnowledgeDocument.model_validate(doc) for doc in value]
                for key, value in raw.items()
            }
        return self._documents

    @property
    def vector_store(self) -> InMemoryVectorStore:
        """
        Lazily initializes and returns the in-memory vector store.

        If the vector store is not already initialized, it loads embeddings from
        `embeddings.json` and populates the store.

        Returns:
            An `InMemoryVectorStore` instance populated with knowledge chunks.
        """
        if self._vector_store is None:
            store = InMemoryVectorStore()
            if EMBEDDINGS_DATA_PATH.exists():
                raw = json.loads(EMBEDDINGS_DATA_PATH.read_text(encoding="utf-8"))
                for chunk in raw:
                    store.add(
                        chunk["vector"],
                        {
                            "chunk_id": chunk["chunk_id"],
                            "text": chunk["text"],
                            **chunk.get("metadata", {}),  # Include any additional metadata
                        },
                    )
            self._vector_store = store
        return self._vector_store

    def search(self, query: str, top_k: int = 5) -> List[VectorSearchResult]:
        """
        Performs a semantic search against the vector store.

        Encodes the query into a vector and finds the `top_k` most similar
        knowledge chunks.

        Args:
            query: The natural language query string.
            top_k: The number of top similar results to return.

        Returns:
            A list of `VectorSearchResult` objects, ordered by similarity.
        """
        vector = self._vectoriser.encode(query)  # Encode the query
        return self.vector_store.search(vector, top_k=top_k)

    def all_guidelines(self) -> Iterable[KnowledgeDocument]:
        """
        Retrieves all Markdown documents identified as planning guidelines.

        Yields:
            `KnowledgeDocument` objects that represent planning guidelines.
        """
        for doc in self.documents.get("markdown", []):
            if doc.identifier.endswith("planning_guidelines.md"):
                yield doc

    def validation_report(self, issues: Iterable[ValidationIssue]) -> ValidationReport:
        """
        Generates a `ValidationReport` from a collection of validation issues.

        Determines if the overall validation is successful (no 'error' severity issues)
        and aggregates all issues.

        Args:
            issues: An iterable of `ValidationIssue` objects.

        Returns:
            A `ValidationReport` summarizing the validation outcome.
        """
        issues_list = list(issues)
        # A report is valid if there are no issues with severity "error"
        is_valid = not any(issue.severity == "error" for issue in issues_list)
        return ValidationReport(is_valid=is_valid, issues=issues_list)

    def knowledge_graph(self):
        """
        Constructs and returns a NetworkX directed graph of the knowledge base.

        The graph represents documents and their sections as nodes, with edges
        indicating hierarchical relationships.

        Returns:
            A `networkx.DiGraph` object representing the knowledge graph.
        """
        import networkx as nx  # Imported locally to avoid circular dependency if not used often

        return build_knowledge_graph(self.documents.get("markdown", []))
