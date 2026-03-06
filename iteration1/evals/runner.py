"""Arize experiment runner for the Earnings Intelligence Pipeline evals.

Usage:
    python -m iteration1.evals.runner --suite code    # run code-based evals only
    python -m iteration1.evals.runner --suite judge   # run LLM judge evals only
    python -m iteration1.evals.runner --suite all     # run everything
    python -m iteration1.evals.runner --suite code --company max
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv, find_dotenv


EVALS_DIR = os.path.dirname(__file__)
GROUND_TRUTH_DIR = os.path.join(EVALS_DIR, "ground_truth")
BASE_DIR = os.path.dirname(EVALS_DIR)
SAMPLE_DOCS_DIR = os.path.join(BASE_DIR, "sample_docs")
SCHEMAS_DIR = os.path.join(BASE_DIR, "schemas")


def _load_ground_truth(filename: str) -> dict:
    """Load a ground truth JSON file from the ground_truth/ folder."""
    path = os.path.join(GROUND_TRUTH_DIR, filename)
    with open(path) as f:
        return json.load(f)


def _load_schema(schema_name: str) -> dict:
    """Load a schema JSON from the schemas/ folder."""
    path = os.path.join(SCHEMAS_DIR, f"{schema_name}.json")
    with open(path) as f:
        return json.load(f)


def _discover_companies() -> list[str]:
    """Find all companies that have a .db file in the data/ folder."""
    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.isdir(data_dir):
        return []
    return [
        f.replace(".db", "")
        for f in sorted(os.listdir(data_dir))
        if f.endswith(".db")
    ]


def _print_eval_result(name: str, result: dict) -> None:
    """Pretty-print a single eval result."""
    score = result.get("score", "N/A")
    score_str = f"{score:.0%}" if isinstance(score, float) else str(score)
    status = "PASS" if score == 1.0 else "WARN" if isinstance(score, float) and score >= 0.7 else "FAIL"
    print(f"  [{status}] {name}: {score_str}")

    for key in ("checks", "total", "correct", "verified", "total_found",
                "with_citations", "missing_citations"):
        if key in result and key not in ("score",):
            val = result[key]
            if isinstance(val, dict):
                for ck, cv in val.items():
                    print(f"         {ck}: {cv}")
            elif isinstance(val, list) and val:
                for item in val[:5]:
                    print(f"         - {item}")
                if len(val) > 5:
                    print(f"         ... and {len(val) - 5} more")
            else:
                print(f"         {key}: {val}")

    errors = result.get("errors", []) + result.get("issues", [])
    if errors:
        for err in errors[:5]:
            print(f"         ! {err}")
        if len(errors) > 5:
            print(f"         ... and {len(errors) - 5} more")


# ---------------------------------------------------------------------------
# Code-Based Eval Suite
# ---------------------------------------------------------------------------

def run_code_evals(company_filter: str = None):
    """Run the 5 ground-truth-free code-based evals against live DB data."""
    from iteration1 import storage
    from iteration1.evals.code_evals import (
        derived_metric_calculation,
        citation_page_accuracy,
        citation_coverage,
        rolling_window_integrity,
        schema_compliance,
    )

    print("\n" + "=" * 60)
    print("  CODE-BASED EVALS (ground-truth-free)")
    print("=" * 60)

    companies = _discover_companies()
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c.lower()]

    if not companies:
        print("  No companies found in data/ folder.")
        return {}

    all_results = {}

    for company in companies:
        print(f"\n--- {company.upper()} ---")
        conn = storage.get_connection(company)
        quarters = storage.list_quarters(conn, company)

        if not quarters:
            print("  No metric data found — skipping.")
            conn.close()
            continue

        schema = _find_schema_for_company(company)
        if not schema:
            print(f"  No schema found for {company} — skipping schema-dependent evals.")
            conn.close()
            continue

        metrics_table = storage.get_metrics_table(conn, company)
        company_results = {}

        # Eval 3: Derived metric calculation
        print("\n  [Eval 3] Derived Metric Calculation")
        for q in quarters:
            metrics_rows = storage.get_metrics_for_quarter(conn, company, q)
            result = derived_metric_calculation(
                [dict(r) for r in metrics_rows],
                schema.get("metrics", []),
            )
            label = f"derived_calc_{q}"
            company_results[label] = result
            _print_eval_result(f"  {q}", result)

        # Eval 4: Citation page accuracy
        print("\n  [Eval 4] Citation Page Accuracy")
        for q in quarters:
            metrics_rows = storage.get_metrics_for_quarter(conn, company, q)
            citations_by_metric = storage.get_citations_for_quarter(conn, company, q)

            flat_citations = []
            for metric_name, cites in citations_by_metric.items():
                m_row = next((r for r in metrics_rows if r["metric_name"] == metric_name), {})
                for c in cites:
                    flat_citations.append({
                        "metric_name": metric_name,
                        "page_number": c["page_number"],
                        "passage": c["passage"],
                        "file_path": c["file_path"],
                        "value": m_row.get("value"),
                    })

            result = citation_page_accuracy(flat_citations)
            label = f"citation_page_{q}"
            company_results[label] = result
            _print_eval_result(f"  {q}", result)

        # Eval 5: Citation coverage
        print("\n  [Eval 5] Citation Coverage")
        for q in quarters:
            metrics_rows = storage.get_metrics_for_quarter(conn, company, q)
            citations_by_metric = storage.get_citations_for_quarter(conn, company, q)
            result = citation_coverage(
                [dict(r) for r in metrics_rows],
                citations_by_metric,
            )
            label = f"citation_coverage_{q}"
            company_results[label] = result
            _print_eval_result(f"  {q}", result)

        # Eval 6: Rolling window integrity
        print("\n  [Eval 6] Rolling Window Integrity")
        result = rolling_window_integrity(metrics_table)
        company_results["rolling_window"] = result
        _print_eval_result("Table", result)

        # Eval 7: Schema compliance
        print("\n  [Eval 7] Schema Compliance")
        result = schema_compliance(metrics_table, schema)
        company_results["schema_compliance"] = result
        _print_eval_result("Table", result)

        conn.close()
        all_results[company] = company_results

    _print_summary(all_results)
    return all_results


def _find_schema_for_company(company: str) -> dict | None:
    """Try to find the schema that matches a company's industry."""
    if not os.path.isdir(SCHEMAS_DIR):
        return None
    for fname in os.listdir(SCHEMAS_DIR):
        if fname.endswith(".json"):
            path = os.path.join(SCHEMAS_DIR, fname)
            with open(path) as f:
                schema = json.load(f)
            return schema
    return None


