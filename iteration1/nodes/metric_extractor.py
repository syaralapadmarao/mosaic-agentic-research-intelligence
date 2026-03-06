"""LLM Extract node — extracts metrics with page-level citations from a presentation."""

from iteration1.state import PipelineState, ExtractionResult
from iteration1.prompts import METRIC_EXTRACTION_PROMPT


def _format_schema_for_prompt(metric_schema) -> str:
    """Format the metric schema into readable text for the extraction prompt."""
    lines = []
    for m in metric_schema.metrics:
        aliases_str = ", ".join(m.aliases) if m.aliases else "none"
        line = f"- {m.name} | unit: {m.unit} | aliases: [{aliases_str}]"
        if m.fallback_formula:
            line += f" | (can also be calculated: {m.fallback_formula})"
        lines.append(line)
    return "\n".join(lines)


def extract_metrics(state: PipelineState, llm) -> dict:
    """LangGraph node: extract metrics from the page-tagged document.

    Uses the metric schema to tell the LLM exactly which metrics to find.
    Each extracted metric includes a page number and passage for citation.

    Returns the 'extracted_metrics' key for PipelineState.
    """
    classification = state["classification"]
    metric_schema = state["metric_schema"]

    structured_llm = llm.with_structured_output(ExtractionResult)
    chain = METRIC_EXTRACTION_PROMPT | structured_llm

    result = chain.invoke({
        "sector": metric_schema.sector or "Financial",
        "doc_type": classification.doc_type,
        "company": classification.company,
        "quarter": state["quarter"],
        "metric_schema_formatted": _format_schema_for_prompt(metric_schema),
        "page_tagged_text": state["page_tagged_text"],
    })

    found_count = sum(1 for m in result.metrics if m.found)
    total = len(result.metrics)

    print(f"[MetricExtractor] {classification.company} ({state['quarter']}) | "
          f"found {found_count}/{total} metrics")
    for m in result.metrics:
        if m.found:
            print(f"  + {m.metric_name}: {m.raw_value} (page {m.page})")
        else:
            print(f"  - {m.metric_name}: NOT FOUND — {m.note}")

    return {"extracted_metrics": result.metrics}
