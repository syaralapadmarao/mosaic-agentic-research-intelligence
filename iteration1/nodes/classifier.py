"""Classifier node + route gate for the Earnings Intelligence Pipeline."""

from iteration1.state import (
    PipelineState,
    DocumentClassification,
    TRANSCRIPT_ROUTE,
    PRESENTATION_ROUTE,
)
from iteration1.prompts import CLASSIFIER_PROMPT

MAX_CLASSIFIER_CHARS = 12_000


def classify_document(state: PipelineState, llm) -> dict:
    """LangGraph node: classify the document and extract metadata.

    Sends the first ~12 000 chars of the document to the LLM.
    The beginning of earnings transcripts contains the richest
    classification signals (company name, call type, participants).

    Returns 'classification' and 'route' keys for PipelineState.
    """
    raw_text = state["raw_text"]
    truncated = raw_text[:MAX_CLASSIFIER_CHARS]

    structured_llm = llm.with_structured_output(DocumentClassification)
    chain = CLASSIFIER_PROMPT | structured_llm

    classification = chain.invoke({
        "file_name": state["file_name"],
        "raw_text": truncated,
    })

    route = (
        PRESENTATION_ROUTE
        if classification.doc_type == "investor_presentation"
        else TRANSCRIPT_ROUTE
    )

    print(f"[Classifier] {classification.doc_type} | "
          f"{classification.company} | {classification.period} | "
          f"confidence={classification.confidence:.2f} → route={route}")

    return {"classification": classification, "route": route}


def route_gate(state: PipelineState) -> str:
    """Conditional edge function: returns the next node name based on route.

    Used by pipeline.py as:
        graph.add_conditional_edges("classify", route_gate, {
            "transcript": "extract_transcript_sections",
            "presentation": "extract_presentation_sections",
        })
    """
    return state["route"]
