from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

import numpy as np
import pandas as pd
from pypfopt import CovarianceShrinkage, EfficientFrontier
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform

OPTIMIZER_VERSION = "3.0.0"
TRADING_DAYS_PER_YEAR: int = 252
MIN_OBSERVATIONS: int = 60
MAX_CONSTRAINT_ITER: int = 50

# Legacy global guardrails — retained for the MODERATE baseline and for
# backward compatibility with callers/tests that import these symbols.
# Per-profile guardrails now live in PROFILE_CONSTRAINTS (see below).
TILT_FACTOR: float = 0.3
ASSET_MIN = 0.05
ASSET_MAX = 0.40
CLUSTER_MIN = 0.10
CLUSTER_MAX = 0.60

ProfileLabel = Literal["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]
ClusterName = str
TiltTarget = Literal["min_vol", "max_vol", "none"]


# ---------------------------------------------------------------------------
# Per-profile guardrails
# ---------------------------------------------------------------------------
#
# Why this exists (ADR-008): the original design applied a single global set
# of box constraints to every profile and tilted AGGRESSIVE toward ERC
# (Equal Risk Contribution). ERC is a *risk-balancing* construction, not a
# return-seeking one, so AGGRESSIVE never asked for more equity. Combined with
# tight uniform caps and an inverse-variance HRP base that piles into the
# near-zero-vol cash ETF, all three profiles collapsed onto the same boundary
# portfolio (CONSERVATIVE and AGGRESSIVE differed by <0.04 in L1 weight
# distance, and AGGRESSIVE had *lower* realised volatility than CONSERVATIVE).
#
# The fix gives each profile (a) its own tilt target and strength, and
# (b) its own per-asset and per-cluster bounds, so risk appetite is expressed
# both as a smooth preference (tilt) and as a hard floor/cap (bounds).

@dataclass(frozen=True)
class ProfileConstraints:
    """Risk-appetite guardrails for a single investor profile."""

    asset_min: float
    asset_max: float
    cluster_bounds: dict[ClusterName, tuple[float, float]]
    tilt_target: TiltTarget
    tilt_factor: float


PROFILE_CONSTRAINTS: dict[ProfileLabel, ProfileConstraints] = {
    "CONSERVATIVE": ProfileConstraints(
        asset_min=0.0,
        asset_max=0.45,
        cluster_bounds={
            "risk_assets": (0.05, 0.25),
            "real_assets": (0.05, 0.20),
            "safe_haven": (0.25, 0.60),
            "cash": (0.10, 0.50),
        },
        tilt_target="min_vol",
        tilt_factor=0.5,
    ),
    "MODERATE": ProfileConstraints(
        asset_min=ASSET_MIN,
        asset_max=ASSET_MAX,
        cluster_bounds={
            "risk_assets": (0.20, 0.45),
            "real_assets": (0.05, 0.25),
            "safe_haven": (0.15, 0.50),
            "cash": (0.02, 0.25),
        },
        tilt_target="none",
        tilt_factor=0.0,
    ),
    "AGGRESSIVE": ProfileConstraints(
        asset_min=0.0,
        asset_max=0.45,
        cluster_bounds={
            "risk_assets": (0.45, 0.75),
            "real_assets": (0.05, 0.25),
            "safe_haven": (0.05, 0.30),
            "cash": (0.0, 0.10),
        },
        tilt_target="max_vol",
        tilt_factor=0.6,
    ),
}

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

    cov = CovarianceShrinkage(prices, frequency=1).ledoit_wolf()

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

    assert len(returns) >= MIN_OBSERVATIONS, (
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
def _compute_min_var_weights(
    cov: pd.DataFrame,
    bounds: tuple[float, float],
) -> dict[str, float]:
    """Minimum-variance target — the risk-averse extreme (CONSERVATIVE)."""
    ef = EfficientFrontier(None, cov, weight_bounds=bounds)
    ef.min_volatility()
    return ef.clean_weights()


def _compute_risk_seeking_weights(cov: pd.DataFrame) -> dict[str, float]:
    """
    Volatility-proportional target — the risk-seeking extreme (AGGRESSIVE).

    The symmetric opposite of minimum variance: weight each asset in proportion
    to its volatility, loading onto the higher-risk assets. Deliberately μ-free
    (it uses only the covariance diagonal), preserving the project's core thesis
    that the optimizer never depends on estimated expected returns — see
    ADR-001 and ADR-008. The per-cluster bounds in PROFILE_CONSTRAINTS steer
    this risk budget toward the risk_assets (equity) cluster rather than gold.
    """
    vol = np.sqrt(np.diag(cov.values))
    w = vol / vol.sum()
    return dict(zip(cov.index, w))


def _apply_profile_tilt(
    hrp_weights: dict[str, float],
    cov: pd.DataFrame,
    constraints: ProfileConstraints,
) -> dict[str, float]:
    """
    Blend the profile-neutral HRP weights toward the profile's risk target.

    CONSERVATIVE tilts toward minimum variance, AGGRESSIVE toward a
    volatility-proportional (risk-seeking) target, MODERATE stays on the
    neutral HRP allocation. Both targets are μ-free, so the optimizer never
    depends on estimated expected returns. The blend strength is the profile's
    ``tilt_factor``.
    """
    if constraints.tilt_target == "none" or constraints.tilt_factor == 0.0:
        return hrp_weights

    bounds = (constraints.asset_min, constraints.asset_max)
    if constraints.tilt_target == "min_vol":
        w_blend = _compute_min_var_weights(cov, bounds)
    else:  # "max_vol" — risk-seeking
        w_blend = _compute_risk_seeking_weights(cov)

    tilt = constraints.tilt_factor
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
    constraints: ProfileConstraints,
) -> tuple[dict[str, float], bool]:
    """
    Project weights onto the profile's per-asset and per-cluster bounds.

    Iterative clip-and-renormalise: clamp each asset to [asset_min, asset_max],
    then scale each cluster back inside its [min, max] band, repeating until
    the projection stabilises. The per-profile cluster floors/caps are the hard
    guarantee that AGGRESSIVE carries materially more risk-asset exposure than
    CONSERVATIVE, independent of the (estimation-noisy) tilt.
    """
    w = pd.Series(weights)
    a_min, a_max = constraints.asset_min, constraints.asset_max
    clipped = False

    for _ in range(MAX_CONSTRAINT_ITER):
        w_clipped = w.clip(lower=a_min, upper=a_max)
        if not w_clipped.equals(w):
            clipped = True
        w = w_clipped / w_clipped.sum()

        for cluster_name in set(cluster_map.values()):
            assets = [t for t, c in cluster_map.items() if c == cluster_name and t in w.index]
            if not assets:
                continue
            c_min, c_max = constraints.cluster_bounds.get(
                cluster_name, (CLUSTER_MIN, CLUSTER_MAX)
            )
            cluster_weight = w[assets].sum()
            if cluster_weight < c_min:
                w[assets] *= c_min / cluster_weight
                clipped = True
            elif cluster_weight > c_max:
                w[assets] *= c_max / cluster_weight
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
    assert profile in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"), \
        f"Unknown profile: {profile!r}"
    constraints = PROFILE_CONSTRAINTS[profile]
    returns = compute_log_returns(prices)
    cov = compute_covariance(prices)
    mu = returns.mean() * TRADING_DAYS_PER_YEAR

    corr = _cov_to_corr(cov)
    dist_matrix = _corr_to_distance(corr)
    condensed = squareform(dist_matrix, checks=False)
    link = linkage(condensed, method="ward")

    sorted_idx = _get_quasi_diagonal_order(link, len(cov.columns))
    sorted_tickers = [cov.columns[i] for i in sorted_idx]

    hrp_raw = _recursive_bisection(cov, sorted_tickers)
    tilted = _apply_profile_tilt(hrp_raw, cov, constraints)
    final_weights, was_clipped = _apply_box_constraints(tilted, cluster_map, constraints)

    solver_status: Literal["optimal", "clipped", "fallback_erc"] = (
        "clipped" if was_clipped else "optimal"
    )

    w_vec = np.array([final_weights[t] for t in cov.columns])
    ann_vol = float(np.sqrt(w_vec @ cov.values @ w_vec * TRADING_DAYS_PER_YEAR))

    exp_ret = float(mu.values @ w_vec)
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
