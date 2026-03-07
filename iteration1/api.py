"""FastAPI backend for the Earnings Intelligence Dashboard.

Wraps the existing pipeline and storage layer, exposing JSON endpoints
that the React frontend consumes.
"""

import os
import re
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
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


def _count_pages(page_tagged_text: str) -> int:
    """Count [PAGE N] tags in the parsed text."""
    if not page_tagged_text:
        return 0
    return len(re.findall(r"\[PAGE\s+\d+\]", page_tagged_text))


def _build_trace(file_name: str, quarter: str, state: dict) -> dict:
    """Build a structured trace summary from the pipeline's final state."""
    trace = {
        "file_name": file_name,
        "quarter": quarter,
        "steps": [],
    }

    page_count = _count_pages(state.get("page_tagged_text", ""))
    trace["steps"].append({
        "node": "parse_pdf",
        "label": "Parse PDF",
        "status": "ok" if page_count > 0 else "warn",
        "summary": f"{page_count} pages extracted",
        "detail": None,
    })

    classification = state.get("classification")
    route = state.get("route")
    if classification:
        cls = classification
        trace["steps"].append({
            "node": "classify",
            "label": "Classify Document",
            "status": "ok",
            "summary": (
                f"{cls.doc_type} | {cls.confidence:.0%} confidence | "
                f"{cls.period} | Workflow {'A (Metrics)' if route == 'presentation' else 'B (Guidance)'}"
            ),
            "detail": {
                "doc_type": cls.doc_type,
                "company": cls.company,
                "ticker": cls.ticker,
                "period": cls.period,
                "doc_date": cls.doc_date,
                "confidence": cls.confidence,
                "summary": cls.summary,
                "route": route,
            },
        })
    else:
        trace["steps"].append({
            "node": "classify",
            "label": "Classify Document",
            "status": "error",
            "summary": "Classification failed",
            "detail": None,
        })

    if route == "presentation":
        extracted = state.get("extracted_metrics") or []
        found = [m for m in extracted if m.found]
        not_found = [m for m in extracted if not m.found]
        trace["steps"].append({
            "node": "extract_metrics",
            "label": "Extract Metrics",
            "status": "ok" if found else "warn",
            "summary": f"{len(found)}/{len(extracted)} metrics found" + (
                f" | missing: {', '.join(m.metric_name for m in not_found)}" if not_found else ""
            ),
            "detail": [
                {
                    "metric": m.metric_name,
                    "found": m.found,
                    "value": m.value,
                    "raw_value": m.raw_value,
                    "unit": m.unit,
                    "page": m.page,
                    "note": m.note,
                }
                for m in extracted
            ],
        })

        calculated = state.get("calculated_metrics") or []
        direct_count = sum(1 for m in calculated if m.found and not (m.note and "calculated" in (m.note or "").lower()))
        calc_count = sum(1 for m in calculated if m.found and m.note and "calculated" in (m.note or "").lower())
        missing_count = sum(1 for m in calculated if not m.found)
        trace["steps"].append({
            "node": "calculate_metrics",
            "label": "Calculate Derived Metrics",
            "status": "ok",
            "summary": f"{direct_count} direct, {calc_count} calculated, {missing_count} missing",
            "detail": [
                {
                    "metric": m.metric_name,
                    "found": m.found,
                    "value": m.value,
                    "unit": m.unit,
                    "note": m.note,
                }
                for m in calculated
            ],
        })

        validation = state.get("validation")
        if validation:
            flagged = [r for r in validation.results if r.status == "flag"]
            trace["steps"].append({
                "node": "validate_metrics",
                "label": "Validate Metrics",
                "status": "flag" if flagged else "ok",
                "summary": (
                    f"{validation.overall_status}" + (
                        f" — {len(flagged)} flagged: "
                        + ", ".join(f"{f.metric_name} ({f.issue})" for f in flagged)
                        if flagged else " — all checks passed"
                    )
                ),
                "detail": [
                    {"metric": r.metric_name, "status": r.status, "issue": r.issue}
                    for r in validation.results
                ],
            })

        trace["steps"].append({
            "node": "assemble_table",
            "label": "Assemble & Save",
            "status": "ok" if state.get("metrics_table") else "warn",
            "summary": f"Saved metrics to DB for {quarter}",
            "detail": None,
        })

    elif route == "transcript":
        items = state.get("guidance_items") or []
        topic_counts = {}
        for item in items:
            topic_counts[item.topic] = topic_counts.get(item.topic, 0) + 1
        trace["steps"].append({
            "node": "extract_guidance",
            "label": "Extract Guidance",
            "status": "ok" if items else "warn",
            "summary": f"{len(items)} items across {len(topic_counts)} topics",
            "detail": [
                {
                    "topic": item.topic,
                    "statement": item.statement,
                    "sentiment": item.sentiment,
                    "speaker": item.speaker,
                    "timeframe": item.timeframe,
                    "page": item.page,
                }
                for item in items
            ],
        })

        deltas_result = state.get("guidance_deltas")
        if deltas_result:
            deltas = deltas_result.deltas or []
            change_counts = {}
            for d in deltas:
                change_counts[d.change_type] = change_counts.get(d.change_type, 0) + 1
            parts = [f"{v} {k}" for k, v in sorted(change_counts.items())]
            trace["steps"].append({
                "node": "detect_deltas",
                "label": "Detect Guidance Deltas",
                "status": "ok",
                "summary": (
                    f"vs {deltas_result.prior_quarter or 'N/A'} — "
                    + (", ".join(parts) if parts else "no changes detected")
                ),
                "detail": [
                    {
                        "topic": d.topic,
                        "change_type": d.change_type,
                        "summary": d.summary,
                        "current": d.current_statement,
                        "prior": d.prior_statement,
                    }
                    for d in deltas
                ],
            })
        else:
            trace["steps"].append({
                "node": "detect_deltas",
                "label": "Detect Guidance Deltas",
                "status": "skip",
                "summary": "No prior quarter to compare",
                "detail": None,
            })

        trace["steps"].append({
            "node": "assemble_guidance",
            "label": "Assemble & Save",
            "status": "ok" if state.get("guidance_table") else "warn",
            "summary": f"Saved guidance to DB for {quarter}",
            "detail": None,
        })

    return trace


