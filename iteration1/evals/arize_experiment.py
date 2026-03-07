"""Arize Cloud experiment runner for the Earnings Intelligence Pipeline.

Uploads eval dataset + runs code & LLM judge evaluators in Arize.

Usage:
    python -m iteration1.evals.arize_experiment
    python -m iteration1.evals.arize_experiment --company apollo
    python -m iteration1.evals.arize_experiment --dataset-name custom-name
    python -m iteration1.evals.arize_experiment --dry-run
"""

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from arize import ArizeClient
from arize.experiments import EvaluationResult
from dotenv import load_dotenv, find_dotenv
from phoenix.evals import LLM

EVAL_MODEL = "gpt-4o-mini"
EXPERIMENT_TIMEOUT_SECONDS = 300
EXPERIMENT_CONCURRENCY = 1

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCHEMAS_DIR = os.path.join(BASE_DIR, "schemas")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Dataset Construction
# ---------------------------------------------------------------------------

def _find_schema() -> dict | None:
    if not os.path.isdir(SCHEMAS_DIR):
        return None
    for fname in os.listdir(SCHEMAS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(SCHEMAS_DIR, fname)) as f:
                return json.load(f)
    return None


def _discover_companies() -> list[str]:
    data_dir = os.path.join(BASE_DIR, "data")
    if not os.path.isdir(data_dir):
        return []
    return [f.replace(".db", "") for f in sorted(os.listdir(data_dir)) if f.endswith(".db")]


def build_dataset_examples(company_filter: str = None) -> list[dict[str, Any]]:
    """Build one dataset row per company+quarter from the SQLite DB.

    Each row contains all the data an evaluator needs:
      - company, quarter, sector
      - metrics_rows, citations, metrics_table, schema (for code evals)
      - guidance topics, items, deltas, transcript path (for LLM judge evals)
    """
    from iteration1 import storage

    schema = _find_schema()
    sector = schema.get("sector", "Financial") if schema else "Financial"

    companies = _discover_companies()
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c.lower()]

    examples = []

    for company in companies:
        conn = storage.get_connection(company)

        metric_quarters = storage.list_quarters(conn, company)
        metrics_table = storage.get_metrics_table(conn, company) if metric_quarters else {}

        guidance_table = storage.get_guidance_table(conn, company)
        guidance_quarters = guidance_table.get("quarters", [])

        all_quarters = sorted(set(metric_quarters + guidance_quarters))

        for quarter in all_quarters:
            metrics_rows = storage.get_metrics_for_quarter(conn, company, quarter)
            citations_by_metric = storage.get_citations_for_quarter(conn, company, quarter)
            guidance_items = storage.get_guidance_for_quarter(conn, company, quarter)
            deltas = storage.get_deltas_for_quarter(conn, company, quarter)

            transcript_path = ""
            if guidance_items:
                rows = conn.execute(
                    "SELECT DISTINCT p.file_path FROM guidance g "
                    "JOIN pdfs p ON g.pdf_id = p.id "
                    "WHERE g.company=? AND g.quarter=? LIMIT 1",
                    (company, quarter)
                ).fetchall()
                if rows:
                    transcript_path = rows[0]["file_path"]

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

            examples.append({
                "company": company,
                "quarter": quarter,
                "sector": sector,
                "has_metrics": len(metrics_rows) > 0,
                "has_guidance": len(guidance_items) > 0,
                "metrics_rows_json": json.dumps([dict(r) for r in metrics_rows]),
                "citations_json": json.dumps(flat_citations),
                "citations_by_metric_json": json.dumps(
                    {k: v for k, v in citations_by_metric.items()}
                ),
                "metrics_table_json": json.dumps(metrics_table),
                "schema_json": json.dumps(schema) if schema else "{}",
                "guidance_items_json": json.dumps(guidance_items),
                "guidance_table_json": json.dumps(guidance_table),
                "guidance_topics": json.dumps(list(guidance_table.get("topics", {}).keys())),
                "deltas_json": json.dumps(deltas),
                "transcript_path": transcript_path,
            })

        conn.close()

    return examples


# ---------------------------------------------------------------------------
# Task Function
# ---------------------------------------------------------------------------

def pipeline_task(dataset_row: dict[str, Any]) -> dict[str, Any]:
    """Pass-through task — data is already in the DB, we just forward the row."""
    return {
        "company": dataset_row["company"],
        "quarter": dataset_row["quarter"],
        "has_metrics": dataset_row.get("has_metrics", False),
        "has_guidance": dataset_row.get("has_guidance", False),
    }


# ---------------------------------------------------------------------------
# Code-Based Evaluators
# ---------------------------------------------------------------------------

