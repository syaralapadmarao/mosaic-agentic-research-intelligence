"""Evaluation Runner for Iteration 2.

Usage:
  python -m iteration2.evals.runner --eval all
  python -m iteration2.evals.runner --eval mnpi
  python -m iteration2.evals.runner --eval retrieval
"""

import argparse
import json
import os
import sys

from iteration2.evals.code_evals import (
    mnpi_gate_accuracy,
    source_attribution_coverage,
    mosaic_completeness_eval,
)


GROUND_TRUTH_DIR = os.path.join(os.path.dirname(__file__), "ground_truth")


def _run_mnpi_eval():
    """Run MNPI gate accuracy evaluation."""
    gt_path = os.path.join(GROUND_TRUTH_DIR, "mnpi_test_docs.json")
    with open(gt_path) as f:
        test_docs = json.load(f)

    result = mnpi_gate_accuracy(test_docs)

    print("\n" + "=" * 60)
    print("EVAL 1: MNPI Gate Accuracy")
    print("=" * 60)
    print(f"Accuracy: {result['accuracy']:.1%} ({result['correct']}/{result['total']})")
    print()

    for d in result["details"]:
        status = "PASS" if d["correct"] else "FAIL"
        print(f"  [{status}] {d['file_name']}: expected={d['expected']}, predicted={d['predicted']}")
        if d.get("reason"):
            print(f"         Reason: {d['reason']}")

    return result


def _run_source_attribution_eval():
    """Run source attribution mock eval."""
    mock_answer = {
        "answer": "Revenue grew 18% YoY...",
        "source_badges": [
            {"claim_index": 0, "source_type": "disclosure", "doc_ref": "transcript.pdf"},
            {"claim_index": 1, "source_type": "opinion", "doc_ref": "motilal_report.md"},
            {"claim_index": 2, "source_type": "field_data", "doc_ref": "visit_note.md"},
        ],
        "mosaic": {
            "disclosure_present": True,
            "opinion_present": True,
            "field_data_present": True,
            "completeness_score": 1.0,
        },
    }

    attr_result = source_attribution_coverage(mock_answer)
    mosaic_result = mosaic_completeness_eval(mock_answer)

    print("\n" + "=" * 60)
    print("EVAL 3: Source Attribution Coverage")
    print("=" * 60)
    print(f"Has attribution: {attr_result['has_attribution']}")
    print(f"Badge count: {attr_result['badge_count']}")
    print(f"Type coverage: {attr_result['type_coverage']:.1%}")
    print(f"Score: {attr_result['score']}")

    print("\n" + "=" * 60)
    print("EVAL 4: Mosaic Completeness")
    print("=" * 60)
    print(f"Score: {mosaic_result['score']:.1%}")
    print(f"Present: {mosaic_result['present']}")
    print(f"Missing: {mosaic_result['missing']}")

    return {"source_attribution": attr_result, "mosaic": mosaic_result}


def main():
    parser = argparse.ArgumentParser(description="Run Iteration 2 evaluations")
    parser.add_argument("--eval", choices=["all", "mnpi", "attribution", "mosaic"], default="all")
    args = parser.parse_args()

    results = {}

    if args.eval in ("all", "mnpi"):
        results["mnpi"] = _run_mnpi_eval()

    if args.eval in ("all", "attribution", "mosaic"):
        results["attribution_mosaic"] = _run_source_attribution_eval()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if "mnpi" in results:
        print(f"  MNPI Gate Accuracy:       {results['mnpi']['accuracy']:.1%}")
    if "attribution_mosaic" in results:
        am = results["attribution_mosaic"]
        print(f"  Source Attribution Score:  {am['source_attribution']['score']}")
        print(f"  Mosaic Completeness:      {am['mosaic']['score']:.1%}")

    print()


if __name__ == "__main__":
    main()