def _run_pipeline_sync(company: str, schema_key: str):
    """Run the pipeline synchronously (called from background task)."""
    _pipeline_status[company] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "current_file": "",
        "current_node": "",
        "errors": [],
        "pres_count": 0,
        "trans_count": 0,
        "traces": [],
    }

    pattern = os.path.join(SAMPLE_DOCS_DIR, company, "**", "*.pdf")
    pdfs = sorted(glob.glob(pattern, recursive=True))

    if not pdfs:
        _pipeline_status[company] = {
            "status": "error",
            "message": f"No PDFs found for '{company}'",
            "traces": [],
        }
        return

    _pipeline_status[company]["total"] = len(pdfs)

    for i, pdf_path in enumerate(pdfs):
        file_name = os.path.basename(pdf_path)
        quarter = _infer_quarter(file_name)

        _pipeline_status[company]["progress"] = i
        _pipeline_status[company]["current_file"] = file_name
        _pipeline_status[company]["current_node"] = "parse_pdf"

        if not quarter:
            _pipeline_status[company]["errors"].append(
                f"Skipped {file_name} — cannot infer quarter"
            )
            _pipeline_status[company]["traces"].append({
                "file_name": file_name,
                "quarter": None,
                "steps": [{
                    "node": "skip",
                    "label": "Skipped",
                    "status": "error",
                    "summary": "Cannot infer quarter from filename",
                    "detail": None,
                }],
            })
            continue

        try:
            _pipeline_status[company]["current_node"] = "processing"
            state = run_single(
                pdf_path, schema_key, quarter, company_name=company,
            )

            trace = _build_trace(file_name, quarter, state)
            _pipeline_status[company]["traces"].append(trace)

            if state.get("metrics_table"):
                _pipeline_status[company]["pres_count"] += 1
            if state.get("guidance_table"):
                _pipeline_status[company]["trans_count"] += 1
        except Exception as e:
            _pipeline_status[company]["errors"].append(
                f"Error on {file_name}: {str(e)}"
            )
            _pipeline_status[company]["traces"].append({
                "file_name": file_name,
                "quarter": quarter,
                "steps": [{
                    "node": "error",
                    "label": "Pipeline Error",
                    "status": "error",
                    "summary": str(e),
                    "detail": None,
                }],
            })

    status = _pipeline_status[company]
    status["status"] = "complete"
    status["progress"] = len(pdfs)
    status["current_node"] = ""
    status["current_file"] = ""
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


@app.get("/api/pipeline/trace/{company}")
def pipeline_trace(company: str) -> dict:
    """Return the per-file pipeline trace with node-level detail."""
    status = _pipeline_status.get(company, {})
    return {
        "status": status.get("status", "idle"),
        "traces": status.get("traces", []),
    }


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
