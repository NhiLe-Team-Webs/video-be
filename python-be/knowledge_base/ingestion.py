"""
Utilities for converting knowledge-base assets into structured documents and embeddings.

This module provides the core functionality for ingesting various knowledge assets
(Markdown files, JSON schemas, etc.) from the `knowledge-base` directory,
processing them into a structured format, generating vector embeddings for text content,
and persisting these processed data into output files.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

import hashlib  # For generating SHA256 hashes of file content
import json  # For parsing and serializing JSON data
from pathlib import Path  # For object-oriented filesystem paths
from typing import Dict, Iterable, List, Sequence  # Type hinting utilities

from jsonschema import Draft202012Validator  # For validating JSON schemas
from jsonschema.exceptions import ValidationError  # Exception for schema validation errors

from .markdown_parser import extract_headings, parse_markdown_document  # Markdown parsing utilities
from .models import (  # Data models for structured knowledge representation
    ElementDefinition,
    ExampleSnippet,
    GlossaryTerm,
    GuidelineRule,
    KnowledgeDocument,
    VectorisedChunk,
    DocumentType,
)
from .paths import (  # File path configurations for the knowledge base
    EMBEDDINGS_DATA_PATH,
    KNOWLEDGE_BASE_ROOT,
    OUTPUT_ROOT,
    SCHEMA_CACHE_PATH,
    STRUCTURED_DATA_PATH,
    ensure_output_dirs,
)
from .vector_store import Vectoriser  # Component for generating vector embeddings


class KnowledgeBaseIngestor:
    """
    Manages the ingestion, processing, vectorization, and persistence of knowledge
    documents from the specified knowledge base root.
    """

    def __init__(self, knowledge_root: Path | None = None) -> None:
        """
        Initializes the KnowledgeBaseIngestor.

        Args:
            knowledge_root: The root directory of the knowledge base. Defaults to
                            `KNOWLEDGE_BASE_ROOT` if not provided.
        """
        self.knowledge_root = knowledge_root or KNOWLEDGE_BASE_ROOT
        self.vectoriser = Vectoriser()  # Initialize the vectorizer for text embeddings

    def load(self) -> Dict[str, List[KnowledgeDocument]]:
        """
        Loads and processes all Markdown and JSON documents from the knowledge base root.

        Recursively scans the `knowledge_root` directory, processes `.md` files
        using `_process_markdown` and `.json` files using `_process_json`.

        Returns:
            A dictionary containing two lists of `KnowledgeDocument` objects,
            categorized by "markdown" and "json" document types.
        """
        documents: Dict[str, List[KnowledgeDocument]] = {"markdown": [], "json": []}
        for path in sorted(self.knowledge_root.rglob("*")):  # Iterate through all files and directories
            if path.is_dir():
                continue  # Skip directories
            if path.suffix.lower() == ".md":
                documents["markdown"].append(self._process_markdown(path))
            elif path.suffix.lower() == ".json":
                documents["json"].append(self._process_json(path))
        return documents

    def _process_markdown(self, path: Path) -> KnowledgeDocument:
        """
        Processes a single Markdown file into a `KnowledgeDocument`.

        Extracts metadata, sections, and headings from the Markdown content.

        Args:
            path: The `Path` object of the Markdown file to process.

        Returns:
            A `KnowledgeDocument` object representing the processed Markdown file.
        """
        text = path.read_text(encoding="utf-8")
        metadata, sections = parse_markdown_document(text)  # Parse Markdown content
        headings = extract_headings(sections)  # Extract headings from sections
        processed_sections = [section.content for section in sections]  # Get raw content of sections
        return KnowledgeDocument(
            identifier=str(path.relative_to(self.knowledge_root)),
            title=metadata.get("title") or path.stem.replace("_", " ").title(),
            doc_type=DocumentType.MARKDOWN,
            path=str(path),
            headings=headings,
            sections=processed_sections,
            metadata=metadata,
        )

    def _process_json(self, path: Path) -> KnowledgeDocument:
        """
        Processes a single JSON file into a `KnowledgeDocument`.

        For schema files (ending with "schema.json"), it performs schema validation.
        A SHA256 hash of the content is stored in metadata for change detection.

        Args:
            path: The `Path` object of the JSON file to process.

        Returns:
            A `KnowledgeDocument` object representing the processed JSON file.

        Raises:
            ValueError: If the JSON file is invalid or schema validation fails.
        """
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)  # Attempt to load JSON content
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

        if path.name.endswith("schema.json"):
            # Validate JSON schema files against Draft202012 standard
            Draft202012Validator.check_schema(data)
        return KnowledgeDocument(
            identifier=str(path.relative_to(self.knowledge_root)),
            title=path.stem.replace("_", " ").title(),
            doc_type=DocumentType.JSON,
            path=str(path),
            metadata={"hash": hashlib.sha256(text.encode("utf-8")).hexdigest()},  # Store content hash
        )

    def vectorise(self, documents: Iterable[KnowledgeDocument]) -> List[VectorisedChunk]:
        """
        Generates vector embeddings for each section of the provided documents.

        Each non-empty section of a Markdown document is converted into a `VectorisedChunk`
        containing its text, metadata, and a vector embedding.

        Args:
            documents: An iterable of `KnowledgeDocument` objects (typically Markdown documents).

        Returns:
            A list of `VectorisedChunk` objects, each representing a vectorised section.
        """
        chunks: List[VectorisedChunk] = []
        for doc in documents:
            for idx, section in enumerate(doc.sections):
                if not section.strip():
                    continue  # Skip empty sections
                vector = self.vectoriser.encode(section)  # Encode section text into a vector
                chunk_id = f"{doc.identifier}::section_{idx}"  # Unique ID for the chunk
                chunks.append(
                    VectorisedChunk(
                        doc_id=doc.identifier,
                        chunk_id=chunk_id,
                        text=section,
                        metadata={
                            "title": doc.title,
                            "heading": doc.headings[idx][0] if idx < len(doc.headings) else "",
                            "path": doc.path,
                        },
                        vector=vector,
                    )
                )
        return chunks

    def persist(
        self,
        documents: Dict[str, List[KnowledgeDocument]],
        vector_chunks: Sequence[VectorisedChunk],
    ) -> None:
        """
        Persists the structured knowledge documents and vector embeddings to output files.

        - Structured Markdown and JSON documents are saved to `STRUCTURED_DATA_PATH`.
        - Vectorized chunks (embeddings) are saved to `EMBEDDINGS_DATA_PATH`.
        - A cache of JSON schema hashes is saved to `SCHEMA_CACHE_PATH` for change detection.

        Args:
            documents: A dictionary of processed `KnowledgeDocument` objects.
            vector_chunks: A sequence of `VectorisedChunk` objects.
        """
        ensure_output_dirs()  # Ensure output directories exist
        STRUCTURED_DATA_PATH.write_text(
            json.dumps(
                {
                    "markdown": [doc.model_dump() for doc in documents["markdown"]],
                    "json": [doc.model_dump() for doc in documents["json"]],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        EMBEDDINGS_DATA_PATH.write_text(
            json.dumps([chunk.__dict__ for chunk in vector_chunks], indent=2),
            encoding="utf-8",
        )
        SCHEMA_CACHE_PATH.write_text(
            json.dumps(
                {
                    doc.identifier: doc.metadata["hash"]
                    for doc in documents["json"]
                    if "hash" in doc.metadata
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def sync_knowledge_base() -> Dict[str, List[KnowledgeDocument]]:
    """
    Orchestrates the full knowledge base synchronization process.

    This function initializes the ingestor, loads all documents, vectorizes
    the Markdown content, and persists the structured data and embeddings.

    Returns:
        A dictionary containing the loaded `KnowledgeDocument` objects,
        categorized by "markdown" and "json".
    """
    ingestor = KnowledgeBaseIngestor()
    documents = ingestor.load()  # Load all knowledge documents
    chunks = ingestor.vectorise(documents["markdown"])  # Vectorize Markdown document sections
    ingestor.persist(documents, chunks)  # Persist structured data and embeddings
    return documents
