"""Extended SQLite storage for Iteration 2.

Adds tables for:
  - sources: document registry with source_type, analyst, firm, MNPI status
  - analyst_estimates: sell-side forward estimates
  - visit_insights: field intelligence observations
  - consensus: divergence records
  - query_cache: semantic cache for query answers
  - mnpi_audit: MNPI screening audit trail

Reuses iteration1.storage patterns and per-company DB location.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

import iteration1.storage as iter1_storage

DATA_DIR = iter1_storage.DATA_DIR


def get_connection(company: str) -> sqlite3.Connection:
    """Open the company DB (creates iter1 tables + iter2 extensions)."""
    conn = iter1_storage.get_connection(company)
    _create_iter2_tables(conn)
    return conn


def _create_iter2_tables(conn: sqlite3.Connection) -> None:
    """Create Iteration 2 tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            source_type TEXT NOT NULL,
            doc_type    TEXT NOT NULL,
            file_name   TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            analyst     TEXT,
            firm        TEXT,
            rating      TEXT,
            target_price REAL,
            date        TEXT,
            mnpi_status TEXT DEFAULT 'cleared',
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company, file_name)
        );

        CREATE TABLE IF NOT EXISTS analyst_estimates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   INTEGER NOT NULL REFERENCES sources(id),
            company     TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value       REAL,
            unit        TEXT,
            period      TEXT NOT NULL,
            analyst     TEXT,
            firm        TEXT
        );

        CREATE TABLE IF NOT EXISTS visit_insights (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   INTEGER NOT NULL REFERENCES sources(id),
            company     TEXT NOT NULL,
            topic       TEXT NOT NULL,
            observation TEXT NOT NULL,
            sentiment   TEXT DEFAULT 'neutral',
            conviction  TEXT DEFAULT 'neutral',
            source_person TEXT,
            date        TEXT
        );

        CREATE TABLE IF NOT EXISTS consensus (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            company             TEXT NOT NULL,
            quarter             TEXT,
            metric_or_topic     TEXT NOT NULL,
            sources_agree       INTEGER DEFAULT 1,
            view_a              TEXT,
            view_b              TEXT,
            divergence_summary  TEXT,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS query_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company         TEXT NOT NULL,
            query_text      TEXT NOT NULL,
            query_normalized TEXT NOT NULL,
            answer_json     TEXT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            invalidated_at  TIMESTAMP,
            UNIQUE(company, query_normalized)
        );

        CREATE TABLE IF NOT EXISTS mnpi_audit (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name       TEXT NOT NULL,
            company         TEXT,
            classification  TEXT NOT NULL,
            confidence      REAL DEFAULT 0.0,
            reason          TEXT,
            action          TEXT NOT NULL,
            pii_entities    TEXT,
            timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def save_source(conn: sqlite3.Connection, company: str, source_type: str,
                doc_type: str, file_name: str, file_path: str,
                analyst: str = None, firm: str = None, rating: str = None,
                target_price: float = None, date: str = None,
                mnpi_status: str = "cleared") -> int:
    """Insert or update a source document record."""
    conn.execute("""
        INSERT INTO sources (company, source_type, doc_type, file_name, file_path,
                             analyst, firm, rating, target_price, date, mnpi_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company, file_name) DO UPDATE SET
            source_type=excluded.source_type, doc_type=excluded.doc_type,
            file_path=excluded.file_path, analyst=excluded.analyst,
            firm=excluded.firm, rating=excluded.rating,
            target_price=excluded.target_price, date=excluded.date,
            mnpi_status=excluded.mnpi_status, ingested_at=CURRENT_TIMESTAMP
    """, (company, source_type, doc_type, file_name, file_path,
          analyst, firm, rating, target_price, date, mnpi_status))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM sources WHERE company=? AND file_name=?",
        (company, file_name)
    ).fetchone()
    return row["id"]


