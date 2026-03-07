"""FastAPI backend for the Multi-Source Research Assistant.

Endpoints:
  POST /api/research/query     — Run the online research pipeline
  POST /api/research/ingest    — Ingest documents via the offline pipeline
  GET  /api/research/sources   — List ingested sources for a company
  GET  /api/research/consensus — Get consensus estimates
  GET  /api/research/cache     — Get cache statistics
  GET  /api/research/mnpi-audit — Get MNPI screening audit log
  GET  /api/research/stats     — Vector store statistics

Also re-exports iteration1 endpoints for the dashboard.
"""

import os
import glob
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from iteration1 import api as iter1_api

from iteration2.pipeline import build_offline_pipeline, _load_schema
from iteration2.online_pipeline import build_online_pipeline
from iteration2.state import ResearchAnswer
from iteration2 import storage as iter2_storage
from iteration2 import vector_store
from iteration2.financial_api import (
    get_live_price, get_consensus_estimates as api_consensus,
    get_peer_comparison, resolve_ticker,
)

SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")
ITER1_SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "iteration1", "sample_docs")

_offline_pipeline = None
_online_pipeline = None
_ingest_status: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _offline_pipeline, _online_pipeline
    _offline_pipeline = build_offline_pipeline()
    _online_pipeline = build_online_pipeline()
    yield

app = FastAPI(title="Multi-Source Research Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    company: str
    query: str


class IngestRequest(BaseModel):
    company: str
    file_paths: list[str] = []


# ── Research Query endpoint ────────────────────────────────────────────────

@app.post("/api/research/query")
async def research_query(req: QueryRequest):
    """Run the online research pipeline."""
    global _online_pipeline
    if _online_pipeline is None:
        _online_pipeline = build_online_pipeline()

    initial_state = {
        "query": req.query,
        "company": req.company,
        "cache_hit": False,
        "cached_answer": None,
        "query_intent": None,
        "retrieved_chunks": None,
        "sql_results": None,
        "mnpi_blocked_chunks": None,
        "filtered_chunks": None,
        "enriched_chunks": None,
        "mosaic": None,
        "answer": None,
    }

    result = await asyncio.to_thread(_online_pipeline.invoke, initial_state)

    answer = result.get("answer")
    if answer is None:
        raise HTTPException(status_code=500, detail="Pipeline returned no answer")

    if isinstance(answer, ResearchAnswer):
        return answer.model_dump()
    elif isinstance(answer, dict):
        return answer
    else:
        return {"answer": str(answer)}


# ── Ingestion endpoints ───────────────────────────────────────────────────

def _run_ingest(company: str, file_paths: list[str]):
    """Run offline ingestion synchronously (background task)."""
    global _offline_pipeline
    if _offline_pipeline is None:
        _offline_pipeline = build_offline_pipeline()

    vector_store.delete_company(company)

    _ingest_status[company] = {
        "status": "running", "progress": 0, "total": len(file_paths),
        "current_file": "", "errors": [], "ingested": 0,
    }

    from iteration1.main import _infer_quarter
    schema = _load_schema(company)

    for i, fp in enumerate(file_paths):
        file_name = os.path.basename(fp)
        _ingest_status[company]["progress"] = i
        _ingest_status[company]["current_file"] = file_name

        quarter = _infer_quarter(file_name) or "unknown"

        try:
            initial_state = {
                "raw_text": "",
                "file_name": file_name,
                "file_path": fp,
                "pdf_path": fp,
                "company": company,
                "quarter": quarter,
                "mnpi_result": None,
                "scrubbed_text": None,
                "classification": None,
                "route": None,
                "source_type": None,
                "metric_schema": schema,
                "page_tagged_text": None,
                "extracted_metrics": None,
                "calculated_metrics": None,
                "validation": None,
                "metrics_table": None,
                "guidance_items": None,
                "guidance_deltas": None,
                "guidance_table": None,
                "sell_side_report": None,
                "visit_note_extraction": None,
                "source_document": None,
                "chunks": None,
            }
            _offline_pipeline.invoke(initial_state)
            _ingest_status[company]["ingested"] += 1
        except Exception as e:
            _ingest_status[company]["errors"].append(f"{file_name}: {str(e)}")

    status = _ingest_status[company]
    status["status"] = "complete"
    status["progress"] = len(file_paths)

    conn = iter2_storage.get_connection(company)
    iter2_storage.invalidate_cache(conn, company)
    conn.close()


@app.post("/api/research/ingest")
def ingest_documents(req: IngestRequest, background_tasks: BackgroundTasks):
    """Start document ingestion for a company."""
    if _ingest_status.get(req.company, {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="Ingestion already running")

    file_paths = req.file_paths
    if not file_paths:
        for docs_dir in [SAMPLE_DOCS_DIR, ITER1_SAMPLE_DOCS_DIR]:
            company_dir = os.path.join(docs_dir, req.company)
            if os.path.isdir(company_dir):
                for ext in ("*.pdf", "*.md"):
                    file_paths.extend(
                        glob.glob(os.path.join(company_dir, "**", ext), recursive=True)
                    )
        file_paths = sorted(set(file_paths))

    if not file_paths:
        raise HTTPException(status_code=404, detail=f"No documents found for '{req.company}'")

    background_tasks.add_task(_run_ingest, req.company, file_paths)
    return {"status": "started", "company": req.company, "file_count": len(file_paths)}


@app.get("/api/research/ingest/status/{company}")
def ingest_status(company: str) -> dict:
    """Poll ingestion progress."""
    return _ingest_status.get(company, {"status": "idle"})


# ── Data endpoints ──────────────────────────────────────────────────────────

@app.get("/api/research/sources/{company}")
def get_sources(company: str, source_type: Optional[str] = None):
    """List ingested source documents."""
    conn = iter2_storage.get_connection(company)
    sources = iter2_storage.get_sources(conn, company, source_type)
    conn.close()
    return {"sources": sources}


@app.get("/api/research/consensus/{company}")
def get_consensus(company: str, period: Optional[str] = None):
    """Get aggregated consensus estimates from sell-side analysts."""
    conn = iter2_storage.get_connection(company)
    consensus = iter2_storage.get_consensus_estimates(conn, company, period)
    conn.close()
    return {"consensus": consensus}


@app.get("/api/research/insights/{company}")
def get_insights(company: str, topic: Optional[str] = None):
    """Get visit note insights."""
    conn = iter2_storage.get_connection(company)
    insights = iter2_storage.get_visit_insights(conn, company, topic)
    conn.close()
    return {"insights": insights}


@app.get("/api/research/divergences/{company}")
def get_divergences(company: str):
    """Get consensus divergence records."""
    conn = iter2_storage.get_connection(company)
    divergences = iter2_storage.get_consensus_divergences(conn, company)
    conn.close()
    return {"divergences": divergences}


@app.get("/api/research/cache/{company}")
def get_cache_stats(company: str):
    """Get cache statistics."""
    conn = iter2_storage.get_connection(company)
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM query_cache WHERE company=?", (company,)
    ).fetchone()["cnt"]
    active = conn.execute(
        "SELECT COUNT(*) as cnt FROM query_cache WHERE company=? AND invalidated_at IS NULL",
        (company,)
    ).fetchone()["cnt"]
    conn.close()
    return {"total_entries": total, "active_entries": active}


@app.get("/api/research/mnpi-audit")
def get_mnpi_audit(company: Optional[str] = None):
    """Get MNPI screening audit log."""
    if company:
        conn = iter2_storage.get_connection(company)
    else:
        conn = iter2_storage.get_connection("_audit")
    audit = iter2_storage.get_mnpi_audit_log(conn, company)
    conn.close()
    return {"audit": audit}


@app.get("/api/research/stats/{company}")
def get_stats(company: str):
    """Get vector store statistics per namespace."""
    stats = vector_store.get_collection_stats(company)
    return {"namespaces": stats}


# ── Financial API (MCP Stub) ─────────────────────────────────────────────

@app.get("/api/finance/price/{company}")
def get_price(company: str):
    """Get mock live price data."""
    ticker = resolve_ticker(company)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"No ticker for '{company}'")
    return get_live_price(ticker)


