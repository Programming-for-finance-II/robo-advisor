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
    """
    Snapshot of portfolio value on a single trading day.
    
    Attributes:
        date: Trading date in ISO format (YYYY-MM-DD).
        portfolio_value: Cumulative portfolio value (normalized to 1.0 at start).
    """
    date: str
    portfolio_value: float


@dataclass
class RebalanceEvent:
    """
    Record of a single portfolio rebalancing event.
    
    Attributes:
        date: Rebalancing date in ISO format (YYYY-MM-DD).
        weights: Target portfolio weights for each ticker (summing to 1.0).
        turnover: One-way turnover (sum of absolute weight changes).
        transaction_cost: Transaction cost incurred (as fraction of portfolio value).
    """
    date: str
    weights: dict[str, float]
    turnover: float
    transaction_cost: float


@dataclass
class StrategyResult:
    """
    Complete backtest results for a single strategy.
    
    Attributes:
        strategy: Strategy identifier ("HRP", "MV", or "1/N").
        cagr: Compound Annual Growth Rate.
        annualised_volatility: Annualized standard deviation of daily returns.
        sharpe_ratio: CAGR divided by annualized volatility.
        max_drawdown: Maximum peak-to-trough decline (negative value).
        calmar_ratio: CAGR divided by absolute max drawdown.
        total_transaction_cost: Cumulative transaction costs (fraction of initial capital).
        n_rebalances: Total number of rebalancing events.
        equity_curve: Daily portfolio values throughout the backtest.
        rebalance_log: Log of all rebalancing events.
    """
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
    """
    Backtest results for all strategies in a single stress-test scenario.
    
    Attributes:
        scenario_key: Machine-readable scenario identifier