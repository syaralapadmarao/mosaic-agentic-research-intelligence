"""Gradio dashboard UI for the Earnings Intelligence Pipeline.

Provides:
  - Company selection (auto-discovers from sample_docs/ subfolders)
  - Schema selection (auto-discovers from schemas/ JSON files)
  - Cold-start processing of all PDFs for a company
  - 8-quarter metrics table with QoQ changes and color-coding (Workflow A)
  - Citation deep-linking (click a metric+quarter to see source passage & page)
  - Validation status panel
  - Guidance Tracker: forward-looking statements by topic across quarters (Workflow B)
  - Guidance Changes: quarter-over-quarter delta detection
"""

import os
import glob

import gradio as gr

from iteration1.main import run_single, _infer_quarter
from iteration1.pipeline import load_schema
from iteration1 import storage

SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")
SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "schemas")


def _discover_companies() -> list[str]:
    """Return sorted list of company folder names under sample_docs/."""
    if not os.path.isdir(SAMPLE_DOCS_DIR):
        return []
    entries = os.listdir(SAMPLE_DOCS_DIR)
    return sorted(
        e for e in entries
        if os.path.isdir(os.path.join(SAMPLE_DOCS_DIR, e)) and not e.startswith(".")
    )


def _discover_schemas() -> list[str]:
    """Return sorted list of schema keys (filenames without .json)."""
    if not os.path.isdir(SCHEMAS_DIR):
        return []
    return sorted(
        f.replace(".json", "")
        for f in os.listdir(SCHEMAS_DIR)
        if f.endswith(".json")
    )


def _find_pdfs(company: str) -> list[str]:
    """Find all PDFs under sample_docs/{company}/ recursively."""
    pattern = os.path.join(SAMPLE_DOCS_DIR, company, "**", "*.pdf")
    return sorted(glob.glob(pattern, recursive=True))


def _qoq_color(change_str: str) -> str:
    """Return a colored markdown span for a QoQ change string."""
    if not change_str:
        return ""
    if change_str.startswith("+"):
        return f' <span style="color:#22c55e;font-size:0.85em">{change_str}</span>'
    if change_str.startswith("-"):
        return f' <span style="color:#ef4444;font-size:0.85em">{change_str}</span>'
    return f' <span style="color:#a3a3a3;font-size:0.85em">{change_str}</span>'


def _build_metrics_markdown(table: dict, citations: dict = None) -> str:
    """Render the metrics table as a Markdown table with QoQ color-coding and page citations.

    citations: {quarter: {metric_name: [{"page_number": N, "passage": "..."}]}}
    """
    if not table or not table.get("quarters"):
        return "*No metrics data yet. Run the pipeline first.*"

    quarters = table["quarters"]
    metrics = table["metrics"]
    citations = citations or {}

    header = "| Metric | " + " | ".join(quarters) + " |"
    separator = "|:---|" + "|".join(":---:" for _ in quarters) + "|"

    rows = []
    for metric_name, data in metrics.items():
        values = data.get("values", {})
        changes = data.get("changes", {})
        unit = data.get("unit", "")
        label = f"**{metric_name}** ({unit})" if unit else f"**{metric_name}**"

        cells = []
        for q in quarters:
            v = values.get(q)
            c = changes.get(q, "")
            if v is not None:
                cell = f"{v:,.1f}"
                page_ref = _get_page_ref(citations, q, metric_name)
                if page_ref:
                    cell += f" <sup>{page_ref}</sup>"
                cell += _qoq_color(c)
            else:
                cell = "—"
            cells.append(cell)

        rows.append(f"| {label} | " + " | ".join(cells) + " |")

    return "\n".join([header, separator] + rows)


def _get_page_ref(citations: dict, quarter: str, metric_name: str) -> str:
    """Build a clickable page reference linking to the source PDF.

    Returns HTML like: <a href="/file=/path/to/file.pdf#page=6" target="_blank">p.6</a>
    For calculated metrics (source='calculated'), appends an asterisk.
    """
    q_cites = citations.get(quarter, {})
    m_cites = q_cites.get(metric_name, [])
    if not m_cites:
        return ""

    links = []
    seen_pages = set()
    is_calculated = any(c.get("source") == "calculated" for c in m_cites)

    for c in m_cites:
        page = c["page_number"]
        if page in seen_pages:
            continue
        seen_pages.add(page)

        file_path = c.get("file_path")
        label = f"p.{page}"
        if is_calculated:
            label += "*"

        if file_path:
            links.append(
                f'<a href="/gradio_api/file={file_path}#page={page}" '
                f'target="_blank" title="Open source PDF at page {page}">'
                f'{label}</a>'
            )
        else:
            links.append(label)

    return ",".join(links)


