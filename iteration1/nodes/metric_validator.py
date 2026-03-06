"""LLM Validate node — sanity-checks extracted and calculated metrics.

Acts as a soft gate: flagged metrics are marked for human review
but the pipeline continues. The validation results are stored in
SQLite alongside the metrics.
"""

from iteration1.state import PipelineState, ValidationResult
from iteration1.prompts import METRIC_VALIDATION_PROMPT


def _format_metrics_for_validation(metrics) -> str:
    """Format all metrics into readable text for the validation prompt."""
    lines = []
    for m in metrics:
        if not m.found:
            lines.append(f"- {m.metric_name}: NOT FOUND ({m.note or 'no details'})")
            continue

        source = "calculated" if m.note and "Calculated" in m.note else "extracted"
        citation = f"(page {m.page})" if m.page else "(no page ref)"
        lines.append(
            f"- {m.metric_name}: {m.value} {m.unit} "
            f"[{source}] {citation}"
        )
    return "\n".join(lines)


def validate_metrics(state: PipelineState, llm) -> dict:
    """LangGraph node: LLM-based sanity check on all metrics.

    Checks unit consistency, range plausibility, extraction errors,
    and internal consistency between direct and derived values.

    Returns the 'validation' key for PipelineState.
    """
    classification = state["classification"]
    schema = state["metric_schema"]
    calculated = state["calculated_metrics"]

    found_metrics = [m for m in calculated if m.found]
    if not found_metrics:
        print("[MetricValidator] No metrics to validate — skipping.")
        return {"validation": ValidationResult(
            results=[],
            overall_status="clean",
        )}

    structured_llm = llm.with_structured_output(ValidationResult)
    chain = METRIC_VALIDATION_PROMPT | structured_llm

    company = state.get("company") or classification.company
    validation = chain.invoke({
        "company": company,
        "quarter": state["quarter"],
        "sector": schema.sector or "Financial",
        "metrics_formatted": _format_metrics_for_validation(calculated),
    })

    flagged = [r for r in validation.results if r.status == "flag"]
    passed = [r for r in validation.results if r.status == "pass"]

    print(f"[MetricValidator] {state['quarter']} | "
          f"pass={len(passed)}, flagged={len(flagged)} → {validation.overall_status}")
    for r in flagged:
        print(f"  ! {r.metric_name}: {r.issue}")

    return {"validation": validation}
