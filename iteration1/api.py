"""FastAPI backend for the Earnings Intelligence Dashboard.

Wraps the existing pipeline and storage layer, exposing JSON endpoints
that the React frontend consumes.
"""

import os
import glob
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from iteration1.main import run_single, _infer_quarter
from iteration1.pipeline import load_schema
from iteration1 import storage
from iteration1.state import (
    SENTIMENT_ARROWS, SENTIMENT_COLORS, SENTIMENT_LEVELS,
)

SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "sample_docs")
SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "schemas")

_pipeline_status: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Earnings Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Discovery endpoints ─────────────────────────────────────────────────

@app.get("/api/companies")
def list_companies() -> list[dict]:
    """Return available companies with metadata from DB if available."""
    if not os.path.isdir(SAMPLE_DOCS_DIR):
        return []
    companies = []
    for name in sorted(os.listdir(SAMPLE_DOCS_DIR)):
        path = os.path.join(SAMPLE_DOCS_DIR, name)
        if not os.path.isdir(path) or name.startswith("."):
            continue
        pdfs = glob.glob(os.path.join(path, "**", "*.pdf"), recursive=True)
        info = {"name": name, "pdf_count": len(pdfs), "quarters_loaded": 0, "last_quarter": None, "topic_count": 0}
        try:
            conn = storage.get_connection(name)
            qs = storage.list_quarters(conn, name)
            info["quarters_loaded"] = len(qs)
            info["last_quarter"] = qs[-1] if qs else None
            topics = conn.execute(
                "SELECT COUNT(DISTINCT topic) as cnt FROM guidance WHERE company=?", (name,)
            ).fetchone()
            info["topic_count"] = topics["cnt"] if topics else 0
            conn.close()
        except Exception:
            pass
        companies.append(info)
    return companies


@app.get("/api/schemas")
def list_schemas() -> list[dict]:
    """Return available metric schemas."""
    if not os.path.isdir(SCHEMAS_DIR):
        return []
    schemas = []
    for f in sorted(os.listdir(SCHEMAS_DIR)):
        if f.endswith(".json"):
            key = f.replace(".json", "")
            schema = load_schema(key)
            schemas.append({
                "key": key,
                "sector": schema.sector or "",
                "metric_count": len(schema.metrics),
            })
    return schemas


# ── Data endpoints ───────────────────────────────────────────────────────

