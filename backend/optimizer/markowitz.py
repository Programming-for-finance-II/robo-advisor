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
    Run Max Sharpe Mean-Variance optimisation as the HRP benchmark.

    Uses Ledoit-Wolf shrinkage on the covariance matrix (same as HRP)
    to ensure a fair comparison: the only difference is the optimisation
    algorithm, not the input data quality.

    Expected returns are estimated via historical mean log returns.
    This is the standard academic approach and is explicitly documented
    as a limitation in the PDF (mu instability — Michaud 1989).

    Args:
        prices: DataFrame of cleaned adjusted close prices from ValidatedDataLoader.
            Each column represents one asset, indexed by date.
        ucits_tickers: Optional list of UCITS tickers currently in use for audit trail.
            If None, defaults to empty list in result.
        fallback_tickers: Optional list of fallback tickers that were applied for audit trail.
            If None, defaults to empty list in result.

    Returns:
        OptimizationResult with algorithm="MV". The result includes:
            - weights: dictionary mapping ticker to portfolio weight
            - expected_return: forward-looking expected annualized return
            - expected_volatility: forward-looking annualized volatility
            - sharpe_ratio: (expected_return - risk_free_rate) / volatility
            - risk_contributions: marginal risk contribution per asset
            - solver_status: "optimal", "clipped", or "fallback_erc"
        
        Note: expected_return and sharpe_ratio are populated here
        (unlike HRP where they are null), because MV explicitly uses mu.
    
    Raises:
        AssertionError: If prices DataFrame is empty or has fewer than 2 assets.
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"

    # ── Step 1: Estimate inputs ──────────────────────────────────────────
    # Ledoit-Wolf shrinkage
    cov: pd.DataFrame = CovarianceShrinkage(prices).ledoit_wolf()

    # Historical mean log returns, annualised
    # Acknowledged limitation: mu is highly unstable out-of-sample
    mu: pd.Series = expected_returns.mean_historical_return(
        prices,
        returns_data=False,
        frequency=RETURNS_FREQUENCY,
        log_returns=True,
    )

    # ── Step 2: Max Sharpe optimisation ──────────────────────────────────
    ef = EfficientFrontier(
        mu,
        cov,
        weight_bounds=(MV_ASSET_MIN, MV_ASSET_MAX),
    )

    try:
        ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
        solver_status: Literal["optimal", "clipped", "fallback_erc"] = "optimal"
    except Exception:
        # Fallback: if Max Sharpe fails (e.g. no feas