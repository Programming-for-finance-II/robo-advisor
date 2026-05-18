"""
tests/test_ucits_fallback.py
============================
Test suite for UCITS fallback logic in ValidatedDataLoader.

Covers the three mandatory cases from the W4 plan:
  1. Fallback triggers when a UCITS ticker returns an empty DataFrame
  2. fallback_tickers_applied is populated in DataQualityReport
  3. DB row records the fallback correctly

Shared with P3 (universe_config.py integrity checks).
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from backend.data.loader import ValidatedDataLoader
from backend.data.universe_config import get_fallback_map, get_ucits_tickers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(tickers: list[str], n: int = 300) -> pd.DataFrame:
    """Return a minimal valid price DataFrame for the given tickers."""
    import numpy as np
    dates = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    data = {t: np.random.uniform(90, 110, size=n) for t in tickers}
    return pd.DataFrame(data, index=dates)


def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame simulating a failed yfinance download."""
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Test 1 — Fallback triggers when UCITS ticker returns empty DataFrame
# ---------------------------------------------------------------------------

def test_fallback_triggers_on_empty_dataframe():
    """
    When yfinance returns an empty DataFrame for a UCITS primary ticker,
    ValidatedDataLoader must switch to the fallback ticker automatically.
    """
    ucits_tickers = get_ucits_tickers()
    fallback_map = get_fallback_map()

    # Pick the first UCITS ticker that has a real fallback
    primary = next(
        t for t in ucits_tickers if fallback_map[t] != t
    )
    fallback = fallback_map[primary]

    # All tickers except the primary one
    other_tickers = [
        t for t in ["EFA", "GLD", "VNQ", "TLT", "TIP"]
        if t != primary
    ]
    all_tickers = [primary] + other_tickers

    def mock_download(tickers, start, end, auto_adjust, progress):
        # Return empty for primary UCITS ticker probe
        if isinstance(tickers, str) and tickers == primary:
            return _empty_df()
        # Return valid data for everything else
        ticker_list = [tickers] if isinstance(tickers, str) else tickers
        return _make_prices(ticker_list)

    with patch("yfinance.download", side_effect=mock_download):
        loader = ValidatedDataLoader()
        prices, report = loader.load(
            tickers=all_tickers,
            start="2023-01-01",
            end="2024-01-01",
        )

    # Fallback must have been applied
    assert primary in report.fallback_tickers_applied, (
        f"Expected {primary} in fallback_tickers_applied, "
        f"got {report.fallback_tickers_applied}"
    )
    assert report.fallback_tickers_applied[primary] == fallback


# ---------------------------------------------------------------------------
# Test 2 — fallback_tickers_applied is populated in DataQualityReport
# ---------------------------------------------------------------------------

def test_fallback_tickers_applied_in_report():
    """
    When a fallback is applied, DataQualityReport.fallback_tickers_applied
    must contain the correct {primary: fallback} mapping.
    The field must be non-empty and serializable via to_dict().
    """
    primary = "CSPX.L"
    fallback = get_fallback_map()[primary]

    other_tickers = ["EFA", "GLD", "VNQ", "TLT", "TIP"]
    all_tickers = [primary] + other_tickers

    def mock_download(tickers, start, end, auto_adjust, progress):
        if isinstance(tickers, str) and tickers == primary:
            # Simulate high NaN ratio by returning mostly NaN data
            dates = pd.date_range("2023-01-01", periods=300, freq="B")
            df = pd.DataFrame(
                {"Close": [float("nan")] * 300},
                index=dates,
            )
            df.columns = pd.MultiIndex.from_tuples(
                [("Close", primary)]
            )
            return df
        ticker_list = [tickers] if isinstance(tickers, str) else tickers
        return _make_prices(ticker_list)

    with patch("yfinance.download", side_effect=mock_download):
        loader = ValidatedDataLoader()
        _, report = loader.load(
            tickers=all_tickers,
            start="2023-01-01",
            end="2024-01-01",
        )

    # Report must be populated
    assert isinstance(report.fallback_tickers_applied, dict)
    assert len(report.fallback_tickers_applied) >= 1
    assert report.fallback_tickers_applied.get(primary) == fallback

    # Must serialize cleanly
    serialized = report.to_dict()
    assert "fallback_tickers_applied" in serialized
    assert serialized["fallback_tickers_applied"][primary] == fallback


# ---------------------------------------------------------------------------
# Test 3 — DB row records the fallback correctly
# ---------------------------------------------------------------------------

def test_fallback_recorded_in_db(tmp_path):
    """
    When a fallback is applied, the recommendation saved to the DB
    must record the fallback in the fallback_tickers_applied column.
    """
    import json
    import datetime
    import uuid
    from backend.data.loader import DataQualityReport
    from backend.data.snapshots import init_db, save_recommendation

    primary = "XEON.MI"
    fallback = get_fallback_map()[primary]

    report_with_fallback = DataQualityReport(
        nan_ratio=0.0,
        missing_tickers=[],
        date_range=(
            datetime.date(2023, 1, 1),
            datetime.date(2024, 1, 1),
        ),
        n_observations=252,
        market_data_hash="abc123",
        ucits_tickers_used=["CSPX.L", "AGGH.MI"],
        fallback_tickers_applied={primary: fallback},
    )

    db_path = str(tmp_path / "test_fallback.db")
    conn = init_db(db_path)

    # Insert required user row to satisfy FK constraint
    conn.execute(
        "INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)",
        ("test_user", "2024-01-01T00:00:00+00:00"),
    )
    conn.commit()

    rec_id = str(uuid.uuid4())

    save_recommendation(conn, {
        "id": rec_id,
        "user_id": "test_user",
        "data_fetch_timestamp": "2024-01-01T00:00:00+00:00",
        "questionnaire_snapshot": "{}",
        "profile_label": "MODERATE",
        "profile_confidence": 0.82,
        "profile_model_version": "rule_based_v1",
        "tickers_used": list(report_with_fallback.ucits_tickers_used),
        "ucits_tickers_used": report_with_fallback.ucits_tickers_used,
        "fallback_tickers_applied": report_with_fallback.fallback_tickers_applied,
        "data_window_start": "2023-01-01",
        "data_window_end": "2024-01-01",
        "market_data_hash": report_with_fallback.market_data_hash,
        "nan_count_pre_clean": 0,
        "nan_count_post_clean": 0,
        "optimizer_version": "hrp_v1",
        "weights_raw_hrp": {},
        "weights_final": {},
        "risk_metrics": {},
        "cluster_structure": {},
        "stress_scenarios": {},
        "llm_model": "none",
        "system_prompt_hash": "none",
        "ground_truth_json_hash": "none",
        "llm_response_raw": "none",
        "llm_response_validated": "none",
    })
    conn.commit()

    row = conn.execute(
        "SELECT fallback_tickers_applied FROM recommendations WHERE id = ?",
        (rec_id,),
    ).fetchone()

    conn.close()

    assert row is not None, "Recommendation not found in DB"
    stored = json.loads(row["fallback_tickers_applied"])
    assert stored.get(primary) == fallback, (
        f"Expected fallback {fallback} for {primary}, got {stored}"
    )