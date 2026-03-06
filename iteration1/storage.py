"""SQLite storage layer for the Earnings Intelligence Pipeline.

Stores metrics, citations, and PDF records per company.
Supports the rolling 8-quarter dashboard by providing
pivot-style queries across quarters.

Database location: data/{company}.db (one DB per company).
"""

import os
import json
import sqlite3
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _db_path(company: str) -> str:
    """Return the SQLite DB path for a company, creating the data dir if needed."""
    os.makedirs(DATA_DIR, exist_ok=True)
    safe_name = company.lower().replace(" ", "_")
    return os.path.join(DATA_DIR, f"{safe_name}.db")


def get_connection(company: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database for a company."""
    conn = sqlite3.connect(_db_path(company))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pdfs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name   TEXT NOT NULL,
            company     TEXT NOT NULL,
            quarter     TEXT NOT NULL,
            doc_type    TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company, quarter, doc_type)
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            quarter     TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value       REAL,
            unit        TEXT,
            source      TEXT NOT NULL,
            found       INTEGER NOT NULL DEFAULT 1,
            note        TEXT,
            pdf_id      INTEGER REFERENCES pdfs(id),
            UNIQUE(company, quarter, metric_name)
        );

        CREATE TABLE IF NOT EXISTS citations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_id   INTEGER NOT NULL REFERENCES metrics(id),
            page_number INTEGER NOT NULL,
            passage     TEXT NOT NULL,
            pdf_id      INTEGER REFERENCES pdfs(id)
        );

        CREATE TABLE IF NOT EXISTS validations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_id   INTEGER NOT NULL REFERENCES metrics(id),
            status      TEXT NOT NULL,
            issue       TEXT
        );

        CREATE TABLE IF NOT EXISTS guidance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            quarter     TEXT NOT NULL,
            topic       TEXT NOT NULL,
            statement   TEXT NOT NULL,
            sentiment   TEXT DEFAULT 'neutral',
            speaker     TEXT,
            timeframe   TEXT,
            page_number INTEGER,
            passage     TEXT,
            pdf_id      INTEGER REFERENCES pdfs(id),
            UNIQUE(company, quarter, topic, statement)
        );

        CREATE TABLE IF NOT EXISTS guidance_deltas (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            company           TEXT NOT NULL,
            quarter           TEXT NOT NULL,
            prior_quarter     TEXT,
            topic             TEXT NOT NULL,
            change_type       TEXT NOT NULL,
            current_statement TEXT,
            prior_statement   TEXT,
            summary           TEXT NOT NULL
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# PDF records
# ---------------------------------------------------------------------------

def save_pdf_record(conn: sqlite3.Connection, file_name: str, company: str,
                    quarter: str, doc_type: str, file_path: str) -> int:
    """Insert or replace a PDF record. Returns the pdf id."""
    cur = conn.execute("""
        INSERT INTO pdfs (file_name, company, quarter, doc_type, file_path)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(company, quarter, doc_type) DO UPDATE SET
            file_name=excluded.file_name,
            file_path=excluded.file_path,
            ingested_at=CURRENT_TIMESTAMP
    """, (file_name, company, quarter, doc_type, file_path))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM pdfs WHERE company=? AND quarter=? AND doc_type=?",
        (company, quarter, doc_type)
    ).fetchone()
    return row["id"]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def save_metric(conn: sqlite3.Connection, company: str, quarter: str,
                metric_name: str, value: Optional[float], unit: str,
                source: str, found: bool = True, note: str = None,
                pdf_id: int = None) -> int:
    """Insert or replace a single metric. Returns the metric id."""
    cur = conn.execute("""
        INSERT INTO metrics (company, quarter, metric_name, value, unit, source, found, note, pdf_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company, quarter, metric_name) DO UPDATE SET
            value=excluded.value,
            unit=excluded.unit,
            source=excluded.source,
            found=excluded.found,
            note=excluded.note,
            pdf_id=excluded.pdf_id
    """, (company, quarter, metric_name, value, unit, source, int(found), note, pdf_id))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM metrics WHERE company=? AND quarter=? AND metric_name=?",
        (company, quarter, metric_name)
    ).fetchone()
    return row["id"]


def get_metrics_for_quarter(conn: sqlite3.Connection, company: str,
                            quarter: str) -> list[dict]:
    """Return all metrics for a given company+quarter."""
    rows = conn.execute(
        "SELECT * FROM metrics WHERE company=? AND quarter=? ORDER BY metric_name",
        (company, quarter)
    ).fetchall()
    return [dict(r) for r in rows]


def get_metrics_table(conn: sqlite3.Connection, company: str,
                      metric_names: list[str] = None,
                      max_quarters: int = 8) -> dict:
    """Build the 8-quarter pivot table for the dashboard.

    Returns:
        {
            "quarters": ["FY25-Q3", "FY25-Q4", ...],
            "metrics": {
                "Revenue": {"unit": "INR Cr", "values": {"FY25-Q3": 2381, ...}},
                ...
            }
        }
    """
    quarter_rows = conn.execute("""
        SELECT DISTINCT quarter FROM metrics
        WHERE company=?
        ORDER BY quarter
    """, (company,)).fetchall()
    quarters = [r["quarter"] for r in quarter_rows][-max_quarters:]

    if not quarters:
        return {"quarters": [], "metrics": {}}

    placeholders = ",".join("?" for _ in quarters)
    query = f"""
        SELECT metric_name, quarter, value, unit
        FROM metrics
        WHERE company=? AND quarter IN ({placeholders})
        ORDER BY metric_name, quarter
    """
    rows = conn.execute(query, [company] + quarters).fetchall()

    metrics = {}
    for r in rows:
        name = r["metric_name"]
        if metric_names and name not in metric_names:
            continue
        if name not in metrics:
            metrics[name] = {"unit": r["unit"], "values": {}}
        metrics[name]["values"][r["quarter"]] = r["value"]

    return {"quarters": quarters, "metrics": metrics}


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

def save_citation(conn: sqlite3.Connection, metric_id: int,
                  page_number: int, passage: str, pdf_id: int = None) -> int:
    """Insert a citation for a metric. Returns the citation id."""
    cur = conn.execute("""
        INSERT INTO citations (metric_id, page_number, passage, pdf_id)
        VALUES (?, ?, ?, ?)
    """, (metric_id, page_number, passage, pdf_id))
    conn.commit()
    return cur.lastrowid


def get_citations_for_metric(conn: sqlite3.Connection,
                             metric_id: int) -> list[dict]:
    """Return all citations for a metric."""
    rows = conn.execute(
        "SELECT * FROM citations WHERE metric_id=? ORDER BY page_number",
        (metric_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_citations_for_quarter(conn: sqlite3.Connection, company: str,
                              quarter: str) -> dict[str, list[dict]]:
    """Return citations grouped by metric name for a company+quarter.

    Returns: {"Revenue": [{"page_number": 12, "passage": "...", "file_path": "..."}], ...}
    """
    rows = conn.execute("""
        SELECT m.metric_name, c.page_number, c.passage, p.file_path, m.source
        FROM citations c
        JOIN metrics m ON c.metric_id = m.id
        LEFT JOIN pdfs p ON c.pdf_id = p.id
        WHERE m.company=? AND m.quarter=?
        ORDER BY m.metric_name, c.page_number
    """, (company, quarter)).fetchall()

    result = {}
    for r in rows:
        name = r["metric_name"]
        if name not in result:
            result[name] = []
        result[name].append({
            "page_number": r["page_number"],
            "passage": r["passage"],
            "file_path": r["file_path"],
            "source": r["source"],
        })
    return result


# ---------------------------------------------------------------------------
# Validations
# ---------------------------------------------------------------------------

def save_validation(conn: sqlite3.Connection, metric_id: int,
                    status: str, issue: str = None) -> int:
    """Insert a validation result for a metric. Returns the validation id."""
    cur = conn.execute("""
        INSERT INTO validations (metric_id, status, issue)
        VALUES (?, ?, ?)
    """, (metric_id, status, issue))
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Guidance
# ---------------------------------------------------------------------------

def save_guidance_item(conn: sqlite3.Connection, company: str, quarter: str,
                       topic: str, statement: str, sentiment: str = "neutral",
                       speaker: str = None, timeframe: str = None,
                       page_number: int = None, passage: str = None,
                       pdf_id: int = None) -> int:
    """Insert or ignore a guidance item. Returns the guidance id."""
    conn.execute("""
        INSERT OR IGNORE INTO guidance
            (company, quarter, topic, statement, sentiment, speaker, timeframe, page_number, passage, pdf_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (company, quarter, topic, statement, sentiment, speaker, timeframe, page_number, passage, pdf_id))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM guidance WHERE company=? AND quarter=? AND topic=? AND statement=?",
        (company, quarter, topic, statement)
    ).fetchone()
    return row["id"] if row else 0


