"""Eval runner for the Earnings Intelligence Pipeline.

Usage:
    python -m iteration1.evals.runner --suite code
    python -m iteration1.evals.runner --suite judge
    python -m iteration1.evals.runner --suite all
    python -m iteration1.evals.runner --suite all --company max
"""

import argparse
import json
import os
import glob

from dotenv import load_dotenv, find_dotenv


EVALS_DIR = os.path.dirname(__file__)
GROUND_TRUTH_DIR = os.path.join(EVALS_DIR, "ground_truth")
BASE_DIR = os.path.dirname(EVALS_DIR)
SAMPLE_DOCS_DIR = os.path.join(BASE_DIR, "sample_docs")
SCHEMAS_DIR = os.path.join(BASE_DIR, "schemas")

EVAL_MODEL = "gpt-4o-mini"

# ── Helpers ──────────────────────────────────────────────────────────────

def _load_ground_truth(filename: str) -> dict:
    path = os.path.join(GROUND_TRUTH_DIR, filename)
    with open(path) as f:
        return json.load(f)


def _load_schema(schema_name: str) -> dict:
    path = os.path.join(SCHEMAS_DIR, f"{schema_name}.json")
    with open(path) as f:
        return json.load(f)


def _find_schema_for_company(company: str) -> dict | None:
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


def _resolve_pdf_path(relative_path: str) -> str:
    full = os.path.join(BASE_DIR, relative_path)
    if os.path.isfile(full):
        return full
    basename = os.path.basename(relative_path)
    matches = glob.glob(os.path.join(SAMPLE_DOCS_DIR, "**", basename), recursive=True)
    return matches[0] if matches else full


# ── Pretty print ─────────────────────────────────────────────────────────

PASS_ICON = "\033[92m✓\033[0m"
WARN_ICON = "\033[93m⚠\033[0m"
FAIL_ICON = "\033[91m✗\033[0m"
SKIP_ICON = "\033[90m–\033[0m"


def _score_icon(score):
    if score is None:
        return SKIP_ICON
    if score == 1.0:
        return PASS_ICON
    if score >= 0.7:
        return WARN_ICON
    return FAIL_ICON


def _print_header(title: str):
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}")


def _print_section(title: str):
    print(f"\n  ── {title} {'─' * max(0, 50 - len(title))}")


# ── Eval 1: Classification Accuracy (Ground Truth) ──────────────────────

def _run_classification_eval() -> list[dict]:
    from iteration1.evals.code_evals import classification_accuracy
    from iteration1.pdf_parser import parse_pdf_with_page_tags
    from iteration1.state import DocumentClassification, PRESENTATION_ROUTE, TRANSCRIPT_ROUTE
    from iteration1.prompts import CLASSIFIER_PROMPT
    from langchain_openai import ChatOpenAI

    gt = _load_ground_truth("classification.json")
    examples = gt.get("examples", [])
    if not examples:
        return []

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(DocumentClassification)
    chain = CLASSIFIER_PROMPT | structured_llm

    results = []
    for ex in examples:
        pdf_path = _resolve_pdf_path(ex["pdf_path"])
        if not os.path.isfile(pdf_path):
            results.append({"file": ex["file_name"], "score": None, "note": "PDF not found"})
            continue

        try:
            text = parse_pdf_with_page_tags(pdf_path)
            classification = chain.invoke({
                "file_name": ex["file_name"],
                "raw_text": text[:12000],
            })
            predicted_type = classification.doc_type
            predicted_route = (
                PRESENTATION_ROUTE if predicted_type == "investor_presentation"
                else TRANSCRIPT_ROUTE
            )
        except Exception as exc:
            results.append({"file": ex["file_name"], "score": 0, "note": f"Error: {exc}"})
            continue

        result = classification_accuracy(predicted_type, predicted_route,
                                         ex["expected_doc_type"], ex["expected_route"])
        result["file"] = ex["file_name"]
        result["predicted_type"] = predicted_type
        result["predicted_route"] = predicted_route
        results.append(result)

    return results


# ── Eval 2: Metric Extraction Accuracy (Ground Truth) ───────────────────

