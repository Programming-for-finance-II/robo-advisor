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
            Each column represents an asset's price history, indexed by date.
        ucits_tickers: Optional list of UCITS-compliant ticker symbols used
            in the optimization, for audit trail purposes.
        fallback_tickers: Optional list of fallback ticker symbols that were
            applied due to data quality issues, for audit trail purposes.

    Returns:
        OptimizationResult: A dictionary containing:
            - algorithm: "MV" (Mean-Variance)
            - weights: Dict mapping ticker symbols to portfolio weights (floats)
            - expected_return: Annualized expected portfolio return
            - expected_volatility: Annualized portfolio standard deviation
            - sharpe_ratio: Risk-adjusted return metric (return - rf) / volatility
            - risk_contributions: Dict of per-asset risk contributions
            - optimizer_version: Version identifier for reproducibility
            - solver_status: "optimal", "clipped", or "fallback_erc"
            - ucits_tickers_used: List of UCITS tickers applied
            - fallback_tickers_applied: List of fallback tickers applied

    Raises:
        AssertionError: If prices DataFrame is empty or has fewer than 2 assets.

    Note:
        Unlike HRP, this method explicitly uses expected returns (mu) and 
        therefore populates expected_return and sharpe_ratio fields. This is
        a known limitation as historical mean returns are unstable out-of-sample.
        
        If Max Sharpe optimization fails, automatically falls back to 
        Minimum Volatility, which is always feasible with box constraints.
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

    # ── Step 2: Max Sharpe optimisation ──────────