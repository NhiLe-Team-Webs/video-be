"""
Helpers for building a lightweight directed graph representing knowledge relationships.

This module provides functionality to construct a graph that visualizes the connections
between different knowledge documents and their sections, aiding in understanding
the overall structure and interdependencies within the knowledge base.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

from typing import Iterable  # Used for type hinting collections

import networkx as nx  # Library for creating and manipulating graphs

from .models import KnowledgeDocument  # Imports the data model for a knowledge document


def build_knowledge_graph(documents: Iterable[KnowledgeDocument]) -> nx.DiGraph:
    """
    Constructs a lightweight directed graph linking document sections by their headings.

    Each document and its individual sections (identified by headings) become nodes
    in the graph. Edges are created from a document node to its section nodes,
    representing a hierarchical relationship.

    Args:
        documents: An iterable collection of `KnowledgeDocument` objects, each
                   representing a parsed document from the knowledge base.

    Returns:
        A `networkx.DiGraph` object representing the knowledge graph.
        - Document nodes have attributes: `type="document"`, `title`, `path`.
        - Section nodes have attributes: `type="section"`, `level` (heading level).
    """
    graph = nx.DiGraph()  # Initialize an empty directed graph
    for doc in documents:
        doc_node = doc.identifier  # Use document identifier as the node name
        # Add the document node with its metadata
        graph.add_node(doc_node, type="document", title=doc.title, path=doc.path)
        for heading, level in doc.headings:
            # Create a unique identifier for each section node
            section_node = f"{doc.identifier}::{heading}"
            # Add the section node with its metadata
            graph.add_node(section_node, type="section", level=level)
            # Add a directed edge from the document to its section
            graph.add_edge(doc_node, section_node)
    return graph  # Return the constructed graph
