"""Post-Retrieval Quality Gates.

Two gates applied after vector retrieval and before synthesis:

1. MNPI 2nd Screen: Re-scan retrieved chunks for MNPI content
   (catches content that slipped past ingestion screening)

2. Corrective RAG: LLM judges each chunk as RELEVANT/TANGENTIAL/IRRELEVANT.
   Only RELEVANT chunks pass through to synthesis.
"""

from iteration2.mnpi_gate import screen_for_mnpi
from iteration2.prompts import CORRECTIVE_RAG_PROMPT
from iteration2.state import OnlinePipelineState, RetrievedChunk


def post_retrieval_mnpi_screen(state: OnlinePipelineState) -> dict:
    """LangGraph node: re-screen retrieved chunks for MNPI content."""
    if state.get("cache_hit"):
        return {}

    chunks = state.get("retrieved_chunks") or []
    sql_results = state.get("sql_results") or []
    all_chunks = chunks + [c for c in sql_results if c.relevance_score > 0]

    blocked = []
    passed = []

    for chunk in all_chunks:
        result = screen_for_mnpi(chunk.text, chunk.file_name)
        if result.is_mnpi:
            blocked.append(chunk.file_name)
        else:
            passed.append(chunk)

    return {
        "mnpi_blocked_chunks": blocked,
        "filtered_chunks": passed,
    }


def corrective_rag(state: OnlinePipelineState, llm) -> dict:
    """LangGraph node: LLM judges chunk relevance.

    Filters out IRRELEVANT chunks before synthesis.
    TANGENTIAL chunks are kept but deprioritized.
    """
    if state.get("cache_hit"):
        return {}

    chunks = state.get("filtered_chunks") or []
    if not chunks:
        return {"filtered_chunks": []}

    query = state["query"]
    chain = CORRECTIVE_RAG_PROMPT | llm

    relevant_chunks = []
    for chunk in chunks[:15]:
        try:
            result = chain.invoke({
                "query": query,
                "source_type": chunk.source_type,
                "doc_type": chunk.doc_type,
                "file_name": chunk.file_name,
                "chunk_text": chunk.text[:2000],
            })

            label = result.content.strip().split("\n")[0].strip().upper()

            if "RELEVANT" in label and "IRRELEVANT" not in label:
                chunk.relevance_label = "RELEVANT"
                relevant_chunks.append(chunk)
            elif "TANGENTIAL" in label:
                chunk.relevance_label = "TANGENTIAL"
                chunk.relevance_score *= 0.5
                relevant_chunks.append(chunk)
        except Exception:
            relevant_chunks.append(chunk)

    relevant_chunks.sort(key=lambda c: c.relevance_score, reverse=True)

    return {"filtered_chunks": relevant_chunks}
