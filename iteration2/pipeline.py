"""Offline Ingestion LangGraph Pipeline for Iteration 2.

Flow:
  parse_document → mnpi_gate → classify → route:
    → Workflow A (iter1: extract_metrics → calc → validate → assemble)
    → Workflow B (iter1: extract_guidance → deltas → assemble)
    → Workflow C (sell_side_extractor → table_extractor → store)
    → Workflow D (visit_note_extractor → store)
  → chunk_and_embed (smart chunk → metadata tag → embed into ChromaDB)
"""

import json
import os
from functools import partial

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END

from iteration1.state import MetricSchema, PRESENTATION_ROUTE, TRANSCRIPT_ROUTE
from iteration1.pdf_parser import parse_pdf_with_page_tags
from iteration1.nodes.metric_extractor import extract_metrics
from iteration1.nodes.metric_calculator import calculate_metrics
from iteration1.nodes.metric_validator import validate_metrics
from iteration1.nodes.metric_assembler import assemble_metrics
from iteration1.nodes.guidance_extractor import extract_guidance
from iteration1.nodes.guidance_delta import detect_deltas
from iteration1.nodes.guidance_assembler import assemble_guidance

from iteration2.state import (
    OfflinePipelineState, SELL_SIDE_ROUTE, VISIT_NOTE_ROUTE,
    BROKER_EMAIL_ROUTE, SOURCE_TYPE_MAP, SourceDocument,
)
from iteration2.mnpi_gate import screen_for_mnpi
from iteration2.md_parser import parse_markdown_document, parse_md_with_section_tags
from iteration2.nodes.classifier import classify_document
from iteration2.nodes.sell_side_extractor import extract_sell_side
from iteration2.nodes.visit_note_extractor import extract_visit_note
from iteration2.nodes.table_extractor import extract_estimates_from_table
from iteration2.nodes.metadata_tagger import build_source_document, tag_chunks
from iteration2.chunker import smart_chunk
from iteration2 import storage as iter2_storage
from iteration2 import vector_store
import iteration1.storage as iter1_storage

SCHEMAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "iteration1", "schemas")


COMPANY_SCHEMA_MAP = {
    "max": "hospital",
    "apollo": "hospital",
    "rainbow": "hospital",
    "kims": "hospital",
}


def _load_schema(company_key: str) -> MetricSchema:
    """Load a metric schema JSON file by company key."""
    safe = company_key.lower().replace(" ", "_")
    schema_key = COMPANY_SCHEMA_MAP.get(safe, safe)
    path = os.path.join(SCHEMAS_DIR, f"{schema_key}.json")
    if not os.path.exists(path):
        path = os.path.join(SCHEMAS_DIR, f"{safe}.json")
    if not os.path.exists(path):
        candidates = [f for f in os.listdir(SCHEMAS_DIR) if f.endswith(".json")]
        for c in candidates:
            if safe in c.lower():
                path = os.path.join(SCHEMAS_DIR, c)
                break
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return MetricSchema(**data)


# ---------------------------------------------------------------------------
# Pipeline Nodes
# ---------------------------------------------------------------------------

def _parse_document_node(state: OfflinePipelineState) -> dict:
    """Parse the document based on file type."""
    file_path = state["file_path"]

    if file_path.endswith(".pdf"):
        tagged = parse_pdf_with_page_tags(file_path)
        return {"raw_text": tagged, "page_tagged_text": tagged}
    elif file_path.endswith(".md"):
        result = parse_markdown_document(file_path)
        return {
            "raw_text": result["section_tagged_text"],
            "page_tagged_text": result["section_tagged_text"],
        }
    else:
        with open(file_path, "r") as f:
            text = f.read()
        tagged = parse_md_with_section_tags(text)
        return {"raw_text": tagged, "page_tagged_text": tagged}


