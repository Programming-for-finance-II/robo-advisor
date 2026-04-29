"""
snapshots.py — Audit trail persistence for market data and recommendations.

Provides three public functions consumed by the FastAPI layer:
  - init_db(db_path)              → sqlite3.Connection
  - save_market_snapshot(conn, df, report) → str  (hash PK)
  - save_recommendation(conn, rec)         → str  (UUID)

Design: connection lifecycle is managed by the caller (FastAPI lifespan),
not by this module. All functions accept an open sqlite3.Connection.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.data.loader import DataQualityReport


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) the SQLite DB and ensure schema is up to date.

    Runs the schema.sql migrations idempotently via CREATE TABLE IF NOT EXISTS.
    Returns an open connection with WAL mode enabled.

    Args:
        db_path: Path to the SQLite file. Use ":memory:" for tests.

    Returns:
        Open sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    schema_path = Path(__file__).parent / "schema.sql"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    with open(schema_path) as f:
        conn.executescript(f.read())

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Market data snapshots
# ---------------------------------------------------------------------------

def save_market_snapshot(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    report: DataQualityReport,
) -> str:
    """Persist a validated price DataFrame for bit-for-bit reproducibility.

    Uses the SHA-256 hash from DataQualityReport as the primary key — if a
    snapshot with the same hash already exists (identical data), the INSERT
    is silently skipped (INSERT OR IGNORE). This makes the function safe to
    call on every recommendation without duplicating data.

    Args:
        conn:   Open SQLite connection (managed by caller).
        df:     Price DataFrame returned by ValidatedDataLoader.load().
        report: DataQualityReport returned by ValidatedDataLoader.load().

    Returns:
        The SHA-256 hash string used as primary key.
    """
    assert isinstance(df, pd.DataFrame), "df must be a pandas DataFrame"
    assert not df.empty, "Cannot persist an empty DataFrame"
    assert len(report.market_data_hash) == 64, "Hash must be a 64-char SHA-256 hex string"  # noqa: E501

    created_at = datetime.now(timezone.utc).isoformat()
    tickers_json = json.dumps(sorted(df.columns.tolist()))
    window_start = report.date_range[0].isoformat()
    window_end = report.date_range[1].isoformat()
    data_csv = df.to_csv()

    conn.execute(
        """
        INSERT OR IGNORE INTO market_data_snapshots
            (hash, created_at, tickers, window_start, window_end, data_csv)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            report.market_data_hash,
            created_at,
            tickers_json,
            window_start,
            window_end,
            data_csv,
        ),
    )
    conn.commit()
    return report.market_data_hash


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def save_recommendation(
    conn: sqlite3.Connection,
    rec: dict,
) -> str:
    """Insert a full recommendation audit record.

    The caller is responsible for providing all required fields. Optional
    fields (fallback_tickers_applied, tilt_applied, regulatory_context,
    validator_flags) default to None if not supplied.

    Args:
        conn: Open SQLite connection (managed by caller).
        rec:  Dictionary with all recommendation fields. See inline comment
              for the expected keys.

    Returns:
        The UUID string used as primary key (rec["id"] if provided,
        otherwise a freshly generated UUID v4).
    """
    rec_id = rec.get("id") or str(uuid.uuid4())
    created_at = rec.get("created_at") or datetime.now(timezone.utc).isoformat()

    # Serialise list/dict fields to JSON strings (schema stores TEXT)
    def _json(val: object) -> str | None:
        if val is None:
            return None
        return val if isinstance(val, str) else json.dumps(val)

    conn.execute(
        """
        INSERT INTO recommendations (
            id, user_id, created_at, data_fetch_timestamp,
            questionnaire_snapshot, profile_label, profile_confidence,
            profile_model_version,
            tickers_used, ucits_tickers_used, fallback_tickers_applied,
            etf_universe_version,
            data_window_start, data_window_end, market_data_hash,
            nan_count_pre_clean, nan_count_post_clean,
            optimizer_algo, optimizer_version, linkage_method,
            shrinkage_method, tilt_applied, guardrails_applied,
            weights_raw_hrp, weights_final,
            risk_metrics, cluster_structure, stress_scenarios,
            regulatory_context,
            llm_model, system_prompt_hash, ground_truth_json_hash,
            llm_response_raw, llm_response_validated,
            validator_version, validator_flags, retry_count,
            disclaimer_shown, disclaimer_text_hash
        ) VALUES (
            ?,?,?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,?,?,
            ?,?,?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,?,?,?,?,?,?,?
        )
        """,
        (
            rec_id,
            rec["user_id"],
            created_at,
            rec.get("data_fetch_timestamp", created_at),
            # Input snapshot
            _json(rec["questionnaire_snapshot"]),
            rec["profile_label"],
            float(rec["profile_confidence"]),
            rec["profile_model_version"],
            # Market data provenance
            _json(rec["tickers_used"]),
            _json(rec["ucits_tickers_used"]),
            _json(rec.get("fallback_tickers_applied")),
            rec.get("etf_universe_version", "v3.1"),
            rec["data_window_start"],
            rec["data_window_end"],
            rec["market_data_hash"],
            int(rec.get("nan_count_pre_clean", 0)),
            int(rec.get("nan_count_post_clean", 0)),
            # Optimizer config
            rec.get("optimizer_algo", "HRP"),
            rec["optimizer_version"],
            rec.get("linkage_method", "ward"),
            rec.get("shrinkage_method", "ledoit_wolf"),
            rec.get("tilt_applied"),
            int(rec.get("guardrails_applied", 0)),
            # Output weights
            _json(rec["weights_raw_hrp"]),
            _json(rec["weights_final"]),
            # Metrics and context
            _json(rec["risk_metrics"]),
            _json(rec["cluster_structure"]),
            _json(rec["stress_scenarios"]),
            _json(rec.get("regulatory_context")),
            # LLM audit
            rec["llm_model"],
            rec["system_prompt_hash"],
            rec["ground_truth_json_hash"],
            rec["llm_response_raw"],
            rec["llm_response_validated"],
            rec.get("validator_version", "v1"),
            _json(rec.get("validator_flags")),
            int(rec.get("retry_count", 0)),
            # Compliance
            int(rec.get("disclaimer_shown", 0)),
            rec.get("disclaimer_text_hash", ""),
        ),
    )
    conn.commit()
    return rec_id


# ---------------------------------------------------------------------------
# Read helpers (used as fallback when yfinance is down)
# ---------------------------------------------------------------------------

def get_latest_snapshot(
    conn: sqlite3.Connection,
    tickers: list[str],
) -> dict | None:
    """Fetch the most recent snapshot for a given set of tickers.

    Used as circuit-breaker fallback: if yfinance fails, the optimizer
    can re-use the last valid snapshot instead of crashing.

    Args:
        conn:    Open SQLite connection.
        tickers: List of ticker strings (order-independent).

    Returns:
        Dict with keys {hash, created_at, window_start, window_end, df}
        where df is the reconstructed DataFrame, or None if not found.
    """
    tickers_json = json.dumps(sorted(tickers))
    row = conn.execute(
        """
        SELECT hash, created_at, window_start, window_end, data_csv
        FROM market_data_snapshots
        WHERE tickers = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (tickers_json,),
    ).fetchone()

    if row is None:
        return None

    import io
    df = pd.read_csv(io.StringIO(row["data_csv"]), index_col=0, parse_dates=True)
    return {
        "hash": row["hash"],
        "created_at": row["created_at"],
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "df": df,
    }
