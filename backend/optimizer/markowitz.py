from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pypfopt import CovarianceShrinkage, EfficientFrontier, expected_returns

from backend.optimizer.hrp import OPTIMIZER_VERSION, OptimizationResult
from backend.optimizer.risk_metrics import compute_risk_contributions
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Asset-level weight bounds — same guardrails as HRP for fair comparison
MV_ASSET_MIN: float = 0.03
MV_ASSET_MAX: float = 0.40

# Risk-free rate for Sharpe computation (annualised, approximate EUR rate 2024)
RISK_FREE_RATE: float = 0.03

# Return estimation method — historical mean log returns, annualised
RETURNS_FREQUENCY: int = 252


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def optimize_markowitz(
    prices: pd.DataFrame,
    ucits_tickers: list[str] | None = None,
    fallback_tickers: list[str] | None = None,
) -> OptimizationResult:
    """
    Run Maximum Sharpe Mean-Variance optimization as the HRP benchmark.

    This function implements the classical Markowitz mean-variance optimization
    using maximum Sharpe ratio as the objective. It uses Ledoit-Wolf shrinkage
    on the covariance matrix (identical to HRP) to ensure a fair comparison where
    the only difference is the optimization algorithm, not input data quality.

    Expected returns are estimated via historical mean log returns, which is the
    standard academic approach. This is explicitly documented as a known limitation
    in the project documentation (mu instability — Michaud 1989).

    The optimizer applies the same asset-level weight bounds as HRP (3%-40%) to
    ensure a controlled comparison. If the maximum Sharpe optimization fails due
    to infeasibility, the function falls back to minimum volatility optimization,
    which is always feasible with box constraints.

    Args:
        prices: DataFrame of cleaned adjusted close prices with tickers as columns
            and dates as index. Must contain at least 2 assets. Typically sourced
            from ValidatedDataLoader.
        ucits_tickers: Optional list of UCITS-compliant tickers currently in use,
            included for audit trail purposes.
        fallback_tickers: Optional list of fallback tickers that were applied due
            to data quality issues, included for audit trail purposes.

    Returns:
        OptimizationResult dataclass with algorithm="MV" containing:
            - weights: Dict mapping tickers to portfolio weights (sum to 1.0)
            - expected_return: Annualized expected return based on historical mean
            - expected_volatility: Annualized portfolio volatility
            - sharpe_ratio: (expected_return - risk_free_rate) / volatility
            - risk_contributions: Dict mapping tickers to marginal risk contributions
            - optimizer_version: Version string for reproducibility
            - solver_status: "optimal", "clipped", or "fallback_erc"
            - ucits_tickers_used: List of UCITS tickers used
            - fallback_tickers_applied: List of fallback tickers applied

        Note: Unlike HRP results, expected_return and sharpe_ratio are populated
        because MV explicitly optimizes on expected returns.

    Raises:
        AssertionError: If prices DataFrame is empty or contains fewer than 2 assets.

    Example:
        >>> prices = pd.DataFrame({...})  # Historical price data
        >>> result = optimize_markowitz(prices, ucits_tickers=['ETF1', 'ETF2'])
        >>> print(result['weights'])
        {'ETF1': 0.35, 'ETF2': 0.65}
        >>> print(f"Sharpe: {result['sharpe_ratio']:.3f}")
        Sharpe: 0.872
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"

    # ── Step 1: Estimate inputs ──────────────────────