def _print_summary(all_results: dict) -> None:
    """Print aggregate summary across all companies."""
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    total_evals = 0
    total_score = 0.0
    perfect = 0

    for company, results in all_results.items():
        scores = [r["score"] for r in results.values() if isinstance(r.get("score"), float)]
        if scores:
            avg = sum(scores) / len(scores)
            perfect_count = sum(1 for s in scores if s == 1.0)
            print(f"  {company}: avg={avg:.0%}  ({perfect_count}/{len(scores)} perfect)")
            total_evals += len(scores)
            total_score += sum(scores)
            perfect += perfect_count

    if total_evals:
        print(f"\n  Overall: avg={total_score / total_evals:.0%}  "
              f"({perfect}/{total_evals} perfect)")


# ---------------------------------------------------------------------------
# LLM Judge Eval Suite
# ---------------------------------------------------------------------------

EVAL_MODEL = "gpt-4o-mini"


def _load_transcript_excerpt(pdf_path: str, max_chars: int = 3000) -> str:
    """Load the first max_chars of a transcript PDF for the judge prompt."""
    if not pdf_path or not os.path.isfile(pdf_path):
        return "(transcript not available)"
    try:
        from iteration1.pdf_parser import parse_pdf_with_page_tags
        text = parse_pdf_with_page_tags(pdf_path)
        return text[:max_chars]
    except Exception:
        return "(error loading transcript)"


