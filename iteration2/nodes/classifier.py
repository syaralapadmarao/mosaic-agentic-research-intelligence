"""Extended Document Classifier for Iteration 2.

Adds sell_side, visit_note, and broker_email to the classification options.
Reuses the iter1 classifier prompt structure with an extended doc_type list.
"""

from langchain_core.prompts import ChatPromptTemplate

from iteration1.state import DocumentClassification
from iteration2.state import (
    SELL_SIDE_ROUTE, VISIT_NOTE_ROUTE, BROKER_EMAIL_ROUTE,
    PRESENTATION_ROUTE, TRANSCRIPT_ROUTE, SOURCE_TYPE_MAP,
)


EXTENDED_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert financial document classifier at a top-tier investment firm.

Classify this document into one of these types:
1. **earnings_call** — Prepared remarks by executives followed by analyst Q&A
2. **investor_presentation** — Slide-deck style content with strategic/financial highlights
3. **sell_side** — Analyst research report with price targets, ratings, financial estimates
4. **visit_note** — Site visit, management meeting, or channel check observations
5. **broker_email** — Short analyst email with market signals, channel checks, or data points
6. **broker_note** — Longer broker research note
7. **press_release** — Official company announcement
8. **other** — None of the above

Also extract:
- Company name and ticker (if identifiable)
- Fiscal period covered (e.g. "Q2 FY26")
- Document date (YYYY-MM-DD if identifiable)
- Confidence (0.0 to 1.0)
- One-sentence summary

KEY CLASSIFICATION SIGNALS:
- sell_side: Has "Rating:", "Target Price:", analyst name + firm, financial estimate tables
- visit_note: Has "Site Visit", "Management Meeting", "Channel Check", "Key Observations", personal assessments
- broker_email: Has "From:", "To:", "Subject:", short format, signal/data point focused
- earnings_call: Has Q&A section, "prepared remarks", analyst questions
- investor_presentation: Has slide content, financial highlights, strategic overview

PERIOD FORMAT: Use "Q1 FY26" style."""),
    ("user", """Classify this document.

FILE NAME: {file_name}

DOCUMENT TEXT (may be truncated):
{raw_text}"""),
])


DOC_TYPE_TO_ROUTE = {
    "earnings_call": TRANSCRIPT_ROUTE,
    "investor_presentation": PRESENTATION_ROUTE,
    "sell_side": SELL_SIDE_ROUTE,
    "broker_note": SELL_SIDE_ROUTE,
    "visit_note": VISIT_NOTE_ROUTE,
    "broker_email": BROKER_EMAIL_ROUTE,
    "press_release": PRESENTATION_ROUTE,
    "other": PRESENTATION_ROUTE,
}


def classify_document(state: dict, llm) -> dict:
    """LangGraph node: classify a document with extended type support."""
    structured_llm = llm.with_structured_output(DocumentClassification)
    chain = EXTENDED_CLASSIFIER_PROMPT | structured_llm

    text = state.get("scrubbed_text") or state.get("raw_text", "")

    classification = chain.invoke({
        "file_name": state["file_name"],
        "raw_text": text[:12000],
    })

    doc_type = classification.doc_type
    route = DOC_TYPE_TO_ROUTE.get(doc_type, PRESENTATION_ROUTE)
    source_type = SOURCE_TYPE_MAP.get(doc_type, "disclosure")

    return {
        "classification": classification,
        "route": route,
        "source_type": source_type,
    }
