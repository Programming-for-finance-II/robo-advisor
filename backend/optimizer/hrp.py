from __future__ import annotations

from typing import Literal, Optional, TypedDict

from pypfopt import CovarianceShrinkage, EfficientFrontier

from scipy.cluster.hierarchy import dendrogram, linkage

from scipy.spatial.distance import squareform

import numpy as np
import pandas as pd

OPTIMIZER_VERSION = "2.0.0"
ASSET_MIN = 0.03
ASSET_MAX = 0.40
CLUSTER_MIN = 0.10
CLUSTER_MAX = 0.60

ProfileLabel = Literal["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]

class OptimizationResult(TypedDict):
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
