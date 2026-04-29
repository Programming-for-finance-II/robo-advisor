"""
test_data_loader.py — Unit tests for ValidatedDataLoader.

All yfinance calls are mocked: tests run offline and deterministically.
The loader probes each UCITS ticker individually after the bulk download,
so the mock must handle both bulk (list) and single-ticker (str) calls.
"""

from __future__ import annotations

import hashlib
from datetime import date
from unittest.mock import patch

import pandas as pd

from backend.data.loader import ValidatedDataLoader


def _make_prices(tickers: list[str], n_days: int = 300) -> pd.DataFrame:
    """Return a clean DataFrame of fake closing prices, UTC-indexed."""
    rng = pd.date_range("2023-01-02", periods=n_days, freq="B", tz="UTC")
    data = {
        t: 100.0 + i + pd.Series(range(n_days), dtype=float).values
        for i, t in enumerate(tickers)
    }
    return pd.DataFrame(data, index=rng)


def _fake_download_factory(full_df: pd.DataFrame):
    """Return a mock for yf.download that handles both bulk and probe calls.

    The loader calls yf.download in two ways:
      1. Bulk: yf.download([t1, t2, ...]) → return full_df
      2. Probe: yf.download("CSPX.L")    → return single-column DataFrame

    This factory produces a mock that responds correctly to both.
    """
    def fake_download(ticker_or_list, **kwargs):
        # Normalize input to list
        if isinstance(ticker_or_list, str):
            requested = [ticker_or_list]
        else:
            requested = list(ticker_or_list)

        if len(requested) > 1:
            # Bulk download — return full DataFrame
            return full_df

        # Single-ticker probe — return just that column
        t = requested[0]
        if t in full_df.columns:
            return full_df[[t]]
        # Unknown ticker — return clean single-column data
        return _make_prices([t])

    return fake_download


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------

def test_load_happy_path():
    """ValidatedDataLoader returns correct DataFrame and DataQualityReport
    when yfinance delivers clean data for all tickers."""
    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]
    clean_df = _make_prices(tickers)

    with patch(
        "backend.data.loader.yf.download",
        side_effect=_fake_download_factory(clean_df),
    ):
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start=date(2023, 1, 2),
            end=date(2024, 1, 2),
        )

    # Shape and content
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    # NaN gate passed
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD

    # Hash is a valid 64-char SHA-256 hex string
    assert len(report.market_data_hash) == 64
    assert all(c in "0123456789abcdef" for c in report.market_data_hash)

    # Hash is reproducible
    expected_hash = hashlib.sha256(df.to_csv().encode()).hexdigest()
    assert report.market_data_hash == expected_hash

    # No fallback needed — empty (list or dict)
    assert len(report.fallback_tickers_applied) == 0


# ---------------------------------------------------------------------------
# Test 2 — UCITS fallback triggered
# ---------------------------------------------------------------------------

def test_ucits_fallback_triggered():
    """When UCITS primary tickers return NaN-heavy data, ValidatedDataLoader
    swaps to fallback tickers and records the substitution."""
    tickers = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]

    # Build primary DataFrame: CSPX.L and AGGH.MI are all-NaN
    primary_df = _make_prices(tickers)
    primary_df["CSPX.L"] = float("nan")
    primary_df["AGGH.MI"] = float("nan")

    fallback_spy = _make_prices(["SPY"])
    fallback_agg = _make_prices(["AGG"])

    def fake_download(ticker_or_list, **kwargs):
        if isinstance(ticker_or_list, str):
            requested = [ticker_or_list]
        else:
            requested = list(ticker_or_list)

        if len(requested) > 1:
            # Bulk download — NaN on UCITS tickers
            return primary_df

        t = requested[0]
        # Probe: UCITS tickers return NaN → triggers fallback
        if t == "CSPX.L":
            nan_df = _make_prices(["CSPX.L"])
            nan_df["CSPX.L"] = float("nan")
            return nan_df
        if t == "AGGH.MI":
            nan_df = _make_prices(["AGGH.MI"])
            nan_df["AGGH.MI"] = float("nan")
            return nan_df
        # Fallback tickers return clean data
        if t == "SPY":
            return fallback_spy
        if t == "AGG":
            return fallback_agg
        # Other tickers: return their column from primary_df
        if t in primary_df.columns:
            return primary_df[[t]]
        return _make_prices([t])

    with patch("backend.data.loader.yf.download", side_effect=fake_download):
        loader = ValidatedDataLoader()
        df, report = loader.load(
            tickers=tickers,
            start=date(2023, 1, 2),
            end=date(2024, 1, 2),
        )

    # Fallback was applied — at least CSPX.L and AGGH.MI
    assert len(report.fallback_tickers_applied) >= 2

    # Works regardless of whether fallback_tickers_applied is dict or list
    applied = report.fallback_tickers_applied
    if isinstance(applied, dict):
        assert "CSPX.L" in applied
        assert "AGGH.MI" in applied
    else:
        assert any("CSPX.L" in s for s in applied)
        assert any("AGGH.MI" in s for s in applied)

    # Final data is clean
    assert report.nan_ratio < ValidatedDataLoader.NAN_THRESHOLD
    assert len(report.market_data_hash) == 64