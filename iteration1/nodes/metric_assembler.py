"""CODE Assemble node — saves metrics to SQLite and builds the 8-quarter table.

This is a deterministic code step (no LLM). It:
1. Saves the current quarter's metrics + citations + validations to SQLite
2. Queries the DB for up to 8 quarters of history
3. Computes QoQ percentage changes
4. Returns the assembled table for the dashboard
"""

from iteration1.state import PipelineState
from iteration1 import storage


def _compute_qoq_changes(table: dict) -> dict:
    """Add QoQ percentage change to each metric's values.

    Modifies table in place, adding a 'changes' dict alongside 'values':
        metrics[name]["changes"] = {"FY25-Q4": "+1.6%", "FY26-Q1": "+1.2%", ...}

    The first quarter in the window has no change (empty string).
    """
    quarters = table["quarters"]
    for name, data in table["metrics"].items():
        changes = {}
        for i, q in enumerate(quarters):
            if i == 0 or q not in data["values"]:
                changes[q] = ""
                continue

            prev_q = quarters[i - 1]
            curr_val = data["values"].get(q)
            prev_val = data["values"].get(prev_q)

            if curr_val is not None and prev_val is not None and prev_val != 0:
                pct = (curr_val - prev_val) / abs(prev_val) * 100
                sign = "+" if pct > 0 else ""
                changes[q] = f"{sign}{pct:.1f}%"
            else:
                changes[q] = ""

        data["changes"] = changes

    return table


def assemble_metrics(state: PipelineState) -> dict:
    """LangGraph node (CODE): persist metrics and build the dashboard table.

    Steps:
    1. Open the SQLite DB for this company
    2. Save the PDF record
    3. Save each metric + its citation + its validation result
    4. Query the rolling 8-quarter table
    5. Compute QoQ changes
    6. Return the table as 'metrics_table' in state

    Returns the 'metrics_table' key for PipelineState.
    """
    classification = state["classification"]
    company = state.get("company") or classification.company
    quarter = state["quarter"]
    calculated = state["calculated_metrics"]
    validation = state["validation"]

    conn = storage.get_connection(company)

    pdf_id = storage.save_pdf_record(
        conn,
        file_name=state["file_name"],
        company=company,
        quarter=quarter,
        doc_type=classification.doc_type,
        file_path=state["pdf_path"],
    )

    validation_lookup = {}
    if validation and validation.results:
        validation_lookup = {r.metric_name: r for r in validation.results}

    for m in calculated:
        source = "calculated" if m.note and "Calculated" in m.note else "direct"
        metric_id = storage.save_metric(
            conn,
            company=company,
            quarter=quarter,
            metric_name=m.metric_name,
            value=m.value,
            unit=m.unit,
            source=source,
            found=m.found,
            note=m.note,
            pdf_id=pdf_id,
        )

        if m.found and m.page is not None and m.passage:
            storage.save_citation(
                conn,
                metric_id=metric_id,
                page_number=m.page,
                passage=m.passage,
                pdf_id=pdf_id,
            )

        vr = validation_lookup.get(m.metric_name)
        if vr:
            storage.save_validation(
                conn,
                metric_id=metric_id,
                status=vr.status,
                issue=vr.issue,
            )

    schema = state["metric_schema"]
    table = storage.get_metrics_table(
        conn,
        company=company,
        metric_names=schema.metric_names(),
    )
    table = _compute_qoq_changes(table)

    conn.close()

    stored_quarters = table["quarters"]
    print(f"[MetricAssembler] {company} | "
          f"saved {quarter} | "
          f"table spans {len(stored_quarters)} quarters: "
          f"{stored_quarters[0] if stored_quarters else '?'} → "
          f"{stored_quarters[-1] if stored_quarters else '?'}")

    return {"metrics_table": table}