def _run_metric_extraction_eval() -> list[dict]:
    from iteration1 import storage
    from iteration1.evals.code_evals import metric_extraction_accuracy

    gt = _load_ground_truth("metric_extraction.json")
    examples = gt.get("examples", [])
    if not examples:
        return []

    results = []
    for ex in examples:
        company = ex["company"]
        quarter = ex["quarter"]
        gt_metrics = ex["metrics"]

        try:
            conn = storage.get_connection(company)
            rows = storage.get_metrics_for_quarter(conn, company, quarter)
            conn.close()
        except Exception:
            results.append({"company": company, "quarter": quarter, "score": None,
                            "note": "No DB data"})
            continue

        extracted = {r["metric_name"]: r["value"] for r in rows if r.get("value") is not None}
        result = metric_extraction_accuracy(extracted, gt_metrics)
        result["company"] = company
        result["quarter"] = quarter
        results.append(result)

    return results


# ── Code Eval Suite ──────────────────────────────────────────────────────

def run_code_evals(company_filter: str = None):
    from iteration1 import storage
    from iteration1.evals.code_evals import (
        derived_metric_calculation,
        citation_page_accuracy,
        citation_coverage,
        rolling_window_integrity,
        schema_compliance,
    )

    _print_header("CODE-BASED EVALS")
    all_scores = []

    # ── Eval 1: Classification ──
    _print_section("Eval 1: Classification Accuracy (ground truth)")
    try:
        cls_results = _run_classification_eval()
        if cls_results:
            for r in cls_results:
                s = r.get("score")
                icon = _score_icon(s)
                fname = r.get("file", "?")[:50]
                extra = ""
                if s == 0:
                    extra = f"  (got: {r.get('predicted_type', '?')}/{r.get('predicted_route', '?')})"
                elif r.get("note"):
                    extra = f"  ({r['note']})"
                print(f"    {icon} {fname}{extra}")
                if s is not None:
                    all_scores.append(("classification", s))
        else:
            print(f"    {SKIP_ICON} No ground truth examples")
    except Exception as exc:
        print(f"    {FAIL_ICON} Error: {exc}")

    # ── Eval 2: Metric Extraction ──
    _print_section("Eval 2: Metric Extraction Accuracy (ground truth)")
    try:
        ext_results = _run_metric_extraction_eval()
        if ext_results:
            for r in ext_results:
                s = r.get("score")
                icon = _score_icon(s)
                label = f"{r.get('company', '?')} {r.get('quarter', '?')}"
                detail = f"{r.get('correct', 0)}/{r.get('total', 0)} metrics matched"
                print(f"    {icon} {label}: {detail}")
                if r.get("errors"):
                    for err in r["errors"][:3]:
                        print(f"        ! {err['metric']}: expected={err.get('expected')}, "
                              f"got={err.get('got', 'missing')}")
                if s is not None:
                    all_scores.append(("metric_extraction", s))
        else:
            print(f"    {SKIP_ICON} No ground truth examples")
    except Exception as exc:
        print(f"    {FAIL_ICON} Error: {exc}")

    # ── Evals 3-7: Per-company ──
    companies = _discover_companies()
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c.lower()]

    for company in companies:
        conn = storage.get_connection(company)
        quarters = storage.list_quarters(conn, company)
        if not quarters:
            conn.close()
            continue

        schema = _find_schema_for_company(company)
        if not schema:
            conn.close()
            continue

        metrics_table = storage.get_metrics_table(conn, company)

        _print_section(f"Eval 3: Derived Metric Calc — {company}")
        for q in quarters:
            rows = storage.get_metrics_for_quarter(conn, company, q)
            r = derived_metric_calculation([dict(row) for row in rows], schema.get("metrics", []))
            icon = _score_icon(r["score"])
            print(f"    {icon} {q}: {r['correct']}/{r['total']} formulas verified")
            all_scores.append(("derived_calc", r["score"]))

        _print_section(f"Eval 4: Citation Page Accuracy — {company}")
        for q in quarters:
            rows = storage.get_metrics_for_quarter(conn, company, q)
            cites_by_metric = storage.get_citations_for_quarter(conn, company, q)
            flat = []
            for mname, cites in cites_by_metric.items():
                m_row = next((r for r in rows if r["metric_name"] == mname), {})
                for c in cites:
                    flat.append({
                        "metric_name": mname, "page_number": c["page_number"],
                        "passage": c["passage"], "file_path": c["file_path"],
                        "value": m_row.get("value"),
                    })
            r = citation_page_accuracy(flat, pdf_base_dir=BASE_DIR)
            icon = _score_icon(r["score"])
            print(f"    {icon} {q}: {r['verified']}/{r['total']} citations verified on page")
            all_scores.append(("citation_page", r["score"]))

        _print_section(f"Eval 5: Citation Coverage — {company}")
        for q in quarters:
            rows = storage.get_metrics_for_quarter(conn, company, q)
            cites_by_metric = storage.get_citations_for_quarter(conn, company, q)
            r = citation_coverage([dict(row) for row in rows], cites_by_metric)
            icon = _score_icon(r["score"])
            print(f"    {icon} {q}: {r['with_citations']}/{r['total_found']} metrics have citations")
            if r.get("missing_citations"):
                print(f"        missing: {', '.join(r['missing_citations'][:5])}")
            all_scores.append(("citation_coverage", r["score"]))

        _print_section(f"Eval 6: Rolling Window Integrity — {company}")
        r = rolling_window_integrity(metrics_table)
        icon = _score_icon(r["score"])
        checks = ", ".join(f"{k}={v}" for k, v in r.get("checks", {}).items())
        print(f"    {icon} {checks}")
        all_scores.append(("rolling_window", r["score"]))

        _print_section(f"Eval 7: Schema Compliance — {company}")
        r = schema_compliance(metrics_table, schema)
        icon = _score_icon(r["score"])
        checks = ", ".join(f"{k}={v}" for k, v in r.get("checks", {}).items())
        print(f"    {icon} {checks}")
        if r.get("issues"):
            for issue in r["issues"][:3]:
                print(f"        ! {issue}")
        all_scores.append(("schema_compliance", r["score"]))

        conn.close()

    _print_code_summary(all_scores)
    return all_scores


