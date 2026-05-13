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
    Perform Maximum Sharpe Ratio Mean-Variance portfolio optimization.

    This function implements the classical Markowitz mean-variance optimization
    using maximum Sharpe ratio as the objective. It serves as a benchmark for
    comparison with Hierarchical Risk Parity (HRP) optimization.

    The optimization uses:
    - Ledoit-Wolf shrinkage for covariance estimation (consistent with HRP)
    - Historical mean log returns for expected return estimation
    - Box constraints matching HRP for fair comparison
    - Risk-free rate of 3% (approximate EUR 2024 rate)

    Known Limitations:
    - Expected returns (mu) are highly unstable out-of-sample (Michaud 1989)
    - Historical returns may not predict future performance
    - Optimization is sensitive to estimation error in expected returns

    Args:
        prices: DataFrame of cleaned adjusted close prices with datetime index
               and tickers as columns. Must contain at least 2 assets with
               sufficient price history. Typically from ValidatedDataLoader.
        ucits_tickers: Optional list of UCITS-compliant tickers used in the
                      portfolio for audit trail purposes.
        fallback_tickers: Optional list of fallback tickers applied when
                         UCITS tickers were unavailable, for audit trail.

    Returns:
        OptimizationResult dictionary containing:
        - algorithm: "MV" (Mean-Variance)
        - weights: Dict mapping ticker symbols to portfolio weights (sum=1.0)
        - expected_return: Annualized expected portfolio return (252 days)
        - expected_volatility: Annualized portfolio volatility
        - sharpe_ratio: Sharpe ratio using RISK_FREE_RATE
        - risk_contributions: Dict mapping tickers to risk contributions
        - optimizer_version: Version string for reproducibility
        - solver_status: "optimal", "clipped", or "fallback_erc"
        - ucits_tickers_used: List of UCITS tickers in the portfolio
        - fallback_tickers_applied: List of fallback tickers used

    Raises:
        AssertionError: If prices DataFrame is empty or has fewer than 2 assets.

    Example:
        >>> prices = pd.DataFrame(...)  # Historical price data
        >>> result = optimize_markowitz(prices, ucits_tickers=['VWCE.DE'])
        >>> print(f"MV Sharpe: {result['sharpe_ratio']:.3f}")
        >>> print(f"Weights: {result['weights']}")
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"

    # ── Step 1: Estimate inputs ──────────────────────────────────────────
    # Ledoit-Wolf shrinkage
    cov: pd.DataFrame = CovarianceShrinkage(prices).ledoit_wolf()

    # Historical mean log returns, annualised
    # Acknowledged limitation: mu is