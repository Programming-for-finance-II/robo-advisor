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

# ---------------------------------------------------------------------------
# Log Returns
# ---------------------------------------------------------------------------
def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    assert not prices.empty, "prices cannot be empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"
    assert not prices.isnull().all().any(), "some tickers have all-NaN prices"

    returns = np.log(prices / prices.shift(1)).dropna()

    assert len(returns) >= 60, (
        f"too few observations ({len(returns)}); need >= 60 for stable covariance"
    )
    return returns

# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------
def _cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    std = np.sqrt(np.diag(cov.values))
    corr = cov.values / np.outer(std, std)
    corr = np.clip(corr, -1.0, 1.0)
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def _corr_to_distance(corr: pd.DataFrame) -> np.ndarray:
    dist = np.sqrt(0.5 * (1.0 - corr.values))
    np.fill_diagonal(dist, 0.0)
    return dist


def _get_quasi_diagonal_order(linkage_matrix: np.ndarray, n: int) -> list[int]:
    d = dendrogram(linkage_matrix, no_plot=True)
    return [int(i) for i in d["leaves"]]
# ---------------------------------------------------------------------------
# Recursive Bisection
# ---------------------------------------------------------------------------
def _get_cluster_variance(cov: pd.DataFrame, assets: list[str]) -> float:
    sub_cov = cov.loc[assets, assets].values
    inv_diag = 1.0 / np.diag(sub_cov)
    w_ivp = inv_diag / inv_diag.sum()
    return float(w_ivp @ sub_cov @ w_ivp)


def _recursive_bisection(
    cov: pd.DataFrame,
    sorted_assets: list[str],
) -> dict[str, float]:
    weights = pd.Series(1.0, index=sorted_assets)
    clusters = [sorted_assets]

    while clusters:
        new_clusters = []
        for cluster in clusters:
            if len(cluster) == 1:
                continue
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            var_left = _get_cluster_variance(cov, left)
            var_right = _get_cluster_variance(cov, right)

            alpha = var_right / (var_left + var_right)
            weights[left] *= alpha
            weights[right] *= (1 - alpha)

            new_clusters.extend([left, right])
        clusters = new_clusters

    return weights.to_dict()
