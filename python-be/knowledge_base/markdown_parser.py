"""
This module provides utilities for parsing Markdown documents, extracting their
front matter (metadata), and segmenting their content into structured sections
based on headings. This is crucial for converting raw Markdown knowledge assets
into a format suitable for the AI knowledge base.
"""

from __future__ import annotations  # Enables postponed evaluation of type annotations

from dataclasses import dataclass  # For creating data classes
from typing import Dict, Iterable, List, Tuple  # Type hinting utilities

import frontmatter  # Library for parsing YAML front matter from Markdown files
from markdown_it import MarkdownIt  # Core Markdown parser library
from mdit_py_plugins.front_matter import front_matter_plugin  # Plugin for MarkdownIt to handle front matter


@dataclass
class MarkdownSection:
    """
    Represents a single section of a Markdown document, typically delimited by a heading.

    Attributes:
        heading: The text of the heading that introduces this section.
                 Empty string if the section is before the first heading.
        level: The heading level (e.g., 1 for #, 2 for ##). 0 if no heading.
        content: The raw Markdown content of the section, excluding the heading itself.
    """
    heading: str
    level: int
    content: str


def _build_parser() -> MarkdownIt:
    """
    Configures and returns a MarkdownIt parser instance.

    The parser is set up with 'commonmark' rules, with breaks and HTML disabled.
    It also enables table and linkify extensions and integrates the front matter plugin.

    Returns:
        A configured `MarkdownIt` parser instance.
    """
    md = MarkdownIt("commonmark", {"breaks": False, "html": False})
    md.enable(["table", "linkify"])  # Enable common Markdown extensions
    md.use(front_matter_plugin)  # Integrate the front matter parsing plugin
    return md


# Global MarkdownIt parser instance to avoid re-initialization
MD = _build_parser()


def parse_markdown_document(raw_text: str) -> Tuple[Dict[str, str], List[MarkdownSection]]:
    """
    Parses a raw Markdown text string into its YAML front matter (metadata)
    and a list of structured `MarkdownSection` objects.

    The function first extracts front matter, then uses the MarkdownIt parser
    to tokenize the remaining content. It then iterates through the tokens
    to identify headings and segment the content into sections.

    Args:
        raw_text: The complete Markdown content as a string, potentially including
                  YAML front matter at the beginning.

    Returns:
        A tuple containing:
        - A dictionary of metadata (key-value pairs from YAML front matter).
        - A list of `MarkdownSection` objects, each representing a logical section
          of the Markdown document.
    """
    post = frontmatter.loads(raw_text)  # Parse front matter and content
    tokens = MD.parse(post.content)  # Parse the Markdown content (without front matter)
    sections: List[MarkdownSection] = []

    current_heading: str = ""
    current_level: int = 0
    buffer: List[str] = []  # Buffer to accumulate content for the current section

    def flush() -> None:
        """
        Helper function to save the buffered content as a `MarkdownSection`
        and reset the buffer for the next section.
        """
        nonlocal current_heading, current_level, buffer
        if current_heading or buffer:  # Only flush if there's content or a heading
            sections.append(
                MarkdownSection(
                    heading=current_heading or "",  # Use empty string if no heading (e.g., preamble)
                    level=current_level,
                    content="\n".join(buffer).strip(),  # Join buffered lines and strip whitespace
                )
            )
            # Reset for the next section
            current_heading = ""
            current_level = 0
            buffer = []

    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            flush()  # A new heading means the previous section is complete
            if token.tag and len(token.tag) > 1 and token.tag[0].lower() == "h" and token.tag[1].isdigit():
                current_level = int(token.tag[1])  # Extract heading level (h1, h2, etc.)
            else:
                current_level = 0
        elif token.type == "heading_close":
            continue  # Ignore closing heading tags
        elif token.type == "inline" and token.map:
            # Inline tokens often contain the actual text of headings or paragraphs
            # Check if the previous token was a heading_open to capture the heading text
            if index > 0 and tokens[index - 1].type == "heading_open":
                current_heading = token.content.strip()
            elif token.content:
                buffer.append(token.content)  # Add other inline content to the buffer
        elif token.children and token.content:
            # For tokens that have children (e.g., lists, blockquotes), their content
            # is usually in the children. For simplicity, we append the token's content.
            # A more robust parser might recursively process children.
            buffer.append(token.content)

    flush()  # Flush any remaining content after the last token
    # Filter out sections that might have only a heading but no actual content
    filtered_sections = [section for section in sections if section.content or section.heading]
    # Convert metadata keys/values to strings for consistency
    return {str(k): str(v) for k, v in post.metadata.items()}, filtered_sections


def extract_headings(sections: Iterable[MarkdownSection]) -> List[Tuple[str, int]]:
    """
    Extracts a list of (heading text, heading level) tuples from a collection
    of `MarkdownSection` objects.

    Args:
        sections: An iterable collection of `MarkdownSection` objects.

    Returns:
        A list of tuples, where each tuple contains the heading text (string)
        and its level (integer) for sections that have a defined heading.
    """
    return [(section.heading, section.level) for section in sections if section.heading]
