"""Code-based evaluation functions for Iteration 2.

Eight evals matching the design doc checkpoints:
  1. MNPI gate accuracy (regex detection of known MNPI markers)
  2. Retrieval recall@k (how many relevant chunks are in top-k)
  3. Source attribution coverage (% of claims with source badges)
  4. Mosaic completeness score (3-namespace coverage)
  5. Consensus divergence detection (are known disagreements surfaced?)
  6. Freshness/staleness accuracy (correct stale flag for old docs)
  7. Cache hit/miss correctness
  8. Corrective RAG precision (were irrelevant chunks filtered out?)
"""

import re
from typing import Optional


def mnpi_gate_accuracy(
    test_documents: list[dict],
) -> dict:
    """Eval 1: Test MNPI gate on known positive and negative examples.

    Each test_document: {"text": str, "expected_mnpi": bool, "file_name": str}
    """
    from iteration2.mnpi_gate import screen_for_mnpi

    correct = 0
    total = len(test_documents)
    results = []

    for doc in test_documents:
        result = screen_for_mnpi(doc["text"], doc.get("file_name", ""))
        predicted = result.is_mnpi
        expected = doc["expected_mnpi"]
        is_correct = predicted == expected
        if is_correct:
            correct += 1
        results.append({
            "file_name": doc.get("file_name", ""),
            "expected": expected,
            "predicted": predicted,
            "correct": is_correct,
            "confidence": result.confidence,
            "reason": result.reason,
        })

    return {
        "eval": "mnpi_gate_accuracy",
        "accuracy": correct / total if total > 0 else 0.0,
        "correct": correct,
        "total": total,
        "details": results,
    }


def retrieval_recall_at_k(
    query: str,
    expected_doc_names: list[str],
    retrieved_chunks: list,
    k: int = 10,
) -> dict:
    """Eval 2: What fraction of expected documents appear in top-k results?"""
    top_k = retrieved_chunks[:k]
    retrieved_names = set(c.file_name for c in top_k)

    found = [name for name in expected_doc_names if name in retrieved_names]

    return {
        "eval": "retrieval_recall_at_k",
        "recall": len(found) / len(expected_doc_names) if expected_doc_names else 0.0,
        "k": k,
        "found": found,
        "missed": [n for n in expected_doc_names if n not in retrieved_names],
        "total_expected": len(expected_doc_names),
    }


def source_attribution_coverage(answer_data: dict) -> dict:
    """Eval 3: What percentage of the answer has source badges?

    Checks if source_badges list is non-empty and covers multiple source types.
    """
    badges = answer_data.get("source_badges", [])
    source_types = set(b.get("source_type", "") for b in badges)

    has_any = len(badges) > 0
    type_coverage = len(source_types) / 3.0

    return {
        "eval": "source_attribution_coverage",
        "has_attribution": has_any,
        "badge_count": len(badges),
        "source_types_present": list(source_types),
        "type_coverage": type_coverage,
        "score": 1.0 if has_any and type_coverage >= 0.66 else (0.5 if has_any else 0.0),
    }


def mosaic_completeness_eval(answer_data: dict) -> dict:
    """Eval 4: Does the answer draw from all 3 source types?"""
    mosaic = answer_data.get("mosaic", {})
    if not mosaic:
        return {"eval": "mosaic_completeness", "score": 0.0, "present": [], "missing": ["disclosure", "opinion", "field_data"]}

    present = []
    missing = []
    for ns in ["disclosure", "opinion", "field_data"]:
        key = f"{ns}_present"
        if mosaic.get(key, False):
            present.append(ns)
        else:
            missing.append(ns)

    return {
        "eval": "mosaic_completeness",
        "score": mosaic.get("completeness_score", len(present) / 3.0),
        "present": present,
        "missing": missing,
    }


def consensus_divergence_detection(
    answer_data: dict,
    expected_divergence_topics: list[str],
) -> dict:
    """Eval 5: Are known divergences surfaced in the answer?"""
    divergences = answer_data.get("divergences", [])
    detected_topics = [d.get("metric_or_topic", "").lower() for d in divergences]

    found = []
    missed = []
    for topic in expected_divergence_topics:
        topic_lower = topic.lower()
        if any(topic_lower in dt for dt in detected_topics):
            found.append(topic)
        else:
            missed.append(topic)

    return {
        "eval": "consensus_divergence_detection",
        "recall": len(found) / len(expected_divergence_topics) if expected_divergence_topics else 1.0,
        "found": found,
        "missed": missed,
        "total_detected": len(divergences),
    }


def freshness_accuracy(
    chunks: list,
    expected_stale_files: list[str],
) -> dict:
    """Eval 6: Are stale documents correctly flagged?"""
    stale_files = set(c.file_name for c in chunks if c.is_stale)

    correct_stale = [f for f in expected_stale_files if f in stale_files]
    missed_stale = [f for f in expected_stale_files if f not in stale_files]

    return {
        "eval": "freshness_accuracy",
        "accuracy": len(correct_stale) / len(expected_stale_files) if expected_stale_files else 1.0,
        "correct_stale": correct_stale,
        "missed_stale": missed_stale,
    }


def cache_correctness(
    company: str,
    query: str,
    first_call_cached: bool,
    second_call_cached: bool,
) -> dict:
    """Eval 7: Does cache behave correctly (miss on first, hit on second)?"""
    return {
        "eval": "cache_correctness",
        "first_call_miss": not first_call_cached,
        "second_call_hit": second_call_cached,
        "score": 1.0 if (not first_call_cached and second_call_cached) else 0.0,
    }


def corrective_rag_precision(
    chunks_before_filter: list,
    chunks_after_filter: list,
) -> dict:
    """Eval 8: Did corrective RAG reduce irrelevant chunks?"""
    before = len(chunks_before_filter)
    after = len(chunks_after_filter)

    filtered_out = before - after
    filter_rate = filtered_out / before if before > 0 else 0.0

    relevant_labels = sum(
        1 for c in chunks_after_filter if getattr(c, 'relevance_label', None) == 'RELEVANT'
    )
    precision = relevant_labels / after if after > 0 else 0.0

    return {
        "eval": "corrective_rag_precision",
        "before_count": before,
        "after_count": after,
        "filtered_out": filtered_out,
        "filter_rate": filter_rate,
        "relevant_precision": precision,
    }