def derived_calc_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.code_evals import derived_metric_calculation

    metrics_rows = json.loads(dataset_row.get("metrics_rows_json", "[]"))
    schema = json.loads(dataset_row.get("schema_json", "{}"))

    if not metrics_rows:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No metrics data")

    result = derived_metric_calculation(metrics_rows, schema.get("metrics", []))
    return EvaluationResult(
        score=result["score"],
        label="PASS" if result["score"] == 1.0 else "FAIL",
        explanation=f"{result['correct']}/{result['total']} formulas verified",
        metadata={"eval": "derived_calc", "errors": json.dumps(result.get("errors", []))},
    )


def citation_page_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.code_evals import citation_page_accuracy

    citations = json.loads(dataset_row.get("citations_json", "[]"))
    if not citations:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No citations")

    result = citation_page_accuracy(citations)
    return EvaluationResult(
        score=result["score"],
        label="PASS" if result["score"] == 1.0 else "WARN" if result["score"] >= 0.7 else "FAIL",
        explanation=f"{result['verified']}/{result['total']} citations verified on page",
        metadata={"eval": "citation_page", "errors": json.dumps(result.get("errors", []))},
    )


def citation_coverage_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.code_evals import citation_coverage

    metrics_rows = json.loads(dataset_row.get("metrics_rows_json", "[]"))
    citations_by_metric = json.loads(dataset_row.get("citations_by_metric_json", "{}"))

    if not metrics_rows:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No metrics")

    result = citation_coverage(metrics_rows, citations_by_metric)
    return EvaluationResult(
        score=result["score"],
        label="PASS" if result["score"] == 1.0 else "FAIL",
        explanation=f"{result['with_citations']}/{result['total_found']} metrics have citations",
        metadata={"eval": "citation_coverage",
                   "missing": json.dumps(result.get("missing_citations", []))},
    )


def rolling_window_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.code_evals import rolling_window_integrity

    metrics_table = json.loads(dataset_row.get("metrics_table_json", "{}"))
    if not metrics_table.get("quarters"):
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No metrics table")

    result = rolling_window_integrity(metrics_table)
    checks_str = ", ".join(f"{k}={v}" for k, v in result.get("checks", {}).items())
    return EvaluationResult(
        score=result["score"],
        label="PASS" if result["score"] == 1.0 else "FAIL",
        explanation=checks_str,
        metadata={"eval": "rolling_window", "issues": json.dumps(result.get("issues", []))},
    )


def schema_compliance_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.code_evals import schema_compliance

    metrics_table = json.loads(dataset_row.get("metrics_table_json", "{}"))
    schema = json.loads(dataset_row.get("schema_json", "{}"))

    if not metrics_table.get("quarters"):
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No metrics table")

    result = schema_compliance(metrics_table, schema)
    checks_str = ", ".join(f"{k}={v}" for k, v in result.get("checks", {}).items())
    return EvaluationResult(
        score=result["score"],
        label="PASS" if result["score"] == 1.0 else "FAIL",
        explanation=checks_str,
        metadata={"eval": "schema_compliance", "issues": json.dumps(result.get("issues", []))},
    )


# ---------------------------------------------------------------------------
# LLM Judge Evaluators
# ---------------------------------------------------------------------------

def _get_eval_llm():
    return LLM(provider="openai", model=EVAL_MODEL)


def taxonomy_quality_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.llm_judge_evals import build_taxonomy_quality_evaluator

    topics = json.loads(dataset_row.get("guidance_topics", "[]"))
    if not topics:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No guidance topics")

    transcript_path = dataset_row.get("transcript_path", "")
    excerpt = "(not available)"
    if transcript_path and os.path.isfile(transcript_path):
        try:
            from iteration1.pdf_parser import parse_pdf_with_page_tags
            excerpt = parse_pdf_with_page_tags(transcript_path)[:3000]
        except Exception:
            pass

    judge = build_taxonomy_quality_evaluator(_get_eval_llm())
    topics_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(topics))

    result = judge.evaluate({
        "company": dataset_row["company"],
        "sector": dataset_row.get("sector", "Financial"),
        "topics_list": topics_list,
        "transcript_excerpt": excerpt,
    })
    score_obj = result[0]
    return EvaluationResult(
        score=float(score_obj.score) if score_obj.score is not None else 0.0,
        label=score_obj.label,
        explanation=score_obj.explanation,
        metadata={"eval": "taxonomy_quality"},
    )