def _format_guidance_items(items: list[dict]) -> str:
    """Format guidance items into readable text for the judge prompt."""
    if not items:
        return "(no guidance items)"
    lines = []
    for g in items:
        speaker = f" [{g.get('speaker', '?')}]" if g.get("speaker") else ""
        sentiment = f" | Sentiment: {g.get('sentiment', '?')}" if g.get("sentiment") else ""
        page = f" (p.{g['page_number']})" if g.get("page_number") else ""
        lines.append(f"  • {g['statement']}{speaker}{sentiment}{page}")
    return "\n".join(lines)


def run_llm_judge_evals(company_filter: str = None):
    """Run all 5 LLM judge evals against live DB guidance data."""
    from phoenix.evals import LLM
    from iteration1 import storage
    from iteration1.evals.llm_judge_evals import (
        build_taxonomy_quality_evaluator,
        build_guidance_completeness_evaluator,
        build_delta_detection_evaluator,
        build_taxonomy_evolution_evaluator,
        build_cross_quarter_evaluator,
    )

    print("\n" + "=" * 60)
    print("  LLM JUDGE EVALS")
    print("=" * 60)

    eval_llm = LLM(provider="openai", model=EVAL_MODEL)

    taxonomy_judge = build_taxonomy_quality_evaluator(eval_llm)
    guidance_judge = build_guidance_completeness_evaluator(eval_llm)
    delta_judge = build_delta_detection_evaluator(eval_llm)
    evolution_judge = build_taxonomy_evolution_evaluator(eval_llm)
    cross_quarter_judge = build_cross_quarter_evaluator(eval_llm)

    companies = _discover_companies()
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c.lower()]

    all_results = {}

    for company in companies:
        conn = storage.get_connection(company)
        guidance_table = storage.get_guidance_table(conn, company)
        quarters = guidance_table.get("quarters", [])
        topics = guidance_table.get("topics", {})

        if not quarters or not topics:
            conn.close()
            continue

        print(f"\n--- {company.upper()} (Guidance: {len(quarters)} quarters, {len(topics)} topics) ---")
        company_results = {}

        # Find transcript PDF path for this company
        transcript_path = None
        for q in quarters:
            rows = conn.execute(
                "SELECT DISTINCT p.file_path FROM guidance g "
                "JOIN pdfs p ON g.pdf_id = p.id "
                "WHERE g.company=? AND g.quarter=? LIMIT 1",
                (company, q)
            ).fetchall()
            if rows:
                transcript_path = rows[0]["file_path"]
                break

        transcript_excerpt = _load_transcript_excerpt(transcript_path)
        schema = _find_schema_for_company(company)
        sector = schema.get("sector", "Financial") if schema else "Financial"

        # --- Judge 1: Taxonomy Quality ---
        print("\n  [Judge 1] Taxonomy Quality")
        topics_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(topics.keys()))
        try:
            result = taxonomy_judge.evaluate({
                "company": company,
                "sector": sector,
                "topics_list": topics_list,
                "transcript_excerpt": transcript_excerpt,
            })
            score_obj = result[0]
            label = score_obj.label or "?"
            score_val = float(score_obj.score) if score_obj.score is not None else 0.0
            print(f"  [{label}] score={score_val:.0%}")
            if score_obj.explanation:
                print(f"         reason: {score_obj.explanation[:120]}")
            company_results["taxonomy_quality"] = {
                "score": score_val, "label": label,
                "explanation": score_obj.explanation,
            }
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            company_results["taxonomy_quality"] = {"score": 0.0, "label": "ERROR", "error": str(exc)}

        # --- Judge 2: Guidance Extraction Completeness (per topic, latest quarter) ---
        print("\n  [Judge 2] Guidance Extraction Completeness")
        latest_q = quarters[-1]
        guidance_scores = []
        for topic, q_data in topics.items():
            items = q_data.get(latest_q, [])
            if not items:
                continue
            extracted_text = _format_guidance_items(items)
            passage = items[0].get("passage", "") or ""
            try:
                result = guidance_judge.evaluate({
                    "company": company,
                    "quarter": latest_q,
                    "topic": topic,
                    "extracted_guidance": extracted_text,
                    "transcript_passage": passage[:1500],
                })
                score_obj = result[0]
                label = score_obj.label or "?"
                score_val = float(score_obj.score) if score_obj.score is not None else 0.0
                guidance_scores.append(score_val)
                status = label
                print(f"    {topic}: [{status}]")
            except Exception as exc:
                print(f"    {topic}: [ERROR] {exc}")
                guidance_scores.append(0.0)

        if guidance_scores:
            avg = sum(guidance_scores) / len(guidance_scores)
            print(f"  Average: {avg:.0%} across {len(guidance_scores)} topics")
            company_results["guidance_completeness"] = {
                "score": avg, "total_topics": len(guidance_scores),
            }

        # --- Judge 3: Delta Detection Accuracy ---
        print("\n  [Judge 3] Delta Detection Accuracy")
        delta_scores = []
        for q in quarters:
            deltas = storage.get_deltas_for_quarter(conn, company, q)
            if not deltas:
                continue
            for d in deltas[:5]:
                try:
                    result = delta_judge.evaluate({
                        "company": company,
                        "current_quarter": q,
                        "prior_quarter": d.get("prior_quarter", "?"),
                        "topic": d["topic"],
                        "change_type": d["change_type"],
                        "current_statement": d.get("current_statement", ""),
                        "prior_statement": d.get("prior_statement", ""),
                        "delta_summary": d["summary"],
                    })
                    score_obj = result[0]
                    label = score_obj.label or "?"
                    score_val = float(score_obj.score) if score_obj.score is not None else 0.0
                    delta_scores.append(score_val)
                    print(f"    {q} [{d['topic']}] {d['change_type']}: [{label}]")
                except Exception as exc:
                    print(f"    {q} [{d['topic']}]: [ERROR] {exc}")
                    delta_scores.append(0.0)

        if delta_scores:
            avg = sum(delta_scores) / len(delta_scores)
            print(f"  Average: {avg:.0%} across {len(delta_scores)} deltas")
            company_results["delta_detection"] = {"score": avg, "total_deltas": len(delta_scores)}
        else:
            print("  (no deltas to evaluate — only 1 quarter of data)")
            company_results["delta_detection"] = {"score": None, "label": "SKIPPED"}

        # --- Judge 4: Taxonomy Evolution Quality ---
        print("\n  [Judge 4] Taxonomy Evolution Quality")
        if len(quarters) >= 2:
            prior_q = quarters[-2]
            current_q = quarters[-1]
            prior_topics = set()
            current_topics = set()
            for topic, q_data in topics.items():
                if prior_q in q_data:
                    prior_topics.add(topic)
                if current_q in q_data:
                    current_topics.add(topic)

            new_topics = current_topics - prior_topics
            dropped_topics = prior_topics - current_topics

            try:
                result = evolution_judge.evaluate({
                    "company": company,
                    "prior_quarter": prior_q,
                    "current_quarter": current_q,
                    "prior_topics": "\n".join(f"  - {t}" for t in sorted(prior_topics)) or "(none)",
                    "current_topics": "\n".join(f"  - {t}" for t in sorted(current_topics)) or "(none)",
                    "new_topics": ", ".join(sorted(new_topics)) or "(none)",
                    "dropped_topics": ", ".join(sorted(dropped_topics)) or "(none)",
                })
                score_obj = result[0]
                label = score_obj.label or "?"
                score_val = float(score_obj.score) if score_obj.score is not None else 0.0
                print(f"  {prior_q} → {current_q}: [{label}]")
                if score_obj.explanation:
                    print(f"         reason: {score_obj.explanation[:120]}")
                company_results["taxonomy_evolution"] = {"score": score_val, "label": label}
            except Exception as exc:
                print(f"  [ERROR] {exc}")
                company_results["taxonomy_evolution"] = {"score": 0.0, "label": "ERROR"}
        else:
            print("  (need 2+ quarters for evolution eval — skipping)")
            company_results["taxonomy_evolution"] = {"score": None, "label": "SKIPPED"}

        # --- Judge 5: Cross-Quarter Comparison Quality ---
        print("\n  [Judge 5] Cross-Quarter Comparison Quality")
        if len(quarters) >= 2:
            cq_scores = []
            for topic, q_data in topics.items():
                if len(q_data) < 2:
                    continue
                guidance_by_q_lines = []
                for q in quarters:
                    items = q_data.get(q, [])
                    if items:
                        summaries = "; ".join(g["statement"][:100] for g in items[:3])
                        guidance_by_q_lines.append(f"  {q}: {summaries}")
                    else:
                        guidance_by_q_lines.append(f"  {q}: (not discussed)")

                comparison = (
                    f"Topic '{topic}' across {len(quarters)} quarters for {company}. "
                    f"The guidance table shows the progression of management statements."
                )

                try:
                    result = cross_quarter_judge.evaluate({
                        "company": company,
                        "topic": topic,
                        "quarters_compared": ", ".join(quarters),
                        "guidance_by_quarter": "\n".join(guidance_by_q_lines),
                        "comparison_text": comparison,
                    })
                    score_obj = result[0]
                    label = score_obj.label or "?"
                    score_val = float(score_obj.score) if score_obj.score is not None else 0.0
                    cq_scores.append(score_val)
                    print(f"    {topic}: [{label}]")
                except Exception as exc:
                    print(f"    {topic}: [ERROR] {exc}")
                    cq_scores.append(0.0)

            if cq_scores:
                avg = sum(cq_scores) / len(cq_scores)
                print(f"  Average: {avg:.0%} across {len(cq_scores)} topics")
                company_results["cross_quarter"] = {"score": avg, "total_topics": len(cq_scores)}
        else:
            print("  (need 2+ quarters for cross-quarter eval — skipping)")
            company_results["cross_quarter"] = {"score": None, "label": "SKIPPED"}

        conn.close()
        all_results[company] = company_results

    if all_results:
        print("\n" + "=" * 60)
        print("  LLM JUDGE SUMMARY")
        print("=" * 60)
        for company, results in all_results.items():
            scores = [r["score"] for r in results.values()
                      if isinstance(r.get("score"), (int, float))]
            if scores:
                avg = sum(scores) / len(scores)
                print(f"  {company}: avg={avg:.0%}  ({len(scores)} evals)")
    else:
        print("\n  No guidance data found — LLM judge evals need transcript workflow data.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(
        description="Earnings Intelligence Pipeline — Eval Runner"
    )
    parser.add_argument(
        "--suite",
        choices=["code", "judge", "all"],
        default="all",
        help="Which eval suite to run (default: all)",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Filter to a specific company (substring match)",
    )
    parser.add_argument(
        "--arize",
        action="store_true",
        help="Upload results to Arize Cloud as an experiment",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="(with --arize) Preview what would be uploaded without running",
    )
    args = parser.parse_args()

    if args.arize:
        from iteration1.evals.arize_experiment import run_arize_experiment
        run_arize_experiment(
            company_filter=args.company,
            dry_run=args.dry_run,
        )
        return

    if args.suite in ("code", "all"):
        run_code_evals(company_filter=args.company)

    if args.suite in ("judge", "all"):
        run_llm_judge_evals(company_filter=args.company)


if __name__ == "__main__":
    main()
