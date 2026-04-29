from __future__ import annotations

from typing import Literal, TypedDict
import numpy as np
import pandas as pd


class OptimizationResult(TypedDict):
    algorithm: Literal["HRP", "MV", "BL"]
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    risk_contributions: dict[str, float]
    optimizer_version: str
    solver_status: Literal["optimal", "infeasible", "fallback"]
    ucits_tickers_used: list[str]
    fallback_tickers_applied: list[str]
    
# ---------------------------------------------------------------------------
# Covariance Estimation
# ---------------------------------------------------------------------------

def compute_covariance(prices: pd.DataFrame) -> np.ndarray:
    """
    Compute Ledoit-Wolf shrinkage covariance matrix from price series.

    Uses analytical shrinkage (Ledoit & Wolf, 2004) via PyPortfolioOpt.
    Shrinkage reduces estimation error on small samples by pulling the
    sample covariance matrix toward a structured estimator (identity-scaled).

    Args:
        prices: DataFrame of adjusted close prices (rows=dates, cols=tickers).

    Returns:
        Shrunk covariance matrix as np.ndarray, shape (n_assets, n_assets).

    Raises:
        AssertionError: if prices is empty or has fewer than 4 assets.
        NotImplementedError: W1 stub — full implementation in W2.
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.notna().all().all(), "prices contains NaN — use ValidatedDataLoader"
    assert len(prices.columns) >= 4, "need at least 4 assets for HRP clustering"

    # TODO W2: uncomment below and remove NotImplementedError
    # from pypfopt import CovarianceShrinkage
    # return CovarianceShrinkage(prices).ledoit_wolf()
    raise NotImplementedError("compute_covariance — full implementation in W2")