def _mnpi_gate_node(state: OfflinePipelineState) -> dict:
    """Screen document for MNPI content."""
    text = state.get("raw_text", "")
    result = screen_for_mnpi(text, state.get("file_name", ""))

    if result.is_mnpi:
        conn = iter2_storage.get_connection(state["company"])
        iter2_storage.log_mnpi_screening(
            conn, state["file_name"], state["company"],
            "MNPI_DETECTED", result.confidence,
            result.reason, "BLOCKED",
        )
        conn.close()

    return {
        "mnpi_result": result,
        "scrubbed_text": result.scrubbed_text or text,
    }


def _route_after_classify(state: OfflinePipelineState) -> str:
    """Route to the appropriate workflow based on classification."""
    mnpi = state.get("mnpi_result")
    if mnpi and mnpi.is_mnpi:
        return "end_blocked"

    route = state.get("route", "")
    if route == SELL_SIDE_ROUTE or route == BROKER_EMAIL_ROUTE:
        return "extract_sell_side"
    elif route == VISIT_NOTE_ROUTE:
        return "extract_visit_note"
    elif route == TRANSCRIPT_ROUTE:
        return "extract_guidance"
    else:
        return "extract_metrics"


def _store_sell_side_node(state: OfflinePipelineState) -> dict:
    """Store sell-side extraction results in SQLite."""
    report = state.get("sell_side_report")
    if not report:
        return {}

    company = state["company"]
    conn = iter2_storage.get_connection(company)

    source_id = iter2_storage.save_source(
        conn, company, "opinion",
        state.get("classification", {}).doc_type if state.get("classification") else "sell_side",
        state["file_name"], state["file_path"],
        analyst=report.analyst, firm=report.firm,
        rating=report.rating, target_price=report.target_price,
        date=report.date,
    )

    for est in report.estimates:
        iter2_storage.save_analyst_estimate(
            conn, source_id, company,
            est.metric_name, est.value, est.unit, est.period,
            analyst=report.analyst, firm=report.firm,
        )

    conn.close()

    parsed = parse_markdown_document(state["file_path"]) if state["file_path"].endswith(".md") else {}
    tables = parsed.get("tables", [])
    additional_estimates = []
    for table in tables:
        additional_estimates.extend(
            extract_estimates_from_table(table, analyst=report.analyst, firm=report.firm)
        )

    return {}


def _store_visit_note_node(state: OfflinePipelineState) -> dict:
    """Store visit note extraction results in SQLite."""
    extraction = state.get("visit_note_extraction")
    if not extraction:
        return {}

    company = state["company"]
    conn = iter2_storage.get_connection(company)

    source_id = iter2_storage.save_source(
        conn, company, "field_data", "visit_note",
        state["file_name"], state["file_path"],
        analyst=extraction.visitor,
        date=extraction.date,
    )

    for insight in extraction.insights:
        iter2_storage.save_visit_insight(
            conn, source_id, company,
            insight.topic, insight.observation,
            insight.sentiment, insight.conviction,
            insight.source_person, extraction.date,
        )

    conn.close()
    return {}


def _chunk_and_embed_node(state: OfflinePipelineState) -> dict:
    """Chunk the document and embed into ChromaDB."""
    mnpi = state.get("mnpi_result")
    if mnpi and mnpi.is_mnpi:
        return {}

    text = state.get("scrubbed_text") or state.get("raw_text", "")
    if not text:
        return {}

    company = state["company"]
    classification = state.get("classification")
    doc_type = classification.doc_type if classification else "unknown"
    source_type = SOURCE_TYPE_MAP.get(doc_type, "disclosure")

    is_page_tagged = state["file_path"].endswith(".pdf")

    parsed = None
    tables = []
    if state["file_path"].endswith(".md"):
        parsed = parse_markdown_document(state["file_path"])
        tables = parsed.get("tables", [])

    chunks = smart_chunk(text, doc_type, tables=tables, is_page_tagged=is_page_tagged)

    header_meta = parsed.get("metadata", {}) if parsed else {}
    source_doc = build_source_document(
        state["file_path"],
        header_metadata=header_meta,
        company_override=company,
    )
    chunks = tag_chunks(chunks, source_doc)

    n = vector_store.embed_and_store(company, source_type, chunks)

    conn = iter2_storage.get_connection(company)

    classification = state.get("classification")
    existing = iter2_storage.get_sources(conn, company)
    already_saved = any(s["file_name"] == state["file_name"] for s in existing)
    if not already_saved:
        iter2_storage.save_source(
            conn, company, source_type,
            doc_type,
            state["file_name"], state["file_path"],
            date=classification.doc_date if classification else None,
        )

    iter2_storage.log_mnpi_screening(
        conn, state["file_name"], company,
        "CLEARED", 0.0, None, "INGESTED",
    )
    conn.close()

    return {"chunks": chunks}


