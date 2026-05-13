from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root without installing the package
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.data.universe_config import get_fallback_map, get_primary_tickers
from backend.optimizer.backtest import LOOKBACK_DAYS, SCENARIOS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NAN_THRESHOLD: float = 0.02
"""Replace ticker with fallback if NaN ratio exceeds this threshold."""

OUTPUT_DIR: Path = ROOT / "data" / "prices"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _business_days_before(date_str: str, n: int) -> str:
    """
    Return the date n business days before date_str as an ISO string.

    Used to extend the download window to cover the lookback period
    needed for covariance estimation on the first rebalance date.
    """
    end = pd.Timestamp(date_str)
    # Offset by n business days (approximate: add 40% buffer for weekends/holidays)
    start = end - pd.offsets.BDay(n + int(n * 0.4))
    return str(start.date())


def _download_tickers(
    tickers: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Download adjusted close prices from yfinance.

    Args:
        tickers: List of ticker symbols.
        start:   Download start date (ISO string, inclusive).
        end:     Download end date (ISO string, inclusive).

    Returns:
        DataFrame of adjusted close prices, DatetimeIndex, columns=tickers.
        Missing tickers produce all-NaN columns (not raised as errors).
    """
    logger.info("Downloading %d tickers from %s to %s ...", len(tickers), start, end)
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    # yfinance returns multi-level columns when multiple tickers are requested
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        # Single ticker — flatten
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

    prices.index = pd.to_datetime(prices.index)
    return prices


def _apply_fallback(
    prices: pd.DataFrame,
    fallback_map: dict[str, str],
    start: str,
    end: str,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Replace sparse primary tickers with their fallback equivalents.

    A primary ticker is replaced if:
    - Its column is entirely absent from the downloaded data, OR
    - Its NaN ratio exceeds NAN_THRESHOLD.

    When replacement is needed, the fallback ticker is downloaded
    separately (if not already present) and substituted in-place.
    The output DataFrame retains the primary ticker column name,
    so downstream code (hrp.py, markowitz.py) does not need to
    be aware of the substitution.

    Args:
        prices:       Downloaded price DataFrame.
        fallback_map: {primary: fallback} from universe_config.
        start:        Download start for fallback re-download.
        end:          Download end for fallback re-download.

    Returns:
        Tuple of (cleaned DataFrame, list of tickers where fallback was applied).
    """
    fallbacks_applied: list[str] = []

    for primary, fallback in fallback_map.items():
        if primary == fallback:
            continue  # US-only ticker, no substitution needed

        needs_fallback = False

        if primary not in prices.columns:
            logger.warning("  %s not in download — will use fallback %s", primary, fallback)
            needs_fallback = True
        else:
            nan_ratio = prices[primary].isna().mean()
            if nan_ratio > NAN_THRESHOLD:
                logger.warning(
                    "  %s NaN ratio %.1f%% > threshold — will use fallback %s",
                    primary, nan_ratio * 100, fallback,
                )
                needs_fallback = True

        if needs_fallback:
            if fallback not in prices.columns:
                fallback_prices = _download_tickers([fallback], start, end)
                prices[fallback] = fallback_prices[fallback]

            # Substitute: rename fallback column to primary ticker name
            prices[primary] = prices[fallback]
            fallbacks_applied.append(primary)
            logger.info("  Applied fallback: %s → %s", primary, fallback)

    return prices, fallbacks_applied


def _validate_prices(prices: pd.DataFrame, scenario_key: str) -> None:
    """
    Assert that the final price DataFrame is usable for backtesting.

    Raises AssertionError if any column has excessive NaN values.
    """
    for ticker in prices.columns:
        nan_ratio = prices[ticker].isna().mean()
        assert nan_ratio <= NAN_THRESHOLD, (
            f"[{scenario_key}] {ticker} still has {nan_ratio:.1%} NaN "
            f"after fallback — check ticker or extend download window."
        )

    assert len(prices) >= LOOKBACK_DAYS + 20, (
        f"[{scenario_key}] Only {len(prices)} rows — "
        f"need at least {LOOKBACK_DAYS + 20} for a valid backtest."
    )
    logger.info(
        "  Validation passed: %d rows × %d tickers, max NaN %.2f%%",
        len(prices),
        len(prices.columns),
        prices.isna().mean().max() * 100,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def download_all_scenarios() -> None:
    """
    Download and save price CSVs for all three backtest scenarios.

    For each scenario:
    1. Compute the required download window (test period + lookback).
    2. Download all primary tickers.
    3. Apply UCITS → US fallback where data is sparse.
    4. Validate the resulting DataFrame.
    5. Forward-fill up to 5 consecutive NaN values (exchange holiday gaps).
    6. Save to data/prices/prices_{scenario_key}.csv.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    primary_tickers = get_primary_tickers()
    fallback_map = get_fallback_map()

    for scenario_key, meta in SCENARIOS.items():
        logger.info("=== Scenario: %s ===", meta["label"])

        # Extend start to cover the lookback window before test_start
        download_start = _business_days_before(meta["test_start"], LOOKBACK_DAYS)
        download_end = meta["test_end"]

        logger.info("  Window: %s → %s", download_start, download_end)

        # Download all primary tickers in one batch
        prices = _download_tickers(primary_tickers, download_start, download_end)

        # Apply fallback for sparse/missing UCITS tickers
        prices, fallbacks_applied = _apply_fallback(
            prices, fallback_map, download_start, download_end
        )

        if fallbacks_applied:
            logger.info("  Fallbacks applied: %s", fallbacks_applied)
        else:
            logger.info("  No fallbacks needed — all primary tickers available.")

        # Forward-fill short gaps (exchange holidays, bank holidays)
        prices = prices.ffill(limit=5)

        # Drop any remaining rows with NaN (e.g. first row after pct_change)
        prices = prices.dropna()

        # Final validation
        _validate_prices(prices, scenario_key)

        # Save
        out_path = OUTPUT_DIR / f"prices_{scenario_key}.csv"
        prices.to_csv(out_path)
        logger.info("  Saved → %s  (%d rows)", out_path, len(prices))

    logger.info("Done. All scenario price files saved to %s", OUTPUT_DIR)


if __name__ == "__main__":
    download_all_scenarios()
