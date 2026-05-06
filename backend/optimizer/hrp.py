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
# ---------------------------------------------------------------------------
# Profile Tilt
# ---------------------------------------------------------------------------
def _compute_min_var_weights(cov: pd.DataFrame) -> dict[str, float]:
    ef = EfficientFrontier(None, cov, weight_bounds=(ASSET_MIN, ASSET_MAX))
    ef.min_volatility()
    return ef.clean_weights()


def _compute_erc_weights(cov: pd.DataFrame) -> dict[str, float]:
    variances = np.diag(cov.values)
    inv_vol = 1.0 / np.sqrt(variances)
    w = inv_vol / inv_vol.sum()
    return dict(zip(cov.index, w))


def _apply_profile_tilt(
    hrp_weights: dict[str, float],
    cov: pd.DataFrame,
    profile: ProfileLabel,
) -> dict[str, float]:
    if profile == "MODERATE":
        return hrp_weights

    if profile == "CONSERVATIVE":
        w_blend = _compute_min_var_weights(cov)
    else:
        w_blend = _compute_erc_weights(cov)

    tilt = 0.3
    w_final = {
        t: (1 - tilt) * hrp_weights[t] + tilt * w_blend.get(t, 0.0)
        for t in hrp_weights
    }
    total = sum(w_final.values())
    return {t: w / total for t, w in w_final.items()}
# ---------------------------------------------------------------------------
# Box Constraints
# ---------------------------------------------------------------------------
def _apply_box_constraints(
    weights: dict[str, float],
    cluster_map: dict[str, str],
) -> tuple[dict[str, float], bool]:
    w = pd.Series(weights)
    clipped = False

    for _ in range(10):
        w_clipped = w.clip(lower=ASSET_MIN, upper=ASSET_MAX)
        if not w_clipped.equals(w):
            clipped = True
        w = w_clipped / w_clipped.sum()

        for cluster_name in set(cluster_map.values()):
            assets = [t for t, c in cluster_map.items() if c == cluster_name and t in w.index]
            if not assets:
                continue
            cluster_weight = w[assets].sum()
            if cluster_weight < CLUSTER_MIN:
                w[assets] *= CLUSTER_MIN / cluster_weight
                clipped = True
            elif cluster_weight > CLUSTER_MAX:
                w[assets] *= CLUSTER_MAX / cluster_weight
                clipped = True
        w = w / w.sum()

    return w.to_dict(), clipped
# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def optimize(
    prices: pd.DataFrame,
    profile: ProfileLabel,
    cluster_map: dict[str, str],
    ucits_tickers: list[str] | None = None,
    fallback_tickers: list[str] | None = None,
) -> OptimizationResult:
    returns = compute_log_returns(prices)
    cov = compute_covariance(prices)

    corr = _cov_to_corr(cov)
    dist_matrix = _corr_to_distance(corr)
    condensed = squareform(dist_matrix, checks=False)
    link = linkage(condensed, method="ward")

    sorted_idx = _get_quasi_diagonal_order(link, len(cov.columns))
    sorted_tickers = [cov.columns[i] for i in sorted_idx]

    hrp_raw = _recursive_bisection(cov, sorted_tickers)
    tilted = _apply_profile_tilt(hrp_raw, cov, profile)
    final_weights, was_clipped = _apply_box_constraints(tilted, cluster_map)

    solver_status: Literal["optimal", "clipped", "fallback_erc"] = (
        "clipped" if was_clipped else "optimal"
    )

    w_vec = np.array([final_weights[t] for t in cov.columns])
    ann_vol = float(np.sqrt(w_vec @ cov.values @ w_vec))

    mean_log_returns = returns.mean() * 252
    exp_ret = float(mean_log_returns.values @ w_vec)
    sharpe = exp_ret / ann_vol if ann_vol > 0 else 0.0

    marginal = cov.values @ w_vec
    rc = w_vec * marginal
    risk_contributions = dict(zip(cov.columns, rc / rc.sum()))

    return OptimizationResult(
        algorithm="HRP",
        weights=final_weights,
        expected_return=round(exp_ret, 6),
        expected_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 6),
        risk_contributions={t: round(v, 6) for t, v in risk_contributions.items()},
        optimizer_version=OPTIMIZER_VERSION,
        solver_status=solver_status,
        ucits_tickers_used=ucits_tickers or [],
        fallback_tickers_applied=fallback_tickers or [],
    )
