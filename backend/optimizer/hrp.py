from __future__ import annotations

from typing import Literal, TypedDict

import numpy as np
import pandas as pd
from pypfopt import CovarianceShrinkage, EfficientFrontier
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform

OPTIMIZER_VERSION = "2.0.0"
ASSET_MIN = 0.03
ASSET_MAX = 0.40
CLUSTER_MIN = 0.10
CLUSTER_MAX = 0.60

ProfileLabel = Literal["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]

class OptimizationResult(TypedDict):
    """
    Result dictionary from portfolio optimization.

    Attributes:
        algorithm: Optimization algorithm used (HRP, MV, or BL).
        weights: Dictionary mapping ticker symbols to portfolio weights.
        expected_return: Annualized expected return.
        expected_volatility: Annualized portfolio volatility (standard deviation).
        sharpe_ratio: Risk-adjusted return metric (return / volatility).
        risk_contributions: Dictionary mapping tickers to their risk contributions.
        optimizer_version: Version string of the optimizer.
        solver_status: Status indicating if solution is optimal, clipped, or fallback.
        ucits_tickers_used: List of UCITS-compliant tickers included in optimization.
        fallback_tickers_applied: List of fallback tickers used when primary data unavailable.
    """
    algorithm: Literal["HRP", "MV", "BL"]
    weights: dict[str, float]
    expected_return: float  
    expected_volatility: float
    sharpe_ratio: float
    risk_contributions: dict[str, float]
    optimizer_version: str
    solver_status: Literal["optimal", "clipped", "fallback_erc"]
    ucits_tickers_used: list[str]
    fallback_tickers_applied: list[str]
    
# ---------------------------------------------------------------------------
# Covariance Estimation
# ---------------------------------------------------------------------------

def compute_covariance(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Ledoit-Wolf shrinkage covariance matrix from price series.

    Uses analytical shrinkage (Ledoit & Wolf, 2004) via PyPortfolioOpt.
    Shrinkage reduces estimation error on small samples by pulling the
    sample covariance matrix toward a structured estimator (identity-scaled).

    Args:
        prices: DataFrame of adjusted close prices (rows=dates, cols=tickers).

    Returns:
        Shrunk covariance matrix as pd.DataFrame, shape (n_assets, n_assets).
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"
    assert not prices.isnull().all().any(), "some tickers have all-NaN prices"

    cov = CovarianceShrinkage(prices).ledoit_wolf()

    eigenvalues = np.linalg.eigvalsh(cov.values)
    assert np.all(eigenvalues >= -1e-8), "covariance matrix is not PSD after LW shrinkage"

    return cov

# ---------------------------------------------------------------------------
# Log Returns
# ---------------------------------------------------------------------------
def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute log returns from price series.

    Log returns are calculated as ln(P_t / P_{t-1}). The first row (NaN) is dropped.
    Requires at least 60 observations for stable covariance estimation.

    Args:
        prices: DataFrame of adjusted close prices (rows=dates, cols=tickers).

    Returns:
        DataFrame of log returns with same columns as prices, one fewer row.
    """
    assert not prices.empty, "prices cannot be empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"
    assert not prices.isnull().all().any(), "some tickers have all-NaN prices"

    returns = np.log(prices / prices.shift(1)).dropna()