def _print_code_summary(all_scores: list[tuple[str, float]]):
    _print_header("CODE EVAL SUMMARY")

    by_eval = {}
    for name, score in all_scores:
        by_eval.setdefault(name, []).append(score)

    total_pass = 0
    total_count = 0

    print(f"\n  {'Eval':<25} {'Avg':>6}  {'Pass':>6}  {'Total':>6}")
    print(f"  {'─' * 25} {'─' * 6}  {'─' * 6}  {'─' * 6}")

    for name, scores in by_eval.items():
        avg = sum(scores) / len(scores) if scores else 0
        perfect = sum(1 for s in scores if s == 1.0)
        icon = _score_icon(1.0 if avg == 1.0 else 0.7 if avg >= 0.7 else 0.0)
        print(f"  {icon} {name:<23} {avg:>5.0%}  {perfect:>5}/{len(scores):<5}")
        total_pass += perfect
        total_count += len(scores)

    if total_count:
        overall = sum(s for _, s in all_scores) / total_count
        print(f"\n  {'Overall':>27} {overall:>5.0%}  {total_pass:>5}/{total_count:<5}")


# ── LLM Judge Eval Suite ─────────────────────────────────────────────────

def _load_transcript_excerpt(pdf_path: str, max_chars: int = 3000) -> str:
    if not pdf_path or not os.path.isfile(pdf_path):
        return "(transcript not available)"
    try:
        from iteration1.pdf_parser import parse_pdf_with_page_tags
        return parse_pdf_with_page_tags(pdf_path)[:max_chars]
    except Exception:
        return "(error loading transcript)"