def get_sources(conn: sqlite3.Connection, company: str,
                source_type: str = None) -> list[dict]:
    """List sources for a company, optionally filtered by source_type."""
    if source_type:
        rows = conn.execute(
            "SELECT * FROM sources WHERE company=? AND source_type=? ORDER BY date DESC",
            (company, source_type)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sources WHERE company=? ORDER BY source_type, date DESC",
            (company,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Analyst Estimates
# ---------------------------------------------------------------------------

def save_analyst_estimate(conn: sqlite3.Connection, source_id: int,
                          company: str, metric_name: str, value: float,
                          unit: str, period: str, analyst: str = None,
                          firm: str = None) -> int:
    """Insert an analyst estimate."""
    cur = conn.execute("""
        INSERT INTO analyst_estimates (source_id, company, metric_name, value, unit, period, analyst, firm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_id, company, metric_name, value, unit, period, analyst, firm))
    conn.commit()
    return cur.lastrowid


def get_analyst_estimates(conn: sqlite3.Connection, company: str,
                          metric_name: str = None) -> list[dict]:
    """Get analyst estimates, optionally filtered by metric."""
    if metric_name:
        rows = conn.execute(
            "SELECT * FROM analyst_estimates WHERE company=? AND metric_name=? ORDER BY firm, period",
            (company, metric_name)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM analyst_estimates WHERE company=? ORDER BY metric_name, firm, period",
            (company,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_consensus_estimates(conn: sqlite3.Connection, company: str,
                            period: str = None) -> dict:
    """Aggregate analyst estimates into consensus (mean/high/low/n_analysts).

    Returns: {metric_name: {period: {mean, high, low, n_analysts, estimates: [...]}}}
    """
    query = "SELECT * FROM analyst_estimates WHERE company=?"
    params = [company]
    if period:
        query += " AND period=?"
        params.append(period)

    rows = conn.execute(query + " ORDER BY metric_name, period", params).fetchall()

    consensus: dict = {}
    for r in rows:
        r = dict(r)
        metric = r["metric_name"]
        per = r["period"]
        if metric not in consensus:
            consensus[metric] = {}
        if per not in consensus[metric]:
            consensus[metric][per] = {"values": [], "estimates": []}

        if r["value"] is not None:
            consensus[metric][per]["values"].append(r["value"])
        consensus[metric][per]["estimates"].append({
            "firm": r["firm"],
            "analyst": r["analyst"],
            "value": r["value"],
            "unit": r["unit"],
        })

    for metric in consensus:
        for per in consensus[metric]:
            vals = consensus[metric][per]["values"]
            if vals:
                consensus[metric][per]["mean"] = sum(vals) / len(vals)
                consensus[metric][per]["high"] = max(vals)
                consensus[metric][per]["low"] = min(vals)
                consensus[metric][per]["n_analysts"] = len(vals)
            else:
                consensus[metric][per].update({"mean": None, "high": None, "low": None, "n_analysts": 0})
            del consensus[metric][per]["values"]

    return consensus


# ---------------------------------------------------------------------------
# Visit Insights
# ---------------------------------------------------------------------------

def save_visit_insight(conn: sqlite3.Connection, source_id: int,
                       company: str, topic: str, observation: str,
                       sentiment: str = "neutral", conviction: str = "neutral",
                       source_person: str = None, date: str = None) -> int:
    """Insert a visit note insight."""
    cur = conn.execute("""
        INSERT INTO visit_insights (source_id, company, topic, observation, sentiment,
                                    conviction, source_person, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_id, company, topic, observation, sentiment, conviction, source_person, date))
    conn.commit()
    return cur.lastrowid


def get_visit_insights(conn: sqlite3.Connection, company: str,
                       topic: str = None) -> list[dict]:
    """Get visit insights, optionally filtered by topic."""
    if topic:
        rows = conn.execute(
            "SELECT * FROM visit_insights WHERE company=? AND topic=? ORDER BY date DESC",
            (company, topic)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM visit_insights WHERE company=? ORDER BY topic, date DESC",
            (company,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Consensus Divergence
# ---------------------------------------------------------------------------

def save_consensus_divergence(conn: sqlite3.Connection, company: str,
                               quarter: str, metric_or_topic: str,
                               sources_agree: bool, view_a: str = None,
                               view_b: str = None,
                               divergence_summary: str = None) -> int:
    """Insert a consensus divergence record."""
    cur = conn.execute("""
        INSERT INTO consensus (company, quarter, metric_or_topic, sources_agree,
                               view_a, view_b, divergence_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (company, quarter, metric_or_topic, int(sources_agree),
          view_a, view_b, divergence_summary))
    conn.commit()
    return cur.lastrowid


def get_consensus_divergences(conn: sqlite3.Connection, company: str,
                               quarter: str = None) -> list[dict]:
    """Get consensus divergences."""
    if quarter:
        rows = conn.execute(
            "SELECT * FROM consensus WHERE company=? AND quarter=? ORDER BY metric_or_topic",
            (company, quarter)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM consensus WHERE company=? ORDER BY quarter DESC, metric_or_topic",
            (company,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Query Cache (Semantic Cache)
# ---------------------------------------------------------------------------

def normalize_query(query: str) -> str:
    """Normalize a query for exact-match cache lookup."""
    return " ".join(query.lower().strip().split())


def cache_lookup(conn: sqlite3.Connection, company: str, query: str) -> Optional[dict]:
    """Check cache for an exact query match. Returns answer JSON or None."""
    norm = normalize_query(query)
    row = conn.execute(
        "SELECT answer_json, created_at FROM query_cache WHERE company=? AND query_normalized=? AND invalidated_at IS NULL",
        (company, norm)
    ).fetchone()
    if row:
        return {"answer": json.loads(row["answer_json"]), "cached_at": row["created_at"]}
    return None


def cache_store(conn: sqlite3.Connection, company: str, query: str,
                answer_json: str) -> int:
    """Store a query-answer pair in the cache."""
    norm = normalize_query(query)
    conn.execute("""
        INSERT INTO query_cache (company, query_text, query_normalized, answer_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company, query_normalized) DO UPDATE SET
            answer_json=excluded.answer_json,
            created_at=CURRENT_TIMESTAMP,
            invalidated_at=NULL
    """, (company, query, norm, answer_json))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM query_cache WHERE company=? AND query_normalized=?",
        (company, norm)
    ).fetchone()
    return row["id"]


def invalidate_cache(conn: sqlite3.Connection, company: str) -> int:
    """Invalidate all cached queries for a company (called after new ingestion)."""
    cur = conn.execute(
        "UPDATE query_cache SET invalidated_at=CURRENT_TIMESTAMP WHERE company=? AND invalidated_at IS NULL",
        (company,)
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# MNPI Audit
# ---------------------------------------------------------------------------

def log_mnpi_screening(conn: sqlite3.Connection, file_name: str,
                       company: str, classification: str, confidence: float,
                       reason: str = None, action: str = "cleared",
                       pii_entities: list = None) -> int:
    """Log an MNPI screening decision."""
    cur = conn.execute("""
        INSERT INTO mnpi_audit (file_name, company, classification, confidence, reason, action, pii_entities)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (file_name, company, classification, confidence, reason, action,
          json.dumps(pii_entities or [])))
    conn.commit()
    return cur.lastrowid


def get_mnpi_audit_log(conn: sqlite3.Connection, company: str = None) -> list[dict]:
    """Get MNPI audit log, optionally filtered by company."""
    if company:
        rows = conn.execute(
            "SELECT * FROM mnpi_audit WHERE company=? ORDER BY timestamp DESC", (company,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM mnpi_audit ORDER BY timestamp DESC").fetchall()
    return [dict(r) for r in rows]
