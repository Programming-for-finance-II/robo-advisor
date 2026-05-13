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
    Represents a single daily portfolio value observation.

    Attributes:
        date: ISO-formatted date string (YYYY-MM-DD).
        portfolio_value: Portfolio value at end of day (starts at 1.0).
    """
    date: str
    portfolio_value: float


@dataclass
class RebalanceEvent:
    """
    Records a single portfolio rebalancing event.

    Attributes:
        date: ISO-formatted date string when rebalancing occurred.
        weights: Dictionary mapping ticker symbols to their new portfolio weights.
        turnover: Total one-way portfolio change (sum of absolute weight differences).
        transaction_cost: Cost incurred as fraction of portfolio value.
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
        strategy: Strategy label (HRP, MV, or 1/N).
        cagr: Compound annual growth rate.
        annualised_volatility: Annualised standard deviation of returns.
        sharpe_ratio: Sharpe ratio (CAGR / volatility).
        max_drawdown: Maximum peak-to-trough decline (negative value).
        calmar_ratio: CAGR divided by absolute max drawdown.
        total_transaction_cost: Cumulative transaction costs as fraction of initial capital.
        n_rebalances: Total number of rebalancing events.
        equity_curve: Daily portfolio value time series.
        rebalance_log: Record of all rebalancing events with weights and costs.
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
    Backtest results for all strategies within a single stress-test scenario.

    Attributes:
        scenario_key: Unique identifier for the scenario (e.g., 'covid_2020').
        scenario_label: Human-readable scenario