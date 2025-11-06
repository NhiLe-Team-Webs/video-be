# python-be/knowledge_base/__init__.py

"""
This `__init__.py` file marks the `knowledge_base` directory as a Python package.
It also exposes key components of the knowledge base module for easier import and usage
in other parts of the `python-be` application.

The module facilitates the ingestion, storage, and retrieval of knowledge for the AI
video automation pipeline.
"""

from .ingestion import KnowledgeBaseIngestor, sync_knowledge_base
from .repository import KnowledgeRepository
from .vector_store import VectorSearchResult

# Defines the public API of the `knowledge_base` package.
# When `from knowledge_base import *` is used, only these names will be imported.
__all__ = [
    "KnowledgeBaseIngestor",  # Class for ingesting data into the knowledge base
    "KnowledgeRepository",    # Class for interacting with the stored knowledge
    "VectorSearchResult",     # Data structure for results from vector store searches
    "sync_knowledge_base",    # Function to synchronize the knowledge base
]
