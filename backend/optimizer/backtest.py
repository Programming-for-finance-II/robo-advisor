from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from backend.optimizer.hrp import ProfileLabel, optimize
from backend.optimizer.markowitz import optimize_markowitz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TC_BPS: int = 10
"""Transaction cost in basis points per rebalancing event (one-way turnover)."""

LOOKBACK_DAYS: int = 252
"""Rolling lookback window for covariance/return estimation (≈ 1 trading year)."""

REBALANCE_FREQ: str = "ME"
"""Pandas offset alias: month-end rebalancing."""

StrategyLabel = Literal["HRP", "MV", "1/N"]

SCENARIOS: dict[str, dict[str, str]] = {
    "gfc_2008": {
        "label": "Global Financial Crisis (2008)",
        "test_start": "2008-01-02",
        "test_end": "2009-06-30",
    },
    "covid_2020": {
        "label": "COVID-19 Crash (2020)",
        "test_start": "2020-01-02",
        "test_end": "2020-12-31",
    },
    "rate_hike_2022": {
        "label": "Rate Hike Cycle (2022)",
        "test_start": "2022-01-03",
        "test_end": "2022-12-30",
    },
}

# ---------------------------------------------------------------------------
# Output dataclasses (JSON-serialisable via asdict())
# ---------------------------------------------------------------------------

@dataclass
class DailyReturn:
    date: str
    portfolio_value: float


@dataclass
class RebalanceEvent:
    date: str
    weights: dict[str, float]
    turnover: float
    transaction_cost: float


@dataclass
class StrategyResult:
    strategy: StrategyLabel
    cagr: float
    annualised_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    total_transaction_cost: float
    n_rebalances: int
    equity_curve: list[DailyReturn]
    rebalance_log: list[RebalanceEvent]


@dataclass
class ScenarioResult:
    scenario_key: str
    scenario_label: str
    test_start: str
    test_end: str
    profile: str
    tickers_used: list[str]
    strategies: dict[str, StrategyResult]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _equal_weights(tickers: list[str]) -> dict[str, float]:
    """Return equal-weight allocation."""
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def _get_weights(
    prices_window: pd.DataFrame,
    profile: ProfileLabel,
    cluster_map: dict[str, str],
    strategy: StrategyLabel,
) -> dict[str, float]:
    """
    Dispatch to the correct optimiser for the given strategy.

    Args:
        prices_window: Price DataFrame for the lookback window (dates × tickers).
        profile:       Investor risk profile.
        cluster_map:   Asset → cluster mapping from universe_config.
        strategy:      One of "HRP", "MV", "1/N".

    Returns:
        Dictionary of ticker → portfolio weight, summing to 1.0.
    """
    tickers = list(prices_window.columns)

    if strategy == "1/N":
        return _equal_weights(tickers)

    if strategy == "HRP":
        result = optimize(prices_window, profile, cluster_map)
        return result["weights"]

    if strategy == "MV":
        # optimize_markowitz takes only prices — no profile tilt, no cluster_map.
        # MV is a pure Max-Sharpe benchmark; profile-awareness is HRP's differentiator.
        result = optimize_markowitz(prices_window)
        return result["weights"]

    raise ValueError(f"Unknown strategy: {strategy!r}")


def _compute_performance_metrics(
    daily_rets: pd.Series,
) -> tuple[float, float, float, float, float]:
    """
    Compute CAGR, annualised volatility, Sharpe, max drawdown, Calmar.

    Args:
        daily_rets: Daily portfolio return series (net of transaction costs).

    Returns:
        Tuple (cagr, vol, sharpe, max_dd, calmar).
    """
    n_days = len(daily_rets)
    assert n_days > 1, "need at least 2 daily returns to compute metrics"

    n_years = n_days / 252

    # Compound total return → CAGR
    total_ret = (1.0 + daily_rets).prod() - 1.0
    cagr = (1.0 + total_ret) ** (1.0 / n_years) - 1.0

    vol = float(daily_rets.std() * np.sqrt(252))
    sharpe = cagr / vol if vol > 0 else 0.0

    # Maximum drawdown from the equity curve
    cum = (1.0 + daily_rets).cumprod()
    rolling_max = cum.cummax()
    drawdowns = cum / rolling_max - 1.0
    max_dd = float(drawdowns.min())

    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    return float(cagr), vol, float(sharpe), max_dd, float(calmar)


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------