def save_guidance_delta(conn: sqlite3.Connection, company: str, quarter: str,
                        prior_quarter: str, topic: str, change_type: str,
                        current_statement: str = None, prior_statement: str = None,
                        summary: str = "") -> int:
    """Insert a guidance delta. Returns the delta id."""
    cur = conn.execute("""
        INSERT INTO guidance_deltas
            (company, quarter, prior_quarter, topic, change_type,
             current_statement, prior_statement, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (company, quarter, prior_quarter, topic, change_type,
          current_statement, prior_statement, summary))
    conn.commit()
    return cur.lastrowid


def get_guidance_for_quarter(conn: sqlite3.Connection, company: str,
                             quarter: str) -> list[dict]:
    """Return all guidance items for a company+quarter, ordered by topic."""
    rows = conn.execute("""
        SELECT g.*, p.file_path
        FROM guidance g
        LEFT JOIN pdfs p ON g.pdf_id = p.id
        WHERE g.company=? AND g.quarter=?
        ORDER BY g.topic, g.id
    """, (company, quarter)).fetchall()
    return [dict(r) for r in rows]


def get_guidance_table(conn: sqlite3.Connection, company: str,
                       max_quarters: int = 8) -> dict:
    """Build the rolling guidance table across quarters.

    Returns:
        {
            "quarters": ["Q3 FY25", "Q4 FY25", ...],
            "topics": {
                "Financial Outlook": {
                    "Q3 FY25": [{"statement": "...", "speaker": "...", ...}],
                    ...
                },
                ...
            }
        }
    """
    quarter_rows = conn.execute("""
        SELECT DISTINCT quarter FROM guidance
        WHERE company=?
        ORDER BY quarter
    """, (company,)).fetchall()
    quarters = [r["quarter"] for r in quarter_rows][-max_quarters:]

    if not quarters:
        return {"quarters": [], "topics": {}}

    placeholders = ",".join("?" for _ in quarters)
    rows = conn.execute(f"""
        SELECT g.topic, g.quarter, g.statement, g.sentiment, g.speaker,
               g.timeframe, g.page_number, g.passage, p.file_path
        FROM guidance g
        LEFT JOIN pdfs p ON g.pdf_id = p.id
        WHERE g.company=? AND g.quarter IN ({placeholders})
        ORDER BY g.topic, g.quarter, g.id
    """, [company] + quarters).fetchall()

    topics = {}
    for r in rows:
        topic = r["topic"]
        q = r["quarter"]
        if topic not in topics:
            topics[topic] = {}
        if q not in topics[topic]:
            topics[topic][q] = []
        topics[topic][q].append({
            "statement": r["statement"],
            "sentiment": r["sentiment"] or "neutral",
            "speaker": r["speaker"],
            "timeframe": r["timeframe"],
            "page_number": r["page_number"],
            "passage": r["passage"],
            "file_path": r["file_path"],
        })

    return {"quarters": quarters, "topics": topics}


def get_deltas_for_quarter(conn: sqlite3.Connection, company: str,
                           quarter: str) -> list[dict]:
    """Return all guidance deltas for a company+quarter."""
    rows = conn.execute("""
        SELECT * FROM guidance_deltas
        WHERE company=? AND quarter=?
        ORDER BY topic, id
    """, (company, quarter)).fetchall()
    return [dict(r) for r in rows]


def get_prior_quarter(conn: sqlite3.Connection, company: str,
                      current_quarter: str) -> str | None:
    """Return the most recent quarter before the current one that has guidance."""
    rows = conn.execute("""
        SELECT DISTINCT quarter FROM guidance
        WHERE company=? AND quarter < ?
        ORDER BY quarter DESC
        LIMIT 1
    """, (company, current_quarter)).fetchall()
    return rows[0]["quarter"] if rows else None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def delete_quarter(conn: sqlite3.Connection, company: str, quarter: str) -> None:
    """Delete all data for a company+quarter (useful for re-processing)."""
    conn.executescript(f"""
        DELETE FROM validations WHERE metric_id IN (
            SELECT id FROM metrics WHERE company='{company}' AND quarter='{quarter}'
        );
        DELETE FROM citations WHERE metric_id IN (
            SELECT id FROM metrics WHERE company='{company}' AND quarter='{quarter}'
        );
        DELETE FROM metrics WHERE company='{company}' AND quarter='{quarter}';
        DELETE FROM pdfs WHERE company='{company}' AND quarter='{quarter}';
    """)
    conn.commit()


def list_quarters(conn: sqlite3.Connection, company: str) -> list[str]:
    """Return all quarters stored for a company, sorted."""
    rows = conn.execute(
        "SELECT DISTINCT quarter FROM metrics WHERE company=? ORDER BY quarter",
        (company,)
    ).fetchall()
    return [r["quarter"] for r in rows]
