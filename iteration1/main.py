"""Entry point for the Earnings Intelligence Pipeline.

Usage (single quarter):
    python -m iteration1.main sample_docs/max/Q1FY26_presentation.pdf \\
        --schema max_healthcare --quarter "Q1 FY26"

Cold-start (batch all PDFs for a company):
    python -m iteration1.main sample_docs/max/ \\
        --schema max_healthcare --cold-start

Options:
    --model   OpenAI model name   (default: gpt-4o-mini)
    --schema  Company schema key  (matches schemas/<key>.json)
    --quarter Fiscal quarter label, e.g. "Q3 FY25" (required for single)
    --cold-start  Process every PDF in the given directory
"""

import argparse
import glob
import os
import re
import sys

from iteration1.pipeline import build_pipeline, load_schema


def _infer_quarter(file_name: str) -> str:
    """Best-effort extraction of quarter from filename.

    Looks for patterns like Q1FY26, Q3_FY25, Q1-FY-26, etc.
    Returns a normalised label such as 'Q1 FY26'.
    """
    pattern = r"[Qq](\d)\s*[-_]?\s*[Ff][Yy]\s*[-_]?(\d{2,4})"
    m = re.search(pattern, file_name)
    if m:
        q = m.group(1)
        fy = m.group(2)
        if len(fy) == 4:
            fy = fy[-2:]
        return f"Q{q} FY{fy}"
    return ""


def _format_metrics_table(table: dict) -> str:
    """Render the 8-quarter table as a human-readable text table."""
    if not table or not table.get("quarters"):
        return "  (no data)"

    quarters = table["quarters"]
    metrics = table["metrics"]

    col_w = 14
    name_w = 22

    header = " " * name_w + "".join(q.rjust(col_w) for q in quarters)
    divider = "─" * len(header)

    lines = [divider, header, divider]
    for metric_name, data in metrics.items():
        values = data.get("values", {})
        changes = data.get("changes", {})
        unit = data.get("unit", "")

        val_cells = []
        for q in quarters:
            v = values.get(q)
            c = changes.get(q, "")
            if v is not None:
                cell = f"{v:,.1f}"
                if c:
                    cell += f" ({c})"
            else:
                cell = "—"
            val_cells.append(cell.rjust(col_w))

        label = f"{metric_name} ({unit})" if unit else metric_name
        lines.append(label.ljust(name_w) + "".join(val_cells))

    lines.append(divider)
    return "\n".join(lines)


def run_single(pdf_path: str, schema_key: str, quarter: str,
               model_name: str = "gpt-4o-mini",
               company_name: str = "") -> dict:
    """Process a single PDF through the pipeline and return the final state.

    Args:
        company_name: Explicit company name (e.g. from folder selection).
                      Falls back to schema.company, then to classifier output.
    """
    file_name = os.path.basename(pdf_path)

    if not quarter:
        quarter = _infer_quarter(file_name)
    if not quarter:
        raise ValueError(
            f"Cannot infer quarter from '{file_name}'. "
            "Pass --quarter 'Q1 FY26' explicitly."
        )

    schema = load_schema(schema_key)
    pipeline = build_pipeline(model_name=model_name)

    company = company_name or schema.company or ""

    initial_state = {
        "raw_text": "",
        "page_tagged_text": "",
        "file_name": file_name,
        "pdf_path": os.path.abspath(pdf_path),
        "company": company,
        "quarter": quarter,
        "classification": None,
        "route": None,
        "metric_schema": schema,
        "extracted_metrics": None,
        "calculated_metrics": None,
        "validation": None,
        "metrics_table": None,
        "guidance_items": None,
        "guidance_deltas": None,
        "guidance_table": None,
    }

    print(f"\n{'─' * 70}")
    print(f"  Earnings Intelligence Pipeline")
    print(f"  Company: {company}  |  File: {file_name}")
    print(f"  Schema: {schema_key}  |  Quarter: {quarter}  |  Model: {model_name}")
    print(f"{'─' * 70}\n")

    final_state = pipeline.invoke(initial_state)
    return final_state


def run_cold_start(folder: str, schema_key: str,
                   model_name: str = "gpt-4o-mini",
                   company_name: str = "") -> dict:
    """Batch-process every PDF in a folder (cold-start mode).

    Returns the final state from the last PDF processed,
    which contains the cumulative metrics_table.
    """
    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {folder}")

    print(f"\n{'═' * 70}")
    print(f"  COLD-START MODE — {len(pdfs)} PDFs in {folder}")
    print(f"{'═' * 70}")

    last_state = None
    for i, pdf_path in enumerate(pdfs, 1):
        file_name = os.path.basename(pdf_path)
        quarter = _infer_quarter(file_name)
        if not quarter:
            print(f"\n  [SKIP] Cannot infer quarter from '{file_name}'")
            continue

        print(f"\n  [{i}/{len(pdfs)}] {file_name} → {quarter}")
        last_state = run_single(
            pdf_path, schema_key, quarter,
            model_name=model_name, company_name=company_name,
        )

    return last_state


def main():
    parser = argparse.ArgumentParser(
        description="Earnings Intelligence Pipeline — Metrics Dashboard"
    )
    parser.add_argument(
        "path",
        help="Path to a single PDF or a folder of PDFs (with --cold-start)",
    )
    parser.add_argument(
        "--schema", required=True,
        help="Company schema key (matches schemas/<key>.json, e.g. max_healthcare)",
    )
    parser.add_argument(
        "--quarter", default="",
        help="Fiscal quarter label, e.g. 'Q3 FY25' (auto-inferred from filename if omitted)",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="OpenAI model name (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--cold-start", action="store_true",
        help="Batch-process every PDF in the given folder",
    )
    args = parser.parse_args()

    try:
        if args.cold_start:
            final_state = run_cold_start(
                args.path, args.schema, model_name=args.model,
            )
        else:
            final_state = run_single(
                args.path, args.schema, args.quarter, model_name=args.model,
            )

        if final_state and final_state.get("metrics_table"):
            table = final_state["metrics_table"]
            validation = final_state.get("validation")

            print(f"\n{'═' * 70}")
            print(f"  METRICS DASHBOARD — {table.get('company', '?')}")
            print(f"{'═' * 70}\n")
            print(_format_metrics_table(table))

            if validation:
                print(f"\n  Validation: {validation.overall_status}")
                for v in validation.results:
                    if v.status == "flag":
                        print(f"    ⚠ {v.metric_name}: {v.issue}")

        elif final_state and final_state.get("guidance_table"):
            table = final_state["guidance_table"]
            print(f"\n{'═' * 70}")
            print(f"  GUIDANCE TRACKER")
            print(f"{'═' * 70}\n")
            for topic, q_data in table.get("topics", {}).items():
                print(f"  [{topic}]")
                for q, items in q_data.items():
                    for item in items:
                        speaker = f" — {item['speaker']}" if item.get("speaker") else ""
                        print(f"    {q}: {item['statement']}{speaker}")
                print()

        else:
            print("\n  No output produced.")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
