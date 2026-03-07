"""Retrieval Node — Multi-namespace semantic search.

Searches across DISCLOSURE, OPINION, and FIELD_DATA namespaces
with metadata filters extracted by the query analyzer.
Uses original query + reformulations for broader recall.
"""

from iteration2.state import OnlinePipelineState, RetrievedChunk
from iteration2 import vector_store


def retrieve(state: OnlinePipelineState) -> dict:
    """LangGraph node: retrieve relevant chunks from ChromaDB."""
    if state.get("cache_hit"):
        return {}

    company = state["company"]
    intent = state.get("query_intent")

    if intent and not intent.is_investment_query:
        return {"retrieved_chunks": []}

    queries = [state["query"]]
    if intent and intent.reformulations:
        queries.extend(intent.reformulations)

    all_chunks: list[RetrievedChunk] = []
    seen_texts: set = set()

    for query in queries:
        results = vector_store.search(
            company=company,
            query=query,
            k=5,
        )
        for chunk in results:
            key = chunk.text[:100]
            if key not in seen_texts:
                seen_texts.add(key)
                all_chunks.append(chunk)

    all_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
    all_chunks = all_chunks[:20]

    return {"retrieved_chunks": all_chunks}
