"""Smart Chunker — Source-type-aware document chunking.

Chunk sizes per design doc:
  - Sell-side reports: 1000-1500 tokens (~1200 chars)
  - Broker emails: 300-500 tokens (~400 chars)
  - Visit notes: 500-800 tokens (~800 chars)
  - Transcripts/Presentations: 1000-1500 tokens (~1200 chars, page-boundary aware)
  - Tables: extract as structured dict + text description chunk
"""

import re
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from iteration2.state import NAMESPACE_DISCLOSURE, NAMESPACE_OPINION, NAMESPACE_FIELD_DATA

CHUNK_CONFIG = {
    "sell_side": {"chunk_size": 1200, "chunk_overlap": 200},
    "broker_email": {"chunk_size": 400, "chunk_overlap": 80},
    "visit_note": {"chunk_size": 800, "chunk_overlap": 150},
    "transcript": {"chunk_size": 1200, "chunk_overlap": 200},
    "investor_presentation": {"chunk_size": 1200, "chunk_overlap": 200},
    "earnings_call": {"chunk_size": 1200, "chunk_overlap": 200},
    "default": {"chunk_size": 1000, "chunk_overlap": 150},
}


def _get_splitter(doc_type: str) -> RecursiveCharacterTextSplitter:
    """Get a text splitter configured for the document type."""
    config = CHUNK_CONFIG.get(doc_type, CHUNK_CONFIG["default"])
    return RecursiveCharacterTextSplitter(
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_page_tagged_text(text: str, doc_type: str) -> list[dict]:
    """Chunk page-tagged text (from PDFs) respecting page boundaries.

    Each chunk gets a 'page_numbers' metadata field indicating which pages it spans.
    """
    page_pattern = re.compile(r"\[PAGE\s+(\d+)\]")
    pages = page_pattern.split(text)

    page_texts: list[tuple[int, str]] = []
    i = 0
    while i < len(pages):
        if i == 0:
            if pages[i].strip():
                page_texts.append((0, pages[i]))
            i += 1
        elif i + 1 < len(pages):
            try:
                page_num = int(pages[i])
                page_texts.append((page_num, pages[i + 1]))
            except ValueError:
                pass
            i += 2
        else:
            i += 1

    splitter = _get_splitter(doc_type)
    chunks = []
    for page_num, page_text in page_texts:
        if not page_text.strip():
            continue
        sub_chunks = splitter.split_text(page_text)
        for sc in sub_chunks:
            chunks.append({
                "text": sc,
                "page_numbers": [page_num],
            })

    return chunks


def chunk_section_tagged_text(text: str, doc_type: str) -> list[dict]:
    """Chunk section-tagged text (from markdown) respecting section boundaries.

    Each chunk gets a 'section' metadata field.
    """
    section_pattern = re.compile(r"\[SECTION\s+\d+:\s*(.+?)\]")
    parts = section_pattern.split(text)

    sections: list[tuple[str, str]] = []
    i = 0
    current_section = "Header"
    while i < len(parts):
        if i == 0:
            if parts[i].strip():
                sections.append((current_section, parts[i]))
            i += 1
        elif i + 1 < len(parts):
            current_section = parts[i].strip()
            sections.append((current_section, parts[i + 1]))
            i += 2
        else:
            i += 1

    splitter = _get_splitter(doc_type)
    chunks = []
    for section_name, section_text in sections:
        if not section_text.strip():
            continue
        sub_chunks = splitter.split_text(section_text)
        for sc in sub_chunks:
            chunks.append({
                "text": sc,
                "section": section_name,
            })

    return chunks


def chunk_table(table: dict) -> dict:
    """Create a text chunk from a structured table.

    Takes a table dict from md_parser.extract_markdown_tables and returns
    a chunk with the text description for embedding.
    """
    return {
        "text": table.get("description", table.get("raw_text", "")),
        "section": "Financial Estimates Table",
        "is_table": True,
        "structured_data": {
            "headers": table.get("headers", []),
            "rows": table.get("rows", []),
        },
    }


def smart_chunk(text: str, doc_type: str, tables: list[dict] = None,
                is_page_tagged: bool = False) -> list[dict]:
    """Main entry point: chunk a document based on its type and format.

    Args:
        text: Document text (either page-tagged or section-tagged).
        doc_type: Document type for chunk sizing.
        tables: Extracted tables from md_parser (for sell-side reports).
        is_page_tagged: True if text uses [PAGE N] tags (PDFs), False for [SECTION] tags (markdown).

    Returns:
        List of chunk dicts with 'text' and metadata fields.
    """
    if is_page_tagged:
        chunks = chunk_page_tagged_text(text, doc_type)
    else:
        chunks = chunk_section_tagged_text(text, doc_type)

    if tables:
        for table in tables:
            table_chunk = chunk_table(table)
            if table_chunk["text"].strip():
                chunks.append(table_chunk)

    for i, chunk in enumerate(chunks):
        chunk["chunk_index"] = i

    return chunks
