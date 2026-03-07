"""Code-based (objective) evaluation functions for Iteration 1.

7 eval metrics — all deterministic, no LLM judge needed:
  1. classification_accuracy      — exact match: predicted route vs expected (NEEDS GT)
  2. metric_extraction_accuracy   — fuzzy match: ±2% tolerance (NEEDS GT)
  3. derived_metric_calculation   — re-run formula, compare stored value
  4. citation_page_accuracy       — parse PDF page, verify value string exists
  5. citation_coverage            — % of extractions with non-null citations
  6. rolling_window_integrity     — structural check on the 8-quarter table
  7. schema_compliance            — all required fields present, correct types

Ground-truth-free evals (can run immediately): 3, 4, 5, 6, 7
Ground-truth-required evals (need manual labels): 1, 2
"""

import glob
import os
import re
from typing import Optional

from langchain_community.document_loaders import PyPDFLoader


# ---------------------------------------------------------------------------
# Eval 1 — Classification Accuracy  (NEEDS GROUND TRUTH)
# ---------------------------------------------------------------------------

def classification_accuracy(predicted_doc_type: str, predicted_route: str,
                            expected_doc_type: str, expected_route: str) -> dict:
    """Exact match on doc_type and routing decision.

    Returns:
        {"score": 0|1, "doc_type_match": bool, "route_match": bool}
    """
    doc_match = predicted_doc_type.strip().lower() == expected_doc_type.strip().lower()
    route_match = predicted_route.strip().lower() == expected_route.strip().lower()
    return {
        "score": 1 if (doc_match and route_match) else 0,
        "doc_type_match": doc_match,
        "route_match": route_match,
    }


# ---------------------------------------------------------------------------
# Eval 2 — Metric Extraction Accuracy  (NEEDS GROUND TRUTH)
# ---------------------------------------------------------------------------