def guidance_completeness_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.llm_judge_evals import build_guidance_completeness_evaluator

    guidance_items = json.loads(dataset_row.get("guidance_items_json", "[]"))
    if not guidance_items:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No guidance items")

    judge = build_guidance_completeness_evaluator(_get_eval_llm())

    by_topic = {}
    for g in guidance_items:
        by_topic.setdefault(g["topic"], []).append(g)

    scores = []
    for topic, items in by_topic.items():
        extracted_text = "\n".join(
            f"  • {g['statement']} [{g.get('speaker', '?')}] "
            f"| Sentiment: {g.get('sentiment', '?')} (p.{g.get('page_number', '?')})"
            for g in items
        )
        passage = items[0].get("passage", "") or ""

        result = judge.evaluate({
            "company": dataset_row["company"],
            "quarter": dataset_row["quarter"],
            "topic": topic,
            "extracted_guidance": extracted_text,
            "transcript_passage": passage[:1500],
        })
        s = result[0]
        if s.score is not None:
            scores.append(float(s.score))

    if not scores:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No evaluable topics")

    avg = sum(scores) / len(scores)
    return EvaluationResult(
        score=avg,
        label="GOOD" if avg >= 0.8 else "PARTIAL" if avg >= 0.4 else "BAD",
        explanation=f"Avg {avg:.0%} across {len(scores)} topics",
        metadata={"eval": "guidance_completeness", "topic_count": len(scores)},
    )


def delta_detection_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.llm_judge_evals import build_delta_detection_evaluator

    deltas = json.loads(dataset_row.get("deltas_json", "[]"))
    if not deltas:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No deltas for this quarter")

    judge = build_delta_detection_evaluator(_get_eval_llm())
    scores = []
    for d in deltas[:5]:
        result = judge.evaluate({
            "company": dataset_row["company"],
            "current_quarter": dataset_row["quarter"],
            "prior_quarter": d.get("prior_quarter", "?"),
            "topic": d["topic"],
            "change_type": d["change_type"],
            "current_statement": d.get("current_statement", ""),
            "prior_statement": d.get("prior_statement", ""),
            "delta_summary": d["summary"],
        })
        s = result[0]
        if s.score is not None:
            scores.append(float(s.score))

    if not scores:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No evaluable deltas")

    avg = sum(scores) / len(scores)
    return EvaluationResult(
        score=avg,
        label="GOOD" if avg >= 0.8 else "PARTIAL" if avg >= 0.4 else "BAD",
        explanation=f"Avg {avg:.0%} across {len(scores)} deltas",
        metadata={"eval": "delta_detection", "delta_count": len(scores)},
    )


def taxonomy_evolution_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.llm_judge_evals import build_taxonomy_evolution_evaluator

    guidance_table = json.loads(dataset_row.get("guidance_table_json", "{}"))
    quarters = guidance_table.get("quarters", [])
    topics = guidance_table.get("topics", {})

    if len(quarters) < 2:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="Need 2+ quarters")

    prior_q, current_q = quarters[-2], quarters[-1]
    prior_t = {t for t, qd in topics.items() if prior_q in qd}
    curr_t = {t for t, qd in topics.items() if current_q in qd}

    judge = build_taxonomy_evolution_evaluator(_get_eval_llm())
    result = judge.evaluate({
        "company": dataset_row["company"],
        "prior_quarter": prior_q, "current_quarter": current_q,
        "prior_topics": "\n".join(f"  - {t}" for t in sorted(prior_t)) or "(none)",
        "current_topics": "\n".join(f"  - {t}" for t in sorted(curr_t)) or "(none)",
        "new_topics": ", ".join(sorted(curr_t - prior_t)) or "(none)",
        "dropped_topics": ", ".join(sorted(prior_t - curr_t)) or "(none)",
    })
    s = result[0]
    return EvaluationResult(
        score=float(s.score) if s.score is not None else 0.0,
        label=s.label,
        explanation=s.explanation,
        metadata={"eval": "taxonomy_evolution"},
    )


def cross_quarter_evaluator(
    dataset_row: dict[str, Any], output: dict[str, Any]
) -> EvaluationResult:
    from iteration1.evals.llm_judge_evals import build_cross_quarter_evaluator

    guidance_table = json.loads(dataset_row.get("guidance_table_json", "{}"))
    quarters = guidance_table.get("quarters", [])
    topics = guidance_table.get("topics", {})

    if len(quarters) < 2 or not topics:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="Need 2+ quarters")

    judge = build_cross_quarter_evaluator(_get_eval_llm())
    scores = []

    for topic, q_data in topics.items():
        if sum(1 for q in quarters if q_data.get(q)) < 2:
            continue
        lines = []
        for q in quarters:
            items = q_data.get(q, [])
            if items:
                lines.append(f"  {q}: {'; '.join(g['statement'][:100] for g in items[:3])}")
            else:
                lines.append(f"  {q}: (not discussed)")

        result = judge.evaluate({
            "company": dataset_row["company"], "topic": topic,
            "quarters_compared": ", ".join(quarters),
            "guidance_by_quarter": "\n".join(lines),
            "comparison_text": f"Topic '{topic}' across {len(quarters)} quarters.",
        })
        s = result[0]
        if s.score is not None:
            scores.append(float(s.score))

    if not scores:
        return EvaluationResult(score=0.0, label="SKIPPED", explanation="No multi-quarter topics")

    avg = sum(scores) / len(scores)
    return EvaluationResult(
        score=avg,
        label="GOOD" if avg >= 0.8 else "PARTIAL" if avg >= 0.4 else "BAD",
        explanation=f"Avg {avg:.0%} across {len(scores)} topics",
        metadata={"eval": "cross_quarter", "topic_count": len(scores)},
    )


