"""Query Analyzer + Semantic Cache.

Two stages:
  1. Cache check: exact query string match against query_cache table
  2. LLM analysis: classify intent, extract filters, generate reformulations

Handles off-topic rejection (is_investment_query=False).
"""

import json
from typing import Optional

from iteration2.prompts import QUERY_ANALYZER_PROMPT
from iteration2.state import QueryIntent, OnlinePipelineState
from iteration2 import storage as iter2_storage

GUIDANCE_TOPICS = [
    "Financial Outlook",
    "Capacity Expansion",
    "Operational Efficiency",
    "Capital Allocation",
    "Strategic Initiatives",
    "Market & Competition",
    "Regulatory & Risk",
]


def check_cache(state: OnlinePipelineState) -> dict:
    """LangGraph node: check semantic cache for exact query match."""
    company = state["company"]
    query = state["query"]

    conn = iter2_storage.get_connection(company)
    result = iter2_storage.cache_lookup(conn, company, query)
    conn.close()

    if result:
        return {
            "cache_hit": True,
            "cached_answer": result["answer"],
        }

    return {
        "cache_hit": False,
        "cached_answer": None,
    }


def analyze_query(state: OnlinePipelineState, llm) -> dict:
    """LangGraph node: LLM-based query analysis."""
    if state.get("cache_hit"):
        return {}

    structured_llm = llm.with_structured_output(QueryIntent)
    chain = QUERY_ANALYZER_PROMPT | structured_llm

    taxonomy_terms = "\n".join(f"  - {t}" for t in GUIDANCE_TOPICS)

    intent = chain.invoke({
        "company": state["company"],
        "query": state["query"],
        "taxonomy_terms": taxonomy_terms,
    })

    return {"query_intent": intent}
