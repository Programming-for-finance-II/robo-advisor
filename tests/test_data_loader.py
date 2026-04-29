"""
test_data_loader.py — Unit tests for ValidatedDataLoader.

All yfinance calls are mocked: tests run offline and deterministically.

Key facts about loader.py (read before modifying these tests):
- load() accepts start/end as strings "YYYY-MM-DD", not date objects.
- _resolve_tickers() probes each UCITS ticker individually via yf.download(str).
- _download() fetches all active tickers via yf.download(list).
- yfinance bulk output has MultiIndex columns: ("Close", "TICKER").
- yfinance single-ticker output has a flat "Close" column.
- fallback_tickers_applied is dict[str, str]: {primary: fallback}.
"""

from __future__ import annotations

import hashlib
from unittest.mock import patch

import pandas as pd
from backend.data.loader import ValidatedDataLoader


# ---------------------------------------------------------------------------
# Helpers — synthetic DataFrames that mimic real yfinance output
# ---------------------------------------------------------------------------

N_DAYS = 300  # > MIN_OBSERVATIONS (252) so the clean() check passes


def _make_bulk_df(tickers: list[str], nan_tickers: list[str] | None = None) -> pd.DataFrame:
    """Mimic yfinance multi-ticker output: MultiIndex columns ("Close", ticker)."""
    nan_tickers = nan_tickers or []
    rng = pd.date_range("2023-01-02", periods=N_DAYS, freq="B")
    columns = pd.MultiIndex.from_product([["Close"], tickers])
    data = {
        ("Close", t): (
            [float("nan")] * N_DAYS if t in nan_tickers
            else [100.0 + i for i in range(N_DAYS)]
        )
        for t in tickers
    }
    return pd.DataFrame(data, index=rng, columns=columns)


def _make_single_df(ticker: str, all_nan: bool = False) -> pd.DataFrame:
    """Mimic yfinance single-ticker output: flat 'Close' column."""
    rng = pd.date_range("2023-01-02", periods=N_DAYS, freq="B")
    values = (
        [float("nan")] * N_DAYS if all_nan
        else [100.0 + i for i in range(N_DAYS)]
    )
    return pd.DataFrame({"Close": values}, index=rng)


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------

def test_load_happy_path():
    """ValidatedDataLoader returns correct DataFrame and DataQualityReport
    when yfinance delivers clean data for all tickers."""
    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]
    bulk_df = _make_bulk_df(tickers)

    def fake_download(ticker_or_list, **kwargs):
        if isinstance(ticker_or_list, list):
            return bulk_df
        # Single-ticker probe — return scalar float values, not Series
        rng = pd.date_range("2023-01-02", periods=N_DAYS, freq="B")
        return pd.DataFrame({"Close": [100.0 + i for i in range(N_DAYS)]}, index=rng)

    with patch("backend.data.loader.yf.download", side_effect=fake_download):
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start="2023-01-02",
            end="2024-01-02",
        )

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD
    assert len(report.market_data_hash) == 64
    assert all(c in "0123456789abcdef" for c in report.market_data_hash)
    expected_hash = hashlib.sha256(df.to_csv().encode()).hexdigest()
    assert report.market_data_hash == expected_hash
    assert len(report.fallback_tickers_applied) == 0


# ---------------------------------------------------------------------------
# Test 2 — UCITS fallback triggered
# ---------------------------------------------------------------------------

def test_ucits_fallback_triggered():
    """When UCITS primary tickers return NaN-heavy data on probe,
    ValidatedDataLoader swaps to fallback tickers and records
    the substitution in DataQualityReport.fallback_tickers_applied."""
    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]

    # After fallback resolution: CSPX.L→SPY, AGGH.MI→AGG
    active_after_fallback = ["SPY", "EFA", "AGG", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]
    bulk_df = _make_bulk_df(active_after_fallback)

    ucits_with_fallback = {"CSPX.L", "AGGH.MI"}

    def fake_download(ticker_or_list, **kwargs):
        if isinstance(ticker_or_list, list):
            # Bulk call from _download() — uses active (post-fallback) tickers
            return bulk_df
        # Probe call from _resolve_tickers()
        t = ticker_or_list
        if t in ucits_with_fallback:
            # Simulate UCITS ticker not available on yfinance
            return _make_single_df(t, all_nan=True)
        return _make_single_df(t, all_nan=False)

    with patch("backend.data.loader.yf.download", side_effect=fake_download):
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start="2023-01-02",
            end="2024-01-02",
        )

    # Fallback was recorded for both UCITS tickers
    assert isinstance(report.fallback_tickers_applied, dict)
    assert "CSPX.L" in report.fallback_tickers_applied
    assert "AGGH.MI" in report.fallback_tickers_applied
    assert report.fallback_tickers_applied["CSPX.L"] == "SPY"
    assert report.fallback_tickers_applied["AGGH.MI"] == "AGG"

    # Final data is clean
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD
    assert len(report.market_data_hash) == 64