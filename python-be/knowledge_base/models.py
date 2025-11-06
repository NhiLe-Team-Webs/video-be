"""
This module defines the Pydantic models and dataclasses used to represent
structured knowledge within the AI video automation pipeline. These models
ensure data consistency and facilitate validation across various components
of the knowledge base, including documents, rules, definitions, and vectorized chunks.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

from dataclasses import dataclass  # For creating simple data-holding classes
from enum import Enum  # For creating enumerated constants
from typing import Dict, List, Optional, Sequence, Tuple  # Type hinting utilities

from pydantic import BaseModel, Field  # Base class for data models and field customization


class DocumentType(str, Enum):
    """
    Enumerates the types of documents stored in the knowledge base.
    """
    MARKDOWN = "markdown"  # Represents a Markdown document (.md)
    JSON = "json"          # Represents a JSON document (.json), including schemas


class KnowledgeDocument(BaseModel):
    """
    Represents a parsed document from the knowledge base, encapsulating its
    content, structure, and metadata.
    """
    identifier: str = Field(description="Unique identifier for the document (e.g., relative path).")
    title: str = Field(description="Human-readable title of the document.")
    doc_type: DocumentType = Field(description="The type of the document (e.g., MARKDOWN, JSON).")
    path: str = Field(description="Absolute file path to the document.")
    headings: List[Tuple[str, int]] = Field(
        default_factory=list,
        description="List of (heading text, level) tuples extracted from Markdown documents."
    )
    sections: List[str] = Field(
        default_factory=list,
        description="List of content sections from Markdown documents, delimited by headings."
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata associated with the document (e.g., YAML front matter)."
    )


class GuidelineRule(BaseModel):
    """
    Represents a single planning guideline rule, typically extracted from
    `planning_guidelines.md`.
    """
    id: str = Field(description="Unique identifier for the guideline rule.")
    title: str = Field(description="Concise title of the guideline rule.")
    description: str = Field(description="Detailed description of the rule.")
    rationale: Optional[str] = Field(
        default=None,
        description="Explanation of why this rule is important or its underlying principle."
    )
    related_sections: Sequence[str] = Field(
        default_factory=list,
        description="List of identifiers for related knowledge base sections."
    )


class ElementDefinition(BaseModel):
    """
    Defines the characteristics of a specific video element type, extracted from
    `element_definitions.md`.
    """
    element_type: str = Field(description="The type of the video element (e.g., 'broll', 'text_overlay').")
    purpose: str = Field(description="The primary purpose or function of this element type.")
    layer: str = Field(description="The rendering layer where this element typically appears.")
    key_fields: Sequence[str] = Field(description="List of essential fields for this element type.")
    defaults: Optional[str] = Field(
        default=None,
        description="Default behaviors or values for this element type."
    )


class GlossaryTerm(BaseModel):
    """
    Represents a single term and its definition from the `glossary.md` file.
    """
    term: str = Field(description="The glossary term.")
    definition: str = Field(description="The definition of the term.")
    related: Sequence[str] = Field(
        default_factory=list,
        description="List of related terms."
    )
    references: Sequence[str] = Field(
        default_factory=list,
        description="List of references or sources for the definition."
    )


class ExampleSnippet(BaseModel):
    """
    Represents a structured example of a video editing pattern or element usage,
    typically from `examples/patterns.json`.
    """
    video_id: str = Field(description="Identifier of the video this example is derived from.")
    timestamp: float = Field(description="Timestamp in the video where this snippet occurs.")
    label: str = Field(description="A descriptive label for the example.")
    outcome: str = Field(description="The desired outcome or effect demonstrated by the snippet.")
    rationale: Optional[str] = Field(
        default=None,
        description="Explanation of why this example is a good illustration."
    )
    elements: Sequence[Dict[str, object]] = Field(
        default_factory=list,
        description="A sequence of video elements (conforming to element_schema.json) in this snippet."
    )


class ValidationIssue(BaseModel):
    """
    Represents a single issue found during the validation of a video plan element.
    """
    code: str = Field(description="A unique code identifying the type of validation issue.")
    message: str = Field(description="A human-readable description of the issue.")
    severity: str = Field(default="error", description="The severity of the issue (e.g., 'error', 'warning').")
    context: Dict[str, object] = Field(
        default_factory=dict,
        description="Additional context or data relevant to the issue (e.g., field name, value)."
    )


class ValidationReport(BaseModel):
    """
    Summarizes the results of a validation process for a video plan.
    """
    is_valid: bool = Field(description="True if the plan is valid, False otherwise.")
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="A list of all validation issues found."
    )


@dataclass
class VectorisedChunk:
    """
    Represents a chunk of text content that has been converted into a vector embedding.
    These chunks are used for similarity search in the vector store.
    """
    doc_id: str = Field(description="The identifier of the source document.")
    chunk_id: str = Field(description="Unique identifier for this specific chunk within the document.")
    text: str = Field(description="The original text content of the chunk.")
    metadata: Dict[str, str] = Field(description="Metadata associated with the chunk (e.g., title, heading, path).")
    vector: List[float] = Field(description="The numerical vector embedding of the text content.")
