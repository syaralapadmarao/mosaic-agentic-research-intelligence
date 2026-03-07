"""Deterministic Metadata Tagger — CODE, no LLM.

Tags each chunk with structured metadata derived from:
  - File path (company name, doc_type from directory structure)
  - Document header (broker_name, analyst, date)
  - Iteration 1 schema (ticker, sector)
  - Source type mapping to namespace
"""

import os
import re
from typing import Optional

from iteration2.state import SOURCE_TYPE_MAP, SourceDocument


def infer_doc_type_from_path(file_path: str) -> str:
    """Infer document type from the file's directory structure."""
    path_lower = file_path.lower()
    if "/sell_side/" in path_lower:
        return "sell_side"
    if "/visit_notes/" in path_lower or "/visit_note/" in path_lower:
        return "visit_note"
    if "/broker_emails/" in path_lower or "/broker_email/" in path_lower:
        return "broker_email"
    if "/transcript/" in path_lower or "/transcripts/" in path_lower:
        return "transcript"
    if "/presentation/" in path_lower or "/presentations/" in path_lower or "/pres/" in path_lower:
        return "investor_presentation"
    if file_path.endswith(".pdf"):
        return "unknown_pdf"
    return "unknown"


def infer_company_from_path(file_path: str) -> Optional[str]:
    """Infer company name from the sample_docs directory structure."""
    match = re.search(r"sample_docs[/\\]([^/\\]+)", file_path)
    if match:
        return match.group(1)
    return None


def get_source_type(doc_type: str) -> str:
    """Map doc_type to namespace (disclosure/opinion/field_data)."""
    return SOURCE_TYPE_MAP.get(doc_type, "disclosure")


def tag_chunks(chunks: list[dict], source_doc: SourceDocument) -> list[dict]:
    """Add source metadata to each chunk.

    Enriches chunk dicts with:
      - company, ticker, sector, region
      - source_type, doc_type
      - broker_name, analyst, date
      - file_name
    """
    metadata = {
        "company": source_doc.company,
        "ticker": source_doc.ticker,
        "sector": source_doc.sector,
        "region": source_doc.region,
        "source_type": source_doc.source_type,
        "doc_type": source_doc.doc_type,
        "broker_name": source_doc.broker_name,
        "analyst": source_doc.analyst,
        "date": source_doc.date,
        "file_name": source_doc.file_name,
    }

    for chunk in chunks:
        chunk["metadata"] = {**metadata, **chunk.get("metadata", {})}
        if "section" in chunk:
            chunk["metadata"]["section"] = chunk["section"]
        if "page_numbers" in chunk:
            chunk["metadata"]["page_numbers"] = chunk["page_numbers"]

    return chunks


def build_source_document(
    file_path: str,
    header_metadata: dict = None,
    company_override: str = None,
    schema_metadata: dict = None,
) -> SourceDocument:
    """Build a SourceDocument from file path, header metadata, and schema.

    Args:
        file_path: Path to the document file.
        header_metadata: Metadata extracted from md_parser.extract_header_metadata.
        company_override: Explicit company name (overrides path inference).
        schema_metadata: Ticker/sector from iter1 schema.
    """
    header_metadata = header_metadata or {}
    schema_metadata = schema_metadata or {}

    company = company_override or infer_company_from_path(file_path) or "unknown"
    doc_type = infer_doc_type_from_path(file_path)
    source_type = get_source_type(doc_type)

    return SourceDocument(
        source_type=source_type,
        doc_type=doc_type,
        file_name=os.path.basename(file_path),
        file_path=file_path,
        company=company,
        ticker=schema_metadata.get("ticker") or header_metadata.get("ticker"),
        sector=schema_metadata.get("sector", "Healthcare"),
        region=schema_metadata.get("region"),
        date=header_metadata.get("date"),
        broker_name=header_metadata.get("firm"),
        analyst=header_metadata.get("analyst"),
    )