def _end_blocked_node(state: OfflinePipelineState) -> dict:
    """Terminal node for MNPI-blocked documents."""
    return {}


# ---------------------------------------------------------------------------
# Pipeline Builder
# ---------------------------------------------------------------------------

def build_offline_pipeline(model_name: str = "gpt-4o-mini") -> StateGraph:
    """Build the offline document ingestion pipeline."""
    load_dotenv(find_dotenv())

    llm = init_chat_model(model_name, model_provider="openai")

    graph = StateGraph(OfflinePipelineState)

    graph.add_node("parse_document", _parse_document_node)
    graph.add_node("mnpi_gate", _mnpi_gate_node)
    graph.add_node("classify", partial(classify_document, llm=llm))

    # Workflow A (iter1: presentations → metrics)
    graph.add_node("extract_metrics", partial(extract_metrics, llm=llm))
    graph.add_node("calculate_metrics", calculate_metrics)
    graph.add_node("validate_metrics", partial(validate_metrics, llm=llm))
    graph.add_node("assemble_table", assemble_metrics)

    # Workflow B (iter1: transcripts → guidance)
    graph.add_node("extract_guidance", partial(extract_guidance, llm=llm))
    graph.add_node("detect_deltas", partial(detect_deltas, llm=llm))
    graph.add_node("assemble_guidance", assemble_guidance)

    # Workflow C (sell-side reports)
    graph.add_node("extract_sell_side", partial(extract_sell_side, llm=llm))
    graph.add_node("store_sell_side", _store_sell_side_node)

    # Workflow D (visit notes)
    graph.add_node("extract_visit_note", partial(extract_visit_note, llm=llm))
    graph.add_node("store_visit_note", _store_visit_note_node)

    # Post-extraction: chunk and embed
    graph.add_node("chunk_and_embed", _chunk_and_embed_node)

    # MNPI blocked terminal
    graph.add_node("end_blocked", _end_blocked_node)

    # --- Edges ---
    graph.set_entry_point("parse_document")
    graph.add_edge("parse_document", "mnpi_gate")
    graph.add_edge("mnpi_gate", "classify")

    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "extract_metrics": "extract_metrics",
            "extract_guidance": "extract_guidance",
            "extract_sell_side": "extract_sell_side",
            "extract_visit_note": "extract_visit_note",
            "end_blocked": "end_blocked",
        },
    )

    # Workflow A edges
    graph.add_edge("extract_metrics", "calculate_metrics")
    graph.add_edge("calculate_metrics", "validate_metrics")
    graph.add_edge("validate_metrics", "assemble_table")
    graph.add_edge("assemble_table", "chunk_and_embed")

    # Workflow B edges
    graph.add_edge("extract_guidance", "detect_deltas")
    graph.add_edge("detect_deltas", "assemble_guidance")
    graph.add_edge("assemble_guidance", "chunk_and_embed")

    # Workflow C edges
    graph.add_edge("extract_sell_side", "store_sell_side")
    graph.add_edge("store_sell_side", "chunk_and_embed")

    # Workflow D edges
    graph.add_edge("extract_visit_note", "store_visit_note")
    graph.add_edge("store_visit_note", "chunk_and_embed")

    # Terminal edges
    graph.add_edge("chunk_and_embed", END)
    graph.add_edge("end_blocked", END)

    return graph.compile()