# ---------------------------------------------------------------------------
# Arize Experiment Orchestration
# ---------------------------------------------------------------------------

def _resolve_or_create_dataset(
    client: ArizeClient, dataset_name: str, examples: list[dict]
) -> str:
    """Find existing dataset by name, or create a new one."""
    page = client.datasets.list(limit=100)
    for ds in page.datasets:
        if ds.name == dataset_name:
            print(f"  Found existing dataset: {ds.name} ({ds.id})")
            return ds.id

    dataset = client.datasets.create(
        name=dataset_name,
        space_id=os.environ["ARIZE_SPACE_ID"],
        examples=examples,
    )
    print(f"  Created dataset: {dataset_name} ({dataset.id}) with {len(examples)} examples")
    return dataset.id


def run_arize_experiment(
    company_filter: str = None,
    dataset_name: str = None,
    dry_run: bool = False,
):
    """Build dataset, define evaluators, and run the Arize experiment."""

    print("\n" + "=" * 60)
    print("  ARIZE EXPERIMENT RUNNER")
    print("=" * 60)

    required_env = ("OPENAI_API_KEY", "ARIZE_API_KEY", "ARIZE_SPACE_ID")
    missing = [k for k in required_env if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    print("\n1. Building dataset from pipeline DB...")
    examples = build_dataset_examples(company_filter)
    if not examples:
        print("   No data found. Run the pipeline first.")
        return

    companies = sorted(set(e["company"] for e in examples))
    quarters = sorted(set(e["quarter"] for e in examples))
    print(f"   {len(examples)} rows: {len(companies)} companies, {len(quarters)} quarters")

    if dataset_name is None:
        dataset_name = f"earnings-intel-eval-{_timestamp()}"

    if dry_run:
        print(f"\n   [DRY RUN] Would create dataset '{dataset_name}' with {len(examples)} rows")
        print("   Evaluators: derived_calc, citation_page, citation_coverage, "
              "rolling_window, schema_compliance, taxonomy_quality, "
              "guidance_completeness, delta_detection")
        return

    print("\n2. Connecting to Arize...")
    arize_client = ArizeClient(api_key=os.environ["ARIZE_API_KEY"])

    print("\n3. Creating/finding dataset...")
    dataset_id = _resolve_or_create_dataset(arize_client, dataset_name, examples)

    print("\n4. Running experiment...")
    experiment_name = f"{dataset_name}-eval-{_timestamp()}"

    evaluators = {
        "derived_calc": derived_calc_evaluator,
        "citation_page": citation_page_evaluator,
        "citation_coverage": citation_coverage_evaluator,
        "rolling_window": rolling_window_evaluator,
        "schema_compliance": schema_compliance_evaluator,
        "taxonomy_quality": taxonomy_quality_evaluator,
        "guidance_completeness": guidance_completeness_evaluator,
        "delta_detection": delta_detection_evaluator,
        "taxonomy_evolution": taxonomy_evolution_evaluator,
        "cross_quarter": cross_quarter_evaluator,
    }

    experiment, results_df = arize_client.experiments.run(
        name=experiment_name,
        dataset_id=dataset_id,
        task=pipeline_task,
        evaluators=evaluators,
        concurrency=EXPERIMENT_CONCURRENCY,
        timeout=EXPERIMENT_TIMEOUT_SECONDS,
        dry_run=False,
    )

    if experiment is None:
        raise RuntimeError("Experiment upload failed: experiment is None.")

    print(f"\n5. Experiment complete!")
    print(f"   Name: {experiment_name}")
    print(f"   ID: {experiment.id}")
    print(f"   Rows: {len(results_df)}")
    print(f"\n   View in Arize: https://app.arize.com/")
    print("   Navigate to Datasets & Experiments → find your experiment.")

    return experiment


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(
        description="Run Earnings Intelligence evals as an Arize experiment"
    )
    parser.add_argument(
        "--company", default=None,
        help="Filter to a specific company (substring match)",
    )
    parser.add_argument(
        "--dataset-name", default=None,
        help="Custom Arize dataset name (default: auto-generated with timestamp)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be uploaded without actually running",
    )
    args = parser.parse_args()

    run_arize_experiment(
        company_filter=args.company,
        dataset_name=args.dataset_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