def _build_validation_markdown(validation) -> str:
    """Render validation results as Markdown."""
    if not validation:
        return "*No validation data.*"

    status_icon = "CLEAN" if validation.overall_status == "clean" else "REVIEW NEEDED"
    lines = [f"**Overall: {status_icon}**\n"]

    for v in validation.results:
        if v.status == "pass":
            lines.append(f"- {v.metric_name}: PASS")
        else:
            lines.append(f"- {v.metric_name}: FLAG — {v.issue}")

    return "\n".join(lines)


def _fetch_all_citations(company: str, quarters: list[str]) -> dict:
    """Fetch citations from SQLite for all quarters.

    Returns: {quarter: {metric_name: [{"page_number": N, "passage": "..."}]}}
    """
    result = {}
    try:
        conn = storage.get_connection(company)
        for q in quarters:
            result[q] = storage.get_citations_for_quarter(conn, company, q)
        conn.close()
    except Exception:
        pass
    return result


def _build_citations_markdown(company: str, quarters: list[str]) -> str:
    """Build a citation reference panel from the SQLite database with PDF links."""
    if not quarters:
        return "*No citations available.*"

    try:
        conn = storage.get_connection(company)
    except Exception:
        return "*Could not open database for citations.*"

    lines = []
    for q in quarters:
        citations = storage.get_citations_for_quarter(conn, company, q)
        if not citations:
            continue
        lines.append(f"### {q}")
        for metric_name, cites in citations.items():
            for c in cites:
                page = c["page_number"]
                file_path = c.get("file_path")
                source = c.get("source", "direct")
                source_tag = " *(calculated)*" if source == "calculated" else ""

                if file_path:
                    page_link = (
                        f'<a href="/gradio_api/file={file_path}#page={page}" '
                        f'target="_blank">p.{page}</a>'
                    )
                else:
                    page_link = f"p.{page}"

                lines.append(
                    f"- **{metric_name}** ({page_link}){source_tag}: "
                    f"*\"{c['passage']}\"*"
                )
        lines.append("")

    conn.close()

    if not lines:
        return "*No citations stored yet.*"
    return "\n".join(lines)


def _sentiment_indicator(sentiment: str) -> str:
    """Return a colored arrow HTML span for a sentiment level."""
    from iteration1.state import SENTIMENT_ARROWS, SENTIMENT_COLORS
    arrow = SENTIMENT_ARROWS.get(sentiment, "→")
    color = SENTIMENT_COLORS.get(sentiment, "#a3a3a3")
    return f'<span style="color:{color};font-weight:bold;font-size:1.2em">{arrow}</span>'


def _guidance_page_link(page: int | None, file_path: str | None) -> str:
    """Build a clickable page citation for guidance items."""
    if not page:
        return ""
    if file_path:
        return (
            f'<a href="/gradio_api/file={file_path}#page={page}" '
            f'target="_blank">[p.{page}]</a>'
        )
    return f"[p.{page}]"


def _compute_topic_tag(topic: str, q_data: dict, quarters: list[str]) -> str:
    """Compute a lifecycle tag for a topic across quarters.

    Tags:
      NEW TOPIC  — topic only appears in the latest quarter
      STALE      — topic last discussed 3+ quarters ago
      DRIFT      — topic changed sentiment direction recently
      (empty)    — normal ongoing topic
    """
    present_quarters = [q for q in quarters if q in q_data and q_data[q]]
    if not present_quarters:
        return ""

    last_seen_idx = max(quarters.index(q) for q in present_quarters)
    first_seen_idx = min(quarters.index(q) for q in present_quarters)
    latest_idx = len(quarters) - 1

    if first_seen_idx == latest_idx and len(present_quarters) == 1:
        return ' <span style="color:#22c55e;font-size:0.8em;font-weight:bold">NEW TOPIC</span>'

    if last_seen_idx < latest_idx - 2:
        return ' <span style="color:#ef4444;font-size:0.8em;font-weight:bold">STALE</span>'

    if len(present_quarters) >= 2:
        recent_two = sorted(present_quarters, key=lambda q: quarters.index(q))[-2:]
        sent_0 = _dominant_sentiment(q_data.get(recent_two[0], []))
        sent_1 = _dominant_sentiment(q_data.get(recent_two[1], []))
        bullish = {"very_bullish", "bullish"}
        cautious = {"cautious", "very_cautious"}
        if (sent_0 in bullish and sent_1 in cautious) or (sent_0 in cautious and sent_1 in bullish):
            return ' <span style="color:#fbbf24;font-size:0.8em;font-weight:bold">DRIFT</span>'

    return ""


