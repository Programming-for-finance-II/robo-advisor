from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from backend.data.universe_config import get_cluster_map

# ---------------------------------------------------------------------------
# Constants — single source of truth (referenced in ADR-003)
# ---------------------------------------------------------------------------

STRESS_CORR_THRESHOLD: float = 0.75   # avg |ρ_LW| trigger
STRESS_VIX_THRESHOLD: float = 30.0    # VIX trigger (secondary signal)

RegimeLabel = Literal["NORMAL", "HIGH_STRESS"]

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeResult:
    """Output of detect_regime().

    Attributes:
        regime:        'NORMAL' or 'HIGH_STRESS'.
        avg_correlation: Mean absolute pairwise correlation from Σ_LW.
        vix_triggered: True if VIX signal caused HIGH_STRESS (secondary).
        corr_triggered: True if correlation signal caused HIGH_STRESS.
    """
    regime: RegimeLabel
    avg_correlation: float
    corr_triggered: bool
    vix_triggered: bool


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_regime(
    cov: pd.DataFrame,
    vix_level: float | None = None,
) -> RegimeResult:
    """Detect market regime from Ledoit-Wolf covariance matrix.

    Args:
        cov:       Daily LW covariance matrix (tickers × tickers).
                   Must be square with at least 2 assets.
        vix_level: Optional current VIX level. If provided and
                   > STRESS_VIX_THRESHOLD, contributes to HIGH_STRESS.

    Returns:
        RegimeResult with regime label and diagnostic fields.

    Raises:
        ValueError: if cov has fewer than 2 assets.
    """
    if cov.shape[0] < 2:
        raise ValueError(
            f"detect_regime requires ≥2 assets; got {cov.shape[0]}"
        )

    # ── Step 1: compute average pairwise |ρ| ─────────────────────────────
    std = np.sqrt(np.diag(cov.values))
    assert np.all(std > 0), "Zero-variance asset in covariance matrix"
    corr_matrix = cov.values / np.outer(std, std)

    n = corr_matrix.shape[0]
    mask = ~np.eye(n, dtype=bool)
    avg_corr = float(np.mean(np.abs(corr_matrix[mask])))

    # ── Step 2: evaluate triggers ─────────────────────────────────────────
    corr_triggered = avg_corr > STRESS_CORR_THRESHOLD
    vix_triggered = (vix_level is not None) and (vix_level > STRESS_VIX_THRESHOLD)

    regime: RegimeLabel = "HIGH_STRESS" if (corr_triggered or vix_triggered) else "NORMAL"

    return RegimeResult(
        regime=regime,
        avg_correlation=round(avg_corr, 6),
        corr_triggered=corr_triggered,
        vix_triggered=vix_triggered,
    )


# ---------------------------------------------------------------------------
# ERC Cluster-Level Fallback
# ---------------------------------------------------------------------------

def get_erc_cluster_weights(
    tickers: list[str],
    cluster_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """Return equal-weight cluster-level ERC portfolio for HIGH_STRESS regime.

    Logic:
        1. Equal weight across clusters (1 / n_clusters each).
        2. Equal weight within each cluster (1 / n_assets_in_cluster).
        3. Clip to [ASSET_WEIGHT_MIN, ASSET_WEIGHT_MAX] and renormalise.

    This is the minimum-assumption portfolio when diversification
    signal is absent (all correlations → 1).

    Args:
        tickers:     List of asset tickers in the universe.
        cluster_map: {ticker: cluster_name}. If None, loads from
                     universe_config.get_cluster_map().

    Returns:
        Dict {ticker: weight}, sums to 1.0.
    """
    from backend.data.universe_config import (
        ASSET_WEIGHT_MIN,
        ASSET_WEIGHT_MAX,
    )

    if cluster_map is None:
        cluster_map = get_cluster_map()

    # Group tickers by cluster
    clusters: dict[str, list[str]] = {}
    for ticker in tickers:
        cluster = cluster_map.get(ticker, "unknown")
        clusters.setdefault(cluster, []).append(ticker)

    n_clusters = len(clusters)
    assert n_clusters > 0, "No clusters found for given tickers"

    cluster_weight = 1.0 / n_clusters

    raw_weights: dict[str, float] = {}
    for cluster_assets in clusters.values():
        asset_weight = cluster_weight / len(cluster_assets)
        for ticker in cluster_assets:
            raw_weights[ticker] = asset_weight

    # Clip and renormalise
    clipped = {t: max(ASSET_WEIGHT_MIN, min(ASSET_WEIGHT_MAX, w))
               for t, w in raw_weights.items()}
    total = sum(clipped.values())
    return {t: round(w / total, 6) for t, w in clipped.items()}