def _run_strategy_backtest(
    prices: pd.DataFrame,
    profile: ProfileLabel,
    cluster_map: dict[str, str],
    strategy: StrategyLabel,
    test_start: str,
    test_end: str,
) -> StrategyResult:
    """
    Run a single-strategy backtest over the test period.

    Rebalances monthly (month-end). On each rebalance day:
      1. Estimate weights on the prior LOOKBACK_DAYS of prices.
      2. Compute turnover vs current holdings.
      3. Deduct transaction cost (TC_BPS bps × turnover) from that day's return.
      4. Update holdings to new weights.

    Args:
        prices:      Full price history (must cover at least LOOKBACK_DAYS
                     before test_start). Columns = tickers, index = DatetimeIndex.
        profile:     Investor risk profile.
        cluster_map: Asset → cluster mapping.
        strategy:    Strategy label.
        test_start:  First day of the test period (ISO string).
        test_end:    Last day of the test period (ISO string).

    Returns:
        StrategyResult dataclass with all metrics and time-series logs.
    """
    tickers = list(prices.columns)

    # Test-period price slice for daily return computation
    test_prices = prices.loc[test_start:test_end]
    assert len(test_prices) >= 20, (
        f"Test period too short for {strategy}: only {len(test_prices)} trading days"
    )
    test_daily_rets = test_prices.pct_change().fillna(0.0)

    # Month-end rebalance dates within the test period
    rebalance_dates: set[pd.Timestamp] = set(
        pd.date_range(test_start, test_end, freq=REBALANCE_FREQ)
        .intersection(test_prices.index)
    )
    # Always rebalance on the first day of the test period
    rebalance_dates.add(test_prices.index[0])

    # State
    current_weights: dict[str, float] = _equal_weights(tickers)
    portfolio_value: float = 1.0
    total_tc: float = 0.0
    n_rebalances: int = 0

    equity_curve: list[DailyReturn] = []
    rebalance_log: list[RebalanceEvent] = []
    daily_ret_list: list[float] = []

    for date in test_prices.index:
        tc_today: float = 0.0

        if date in rebalance_dates:
            # Build lookback window ending on the day before today
            lookback_end = prices.index[prices.index.get_loc(date) - 1]
            lookback_start_pos = max(0, prices.index.get_loc(lookback_end) - LOOKBACK_DAYS + 1)
            lookback_start = prices.index[lookback_start_pos]
            prices_window = prices.loc[lookback_start:lookback_end]

            if len(prices_window) >= 60:
                try:
                    new_weights = _get_weights(prices_window, profile, cluster_map, strategy)
                except Exception as exc:
                    logger.warning(
                        "Optimisation failed on %s for %s (%s), keeping current weights: %s",
                        date.date(), strategy, profile, exc,
                    )
                    new_weights = current_weights
            else:
                logger.warning(
                    "Lookback window too small (%d days) on %s — keeping current weights",
                    len(prices_window), date.date(),
                )
                new_weights = current_weights

            # Turnover = total one-way portfolio change
            all_tickers = set(new_weights) | set(current_weights)
            turnover = sum(
                abs(new_weights.get(t, 0.0) - current_weights.get(t, 0.0))
                for t in all_tickers
            )
            tc_today = (TC_BPS / 10_000) * turnover
            total_tc += tc_today
            n_rebalances += 1

            rebalance_log.append(RebalanceEvent(
                date=str(date.date()),
                weights={t: round(w, 6) for t, w in new_weights.items()},
                turnover=round(turnover, 6),
                transaction_cost=round(tc_today, 6),
            ))
            current_weights = new_weights

        # Daily portfolio return: weighted sum of asset returns − transaction cost
        asset_rets = test_daily_rets.loc[date]
        port_ret = float(sum(
            current_weights.get(t, 0.0) * asset_rets.get(t, 0.0)
            for t in tickers
        )) - tc_today

        daily_ret_list.append(port_ret)
        portfolio_value *= (1.0 + port_ret)

        equity_curve.append(DailyReturn(
            date=str(date.date()),
            portfolio_value=round(portfolio_value, 6),
        ))

    daily_rets_series = pd.Series(daily_ret_list, index=test_prices.index)
    cagr, vol, sharpe, max_dd, calmar = _compute_performance_metrics(daily_rets_series)

    return StrategyResult(
        strategy=strategy,
        cagr=round(cagr, 6),
        annualised_volatility=round(vol, 6),
        sharpe_ratio=round(sharpe, 6),
        max_drawdown=round(max_dd, 6),
        calmar_ratio=round(calmar, 6),
        total_transaction_cost=round(total_tc, 6),
        n_rebalances=n_rebalances,
        equity_curve=equity_curve,
        rebalance_log=rebalance_log,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_scenario(
    prices: pd.DataFrame,
    profile: ProfileLabel,
    cluster_map: dict[str, str],
    scenario_key: str,
) -> ScenarioResult:
    """
    Run HRP, MV, and 1/N backtests for a single named scenario.

    The prices DataFrame must cover at least LOOKBACK_DAYS before the
    scenario test_start — caller is responsible for downloading enough history.

    Args:
        prices:       Price history, index=DatetimeIndex, columns=tickers.
        profile:      Investor risk profile label.
        cluster_map:  Asset → cluster mapping.
        scenario_key: Key from the SCENARIOS dict (e.g. "covid_2020").

    Returns:
        ScenarioResult with results for all three strategies.
    """
    assert scenario_key in SCENARIOS, (
        f"Unknown scenario key {scenario_key!r}. "
        f"Available: {list(SCENARIOS.keys())}"
    )
    meta = SCENARIOS[scenario_key]
    test_start = meta["test_start"]
    test_end = meta["test_end"]

    strategies_results: dict[str, StrategyResult] = {}
    for strategy in ("HRP", "MV", "1/N"):
        logger.info("Running %s / %s / %s", scenario_key, profile, strategy)
        strategies_results[strategy] = _run_strategy_backtest(
            prices=prices,
            profile=profile,
            cluster_map=cluster_map,
            strategy=strategy,  # type: ignore[arg-type]
            test_start=test_start,
            test_end=test_end,
        )

    return ScenarioResult(
        scenario_key=scenario_key,
        scenario_label=meta["label"],
        test_start=test_start,
        test_end=test_end,
        profile=profile,
        tickers_used=list(prices.columns),
        strategies=strategies_results,
    )


def run_all_scenarios(
    prices: pd.DataFrame,
    profile: ProfileLabel,
    cluster_map: dict[str, str],
) -> dict[str, ScenarioResult]:
    """
    Run all three stress scenarios and return a keyed results dict.

    Args:
        prices:      Full price history covering 2006-2023 (for all scenarios).
        profile:     Investor risk profile label.
        cluster_map: Asset → cluster mapping.

    Returns:
        Dict mapping scenario_key → ScenarioResult.
    """
    results: dict[str, ScenarioResult] = {}
    for scenario_key in SCENARIOS:
        results[scenario_key] = run_scenario(prices, profile, cluster_map, scenario_key)
    return results


def export_results_json(
    results: dict[str, ScenarioResult],
    output_dir: Path,
    profile: str,
) -> None:
    """
    Serialise backtest results to JSON files.

    Writes one file per scenario plus a summary file:
        {output_dir}/backtest_{scenario_key}_{profile}.json
        {output_dir}/backtest_summary_{profile}.json

    Args:
        results:    Output of run_all_scenarios().
        output_dir: Target directory (created if absent).
        profile:    Profile label string, used in filename.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict] = {}

    for key, result in results.items():
        # Per-scenario full file (equity curve + rebalance log)
        scenario_path = output_dir / f"backtest_{key}_{profile.lower()}.json"
        with scenario_path.open("w") as fh:
            json.dump(asdict(result), fh, indent=2)
        logger.info("Exported %s", scenario_path)

        # Summary entry (metrics only — no time-series)
        summary[key] = {
            "scenario_label": result.scenario_label,
            "test_start": result.test_start,
            "test_end": result.test_end,
            "profile": result.profile,
            "strategies": {
                strat: {
                    "cagr": sr.cagr,
                    "annualised_volatility": sr.annualised_volatility,
                    "sharpe_ratio": sr.sharpe_ratio,
                    "max_drawdown": sr.max_drawdown,
                    "calmar_ratio": sr.calmar_ratio,
                    "total_transaction_cost": sr.total_transaction_cost,
                    "n_rebalances": sr.n_rebalances,
                }
                for strat, sr in result.strategies.items()
            },
        }

    summary_path = output_dir / f"backtest_summary_{profile.lower()}.json"
    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)
    logger.info("Exported summary → %s", summary_path)
