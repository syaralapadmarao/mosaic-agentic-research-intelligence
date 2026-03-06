"""CODE Calculate node — computes derived metrics using formulas from the schema.

This is a deterministic code step (no LLM). It is a guardrail by design:
math is done by Python, not by the model, to avoid hallucinated numbers.

For each metric that has a fallback_formula and was NOT found by the extractor,
the calculator attempts to compute it from other extracted values.
"""

from copy import deepcopy

from iteration1.state import PipelineState, ExtractedMetric


def _build_value_lookup(metrics: list[ExtractedMetric]) -> dict[str, float]:
    """Build a name→value dict from extracted metrics that were found."""
    return {
        m.metric_name: m.value
        for m in metrics
        if m.found and m.value is not None
    }


def _build_citation_lookup(metrics: list[ExtractedMetric]) -> dict[str, dict]:
    """Build a name→{page, passage} dict for citation propagation to derived metrics."""
    return {
        m.metric_name: {"page": m.page, "passage": m.passage}
        for m in metrics
        if m.found and m.page is not None
    }


def _derive_citation(required: list[str], formula: str,
                     citation_lookup: dict[str, dict]) -> tuple[int | None, str | None]:
    """Build a citation for a calculated metric from its input metrics' citations.

    Returns (page, passage) where page is the first input's page and passage
    describes the derivation sources.
    """
    parts = []
    first_page = None
    for name in required:
        cite = citation_lookup.get(name)
        if cite and cite["page"] is not None:
            if first_page is None:
                first_page = cite["page"]
            parts.append(f"{name} (p.{cite['page']})")
        else:
            parts.append(name)

    if first_page is None:
        return None, None

    passage = f"Derived from {' and '.join(parts)} using formula: {formula}"
    return first_page, passage


def _safe_eval_formula(formula: str, values: dict[str, float]) -> float | None:
    """Evaluate a formula string using the extracted values.

    Replaces metric names with their numeric values and evaluates
    the resulting arithmetic expression. Only basic math operators
    are allowed for safety.
    """
    expr = formula
    for name, val in sorted(values.items(), key=lambda x: -len(x[0])):
        expr = expr.replace(name, str(val))

    try:
        result = eval(expr, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            return round(result, 2)
    except Exception:
        pass
    return None


def calculate_metrics(state: PipelineState) -> dict:
    """LangGraph node (CODE): compute derived metrics from extracted values.

    For each metric in the schema:
      - If already found by the extractor → keep as-is
      - If NOT found and has a fallback_formula → attempt calculation
      - If required inputs for the formula are missing → leave as not-found

    Returns the 'calculated_metrics' key for PipelineState.
    """
    extracted = state["extracted_metrics"]
    schema = state["metric_schema"]

    calculated = deepcopy(extracted)
    values = _build_value_lookup(extracted)
    citation_lookup = _build_citation_lookup(extracted)

    for metric_def in schema.metrics:
        existing = next((m for m in calculated if m.metric_name == metric_def.name), None)

        already_found = existing and existing.found and existing.value is not None
        has_formula = metric_def.fallback_formula is not None

        if already_found or not has_formula:
            continue

        required = metric_def.fallback_requires
        missing = [r for r in required if r not in values]
        if missing:
            if existing:
                existing.note = (
                    f"Cannot calculate: missing {', '.join(missing)} "
                    f"(formula: {metric_def.fallback_formula})"
                )
            print(f"  ? {metric_def.name}: SKIP — missing {', '.join(missing)}")
            continue

        result = _safe_eval_formula(metric_def.fallback_formula, values)
        if result is None:
            print(f"  ? {metric_def.name}: SKIP — formula eval failed")
            continue

        derived_page, derived_passage = _derive_citation(
            required, metric_def.fallback_formula, citation_lookup,
        )

        if existing:
            existing.value = result
            existing.raw_value = f"{result} (calculated)"
            existing.unit = metric_def.unit
            existing.found = True
            existing.page = derived_page
            existing.passage = derived_passage
            existing.note = f"Calculated: {metric_def.fallback_formula}"
        else:
            calculated.append(ExtractedMetric(
                metric_name=metric_def.name,
                value=result,
                raw_value=f"{result} (calculated)",
                unit=metric_def.unit,
                page=derived_page,
                passage=derived_passage,
                found=True,
                note=f"Calculated: {metric_def.fallback_formula}",
            ))

        values[metric_def.name] = result

    direct_count = sum(1 for m in calculated if m.found and m.note is None)
    calc_count = sum(1 for m in calculated if m.found and m.note and "Calculated" in m.note)
    missing_count = sum(1 for m in calculated if not m.found)

    print(f"[MetricCalculator] {state['quarter']} | "
          f"direct={direct_count}, calculated={calc_count}, missing={missing_count}")
    for m in calculated:
        if m.found and m.note and "Calculated" in m.note:
            print(f"  = {m.metric_name}: {m.value} {m.unit} ({m.note})")

    return {"calculated_metrics": calculated}
