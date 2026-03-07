"""Workflow D: Visit Note / Channel Check Extractor.

Extracts structured observations, sentiment signals, and conviction
from visit notes and channel checks.
"""

from iteration2.prompts import VISIT_NOTE_EXTRACTION_PROMPT
from iteration2.state import VisitNoteExtraction, OfflinePipelineState, GuidanceItem

GUIDANCE_TOPICS = [
    "Financial Outlook",
    "Capacity Expansion",
    "Operational Efficiency",
    "Capital Allocation",
    "Strategic Initiatives",
    "Market & Competition",
    "Regulatory & Risk",
]


def extract_visit_note(state: OfflinePipelineState, llm) -> dict:
    """LangGraph node: extract insights from a visit note or channel check."""
    structured_llm = llm.with_structured_output(VisitNoteExtraction)
    chain = VISIT_NOTE_EXTRACTION_PROMPT | structured_llm

    text = state.get("scrubbed_text") or state.get("raw_text", "")
    topics_formatted = "\n".join(f"  - {t}" for t in GUIDANCE_TOPICS)

    extraction = chain.invoke({
        "company": state["company"],
        "sector": "Healthcare",
        "section_tagged_text": text[:15000],
        "topics_formatted": topics_formatted,
    })

    return {"visit_note_extraction": extraction}