def _dominant_sentiment(items: list[dict]) -> str:
    """Return the most common sentiment from a list of guidance items."""
    if not items:
        return "neutral"
    sentiments = [i.get("sentiment", "neutral") for i in items]
    return max(set(sentiments), key=sentiments.count)


def _build_guidance_markdown(company: str) -> str:
    """Build the Guidance Tracker as a topic × quarter matrix.

    Layout mirrors the screenshot: topics as rows, quarters as columns.
    Each cell has a sentiment arrow, condensed summary, and page citations.
    """
    try:
        conn = storage.get_connection(company)
        table = storage.get_guidance_table(conn, company)
        conn.close()
    except Exception:
        return "*Could not load guidance data.*"

    quarters = table.get("quarters", [])
    topics = table.get("topics", {})
    if not quarters or not topics:
        return "*No guidance data yet. Process a transcript to populate.*"

    short_q = [q.replace("FY", "'").replace(" ", "") for q in quarters]

    legend = (
        '<span style="font-size:0.85em;color:#a3a3a3">'
        'Sentiment: '
        '<span style="color:#22c55e">↑</span> Very Bullish · '
        '<span style="color:#86efac">↗</span> Bullish · '
        '<span style="color:#a3a3a3">→</span> Neutral · '
        '<span style="color:#fbbf24">↘</span> Cautious · '
        '<span style="color:#ef4444">↓</span> Very Cautious · '
        '<span style="color:#22c55e;font-weight:bold">NEW TOPIC</span> · '
        '<span style="color:#ef4444;font-weight:bold">STALE</span> · '
        '<span style="color:#fbbf24;font-weight:bold">DRIFT</span> · '
        '*Not discussed*'
        '</span>'
    )

    header = "| TOPIC | " + " | ".join(short_q) + " |"
    separator = "|:---|" + "|".join(":---:" for _ in quarters) + "|"

    rows = []
    for topic, q_data in topics.items():
        tag = _compute_topic_tag(topic, q_data, quarters)
        label = f"**{topic}**{tag}"

        cells = []
        for q in quarters:
            items = q_data.get(q, [])
            if not items:
                cells.append("*Not discussed*")
                continue

            sentiment = _dominant_sentiment(items)
            arrow = _sentiment_indicator(sentiment)

            stmts = [i["statement"] for i in items]
            summary = " ".join(stmts)
            if len(summary) > 200:
                summary = summary[:197] + "..."

            pages = []
            seen = set()
            for i in items:
                p = i.get("page_number")
                if p and p not in seen:
                    seen.add(p)
                    pages.append(_guidance_page_link(p, i.get("file_path")))

            cite_str = " ".join(pages) if pages else ""
            cell = f"{arrow} {summary}"
            if cite_str:
                cell += f"<br>{cite_str}"

            cells.append(cell)

        rows.append(f"| {label} | " + " | ".join(cells) + " |")

    return "\n".join([legend, "", header, separator] + rows)


def _build_deltas_markdown(company: str, quarters: list[str]) -> str:
    """Build the Guidance Changes panel — all quarter-over-quarter deltas."""
    if not quarters:
        return "*No delta data yet.*"

    try:
        conn = storage.get_connection(company)
    except Exception:
        return "*Could not load delta data.*"

    change_icons = {
        "new": "NEW",
        "upgraded": "UP",
        "downgraded": "DOWN",
        "reiterated": "SAME",
        "removed": "GONE",
    }

    lines = []
    for q in quarters:
        deltas = storage.get_deltas_for_quarter(conn, company, q)
        if not deltas:
            continue
        prior = deltas[0].get("prior_quarter", "?")
        lines.append(f"### {q} vs {prior}")

        for d in deltas:
            icon = change_icons.get(d["change_type"], d["change_type"])
            lines.append(f"- **[{icon}]** [{d['topic']}] {d['summary']}")
            if d.get("current_statement"):
                lines.append(f"  - *Current:* {d['current_statement']}")
            if d.get("prior_statement"):
                lines.append(f"  - *Prior:* {d['prior_statement']}")

        lines.append("")

    conn.close()

    if not lines:
        return "*No quarter-over-quarter changes detected yet.*"
    return "\n".join(lines)