@app.get("/api/metrics/{company}")
def get_metrics(company: str) -> dict:
    """Return the rolling metrics table for a company."""
    try:
        conn = storage.get_connection(company)
        table = storage.get_metrics_table(conn, company)

        metrics_with_changes = {}
        quarters = table.get("quarters", [])
        for name, data in table.get("metrics", {}).items():
            values = data.get("values", {})
            changes = {}
            for i, q in enumerate(quarters):
                if i == 0 or q not in values:
                    changes[q] = None
                    continue
                prev_q = quarters[i - 1]
                prev_v = values.get(prev_q)
                curr_v = values.get(q)
                if prev_v and curr_v and prev_v != 0:
                    pct = ((curr_v - prev_v) / abs(prev_v)) * 100
                    changes[q] = round(pct, 1)
                else:
                    changes[q] = None
            metrics_with_changes[name] = {
                "unit": data.get("unit", ""),
                "values": values,
                "changes": changes,
            }

        conn.close()
        return {"quarters": quarters, "metrics": metrics_with_changes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/citations/{company}")
def get_citations(company: str) -> dict:
    """Return all citations grouped by quarter and metric."""
    try:
        conn = storage.get_connection(company)
        quarters = storage.list_quarters(conn, company)
        result = {}
        for q in quarters:
            result[q] = storage.get_citations_for_quarter(conn, company, q)
        conn.close()
        return {"quarters": quarters, "citations": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/guidance/{company}")
def get_guidance(company: str) -> dict:
    """Return the guidance tracker table (topics x quarters)."""
    try:
        conn = storage.get_connection(company)
        table = storage.get_guidance_table(conn, company)
        conn.close()
        return table
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/deltas/{company}")
def get_deltas(company: str) -> dict:
    """Return all guidance deltas across quarters."""
    try:
        conn = storage.get_connection(company)
        g_quarters = [r["quarter"] for r in conn.execute(
            "SELECT DISTINCT quarter FROM guidance WHERE company=? ORDER BY quarter",
            (company,)
        ).fetchall()]

        all_deltas = {}
        for q in g_quarters:
            deltas = storage.get_deltas_for_quarter(conn, company, q)
            if deltas:
                all_deltas[q] = deltas
        conn.close()
        return {"quarters": g_quarters, "deltas": all_deltas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pipeline execution ───────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    company: str
    schema_key: str


def _run_pipeline_sync(company: str, schema_key: str):
    """Run the pipeline synchronously (called from background task)."""
    _pipeline_status[company] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "current_file": "",
        "errors": [],
        "pres_count": 0,
        "trans_count": 0,
    }

    pattern = os.path.join(SAMPLE_DOCS_DIR, company, "**", "*.pdf")
    pdfs = sorted(glob.glob(pattern, recursive=True))

    if not pdfs:
        _pipeline_status[company] = {
            "status": "error",
            "message": f"No PDFs found for '{company}'",
        }
        return

    _pipeline_status[company]["total"] = len(pdfs)

    for i, pdf_path in enumerate(pdfs):
        file_name = os.path.basename(pdf_path)
        quarter = _infer_quarter(file_name)

        _pipeline_status[company]["progress"] = i
        _pipeline_status[company]["current_file"] = file_name

        if not quarter:
            _pipeline_status[company]["errors"].append(
                f"Skipped {file_name} — cannot infer quarter"
            )
            continue

        try:
            state = run_single(
                pdf_path, schema_key, quarter, company_name=company,
            )
            if state.get("metrics_table"):
                _pipeline_status[company]["pres_count"] += 1
            if state.get("guidance_table"):
                _pipeline_status[company]["trans_count"] += 1
        except Exception as e:
            _pipeline_status[company]["errors"].append(
                f"Error on {file_name}: {str(e)}"
            )

    status = _pipeline_status[company]
    status["status"] = "complete"
    status["progress"] = len(pdfs)
    status["message"] = (
        f"Processed {len(pdfs)} PDFs: "
        f"{status['pres_count']} presentations, "
        f"{status['trans_count']} transcripts."
    )


@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    """Start pipeline processing for a company (runs in background)."""
    if _pipeline_status.get(req.company, {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running for this company")

    background_tasks.add_task(_run_pipeline_sync, req.company, req.schema_key)
    return {"status": "started", "company": req.company}


@app.get("/api/pipeline/status/{company}")
def pipeline_status(company: str) -> dict:
    """Poll pipeline progress."""
    return _pipeline_status.get(company, {"status": "idle"})


# ── PDF serving ──────────────────────────────────────────────────────────

@app.get("/api/pdf/{company}/{path:path}")
def serve_pdf(company: str, path: str):
    """Serve a PDF file for citation deep-linking."""
    full_path = os.path.join(SAMPLE_DOCS_DIR, company, path)
    if not os.path.isfile(full_path):
        basename = os.path.basename(path)
        matches = glob.glob(os.path.join(SAMPLE_DOCS_DIR, company, "**", basename), recursive=True)
        if matches:
            full_path = matches[0]
        else:
            raise HTTPException(status_code=404, detail=f"PDF not found: {path}")
    return FileResponse(full_path, media_type="application/pdf")


# ── Reference data ───────────────────────────────────────────────────────

@app.get("/api/sentiment-config")
def sentiment_config():
    """Return sentiment display configuration."""
    return {
        "levels": SENTIMENT_LEVELS,
        "arrows": SENTIMENT_ARROWS,
        "colors": SENTIMENT_COLORS,
    }
