"""
This module defines and manages file paths for the knowledge base, including
the root directories for source knowledge documents and the output directories
for processed and vectorized data. It ensures a consistent and organized
filesystem structure for the AI video automation pipeline.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

from pathlib import Path  # For object-oriented filesystem paths


# Determines the root directory of the entire project.
# Path(__file__).resolve() gets the absolute path of the current file.
# .parents[1] navigates up two levels:
# 1. From `paths.py` to `knowledge_base/`
# 2. From `knowledge_base/` to `python-be/` (which is the PROJECT_ROOT)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Defines the root directory where raw knowledge base Markdown and JSON files are stored.
# This is one level up from `python-be/` (i.e., the main project directory).
KNOWLEDGE_BASE_ROOT = PROJECT_ROOT.parent / "knowledge-base"

# Defines the root directory for all processed knowledge base outputs.
# This is located within the `python-be/outputs/knowledge/` directory.
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "knowledge"

# Specific file paths for structured data, embeddings, and schema cache within OUTPUT_ROOT.
STRUCTURED_DATA_PATH = OUTPUT_ROOT / "structured.json"  # Path to store structured knowledge documents
EMBEDDINGS_DATA_PATH = OUTPUT_ROOT / "embeddings.json"  # Path to store vector embeddings of knowledge chunks
SCHEMA_CACHE_PATH = OUTPUT_ROOT / "schema_cache.json"    # Path to store hashes of JSON schemas for change detection


def ensure_output_dirs() -> None:
    """
    Ensures that the output directory for processed knowledge base data exists.
    If the directory does not exist, it will be created, along with any necessary
    parent directories.
    """
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)  # Create directory if it doesn't exist
