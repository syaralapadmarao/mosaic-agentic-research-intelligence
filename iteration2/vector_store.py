"""3-Namespace ChromaDB Vector Store with OpenAI Embeddings.

Namespaces:
  A: DISCLOSURE — transcripts, presentations (authoritative, lagging, 90d)
  B: OPINION — sell-side reports, broker emails (forward-looking, biased, 60d)
  C: FIELD_DATA — visit notes (highest alpha, highest MNPI risk, 90d)

Each namespace is a separate ChromaDB collection per company.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from iteration2.state import (
    NAMESPACE_DISCLOSURE, NAMESPACE_OPINION, NAMESPACE_FIELD_DATA,
    FRESHNESS_THRESHOLDS_DAYS, RetrievedChunk,
)

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "data", "chroma")
NAMESPACES = [NAMESPACE_DISCLOSURE, NAMESPACE_OPINION, NAMESPACE_FIELD_DATA]


def _get_client() -> chromadb.PersistentClient:
    """Get a persistent ChromaDB client."""
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_embedding_fn() -> OpenAIEmbeddingFunction:
    """Get OpenAI embedding function for ChromaDB."""
    return OpenAIEmbeddingFunction(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model_name="text-embedding-3-small",
    )


def _collection_name(company: str, namespace: str) -> str:
    """Build a collection name: e.g. 'max_disclosure'."""
    safe = company.lower().replace(" ", "_").replace("-", "_")
    return f"{safe}_{namespace}"


def get_collection(company: str, namespace: str):
    """Get or create a ChromaDB collection for a company+namespace."""
    client = _get_client()
    return client.get_or_create_collection(
        name=_collection_name(company, namespace),
        embedding_function=_get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def embed_and_store(company: str, namespace: str, chunks: list[dict]) -> int:
    """Embed and store chunks into the specified namespace collection.

    Args:
        company: Company name.
        namespace: 'disclosure', 'opinion', or 'field_data'.
        chunks: List of chunk dicts with 'text' and 'metadata' fields.

    Returns:
        Number of chunks stored.
    """
    if not chunks:
        return 0

    collection = get_collection(company, namespace)

    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        if not text.strip():
            continue

        chunk_id = f"{company}_{namespace}_{chunk.get('metadata', {}).get('file_name', 'unknown')}_{i}"
        metadata = {}
        for k, v in chunk.get("metadata", {}).items():
            if v is not None and isinstance(v, (str, int, float, bool)):
                metadata[k] = v
            elif isinstance(v, list):
                metadata[k] = str(v)

        ids.append(chunk_id)
        documents.append(text)
        metadatas.append(metadata)

    if not ids:
        return 0

    batch_size = 100
    total = 0
    for start in range(0, len(ids), batch_size):
        end = min(start + batch_size, len(ids))
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        total += end - start

    return total


def delete_company(company: str) -> None:
    """Delete all collections for a company (for re-ingestion)."""
    client = _get_client()
    for ns in NAMESPACES:
        name = _collection_name(company, ns)
        try:
            client.delete_collection(name)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def search(company: str, query: str, namespaces: list[str] = None,
           k: int = 10, metadata_filters: dict = None) -> list[RetrievedChunk]:
    """Search across specified namespaces for a company.

    Args:
        company: Company name.
        query: Search query text.
        namespaces: List of namespaces to search. Defaults to all three.
        k: Number of results per namespace.
        metadata_filters: ChromaDB where clause dict.

    Returns:
        List of RetrievedChunk objects, sorted by relevance_score descending.
    """
    if namespaces is None:
        namespaces = NAMESPACES

    all_chunks: list[RetrievedChunk] = []

    for ns in namespaces:
        try:
            collection = get_collection(company, ns)
            query_kwargs: dict = {"query_texts": [query], "n_results": k}

            if metadata_filters:
                where = {}
                for key, val in metadata_filters.items():
                    if val is not None:
                        where[key] = val
                if where:
                    query_kwargs["where"] = where

            results = collection.query(**query_kwargs)

            if not results or not results.get("documents"):
                continue

            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            distances = results["distances"][0] if results.get("distances") else [1.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, distances):
                relevance = max(0.0, 1.0 - dist)

                doc_date = meta.get("date", "")
                freshness_days = 0
                is_stale = False
                if doc_date:
                    freshness_days = _compute_freshness_days(doc_date)
                    threshold = FRESHNESS_THRESHOLDS_DAYS.get(ns, 90)
                    is_stale = freshness_days > threshold

                all_chunks.append(RetrievedChunk(
                    text=doc,
                    source_type=ns,
                    doc_type=meta.get("doc_type", "unknown"),
                    company=company,
                    file_name=meta.get("file_name", "unknown"),
                    section=meta.get("section"),
                    date=doc_date,
                    broker_name=meta.get("broker_name"),
                    relevance_score=relevance,
                    is_stale=is_stale,
                    freshness_days=freshness_days,
                ))

        except Exception:
            continue

    all_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
    return all_chunks


def _compute_freshness_days(date_str: str) -> int:
    """Compute days since the document date."""
    date_formats = ["%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"]
    for fmt in date_formats:
        try:
            doc_date = datetime.strptime(date_str, fmt)
            return (datetime.now() - doc_date).days
        except ValueError:
            continue
    return 0


def get_collection_stats(company: str) -> dict:
    """Get document counts per namespace for a company."""
    stats = {}
    for ns in NAMESPACES:
        try:
            collection = get_collection(company, ns)
            stats[ns] = collection.count()
        except Exception:
            stats[ns] = 0
    return stats
