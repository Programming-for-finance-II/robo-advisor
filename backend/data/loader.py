"""
ValidatedDataLoader — backend/data/loader.py
============================================
Downloads, validates and cleans market price data from yfinance.

Implements:
- NaN gate: rejects data with NaN ratio > 2%
- Forward-fill: fills gaps up to 2 consecutive days
- SHA-256 hash: for audit trail and DB deduplication
- UCITS fallback: substitutes tickers with excessive NaN
  using the fallback map from universe_config.py

Consumed by:
  - backend/api/         (all endpoints that need price data)
  - backend/optimizer/   (hrp.py, markowitz.py)
  - tests/test_data_loader.py
  - tests/test_ucits_fallback.py


"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import yfinance as yf

from backend.data.universe_config import get_fallback_map, get_ucits_tickers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DataQualityError(Exception):
    """Raised when downloaded data fails quality checks."""


# ---------------------------------------------------------------------------
# DataQualityReport — returned alongside prices for audit trail
# ---------------------------------------------------------------------------

@dataclass
class DataQualityReport:
    """
    Summary of data quality checks performed during loading.

    Stored in the DB as part of the recommendation audit trail.
    All fields map directly to columns in the recommendations table.
    """
    nan_ratio: float
    missing_tickers: list[str]
    date_range: tuple[date, date]
    n_observations: int
    market_data_hash: str
    ucits_tickers_used: list[str]
    fallback_tickers_applied: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for DB storage and Ground Truth JSON."""
        return {
            "nan_ratio": round(self.nan_ratio, 6),
            "missing_tickers": self.missing_tickers,
            "date_range": [
                self.date_range[0].isoformat(),
                self.date_range[1].isoformat(),
            ],
            "n_observations": self.n_observations,
            "market_data_hash": self.market_data_hash,
            "ucits_tickers_used": self.ucits_tickers_used,
            "fallback_tickers_applied": self.fallback_tickers_applied,
        }


# ---------------------------------------------------------------------------
# ValidatedDataLoader
# ---------------------------------------------------------------------------

class ValidatedDataLoader:
    """
    Downloads and validates historical adjusted close prices.

    Parameters
    ----------
    nan_threshold : float
        Maximum acceptable NaN ratio before raising DataQualityError.
        Default 0.02 (2%) per design v3.1.
    ffill_limit : int
        Maximum consecutive NaN days to forward-fill. Default 2.
    min_observations : int
        Minimum number of valid trading days required. Default 252 (1 year).

    Raises
    ------
    DataQualityError
        If NaN ratio exceeds threshold after forward-fill,
        or if fewer than min_observations rows remain.
    """

    NAN_THRESHOLD: float = 0.02
    FFILL_LIMIT: int = 2
    MIN_OBSERVATIONS: int = 252

    def __init__(
        self,
        nan_threshold: float = NAN_THRESHOLD,
        ffill_limit: int = FFILL_LIMIT,
        min_observations: int = MIN_OBSERVATIONS,
    ) -> None:
        self.nan_threshold = nan_threshold
        self.ffill_limit = ffill_limit
        self.min_observations = min_observations
        self._fallback_map = get_fallback_map()
        self._ucits_tickers = set(get_ucits_tickers())

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> tuple[pd.DataFrame, DataQualityReport]:
        """
        Download, validate and clean price data for the given tickers.

        Parameters
        ----------
        tickers : list[str]
            Primary tickers to load (from universe_config.get_primary_tickers()).
        start : str
            Start date in 'YYYY-MM-DD' format.
        end : str
            End date in 'YYYY-MM-DD' format.

        Returns
        -------
        prices : pd.DataFrame
            Cleaned adjusted close prices. Index is DatetimeIndex (UTC).
            Columns are the active tickers (primary or fallback).
        report : DataQualityReport
            Quality metrics and provenance metadata for audit trail.
        """
        active_tickers, fallback_applied = self._resolve_tickers(tickers, start, end)
        prices = self._download(active_tickers, start, end)
        prices = self._clean(prices)
        report = self._build_report(prices, active_tickers, fallback_applied)
        return prices, report

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _resolve_tickers(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> tuple[list[str], dict[str, str]]:
        """
        Check each primary ticker and substitute fallback if data is poor.

        Returns active ticker list and a dict of substitutions applied.
        """
        fallback_applied: dict[str, str] = {}
        active: list[str] = []

        for ticker in tickers:
            fallback = self._fallback_map.get(ticker, ticker)
            if fallback == ticker:
                # No UCITS alternative — use as-is
                active.append(ticker)
                continue

            # Check primary ticker quality
            try:
                raw = yf.download(
                    ticker,
                    start=start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                )
                close = self._extract_close(raw, ticker)
                nan_ratio = close.isna().mean()

                if nan_ratio > self.nan_threshold:
                    logger.warning(
                        "Ticker %s NaN ratio %.3f > threshold %.3f — "
                        "switching to fallback %s",
                        ticker, nan_ratio, self.nan_threshold, fallback,
                    )
                    active.append(fallback)
                    fallback_applied[ticker] = fallback
                else:
                    active.append(ticker)

            except Exception as exc:
                logger.warning(
                    "Failed to probe ticker %s (%s) — using fallback %s",
                    ticker, exc, fallback,
                )
                active.append(fallback)
                fallback_applied[ticker] = fallback

        return active, fallback_applied

    def _download(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        """Download adjusted close prices for all active tickers."""
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            raise DataQualityError("yfinance returned empty DataFrame.")

        return self._extract_close(raw, tickers)

    def _extract_close(self, raw: pd.DataFrame, tickers) -> pd.DataFrame:
        """Extract 'Close' column(s) from yfinance multi-level output."""
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            # Single ticker — raw is already a Series or flat DataFrame
            prices = raw[["Close"]] if "Close" in raw.columns else raw
            if isinstance(tickers, str):
                prices.columns = [tickers]
        return prices

    def _clean(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Forward-fill gaps, drop remaining NaN, validate quality."""
        prices = prices.ffill(limit=self.ffill_limit).dropna()

        if prices.empty:
            raise DataQualityError("No valid rows remain after cleaning.")

        nan_ratio = prices.isna().mean().mean()
        if nan_ratio > self.nan_threshold:
            raise DataQualityError(
                f"NaN ratio {nan_ratio:.4f} exceeds threshold "
                f"{self.nan_threshold:.4f} after forward-fill."
            )

        if len(prices) < self.min_observations:
            raise DataQualityError(
                f"Only {len(prices)} observations after cleaning — "
                f"minimum required: {self.min_observations}."
            )

        # Ensure UTC-aware DatetimeIndex
        if prices.index.tz is None:
            prices.index = prices.index.tz_localize("UTC")

        return prices

    def _build_report(
        self,
        prices: pd.DataFrame,
        active_tickers: list[str],
        fallback_applied: dict[str, str],
    ) -> DataQualityReport:
        """Build DataQualityReport from cleaned prices."""
        nan_ratio = prices.isna().mean().mean()
        market_data_hash = hashlib.sha256(
            prices.to_csv().encode()
        ).hexdigest()

        ucits_in_use = [t for t in active_tickers if t in self._ucits_tickers]

        return DataQualityReport(
            nan_ratio=float(nan_ratio),
            missing_tickers=[
                t for t in active_tickers if t not in prices.columns
            ],
            date_range=(
                prices.index[0].date(),
                prices.index[-1].date(),
            ),
            n_observations=len(prices),
            market_data_hash=market_data_hash,
            ucits_tickers_used=ucits_in_use,
            fallback_tickers_applied=fallback_applied,
        )
