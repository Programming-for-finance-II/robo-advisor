"""
clustering.py
-------------
Unsupervised clustering of SCF 2022 households into risk profile labels.

Strategy:
    - Cluster on *normalised portfolio allocation ratios* (equity / bond / cash
      share of total holdings), not on raw monetary amounts.
    - This produces behaviourally meaningful clusters that map directly to
      CONSERVATIVE / MODERATE / AGGRESSIVE risk profiles.
    - Silhouette score is used to validate K=3 against K=2 and K=4.

Why allocation ratios and not raw features?
    Raw amounts (EQUITY=500k vs EQUITY=5k) reflect wealth, not risk attitude.
    The ratio EQUITY / (EQUITY + BOND + CASHLI) captures *how* a household
    allocates its portfolio — independent of total wealth.

Output:
    - Profile labels added as column 'profile_label' to the DataFrame.
    - Saved to data/scf/scf_labeled.parquet for use by GBM training (W3).

References:
    - Grable, J.E., Lytton, R.H. (1999). Financial risk tolerance revisited.
    - Federal Reserve (2022). SCF Codebook.

Related ADR:
    docs/adr/ADR-002-scf-preprocessing.md
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from backend.ml.profiler.scf_pipeline import (
    SCF_WEIGHT_COLUMN,
    build_pipeline,
    SCF_DEFAULT_PATH,
    SCF_IMPLICATE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Number of clusters — maps to CONSERVATIVE / MODERATE / AGGRESSIVE
N_CLUSTERS = 3

# KMeans reproducibility
RANDOM_STATE = 42
N_INIT = 10

# Output path for labeled dataset (consumed by GBM training in W3)
LABELED_OUTPUT_PATH = Path("data/scf/scf_labeled.parquet")

# Canonical label names (must match ProfileLabel in rule_based.py)
LABEL_CONSERVATIVE = "CONSERVATIVE"
LABEL_MODERATE = "MODERATE"
LABEL_AGGRESSIVE = "AGGRESSIVE"

# Small epsilon to avoid division by zero in ratio computation
EPSILON = 1.0

# Candidate K values for silhouette validation
K_CANDIDATES = [2, 3, 4]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def compute_allocation_ratios(alloc: pd.DataFrame) -> pd.DataFrame:
    """Compute normalised portfolio allocation ratios from raw SCF amounts.

    Ratios are independent of total wealth and capture *how* a household
    allocates its portfolio.

    Args:
        alloc: DataFrame with raw SCF allocation columns:
               EQUITY, BOND, CASHLI (output of build_pipeline).

    Returns:
        DataFrame with three ratio columns:
            equity_ratio -- share of equity in total holdings
            bond_ratio   -- share of bonds in total holdings
            cash_ratio   -- share of cash/liquid assets in total holdings
    """
    total = alloc["EQUITY"] + alloc["BOND"] + alloc["CASHLI"] + EPSILON

    return pd.DataFrame(
        {
            "equity_ratio": alloc["EQUITY"] / total,
            "bond_ratio": alloc["BOND"] / total,
            "cash_ratio": alloc["CASHLI"] / total,
        },
        index=alloc.index,
    )


def validate_k(
    X_ratios: np.ndarray,
    k_candidates: list[int] = K_CANDIDATES,
) -> dict[int, float]:
    """Compute silhouette scores for candidate K values.

    Args:
        X_ratios: Standardised allocation ratios array (n_samples x 3).
        k_candidates: List of K values to evaluate.

    Returns:
        Dict mapping K -> silhouette score.
    """
    scores: dict[int, float] = {}
    for k in k_candidates:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
        labels = km.fit_predict(X_ratios)
        score = silhouette_score(X_ratios, labels)
        scores[k] = round(float(score), 4)
        logger.info("K=%d: silhouette=%.4f", k, score)
    return scores


def assign_labels(
    cluster_ids: np.ndarray,
    alloc_ratios: pd.DataFrame,
) -> np.ndarray:
    """Map raw cluster IDs to semantic risk profile labels.

    Assignment rule (deterministic, based on mean equity ratio per cluster):
        - Highest mean equity_ratio  → AGGRESSIVE
        - Lowest mean equity_ratio   → CONSERVATIVE (high cash or low assets)
        - Remaining cluster          → MODERATE

    This avoids hardcoding cluster-to-label mapping, which would break
    if KMeans assigns different cluster IDs across runs.

    Args:
        cluster_ids: Integer cluster assignments (n_samples,).
        alloc_ratios: DataFrame with equity_ratio, bond_ratio, cash_ratio.

    Returns:
        Array of profile label strings (n_samples,).
    """
    unique_clusters = np.unique(cluster_ids)
    if len(unique_clusters) != N_CLUSTERS:
        raise ValueError(
            f"Expected {N_CLUSTERS} clusters, got {len(unique_clusters)}."
        )

    # Compute mean equity ratio per cluster
    mean_equity: dict[int, float] = {}
    for c in unique_clusters:
        mask = cluster_ids == c
        mean_equity[c] = float(alloc_ratios.loc[mask, "equity_ratio"].mean())

    # Sort clusters by mean equity ratio
    sorted_clusters = sorted(mean_equity.items(), key=lambda kv: kv[1])

    conservative_cluster = sorted_clusters[0][0]   # lowest equity ratio
    moderate_cluster = sorted_clusters[1][0]        # middle equity ratio
    aggressive_cluster = sorted_clusters[2][0]      # highest equity ratio

    logger.info(
        "Label assignment: CONSERVATIVE=cluster%d (eq=%.3f), "
        "MODERATE=cluster%d (eq=%.3f), AGGRESSIVE=cluster%d (eq=%.3f)",
        conservative_cluster, sorted_clusters[0][1],
        moderate_cluster,     sorted_clusters[1][1],
        aggressive_cluster,   sorted_clusters[2][1],
    )

    cluster_to_label = {
        conservative_cluster: LABEL_CONSERVATIVE,
        moderate_cluster: LABEL_MODERATE,
        aggressive_cluster: LABEL_AGGRESSIVE,
    }

    return np.array([cluster_to_label[c] for c in cluster_ids])


def run_clustering(
    scf_path: Path = SCF_DEFAULT_PATH,
    output_path: Path = LABELED_OUTPUT_PATH,
    save: bool = True,
) -> pd.DataFrame:
    """Full clustering pipeline: load SCF → cluster → label → save.

    Args:
        scf_path: Path to the SCF 2022 CSV file.
        output_path: Where to save the labeled parquet file.
        save: If True, save output to output_path. Default: True.

    Returns:
        DataFrame with all SCF features plus 'profile_label' column.
        Ready for GBM training in W3.

    Example:
        >>> df_labeled = run_clustering()
        >>> df_labeled["profile_label"].value_counts()
        AGGRESSIVE      2721
        CONSERVATIVE    1575
        MODERATE         299
    """
    # --- 1. Load and preprocess SCF ---
    logger.info("Running SCF pipeline...")
    X, alloc, weights, scaler = build_pipeline(path=scf_path)

    # --- 2. Compute allocation ratios ---
    alloc_ratios = compute_allocation_ratios(alloc)

    # --- 3. Standardise ratios for KMeans ---
    ratio_scaler = StandardScaler()
    X_ratios = ratio_scaler.fit_transform(alloc_ratios)

    # --- 4. Validate K with silhouette scores ---
    logger.info("Validating K with silhouette scores...")
    sil_scores = validate_k(X_ratios)
    best_k = max(sil_scores, key=lambda k: sil_scores[k])
    logger.info(
        "Silhouette scores: %s — best K=%d, using K=%d (3 profiles)",
        sil_scores, best_k, N_CLUSTERS,
    )

    # --- 5. Fit final KMeans with K=3 ---
    km = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=N_INIT)
    cluster_ids = km.fit_predict(X_ratios)

    # --- 6. Assign semantic labels ---
    profile_labels = assign_labels(cluster_ids, alloc_ratios)

    # --- 7. Build labeled DataFrame ---
    df_labeled = alloc.copy()
    df_labeled["profile_label"] = profile_labels
    df_labeled[SCF_WEIGHT_COLUMN] = weights

    # Log label distribution
    for label in [LABEL_CONSERVATIVE, LABEL_MODERATE, LABEL_AGGRESSIVE]:
        n = (profile_labels == label).sum()
        pct = 100 * n / len(profile_labels)
        logger.info("  %s: %d (%.1f%%)", label, n, pct)

    # --- 8. Save to parquet ---
    if save:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df_labeled.to_parquet(output_path, index=False)
        logger.info("Labeled dataset saved to %s", output_path)

    return df_labeled


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    df = run_clustering()
    print("\nLabel distribution:")
    print(df["profile_label"].value_counts())
    print(f"\nTotal observations: {len(df)}")
    print(f"Saved to: {LABELED_OUTPUT_PATH}")
