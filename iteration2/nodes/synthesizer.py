"""Pre-synthesis Enrichment + LLM Synthesis + Consensus Divergence.

Three stages:
1. Enrich: Add mosaic completeness, stale warnings, live price context
2. Synthesize: LLM generates answer with inline source badges
3. Divergence: Detect and flag consensus disagreements
"""

import json
from typing import Optional

from iteration2.prompts import SYNTHESIS_PROMPT
from iteration2.state import (
    OnlinePipelineState, RetrievedChunk, ResearchAnswer,
    MosaicCompleteness, ConsensusDivergence, SourceBadge,
    NAMESPACE_DISCLOSURE, NAMESPACE_OPINION, NAMESPACE_FIELD_DATA,
    FRESHNESS_THRESHOLDS_DAYS,
)
from iteration2.financial_api import resolve_ticker, get_live_price
from iteration2 import storage as iter2_storage


def enrich_context(state: OnlinePipelineState) -> dict:
    """LangGraph node: add mosaic completeness and stale warnings."""
    if state.get("cache_hit"):
        return {}

    chunks = state.get("filtered_chunks") or []

    source_types = set(c.source_type for c in chunks)
    missing = []
    for ns in [NAMESPACE_DISCLOSURE, NAMESPACE_OPINION, NAMESPACE_FIELD_DATA]:
        if ns not in source_types:
            missing.append(ns)

    score = len(source_types) / 3.0

    mosaic = MosaicCompleteness(
        disclosure_present=NAMESPACE_DISCLOSURE in source_types,
        opinion_present=NAMESPACE_OPINION in source_types,
        field_data_present=NAMESPACE_FIELD_DATA in source_types,
        missing_types=missing,
        completeness_score=score,
    )

    stale_chunks = [c for c in chunks if c.is_stale]

    ticker = resolve_ticker(state["company"])
    price_context = ""
    if ticker:
        price_data = get_live_price(ticker)
        if price_data.get("status") == "ok":
            d = price_data["data"]
            price_context = (
                f"\n[LIVE DATA] {ticker}: CMP ₹{d['cmp']}, "
                f"Day Change: {d['day_change_pct']:+.1f}%, "
                f"Market Cap: ₹{d['market_cap_cr']:,} Cr"
            )

    enriched = list(chunks)
    if price_context:
        enriched.insert(0, RetrievedChunk(
            text=price_context,
            source_type="disclosure",
            doc_type="live_data",
            company=state["company"],
            file_name="financial_api",
            relevance_score=1.0,
        ))

    return {
        "enriched_chunks": enriched,
        "mosaic": mosaic,
    }


def synthesize(state: OnlinePipelineState, llm) -> dict:
    """LangGraph node: LLM synthesis with source attribution."""
    if state.get("cache_hit"):
        cached = state.get("cached_answer")
        if isinstance(cached, dict):
            cached["cached"] = True
            return {"answer": ResearchAnswer(**cached)}
        return {"answer": cached}

    chunks = state.get("enriched_chunks") or state.get("filtered_chunks") or []

    if not chunks:
        intent = state.get("query_intent")
        if intent and not intent.is_investment_query:
            return {"answer": ResearchAnswer(
                answer=f"I can only help with investment research queries. {intent.rejection_reason or ''}",
                response_state="MNPI Block",
            )}
        return {"answer": ResearchAnswer(
            answer="No relevant information found for this query. Try broadening your search or ingesting more documents.",
            response_state="No Results",
        )}

    context_parts = []
    for i, chunk in enumerate(chunks):
        stale_tag = " [STALE]" if chunk.is_stale else ""
        context_parts.append(
            f"[Source {i+1}] ({chunk.source_type}/{chunk.doc_type}) "
            f"File: {chunk.file_name}{stale_tag}\n{chunk.text}"
        )
    context = "\n\n---\n\n".join(context_parts)

    chain = SYNTHESIS_PROMPT | llm
    result = chain.invoke({
        "company": state["company"],
        "query": state["query"],
        "context": context[:25000],
    })

    answer_text = result.content

    source_badges = []
    for i, chunk in enumerate(chunks):
        if chunk.doc_type != "live_data":
            source_badges.append(SourceBadge(
                claim_index=i,
                source_type=chunk.source_type,
                doc_ref=chunk.file_name,
                date=chunk.date,
                broker_name=chunk.broker_name,
            ))

    mosaic = state.get("mosaic", MosaicCompleteness())
    stale_warnings = [
        {"file": c.file_name, "age_days": c.freshness_days, "source_type": c.source_type}
        for c in chunks if c.is_stale
    ]

    response_state = "Normal"
    if any(c.is_stale for c in chunks):
        response_state = "Stale"

    return {"answer": ResearchAnswer(
        answer=answer_text,
        source_badges=source_badges,
        mosaic=mosaic,
        stale_warnings=stale_warnings,
        response_state=response_state,
    )}


def detect_divergence(state: OnlinePipelineState, llm) -> dict:
    """LangGraph node: detect consensus divergences in the answer."""
    if state.get("cache_hit"):
        return {}

    answer = state.get("answer")
    if not answer:
        return {}

    chunks = state.get("enriched_chunks") or state.get("filtered_chunks") or []
    opinion_chunks = [c for c in chunks if c.source_type == NAMESPACE_OPINION]

    if len(opinion_chunks) < 2:
        return {}

    firms = {}
    for chunk in opinion_chunks:
        firm = chunk.broker_name or chunk.file_name
        if firm not in firms:
            firms[firm] = []
        firms[firm].append(chunk.text[:500])

    if len(firms) < 2:
        return {}

    firm_names = list(firms.keys())
    firm_views = "\n\n".join(
        f"**{name}:** {' '.join(texts[:2])}" for name, texts in firms.items()
    )

    from langchain_core.prompts import ChatPromptTemplate
    divergence_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert at detecting consensus divergence among sell-side analysts.

Given views from multiple firms, identify any metrics or topics where they DISAGREE.
Only flag genuine disagreements (bullish vs bearish, materially different estimates).
Do NOT flag minor differences or different emphasis on the same view.

For each divergence found, output JSON:
{{"divergences": [{{"metric_or_topic": "...", "view_a": "Firm A (Rating): view...", "view_b": "Firm B (Rating): view...", "divergence_summary": "brief explanation"}}]}}

If no divergences, output: {{"divergences": []}}"""),
        ("user", """Firm views on {company}:

{firm_views}"""),
    ])

    try:
        chain = divergence_prompt | llm
        result = chain.invoke({
            "company": state["company"],
            "firm_views": firm_views,
        })

        import re
        json_match = re.search(r'\{[\s\S]*\}', result.content)
        if json_match:
            data = json.loads(json_match.group())
            divergences = [
                ConsensusDivergence(
                    metric_or_topic=d.get("metric_or_topic", ""),
                    sources_agree=False,
                    view_a=d.get("view_a", ""),
                    view_b=d.get("view_b", ""),
                    divergence_summary=d.get("divergence_summary", ""),
                )
                for d in data.get("divergences", [])
            ]

            if divergences:
                answer.divergences = divergences
                answer.response_state = "Consensus Divergence"

                conn = iter2_storage.get_connection(state["company"])
                for div in divergences:
                    iter2_storage.save_consensus_divergence(
                        conn, state["company"], "",
                        div.metric_or_topic, False,
                        div.view_a, div.view_b, div.divergence_summary,
                    )
                conn.close()

            return {"answer": answer}

    except Exception:
        pass

    return {}
