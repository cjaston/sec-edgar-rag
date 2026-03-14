"""
Query audit logging for compliance and observability.

Every query is logged to a local SQLite database with full context:
who asked, what they asked, what was retrieved, what model answered,
how long it took, and how many tokens were used.

This serves three purposes:
  1. Compliance — audit trail of who accessed what data
  2. Observability — track latency, token costs, retrieval quality
  3. UI — query history in the Streamlit sidebar

In production, this would write to Postgres or a log aggregation service
(Datadog, Grafana Loki). The schema is designed for that migration.
"""

import uuid
import sqlite3
import json
from datetime import datetime, timezone

import config


_initialized = False


def _ensure_db():
    """Initialize the database on first use, not on import."""
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


def _get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory for dict-like access."""
    conn = sqlite3.connect(str(config.AUDIT_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the audit log table if it doesn't exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            query_id         TEXT PRIMARY KEY,
            timestamp        TEXT NOT NULL,
            user_id          TEXT NOT NULL,
            user_role        TEXT NOT NULL,
            query_text       TEXT NOT NULL,
            chunks_retrieved TEXT,
            chunks_used      INTEGER,
            access_filtered  INTEGER DEFAULT 0,
            llm_provider     TEXT,
            llm_model        TEXT,
            response_text    TEXT,
            input_tokens     INTEGER,
            output_tokens    INTEGER,
            total_tokens     INTEGER,
            latency_ms       INTEGER,
            error            TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_query(
    user_id: str,
    user_role: str,
    query_text: str,
    chunks_retrieved: list[str] | None = None,
    chunks_used: int = 0,
    access_filtered: int = 0,
    llm_provider: str = "",
    llm_model: str = "",
    response_text: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    error: str = "",
) -> str:
    """
    Log a query to the audit database. Returns the query_id.

    Called by the RAG orchestrator after each query completes (or fails).
    """
    _ensure_db()
    query_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    conn = _get_connection()
    conn.execute(
        """
        INSERT INTO query_log (
            query_id, timestamp, user_id, user_role, query_text,
            chunks_retrieved, chunks_used, access_filtered,
            llm_provider, llm_model, response_text,
            input_tokens, output_tokens, total_tokens,
            latency_ms, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            query_id,
            timestamp,
            user_id,
            user_role,
            query_text,
            json.dumps(chunks_retrieved) if chunks_retrieved else "[]",
            chunks_used,
            access_filtered,
            llm_provider,
            llm_model,
            response_text,
            input_tokens,
            output_tokens,
            input_tokens + output_tokens,
            latency_ms,
            error,
        ),
    )
    conn.commit()
    conn.close()
    return query_id


def get_history(limit: int = 50) -> list[dict]:
    """Retrieve recent queries from the audit log, newest first."""
    _ensure_db()
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM query_log ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    """Get aggregate statistics from the audit log."""
    _ensure_db()
    conn = _get_connection()

    row = conn.execute("""
        SELECT
            COUNT(*) as total_queries,
            AVG(latency_ms) as avg_latency_ms,
            SUM(total_tokens) as total_tokens,
            SUM(CASE WHEN error = '' OR error IS NULL THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN error != '' AND error IS NOT NULL THEN 1 ELSE 0 END) as failed
        FROM query_log
    """).fetchone()

    conn.close()

    if not row or row["total_queries"] == 0:
        return {"total_queries": 0}

    return {
        "total_queries": row["total_queries"],
        "avg_latency_ms": round(row["avg_latency_ms"] or 0),
        "total_tokens": row["total_tokens"] or 0,
        "successful": row["successful"],
        "failed": row["failed"],
    }