@app.get("/api/finance/consensus/{company}")
def get_finance_consensus(company: str):
    """Get consensus estimates from MCP stub."""
    return api_consensus(company)


@app.get("/api/finance/peers/{company}")
def get_peers(company: str):
    """Get peer comparison from MCP stub."""
    ticker = resolve_ticker(company)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"No ticker for '{company}'")
    return get_peer_comparison(ticker)


# ── Include iteration1 endpoints ──────────────────────────────────────────

from iteration1.api import (
    list_companies, list_schemas, get_metrics, get_citations,
    get_guidance, get_deltas, run_pipeline, pipeline_status,
    serve_pdf, sentiment_config,
)

app.add_api_route("/api/companies", list_companies, methods=["GET"])
app.add_api_route("/api/schemas", list_schemas, methods=["GET"])
app.add_api_route("/api/metrics/{company}", get_metrics, methods=["GET"])
app.add_api_route("/api/citations/{company}", get_citations, methods=["GET"])
app.add_api_route("/api/guidance/{company}", get_guidance, methods=["GET"])
app.add_api_route("/api/deltas/{company}", get_deltas, methods=["GET"])
app.add_api_route("/api/pipeline/run", run_pipeline, methods=["POST"])
app.add_api_route("/api/pipeline/status/{company}", pipeline_status, methods=["GET"])
app.add_api_route("/api/pdf/{company}/{path:path}", serve_pdf, methods=["GET"])
app.add_api_route("/api/sentiment-config", sentiment_config, methods=["GET"])
