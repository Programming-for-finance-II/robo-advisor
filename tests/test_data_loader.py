"""
test_data_loader.py — Unit tests for ValidatedDataLoader.

All yfinance calls are mocked: tests run offline and deterministically.
Tests cover:
  1. Happy path — clean data, correct hash and report fields.
  2. UCITS fallback — primary ticker returns NaN-heavy data,
     fallback ticker is used and recorded in DataQualityReport.
"""

from __future__ import annotations

import hashlib
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.data.loader import DataQualityReport, ValidatedDataLoader


# ---------------------------------------------------------------------------
# Helpers — synthetic price DataFrames
# ---------------------------------------------------------------------------

def _make_prices(tickers: list[str], n_days: int = 300) -> pd.DataFrame:
    """Return a clean DataFrame of fake closing prices, UTC-indexed."""


    rng = pd.date_range("2023-01-02", periods=n_days, freq="B", tz="UTC")
    data = {t: 100.0 + i + pd.Series(range(n_days), dtype=float).values
            for i, t in enumerate(tickers)}
    return pd.DataFrame(data, index=rng)


def _make_nan_prices(tickers: list[str], n_days: int = 300) -> pd.DataFrame:
    """Return a DataFrame where every value is NaN (simulates missing UCITS ticker)."""
    rng = pd.date_range("2023-01-02", periods=n_days, freq="B", tz="UTC")
    data = {t: float("nan") for t in tickers}
    return pd.DataFrame(data, index=rng)


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------

def test_load_happy_path():
    """ValidatedDataLoader returns correct DataFrame and DataQualityReport
    when yfinance delivers clean data for all tickers."""

    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]
    clean_df = _make_prices(tickers)

    # Patch yf.download to return our synthetic prices
    with patch("backend.data.loader.yf.download", return_value=clean_df) as mock_dl:
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start=date(2023, 1, 2),
            end=date(2024, 1, 2),
        )

    # Shape checks
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    # NaN gate passed
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD

    # Hash is a valid SHA-256 hex string
    assert isinstance(report.market_data_hash, str)
    assert len(report.market_data_hash) == 64
    assert all(c in "0123456789abcdef" for c in report.market_data_hash)

    # Hash is reproducible — same data → same hash
    expected_hash = hashlib.sha256(df.to_csv().encode()).hexdigest()
    assert report.market_data_hash == expected_hash

    # No fallback was needed
    assert report.fallback_tickers_applied == []

    # yfinance was called exactly once
    mock_dl.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — UCITS fallback triggered
# ---------------------------------------------------------------------------

def test_ucits_fallback_triggered():
    """When a UCITS primary ticker returns NaN-heavy data,
    ValidatedDataLoader swaps to the fallback ticker and records
    the substitution in DataQualityReport.fallback_tickers_applied."""

    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]

    # First download: CSPX.L and AGGH.MI are all-NaN (UCITS unavailable)
    primary_df = _make_prices(tickers)
    primary_df["CSPX.L"] = float("nan")   # simulate UCITS ticker missing
    primary_df["AGGH.MI"] = float("nan")  # simulate second UCITS ticker missing

    # Fallback downloads return clean single-column Series
    fallback_spy = _make_prices(["SPY"])["SPY"]
    fallback_agg = _make_prices(["AGG"])["AGG"]

    download_call_count = 0

    def fake_download(ticker_or_list, **kwargs):
        nonlocal download_call_count
        download_call_count += 1

        # First call → full universe (with NaN on UCITS)
        if download_call_count == 1:
            return primary_df

        # Subsequent calls → individual fallback tickers
        if ticker_or_list == "SPY":
            return pd.DataFrame({"Close": fallback_spy})
        if ticker_or_list == "AGG":
            return pd.DataFrame({"Close": fallback_agg})

        return _make_prices([ticker_or_list])

    with patch("backend.data.loader.yf.download", side_effect=fake_download):
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start=date(2023, 1, 2),
            end=date(2024, 1, 2),
        )

    # Fallback was applied for both UCITS tickers
    assert len(report.fallback_tickers_applied) == 2
    assert any("CSPX.L" in s for s in report.fallback_tickers_applied)
    assert any("AGGH.MI" in s for s in report.fallback_tickers_applied)

    # Final DataFrame has no excessive NaN
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD

    # Hash is still computed on the final (post-fallback) prices
    assert len(report.market_data_hash) == 64