def metric_extraction_accuracy(extracted: dict, ground_truth: dict,
                               tolerance: float = 0.02) -> dict:
    """Fuzzy numeric match with configurable tolerance (default ±2%).

    Args:
        extracted:    {"metric_name": value, ...}
        ground_truth: {"metric_name": value, ...}  (None = not expected)
        tolerance:    relative tolerance, e.g. 0.02 = ±2%

    Returns:
        {"score": float 0-1, "total": int, "correct": int, "errors": [...]}
    """
    errors = []
    correct = 0
    total = 0

    for metric_name, gt_value in ground_truth.items():
        if gt_value is None:
            continue
        total += 1
        ext_value = extracted.get(metric_name)

        if ext_value is None:
            errors.append({"metric": metric_name, "issue": "missing", "expected": gt_value})
            continue

        if gt_value == 0:
            if ext_value == 0:
                correct += 1
            else:
                errors.append({"metric": metric_name, "issue": "wrong",
                               "expected": gt_value, "got": ext_value})
            continue

        relative_error = abs(ext_value - gt_value) / abs(gt_value)
        if relative_error <= tolerance:
            correct += 1
        else:
            errors.append({"metric": metric_name, "issue": "wrong",
                           "expected": gt_value, "got": ext_value,
                           "relative_error": round(relative_error, 4)})

    return {
        "score": correct / total if total > 0 else 1.0,
        "total": total,
        "correct": correct,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Eval 3 — Derived Metric Calculation  (GROUND-TRUTH-FREE)
# ---------------------------------------------------------------------------

def derived_metric_calculation(metrics_rows: list[dict],
                               schema_metrics: list[dict]) -> dict:
    """Re-run each fallback formula and verify it matches the stored value.

    Args:
        metrics_rows:  list of dicts from the metrics table
                       (keys: metric_name, value, unit, source, note)
        schema_metrics: list of metric defs from schema JSON
                       (keys: name, fallback_formula, fallback_requires)

    Returns:
        {"score": float, "total": int, "correct": int, "errors": [...]}
    """
    value_lookup = {
        r["metric_name"]: r["value"]
        for r in metrics_rows
        if r.get("value") is not None
    }

    formulas = {}
    for m in schema_metrics:
        if m.get("fallback_formula"):
            formulas[m["name"]] = {
                "formula": m["fallback_formula"],
                "requires": m.get("fallback_requires", []),
            }

    errors = []
    correct = 0
    total = 0

    for name, info in formulas.items():
        stored_value = value_lookup.get(name)
        if stored_value is None:
            continue

        stored_row = next((r for r in metrics_rows if r["metric_name"] == name), {})
        if stored_row.get("source") != "calculated":
            continue

        total += 1
        required_values = {
            req: value_lookup[req]
            for req in info["requires"]
            if req in value_lookup
        }
        if len(required_values) != len(info["requires"]):
            errors.append({"metric": name, "issue": "missing_inputs",
                           "missing": [r for r in info["requires"] if r not in value_lookup]})
            continue

        expr = info["formula"]
        for dep_name, dep_val in sorted(required_values.items(), key=lambda x: -len(x[0])):
            expr = expr.replace(dep_name, str(dep_val))

        try:
            recalculated = round(eval(expr, {"__builtins__": {}}, {}), 2)
        except Exception as exc:
            errors.append({"metric": name, "issue": "formula_error", "error": str(exc)})
            continue

        if abs(recalculated - stored_value) < 0.015:
            correct += 1
        else:
            errors.append({
                "metric": name,
                "issue": "mismatch",
                "stored": stored_value,
                "recalculated": recalculated,
                "formula": info["formula"],
            })

    return {
        "score": correct / total if total > 0 else 1.0,
        "total": total,
        "correct": correct,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Eval 4 — Citation Page Accuracy  (GROUND-TRUTH-FREE)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Collapse whitespace and commas for fuzzy string matching."""
    text = text.replace(",", "").replace("'", "").replace("\u2019", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_page_text(pdf_path: str, page_number: int) -> Optional[str]:
    """Load a single page from a PDF (1-indexed). Returns None on error."""
    try:
        loader = PyPDFLoader(pdf_path)
        pages = loader.load()
        idx = page_number - 1
        if 0 <= idx < len(pages):
            return pages[idx].page_content
    except Exception:
        pass
    return None


def citation_page_accuracy(citations: list[dict], pdf_base_dir: str = "") -> dict:
    """Verify that each citation's claimed value actually appears on the cited page.

    Args:
        citations: list of dicts with keys:
            metric_name, page_number, passage, file_path, value (raw_value or str)
        pdf_base_dir: prefix path if file_path is relative

    Returns:
        {"score": float 0-1, "total": int, "verified": int, "errors": [...]}
    """
    errors = []
    verified = 0
    total = 0

    pdf_cache: dict[str, dict[int, str]] = {}

    for cite in citations:
        page_num = cite.get("page_number")
        file_path = cite.get("file_path", "")
        passage = cite.get("passage") or ""
        metric_name = cite.get("metric_name", "?")

        if not page_num or not file_path:
            continue

        total += 1

        if not os.path.isfile(file_path):
            if pdf_base_dir and not file_path.startswith("/"):
                file_path = os.path.join(pdf_base_dir, file_path)
            if not os.path.isfile(file_path):
                basename = os.path.basename(file_path)
                base_search = pdf_base_dir or os.path.dirname(os.path.dirname(__file__))
                matches = glob.glob(os.path.join(base_search, "**", basename), recursive=True)
                if matches:
                    file_path = matches[0]

        cache_key = file_path
        if cache_key not in pdf_cache:
            pdf_cache[cache_key] = {}

        if page_num not in pdf_cache[cache_key]:
            page_text = _extract_page_text(file_path, page_num)
            pdf_cache[cache_key][page_num] = page_text or ""

        page_text = pdf_cache[cache_key][page_num]
        if not page_text:
            errors.append({"metric": metric_name, "page": page_num,
                           "issue": "page_empty_or_missing"})
            continue

        normalized_page = _normalize(page_text)

        found = False
        search_terms = _build_search_terms(passage, cite.get("value"))
        for term in search_terms:
            if term and _normalize(term) in normalized_page:
                found = True
                break

        if found:
            verified += 1
        else:
            errors.append({
                "metric": metric_name,
                "page": page_num,
                "issue": "value_not_found_on_page",
                "searched_terms": search_terms[:3],
            })

    return {
        "score": verified / total if total > 0 else 1.0,
        "total": total,
        "verified": verified,
        "errors": errors,
    }


def _build_search_terms(passage: str, value=None) -> list[str]:
    """Build a list of search strings from the passage and numeric value."""
    terms = []
    if passage:
        words = passage.split()
        if len(words) > 3:
            terms.append(" ".join(words[:6]))
        terms.append(passage[:40])

    if value is not None:
        val_str = str(value)
        terms.append(val_str)
        if "." in val_str:
            terms.append(val_str.rstrip("0").rstrip("."))

    return [t for t in terms if t and len(t.strip()) > 1]


# ---------------------------------------------------------------------------
# Eval 5 — Citation Coverage  (GROUND-TRUTH-FREE)
# ---------------------------------------------------------------------------

def citation_coverage(metrics_rows: list[dict],
                      citations_by_metric: dict[str, list]) -> dict:
    """Percentage of found metrics that have at least one citation.

    Args:
        metrics_rows: list of metric dicts (metric_name, value, found)
        citations_by_metric: {metric_name: [citation_dicts]}

    Returns:
        {"score": float 0-1, "total_found": int, "with_citations": int,
         "missing_citations": [...]}
    """
    found_metrics = [r for r in metrics_rows if r.get("found", r.get("value") is not None)]
    missing = []
    cited = 0

    for m in found_metrics:
        name = m["metric_name"]
        cites = citations_by_metric.get(name, [])
        if cites:
            cited += 1
        else:
            missing.append(name)

    total = len(found_metrics)
    return {
        "score": cited / total if total > 0 else 1.0,
        "total_found": total,
        "with_citations": cited,
        "missing_citations": missing,
    }


# ---------------------------------------------------------------------------
# Eval 6 — Rolling Window Integrity  (GROUND-TRUTH-FREE)
# ---------------------------------------------------------------------------

def rolling_window_integrity(metrics_table: dict,
                             expected_max_quarters: int = 8) -> dict:
    """Structural check on the rolling quarter table.

    Checks:
      a) Quarter count <= expected_max_quarters
      b) Quarters are in chronological order
      c) No duplicate quarters
      d) Every metric has entries across all quarters (sparseness check)

    Args:
        metrics_table: {"quarters": [...], "metrics": {name: {"unit": ..., "values": {q: v}}}}

    Returns:
        {"score": float 0-1, "checks": {check_name: pass|fail}, "issues": [...]}
    """
    issues = []
    quarters = metrics_table.get("quarters", [])
    metrics = metrics_table.get("metrics", {})

    checks = {
        "quarter_count": True,
        "no_duplicates": True,
        "chronological_order": True,
        "metric_coverage": True,
    }

    if len(quarters) > expected_max_quarters:
        checks["quarter_count"] = False
        issues.append(f"Quarter count {len(quarters)} exceeds max {expected_max_quarters}")

    if len(quarters) != len(set(quarters)):
        checks["no_duplicates"] = False
        issues.append(f"Duplicate quarters found: {[q for q in quarters if quarters.count(q) > 1]}")

    if quarters != sorted(quarters):
        checks["chronological_order"] = False
        issues.append(f"Quarters not in chronological order: {quarters}")

    sparse_metrics = []
    for name, data in metrics.items():
        values = data.get("values", {})
        populated = sum(1 for q in quarters if q in values and values[q] is not None)
        if populated < len(quarters) * 0.5:
            sparse_metrics.append({"metric": name, "populated": populated,
                                   "total_quarters": len(quarters)})
    if sparse_metrics:
        checks["metric_coverage"] = False
        issues.append(f"{len(sparse_metrics)} metrics have <50% quarter coverage")
        for sm in sparse_metrics:
            issues.append(f"  {sm['metric']}: {sm['populated']}/{sm['total_quarters']} quarters")

    passed = sum(1 for v in checks.values() if v)
    return {
        "score": passed / len(checks) if checks else 1.0,
        "checks": {k: "pass" if v else "fail" for k, v in checks.items()},
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Eval 7 — Schema Compliance  (GROUND-TRUTH-FREE)
# ---------------------------------------------------------------------------

def schema_compliance(metrics_table: dict, schema: dict) -> dict:
    """Verify pipeline output conforms to the schema definition.

    Checks:
      a) All schema metrics present in the table
      b) Units match schema expectations
      c) Values are numeric (not strings, not NaN)
      d) Table structure has required keys

    Args:
        metrics_table: {"quarters": [...], "metrics": {name: {"unit": ..., "values": {q: v}}}}
        schema:        parsed schema JSON with "metrics" list

    Returns:
        {"score": float 0-1, "checks": {check_name: pass|fail}, "issues": [...]}
    """
    issues = []
    checks = {
        "structure": True,
        "all_metrics_present": True,
        "units_match": True,
        "values_numeric": True,
    }

    if "quarters" not in metrics_table or "metrics" not in metrics_table:
        checks["structure"] = False
        issues.append("Missing required keys: 'quarters' and/or 'metrics'")
        passed = sum(1 for v in checks.values() if v)
        return {"score": passed / len(checks), "checks": checks, "issues": issues}

    table_metrics = metrics_table.get("metrics", {})
    schema_metrics = schema.get("metrics", [])
    schema_names = {m["name"] for m in schema_metrics}
    schema_units = {m["name"]: m.get("unit", "") for m in schema_metrics}

    missing_metrics = schema_names - set(table_metrics.keys())
    if missing_metrics:
        checks["all_metrics_present"] = False
        issues.append(f"Missing metrics: {sorted(missing_metrics)}")

    unit_mismatches = []
    for name, data in table_metrics.items():
        if name in schema_units:
            expected_unit = schema_units[name]
            actual_unit = data.get("unit", "")
            if expected_unit and actual_unit and expected_unit.lower() != actual_unit.lower():
                unit_mismatches.append({"metric": name,
                                        "expected": expected_unit, "actual": actual_unit})
    if unit_mismatches:
        checks["units_match"] = False
        for um in unit_mismatches:
            issues.append(f"Unit mismatch: {um['metric']} — "
                          f"expected '{um['expected']}', got '{um['actual']}'")

    non_numeric = []
    for name, data in table_metrics.items():
        for q, v in data.get("values", {}).items():
            if v is not None and not isinstance(v, (int, float)):
                non_numeric.append({"metric": name, "quarter": q, "value": v})
    if non_numeric:
        checks["values_numeric"] = False
        issues.append(f"{len(non_numeric)} non-numeric values found")

    passed = sum(1 for v in checks.values() if v)
    return {
        "score": passed / len(checks) if checks else 1.0,
        "checks": {k: "pass" if v else "fail" for k, v in checks.items()},
        "issues": issues,
    }
