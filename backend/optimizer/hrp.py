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
    Result dictionary returned by the HRP optimization process.
    
    Attributes:
        algorithm: Optimization algorithm used ("HRP", "MV", or "BL").
        weights: Dictionary mapping ticker symbols to portfolio weights (sum to 1.0).
        expected_return: Annualized expected portfolio return.
        expected_volatility: Annualized portfolio volatility (standard deviation).
        sharpe_ratio: Ratio of expected return to volatility.
        risk_contributions: Dictionary mapping tickers to their marginal contribution to portfolio risk.
        optimizer_version: Version string of the optimizer.
        solver_status: Status of the optimization ("optimal", "clipped", or "fallback_erc").
        ucits_tickers_used: List of UCITS-compliant tickers used in the optimization.
        fallback_tickers_applied: List of fallback tickers applied when primary tickers were unavailable.
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
    
    Raises:
        AssertionError: If prices is empty, has fewer than 2 assets, or contains all-NaN columns.
        AssertionError: If resulting covariance matrix is not positive semi-definite.
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
    
    Calculates continuously compounded returns as ln(P_t / P_{t-1}) and removes
    the first row (NaN). Validates that sufficient observations remain for stable
    covariance estimation.
    
    Args:
        prices: DataFrame of adjusted close prices (rows=dates, cols=tickers).
    
    Returns:
        DataFrame of log returns with at least 60