def process_company(company: str, schema_key: str,
                    progress=gr.Progress()) -> tuple:
    """Cold-start: process every PDF for the selected company.

    Returns (metrics_md, validation_md, citations_md,
             guidance_md, deltas_md, status_msg).
    """
    if not company:
        msg = "Please select a company."
        return (msg,) + ("",) * 4 + (msg,)
    if not schema_key:
        msg = "Please select a schema."
        return (msg,) + ("",) * 4 + (msg,)

    pdfs = _find_pdfs(company)
    if not pdfs:
        msg = f"No PDFs found for '{company}' in sample_docs/."
        return (msg,) + ("",) * 4 + (msg,)

    schema = load_schema(schema_key)
    company_name = company
    last_metrics_state = None
    last_guidance_state = None
    errors = []
    pres_count = 0
    trans_count = 0

    for i, pdf_path in enumerate(pdfs):
        file_name = os.path.basename(pdf_path)
        quarter = _infer_quarter(file_name)
        progress((i, len(pdfs)), desc=f"Processing {file_name}")

        if not quarter:
            errors.append(f"Skipped {file_name} — cannot infer quarter")
            continue

        try:
            state = run_single(
                pdf_path, schema_key, quarter,
                company_name=company_name,
            )
            if state.get("metrics_table"):
                last_metrics_state = state
                pres_count += 1
            if state.get("guidance_table"):
                last_guidance_state = state
                trans_count += 1
        except Exception as e:
            errors.append(f"Error on {file_name}: {e}")

    progress((len(pdfs), len(pdfs)), desc="Done")

    metrics_md = "*No presentation data yet.*"
    validation_md = ""
    citations_md = ""
    guidance_md = "*No transcript data yet.*"
    deltas_md = ""

    if last_metrics_state and last_metrics_state.get("metrics_table"):
        table = last_metrics_state["metrics_table"]
        validation = last_metrics_state.get("validation")
        quarters = table.get("quarters", [])

        all_citations = _fetch_all_citations(company_name, quarters)
        metrics_md = _build_metrics_markdown(table, citations=all_citations)
        validation_md = _build_validation_markdown(validation)
        citations_md = _build_citations_markdown(company_name, quarters)

    guidance_md = _build_guidance_markdown(company_name)

    try:
        conn = storage.get_connection(company_name)
        g_quarters = [r["quarter"] for r in conn.execute(
            "SELECT DISTINCT quarter FROM guidance WHERE company=? ORDER BY quarter",
            (company_name,)
        ).fetchall()]
        conn.close()
        deltas_md = _build_deltas_markdown(company_name, g_quarters)
    except Exception:
        deltas_md = "*No delta data available.*"

    status = (
        f"Processed {len(pdfs)} PDFs: "
        f"{pres_count} presentations (Workflow A), "
        f"{trans_count} transcripts (Workflow B)."
    )
    if errors:
        status += "\n\nWarnings:\n" + "\n".join(f"- {e}" for e in errors)

    return metrics_md, validation_md, citations_md, guidance_md, deltas_md, status


def create_app() -> gr.Blocks:
    """Build and return the Gradio Earnings Intelligence Dashboard."""
    companies = _discover_companies()
    schemas = _discover_schemas()

    with gr.Blocks(
        title="Earnings Intelligence Dashboard",
    ) as app:

        gr.Markdown("# Earnings Intelligence Dashboard")
        gr.Markdown(
            "Select a company and schema, then click **Run Pipeline** to "
            "process all PDFs (presentations + transcripts) and generate the dashboard."
        )

        with gr.Row():
            company_dd = gr.Dropdown(
                choices=companies,
                label="Company Folder",
                value=companies[0] if companies else None,
                scale=2,
            )
            schema_dd = gr.Dropdown(
                choices=schemas,
                label="Metric Schema",
                value=schemas[0] if schemas else None,
                scale=2,
            )
            run_btn = gr.Button("Run Pipeline", variant="primary", scale=1)

        status_box = gr.Textbox(label="Status", lines=2, interactive=False)

        with gr.Tabs():
            with gr.TabItem("Metrics Table"):
                metrics_output = gr.Markdown(
                    value="*Run the pipeline to see the metrics dashboard.*"
                )

            with gr.TabItem("Validation"):
                validation_output = gr.Markdown(
                    value="*Run the pipeline to see validation results.*"
                )

            with gr.TabItem("Citations"):
                citations_output = gr.Markdown(
                    value="*Run the pipeline to see citation sources.*"
                )

            with gr.TabItem("Guidance Tracker"):
                guidance_output = gr.Markdown(
                    value="*Run the pipeline to see forward-looking guidance from earnings call transcripts.*"
                )

            with gr.TabItem("Guidance Changes"):
                deltas_output = gr.Markdown(
                    value="*Run the pipeline to see quarter-over-quarter guidance changes.*"
                )

        run_btn.click(
            fn=process_company,
            inputs=[company_dd, schema_dd],
            outputs=[
                metrics_output, validation_output, citations_output,
                guidance_output, deltas_output, status_box,
            ],
            show_progress="full",
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        theme=gr.themes.Soft(),
        allowed_paths=[SAMPLE_DOCS_DIR],
    )
