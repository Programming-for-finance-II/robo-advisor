"""
scripts/run_backtest.py
Run walk-forward backtests for all profiles and stress scenarios.

Usage:
    python scripts/run_backtest.py [--profiles CONSERVATIVE MODERATE AGGRESSIVE]

Downloads price CSVs to data/prices/, runs the backtest engine, and writes
JSON output to backtest_output/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.data.universe_config import get_cluster_map, get_fallback_map, get_primary_tickers
from backend.optimizer.backtest import (
    LOOKBACK_DAYS,
    SCENARIOS,
    ScenarioResult,
    export_results_json,
    run_scenario,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PRICES_DIR = ROOT / "data" / "prices"
OUTPUT_DIR = ROOT / "backtest_output"
NAN_THRESHOLD = 0.02


def _business_days_before(date_str: str, n: int) -> str:
    end = pd.Timestamp(date_str)
    start = end - pd.offsets.BDay(n + int(n * 0.4))
    return str(start.date())


def _download_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    logger.info("Downloading %d tickers %s → %s", len(tickers), start, end)
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False, threads=True)
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": tickers[0]})
    prices.index = pd.to_datetime(prices.index)
    return prices


def _apply_fallback(prices: pd.DataFrame, fallback_map: dict[str, str], start: str, end: str) -> pd.DataFrame:
    for primary, fallback in fallback_map.items():
        if primary == fallback:
            continue
        needs_fallback = (
            primary not in prices.columns
            or prices[primary].isna().mean() > NAN_THRESHOLD
        )
        if needs_fallback:
            logger.warning("  Fallback: %s → %s", primary, fallback)
            if fallback not in prices.columns:
                fb_prices = _download_prices([fallback], start, end)
                prices[fallback] = fb_prices[fallback]
            prices[primary] = prices[fallback]
    return prices


def load_scenario_prices(scenario_key: str, meta: dict) -> pd.DataFrame:
    """Download (or load cached) prices for a single scenario."""
    csv_path = PRICES_DIR / f"prices_{scenario_key}.csv"
    if csv_path.exists():
        logger.info("Loading cached prices: %s", csv_path)
        prices = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        return prices

    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    download_start = _business_days_before(meta["test_start"], LOOKBACK_DAYS)
    download_end = meta["test_end"]

    primary_tickers = get_primary_tickers()
    fallback_map = get_fallback_map()

    prices = _download_prices(primary_tickers, download_start, download_end)
    prices = _apply_fallback(prices, fallback_map, download_start, download_end)
    prices = prices.ffill(limit=5).dropna()

    assert len(prices) >= LOOKBACK_DAYS + 20, (
        f"[{scenario_key}] Too few rows: {len(prices)}"
    )
    prices.to_csv(csv_path)
    logger.info("Saved prices → %s  (%d rows)", csv_path, len(prices))
    return prices


def run_for_profile(profile: str) -> None:
    logger.info("=== Profile: %s ===", profile)
    cluster_map = get_cluster_map()

    all_results: dict[str, ScenarioResult] = {}
    for scenario_key, meta in SCENARIOS.items():
        logger.info("  Scenario: %s", meta["label"])
        prices = load_scenario_prices(scenario_key, meta)
        result = run_scenario(prices, profile, cluster_map, scenario_key)  # type: ignore[arg-type]
        all_results[scenario_key] = result

    export_results_json(all_results, OUTPUT_DIR, profile)
    logger.info("Done: %s", profile)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward backtests")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["CONSERVATIVE", "MODERATE", "AGGRESSIVE"],
        choices=["CONSERVATIVE", "MODERATE", "AGGRESSIVE"],
        help="Profiles to run (default: all three)",
    )
    args = parser.parse_args()

    for profile in args.profiles:
        run_for_profile(profile)

    logger.info("All done. Output in %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()