def _format_guidance_items(items: list[dict]) -> str:
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
    from phoenix.evals import LLM
    from iteration1 import storage
    from iteration1.evals.llm_judge_evals import (
        build_taxonomy_quality_evaluator,
        build_guidance_completeness_evaluator,
        build_delta_detection_evaluator,
        build_taxonomy_evolution_evaluator,
        build_cross_quarter_evaluator,
    )

    _print_header("LLM JUDGE EVALS")

    eval_llm = LLM(provider="openai", model=EVAL_MODEL)
    taxonomy_judge = build_taxonomy_quality_evaluator(eval_llm)
    guidance_judge = build_guidance_completeness_evaluator(eval_llm)
    delta_judge = build_delta_detection_evaluator(eval_llm)
    evolution_judge = build_taxonomy_evolution_evaluator(eval_llm)
    cross_quarter_judge = build_cross_quarter_evaluator(eval_llm)

    companies = _discover_companies()
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c.lower()]

    all_scores = []

    for company in companies:
        conn = storage.get_connection(company)
        guidance_table = storage.get_guidance_table(conn, company)
        quarters = guidance_table.get("quarters", [])
        topics = guidance_table.get("topics", {})

        if not quarters or not topics:
            conn.close()
            continue

        print(f"\n  ── {company.upper()} ({len(quarters)}Q, {len(topics)} topics) {'─' * 20}")

        transcript_path = None
        for q in quarters:
            rows = conn.execute(
                "SELECT DISTINCT p.file_path FROM guidance g "
                "JOIN pdfs p ON g.pdf_id = p.id "
                "WHERE g.company=? AND g.quarter=? LIMIT 1", (company, q)
            ).fetchall()
            if rows:
                transcript_path = rows[0]["file_path"]
                break

        transcript_excerpt = _load_transcript_excerpt(transcript_path)
        schema = _find_schema_for_company(company)
        sector = schema.get("sector", "Financial") if schema else "Financial"

        # Judge 1: Taxonomy Quality
        _print_section("Judge 1: Taxonomy Quality")
        topics_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(topics.keys()))
        try:
            result = taxonomy_judge.evaluate({
                "company": company, "sector": sector,
                "topics_list": topics_list, "transcript_excerpt": transcript_excerpt,
            })
            s = result[0]
            score_val = float(s.score) if s.score is not None else 0.0
            print(f"    {_score_icon(score_val)} {s.label or '?'} — {(s.explanation or '')[:100]}")
            all_scores.append(("taxonomy_quality", score_val))
        except Exception as exc:
            print(f"    {FAIL_ICON} Error: {exc}")

        # Judge 2: Guidance Completeness
        _print_section("Judge 2: Guidance Completeness")
        latest_q = quarters[-1]
        g_scores = []
        for topic, q_data in topics.items():
            items = q_data.get(latest_q, [])
            if not items:
                continue
            try:
                result = guidance_judge.evaluate({
                    "company": company, "quarter": latest_q, "topic": topic,
                    "extracted_guidance": _format_guidance_items(items),
                    "transcript_passage": (items[0].get("passage", "") or "")[:1500],
                })
                s = result[0]
                sv = float(s.score) if s.score is not None else 0.0
                g_scores.append(sv)
                print(f"    {_score_icon(sv)} {topic}: {s.label or '?'}")
            except Exception as exc:
                print(f"    {FAIL_ICON} {topic}: {exc}")

        if g_scores:
            avg = sum(g_scores) / len(g_scores)
            all_scores.append(("guidance_completeness", avg))

        # Judge 3: Delta Detection
        _print_section("Judge 3: Delta Detection")
        d_scores = []
        for q in quarters:
            deltas = storage.get_deltas_for_quarter(conn, company, q)
            for d in (deltas or [])[:5]:
                try:
                    result = delta_judge.evaluate({
                        "company": company, "current_quarter": q,
                        "prior_quarter": d.get("prior_quarter", "?"),
                        "topic": d["topic"], "change_type": d["change_type"],
                        "current_statement": d.get("current_statement", ""),
                        "prior_statement": d.get("prior_statement", ""),
                        "delta_summary": d["summary"],
                    })
                    s = result[0]
                    sv = float(s.score) if s.score is not None else 0.0
                    d_scores.append(sv)
                    print(f"    {_score_icon(sv)} {q} · {d['topic']} ({d['change_type']}): {s.label}")
                except Exception as exc:
                    print(f"    {FAIL_ICON} {q} · {d['topic']}: {exc}")

        if d_scores:
            all_scores.append(("delta_detection", sum(d_scores) / len(d_scores)))
        else:
            print(f"    {SKIP_ICON} No deltas (single quarter)")

        # Judge 4: Taxonomy Evolution
        _print_section("Judge 4: Taxonomy Evolution")
        if len(quarters) >= 2:
            prior_q, current_q = quarters[-2], quarters[-1]
            prior_t = {t for t, qd in topics.items() if prior_q in qd}
            curr_t = {t for t, qd in topics.items() if current_q in qd}
            try:
                result = evolution_judge.evaluate({
                    "company": company, "prior_quarter": prior_q, "current_quarter": current_q,
                    "prior_topics": "\n".join(f"  - {t}" for t in sorted(prior_t)) or "(none)",
                    "current_topics": "\n".join(f"  - {t}" for t in sorted(curr_t)) or "(none)",
                    "new_topics": ", ".join(sorted(curr_t - prior_t)) or "(none)",
                    "dropped_topics": ", ".join(sorted(prior_t - curr_t)) or "(none)",
                })
                s = result[0]
                sv = float(s.score) if s.score is not None else 0.0
                print(f"    {_score_icon(sv)} {prior_q} → {current_q}: {s.label}")
                all_scores.append(("taxonomy_evolution", sv))
            except Exception as exc:
                print(f"    {FAIL_ICON} Error: {exc}")
        else:
            print(f"    {SKIP_ICON} Need 2+ quarters")

        # Judge 5: Cross-Quarter Comparison
        _print_section("Judge 5: Cross-Quarter Comparison")
        if len(quarters) >= 2:
            cq_scores = []
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
                try:
                    result = cross_quarter_judge.evaluate({
                        "company": company, "topic": topic,
                        "quarters_compared": ", ".join(quarters),
                        "guidance_by_quarter": "\n".join(lines),
                        "comparison_text": (
                            f"Topic '{topic}' across {len(quarters)} quarters for {company}. "
                            f"The guidance table shows the progression of management statements."
                        ),
                    })
                    s = result[0]
                    sv = float(s.score) if s.score is not None else 0.0
                    cq_scores.append(sv)
                    print(f"    {_score_icon(sv)} {topic}: {s.label}")
                except Exception as exc:
                    print(f"    {FAIL_ICON} {topic}: {exc}")

            if cq_scores:
                all_scores.append(("cross_quarter", sum(cq_scores) / len(cq_scores)))
        else:
            print(f"    {SKIP_ICON} Need 2+ quarters")

        conn.close()

    _print_judge_summary(all_scores)
    return all_scores


