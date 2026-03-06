"""LLM Delta node — detects quarter-over-quarter changes in management guidance."""

from iteration1.state import PipelineState, DeltaDetectionResult
from iteration1.prompts import GUIDANCE_DELTA_PROMPT
from iteration1 import storage


def _format_guidance_for_prompt(items: list[dict]) -> str:
    """Format stored guidance items into readable text for the delta prompt."""
    if not items:
        return "(no guidance available for this quarter)"

    lines = []
    current_topic = None
    for g in items:
        if g["topic"] != current_topic:
            current_topic = g["topic"]
            lines.append(f"\n[{current_topic}]")
        speaker = f" — {g['speaker']}" if g.get("speaker") else ""
        timeframe = f" ({g['timeframe']})" if g.get("timeframe") else ""
        lines.append(f"  • {g['statement']}{speaker}{timeframe}")
    return "\n".join(lines)


def detect_deltas(state: PipelineState, llm) -> dict:
    """LangGraph node: compare current quarter's guidance against the prior quarter.

    Fetches the prior quarter's guidance from SQLite, then asks the LLM to
    identify new, upgraded, downgraded, reiterated, or removed guidance.

    If no prior quarter exists (first transcript ingested), returns an empty
    DeltaDetectionResult.

    Returns the 'guidance_deltas' key for PipelineState.
    """
    classification = state["classification"]
    company = state.get("company") or classification.company
    quarter = state["quarter"]
    schema = state.get("metric_schema")
    sector = schema.sector if schema else "Financial"

    conn = storage.get_connection(company)
    prior_quarter = storage.get_prior_quarter(conn, company, quarter)

    if not prior_quarter:
        conn.close()
        print(f"[GuidanceDelta] {quarter} | no prior quarter found — skipping delta detection")
        return {"guidance_deltas": DeltaDetectionResult(deltas=[], prior_quarter=None)}

    prior_guidance = storage.get_guidance_for_quarter(conn, company, prior_quarter)
    conn.close()

    current_items = state.get("guidance_items", [])
    current_formatted = _format_guidance_for_prompt([
        {"topic": g.topic, "statement": g.statement,
         "speaker": g.speaker, "timeframe": g.timeframe}
        for g in current_items
    ])
    prior_formatted = _format_guidance_for_prompt(prior_guidance)

    structured_llm = llm.with_structured_output(DeltaDetectionResult)
    chain = GUIDANCE_DELTA_PROMPT | structured_llm

    result = chain.invoke({
        "company": company,
        "sector": sector,
        "current_quarter": quarter,
        "prior_quarter": prior_quarter,
        "current_guidance_formatted": current_formatted,
        "prior_guidance_formatted": prior_formatted,
    })
    result.prior_quarter = prior_quarter

    by_type = {}
    for d in result.deltas:
        by_type.setdefault(d.change_type, []).append(d)

    print(f"[GuidanceDelta] {quarter} vs {prior_quarter} | "
          f"{len(result.deltas)} changes detected")
    for change_type, deltas in by_type.items():
        print(f"  {change_type}: {len(deltas)}")
        for d in deltas:
            print(f"    • [{d.topic}] {d.summary[:80]}")

    return {"guidance_deltas": result}
