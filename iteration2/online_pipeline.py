"""Online Research Query Pipeline (LangGraph).

Flow:
  check_cache → [HIT?] → return cached
                [MISS] → analyze_query → [investment?]:
                  [NO]  → empty response with rejection
                  [YES] → retrieve + text_to_sql (parallel)
                       → mnpi_2nd_screen → corrective_rag
                       → enrich_context → synthesize → detect_divergence
                       → cache_store → return
"""

import json
from functools import partial

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END

from iteration2.state import OnlinePipelineState, ResearchAnswer
from iteration2.nodes.query_analyzer import check_cache, analyze_query
from iteration2.nodes.retriever import retrieve
from iteration2.nodes.text_to_sql import text_to_sql
from iteration2.nodes.quality_gates import post_retrieval_mnpi_screen, corrective_rag
from iteration2.nodes.synthesizer import enrich_context, synthesize, detect_divergence
from iteration2 import storage as iter2_storage


def _route_after_cache(state: OnlinePipelineState) -> str:
    """Route based on cache hit."""
    if state.get("cache_hit"):
        return "synthesize"
    return "analyze_query"


def _route_after_analysis(state: OnlinePipelineState) -> str:
    """Route based on query analysis."""
    intent = state.get("query_intent")
    if intent and not intent.is_investment_query:
        return "synthesize"
    return "retrieve"


def _cache_store_node(state: OnlinePipelineState) -> dict:
    """Store the answer in the cache."""
    answer = state.get("answer")
    if not answer or state.get("cache_hit"):
        return {}

    try:
        company = state["company"]
        conn = iter2_storage.get_connection(company)
        answer_json = answer.model_dump_json() if hasattr(answer, "model_dump_json") else json.dumps(answer.__dict__)
        iter2_storage.cache_store(conn, company, state["query"], answer_json)
        conn.close()
    except Exception:
        pass

    return {}


def build_online_pipeline(model_name: str = "gpt-4o-mini") -> StateGraph:
    """Build the online research query pipeline."""
    load_dotenv(find_dotenv())

    llm = init_chat_model(model_name, model_provider="openai")

    graph = StateGraph(OnlinePipelineState)

    graph.add_node("check_cache", check_cache)
    graph.add_node("analyze_query", partial(analyze_query, llm=llm))
    graph.add_node("retrieve", retrieve)
    graph.add_node("text_to_sql", partial(text_to_sql, llm=llm))
    graph.add_node("mnpi_screen", post_retrieval_mnpi_screen)
    graph.add_node("corrective_rag", partial(corrective_rag, llm=llm))
    graph.add_node("enrich_context", enrich_context)
    graph.add_node("synthesize", partial(synthesize, llm=llm))
    graph.add_node("detect_divergence", partial(detect_divergence, llm=llm))
    graph.add_node("cache_store", _cache_store_node)

    graph.set_entry_point("check_cache")

    graph.add_conditional_edges(
        "check_cache",
        _route_after_cache,
        {"synthesize": "synthesize", "analyze_query": "analyze_query"},
    )

    graph.add_conditional_edges(
        "analyze_query",
        _route_after_analysis,
        {"synthesize": "synthesize", "retrieve": "retrieve"},
    )

    graph.add_edge("retrieve", "text_to_sql")
    graph.add_edge("text_to_sql", "mnpi_screen")
    graph.add_edge("mnpi_screen", "corrective_rag")
    graph.add_edge("corrective_rag", "enrich_context")
    graph.add_edge("enrich_context", "synthesize")
    graph.add_edge("synthesize", "detect_divergence")
    graph.add_edge("detect_divergence", "cache_store")
    graph.add_edge("cache_store", END)

    return graph.compile()