def _print_judge_summary(all_scores: list[tuple[str, float]]):
    _print_header("LLM JUDGE SUMMARY")

    by_eval = {}
    for name, score in all_scores:
        by_eval.setdefault(name, []).append(score)

    print(f"\n  {'Judge':<25} {'Avg':>6}  {'Count':>6}")
    print(f"  {'─' * 25} {'─' * 6}  {'─' * 6}")

    total_score = 0
    total_count = 0
    for name, scores in by_eval.items():
        avg = sum(scores) / len(scores) if scores else 0
        icon = _score_icon(1.0 if avg >= 0.8 else 0.7 if avg >= 0.5 else 0.0)
        print(f"  {icon} {name:<23} {avg:>5.0%}  {len(scores):>5}")
        total_score += sum(scores)
        total_count += len(scores)

    if total_count:
        overall = total_score / total_count
        print(f"\n  {'Overall':>27} {overall:>5.0%}  {total_count:>5}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(description="Earnings Intelligence Pipeline — Eval Runner")
    parser.add_argument("--suite", choices=["code", "judge", "all"], default="all")
    parser.add_argument("--company", default=None, help="Filter to a specific company")
    parser.add_argument("--arize", action="store_true", help="Upload to Arize Cloud")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.arize:
        from iteration1.evals.arize_experiment import run_arize_experiment
        run_arize_experiment(company_filter=args.company, dry_run=args.dry_run)
        return

    if args.suite in ("code", "all"):
        run_code_evals(company_filter=args.company)

    if args.suite in ("judge", "all"):
        run_llm_judge_evals(company_filter=args.company)


if __name__ == "__main__":
    main()
