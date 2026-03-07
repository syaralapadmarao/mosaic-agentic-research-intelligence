"""Workflow C: Sell-Side Report Extractor.

Extracts ratings, target prices, analyst estimates, thesis, and risks
from sell-side research reports.
"""

from iteration2.prompts import SELL_SIDE_EXTRACTION_PROMPT
from iteration2.state import SellSideReport, OfflinePipelineState


def extract_sell_side(state: OfflinePipelineState, llm) -> dict:
    """LangGraph node: extract structured data from a sell-side report."""
    structured_llm = llm.with_structured_output(SellSideReport)
    chain = SELL_SIDE_EXTRACTION_PROMPT | structured_llm

    text = state.get("scrubbed_text") or state.get("raw_text", "")

    report = chain.invoke({
        "company": state["company"],
        "section_tagged_text": text[:15000],
    })

    return {"sell_side_report": report}
