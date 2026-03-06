"""LangGraph pipeline wiring for the Earnings Intelligence Pipeline.

Shared entry: parse_pdf → classify, then branch by doc_type:

  Workflow A (Presentations):
    parse_pdf → classify → extract_metrics → calculate_metrics
    → validate_metrics → assemble_table → END

  Workflow B (Transcripts):
    parse_pdf → classify → extract_guidance → detect_deltas
    → assemble_guidance → END
"""

import json
import os
from functools import partial

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END

from iteration1.state import (
    PipelineState, MetricSchema,
    PRESENTATION_ROUTE, TRANSCRIPT_ROUTE,
)
from iteration1.tracing import setup_arize_tracing
from iteration1.pdf_parser import parse_pdf_with_page_tags
from iteration1.nodes.classifier import classify_document
from iteration1.nodes.metric_extractor import extract_metrics
from iteration1.nodes.metric_calculator import calculate_metrics
from iteration1.nodes.metric_validator import validate_metrics
from iteration1.nodes.metric_assembler import assemble_metrics
from iteration1.nodes.guidance_extractor import extract_guidance
from iteration1.nodes.guidance_delta import detect_deltas
from iteration1.nodes.guidance_assembler import assemble_guidance

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "schemas")


def _load_schema(company_key: str) -> MetricSchema:
    """Load a metric schema JSON file by company key (e.g. 'max_healthcare')."""
    path = os.path.join(SCHEMAS_DIR, f"{company_key}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No metric schema found at {path}")
    with open(path) as f:
        data = json.load(f)
    return MetricSchema(**data)


def _parse_pdf_node(state: PipelineState) -> dict:
    """LangGraph node: parse the PDF with page tags."""
    tagged = parse_pdf_with_page_tags(state["pdf_path"])
    result = {"page_tagged_text": tagged}
    if not state.get("raw_text"):
        result["raw_text"] = tagged
    return result


def _route_after_parse(state: PipelineState) -> str:
    """Conditional edge: route to Workflow A or B based on doc_type."""
    route = state.get("route")
    if route == TRANSCRIPT_ROUTE:
        return "extract_guidance"
    return "extract_metrics"


def build_pipeline(model_name: str = "gpt-4o-mini") -> StateGraph:
    """Build and compile the full pipeline with both workflows.

    parse_pdf runs first so the classifier has actual content.
    After parse_pdf → classify, routes to:
      - Workflow A (extract_metrics → ...) for presentations
      - Workflow B (extract_guidance → ...) for transcripts
    """
    load_dotenv(find_dotenv())
    setup_arize_tracing()

    llm = init_chat_model(model_name, model_provider="openai")

    graph = StateGraph(PipelineState)

    # --- Shared nodes ---
    graph.add_node("classify", partial(classify_document, llm=llm))
    graph.add_node("parse_pdf", _parse_pdf_node)

    # --- Workflow A: Presentation → Metrics ---
    graph.add_node("extract_metrics", partial(extract_metrics, llm=llm))
    graph.add_node("calculate_metrics", calculate_metrics)
    graph.add_node("validate_metrics", partial(validate_metrics, llm=llm))
    graph.add_node("assemble_table", assemble_metrics)

    # --- Workflow B: Transcript → Guidance ---
    graph.add_node("extract_guidance", partial(extract_guidance, llm=llm))
    graph.add_node("detect_deltas", partial(detect_deltas, llm=llm))
    graph.add_node("assemble_guidance", assemble_guidance)

    # --- Edges ---
    # Parse PDF first so the classifier has actual content (not just filename)
    graph.set_entry_point("parse_pdf")
    graph.add_edge("parse_pdf", "classify")

    graph.add_conditional_edges(
        "classify",
        _route_after_parse,
        {
            "extract_metrics": "extract_metrics",
            "extract_guidance": "extract_guidance",
        },
    )

    # Workflow A edges
    graph.add_edge("extract_metrics", "calculate_metrics")
    graph.add_edge("calculate_metrics", "validate_metrics")
    graph.add_edge("validate_metrics", "assemble_table")
    graph.add_edge("assemble_table", END)

    # Workflow B edges
    graph.add_edge("extract_guidance", "detect_deltas")
    graph.add_edge("detect_deltas", "assemble_guidance")
    graph.add_edge("assemble_guidance", END)

    return graph.compile()


def load_schema(company_key: str) -> MetricSchema:
    """Public wrapper for loading a metric schema."""
    return _load_schema(company_key)
