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
        prices: Cleaned adjusted close prices from ValidatedDataLoader.
            Must be a non-empty DataFrame with at least 2 columns (assets).
            Index should be DatetimeIndex with daily frequency.
        ucits_tickers: Optional list of UCITS-compliant tickers used in
            the optimization. Stored for audit trail purposes.
        fallback_tickers: Optional list of fallback tickers applied when
            UCITS tickers were unavailable. Stored for audit trail.

    Returns:
        OptimizationResult: Dictionary with the following keys:
            - algorithm: "MV" (Mean-Variance)
            - weights: Dict mapping ticker to optimal weight (sum to 1.0)
            - expected_return: Annualised expected portfolio return
            - expected_volatility: Annualised portfolio volatility
            - sharpe_ratio: (expected_return - risk_free_rate) / volatility
            - risk_contributions: Dict mapping ticker to % risk contribution
            - optimizer_version: Version string for reproducibility
            - solver_status: "optimal", "clipped", or "fallback_erc"
            - ucits_tickers_used: List of UCITS tickers
            - fallback_tickers_applied: List of fallback tickers

    Raises:
        AssertionError: If prices is empty or has fewer than 2 assets.

    Note:
        Unlike HRP, MV results include expected_return and sharpe_ratio
        because the optimizer explicitly uses expected return estimates.
        If Max Sharpe fails, the optimizer falls back to Min Volatility.
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
        weight_bounds=(