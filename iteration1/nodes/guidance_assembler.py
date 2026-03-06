"""CODE Assemble node — saves guidance to SQLite and builds the guidance table.

This is a deterministic code step (no LLM). It:
1. Saves the current quarter's guidance items to SQLite
2. Saves any detected deltas
3. Queries the DB for up to 8 quarters of guidance history
4. Returns the assembled table for the dashboard
"""

from iteration1.state import PipelineState
from iteration1 import storage


def assemble_guidance(state: PipelineState) -> dict:
    """LangGraph node (CODE): persist guidance and build the dashboard table.

    Steps:
    1. Open the SQLite DB for this company
    2. Save the PDF record (if not already saved by Workflow A)
    3. Save each guidance item
    4. Save deltas (if any)
    5. Query the rolling guidance table
    6. Return the table as 'guidance_table' in state

    Returns the 'guidance_table' key for PipelineState.
    """
    classification = state["classification"]
    company = state.get("company") or classification.company
    quarter = state["quarter"]
    guidance_items = state.get("guidance_items", [])
    deltas = state.get("guidance_deltas")

    conn = storage.get_connection(company)

    pdf_id = storage.save_pdf_record(
        conn,
        file_name=state["file_name"],
        company=company,
        quarter=quarter,
        doc_type=classification.doc_type,
        file_path=state["pdf_path"],
    )

    for item in guidance_items:
        storage.save_guidance_item(
            conn,
            company=company,
            quarter=quarter,
            topic=item.topic,
            statement=item.statement,
            sentiment=item.sentiment,
            speaker=item.speaker,
            timeframe=item.timeframe,
            page_number=item.page,
            passage=item.passage,
            pdf_id=pdf_id,
        )

    if deltas and deltas.deltas:
        prior_q = deltas.prior_quarter or ""
        for d in deltas.deltas:
            storage.save_guidance_delta(
                conn,
                company=company,
                quarter=quarter,
                prior_quarter=prior_q,
                topic=d.topic,
                change_type=d.change_type,
                current_statement=d.current_statement,
                prior_statement=d.prior_statement,
                summary=d.summary,
            )

    table = storage.get_guidance_table(conn, company=company)
    conn.close()

    stored_quarters = table["quarters"]
    topic_count = len(table["topics"])
    total_items = sum(
        len(items)
        for topic_data in table["topics"].values()
        for items in topic_data.values()
    )

    print(f"[GuidanceAssembler] {company} | "
          f"saved {quarter} | "
          f"{topic_count} topics, {total_items} total items | "
          f"table spans {len(stored_quarters)} quarters: "
          f"{stored_quarters[0] if stored_quarters else '?'} → "
          f"{stored_quarters[-1] if stored_quarters else '?'}")

    return {"guidance_table": table}
