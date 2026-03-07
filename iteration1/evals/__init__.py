"""Evaluation harness for the Earnings Intelligence Pipeline.

Modules:
  code_evals        — 7 objective, code-based eval functions (2 with ground truth, 5 ground-truth-free)
  llm_judge_evals   — 5 subjective, LLM-as-judge eval functions
  runner            — CLI entry point for running eval suites
  arize_experiment  — Arize Cloud experiment runner with 10 evaluators
"""
