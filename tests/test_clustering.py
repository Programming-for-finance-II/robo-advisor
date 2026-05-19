"""
tests/test_clustering.py
========================
Unit tests for backend/ml/profiler/clustering.py.

Strategy:
  - compute_allocation_ratios() and assign_labels() are pure functions
    tested with synthetic data — always run.
  - validate_k() is tested with a small synthetic array — always run.
  - run_clustering() requires data/scf/scf2022.csv — skipped when absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.ml.profiler.clustering import (
    EPSILON,
    LABEL_AGGRESSIVE,
    LABEL_CONSERVATIVE,
    LABEL_MODERATE,
    N_CLUSTERS,
    SCF_DEFAULT_PATH,
    assign_labels,
    compute_allocation_ratios,
    validate_k,
)

# ---------------------------------------------------------------------------
# Skip marker for tests that need the real SCF file
# ---------------------------------------------------------------------------

_skip_no_scf = pytest.mark.skipif(
    not SCF_DEFAULT_PATH.exists(),
    reason="data/scf/scf2022.csv not present in this environment",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alloc(n: int = 30) -> pd.DataFrame:
    """Synthetic SCF allocation DataFrame with columns EQUITY, BOND, CASHLI."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "EQUITY": rng.integers(0, 100_000, n).astype(float),
            "BOND": rng.integers(0, 50_000, n).astype(float),
            "CASHLI": rng.integers(0, 30_000, n).astype(float),
            "STOCKS": rng.integers(0, 80_000, n).astype(float),
        }
    )


def _make_clear_alloc_ratios() -> tuple[np.ndarray, pd.DataFrame]:
    """
    Return (cluster_ids, alloc_ratios) where each cluster has unambiguous
    mean equity ratios:
      cluster 0 → equity_ratio ≈ 0.80  (AGGRESSIVE)
      cluster 1 → equity_ratio ≈ 0.40  (MODERATE)
      cluster 2 → equity_ratio ≈ 0.05  (CONSERVATIVE)
    """
    n = 10  # samples per cluster
    cluster_ids = np.array([0] * n + [1] * n + [2] * n)
    alloc_ratios = pd.DataFrame(
        {
            "equity_ratio": [0.80] * n + [0.40] * n + [0.05] * n,
            "bond_ratio": [0.10] * n + [0.35] * n + [0.50] * n,
            "cash_ratio": [0.10] * n + [0.25] * n + [0.45] * n,
        }
    )
    return cluster_ids, alloc_ratios


# ---------------------------------------------------------------------------
# compute_allocation_ratios()
# ---------------------------------------------------------------------------


class TestComputeAllocationRatios:
    """Tests for compute_allocation_ratios() — pure function."""

    def test_returns_three_ratio_columns(self):
        """Output must have equity_ratio, bond_ratio, cash_ratio columns."""
        df = compute_allocation_ratios(_make_alloc())
        assert set(df.columns) == {"equity_ratio", "bond_ratio", "cash_ratio"}

    def test_ratios_in_unit_interval(self):
        """All ratio values must lie in [0, 1]."""
        df = compute_allocation_ratios(_make_alloc(n=100))
        for col in ["equity_ratio", "bond_ratio", "cash_ratio"]:
            assert df[col].between(0.0, 1.0).all(), f"{col} out of [0,1]"

    def test_ratio_sum_at_most_one(self):
        """Sum of three ratios per row must be ≤ 1 (EPSILON denominator inflates total)."""
        df = compute_allocation_ratios(_make_alloc(n=50))
        row_sums = df[["equity_ratio", "bond_ratio", "cash_ratio"]].sum(axis=1)
        assert (row_sums <= 1.0 + 1e-9).all()

    def test_zero_allocation_no_division_error(self):
        """A row with all-zero allocations must not raise ZeroDivisionError."""
        alloc = pd.DataFrame({"EQUITY": [0.0], "BOND": [0.0], "CASHLI": [0.0], "STOCKS": [0.0]})
        df = compute_allocation_ratios(alloc)
        # total = 0 + EPSILON, so each ratio = 0 / EPSILON = 0
        assert df["equity_ratio"].iloc[0] == pytest.approx(0.0)

    def test_pure_equity_portfolio(self):
        """A portfolio with only equity must have equity_ratio ≈ 1."""
        alloc = pd.DataFrame(
            {"EQUITY": [100_000.0], "BOND": [0.0], "CASHLI": [0.0], "STOCKS": [0.0]}
        )
        df = compute_allocation_ratios(alloc)
        expected = 100_000.0 / (100_000.0 + EPSILON)
        assert df["equity_ratio"].iloc[0] == pytest.approx(expected)

    def test_preserves_index(self):
        """Output DataFrame must preserve the index of the input."""
        alloc = _make_alloc(n=10)
        alloc.index = range(100, 110)
        df = compute_allocation_ratios(alloc)
        assert list(df.index) == list(alloc.index)

    def test_row_count_unchanged(self):
        """Output row count must match input row count."""
        alloc = _make_alloc(n=25)
        df = compute_allocation_ratios(alloc)
        assert len(df) == 25


# ---------------------------------------------------------------------------
# assign_labels()
# ---------------------------------------------------------------------------


class TestAssignLabels:
    """Tests for assign_labels() — pure function."""

    def test_labels_are_canonical_strings(self):
        """All labels must be one of the three canonical profile strings."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        assert set(labels).issubset({LABEL_CONSERVATIVE, LABEL_MODERATE, LABEL_AGGRESSIVE})

    def test_high_equity_cluster_is_aggressive(self):
        """Cluster with highest mean equity_ratio must map to AGGRESSIVE."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        # cluster 0 has equity_ratio=0.80 — must be AGGRESSIVE
        assert labels[0] == LABEL_AGGRESSIVE

    def test_low_equity_cluster_is_conservative(self):
        """Cluster with lowest mean equity_ratio must map to CONSERVATIVE."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        # cluster 2 has equity_ratio=0.05 — must be CONSERVATIVE
        assert labels[20] == LABEL_CONSERVATIVE

    def test_mid_equity_cluster_is_moderate(self):
        """Cluster with middle mean equity_ratio must map to MODERATE."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        # cluster 1 has equity_ratio=0.40 — must be MODERATE
        assert labels[10] == LABEL_MODERATE

    def test_output_length_matches_input(self):
        """Output array length must equal the number of input samples."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        assert len(labels) == len(cluster_ids)

    def test_all_three_labels_present(self):
        """All three profile labels must appear in the output."""
        cluster_ids, alloc_ratios = _make_clear_alloc_ratios()
        labels = assign_labels(cluster_ids, alloc_ratios)
        assert set(labels) == {LABEL_CONSERVATIVE, LABEL_MODERATE, LABEL_AGGRESSIVE}

    def test_wrong_n_clusters_raises(self):
        """Passing only 2 unique cluster IDs for N_CLUSTERS=3 must raise ValueError."""
        cluster_ids = np.array([0] * 10 + [1] * 10)  # only 2 clusters
        alloc_ratios = pd.DataFrame(
            {
                "equity_ratio": [0.8] * 10 + [0.2] * 10,
                "bond_ratio": [0.1] * 10 + [0.4] * 10,
                "cash_ratio": [0.1] * 10 + [0.4] * 10,
            }
        )
        with pytest.raises(ValueError, match=f"Expected {N_CLUSTERS} clusters"):
            assign_labels(cluster_ids, alloc_ratios)


# ---------------------------------------------------------------------------
# validate_k()
# ---------------------------------------------------------------------------


class TestValidateK:
    """Tests for validate_k() using synthetic data."""

    def _synthetic_X(self, n: int = 60) -> np.ndarray:
        """Three clearly-separated clusters in 3-D ratio space."""
        rng = np.random.default_rng(0)
        c0 = rng.normal([0.8, 0.1, 0.1], 0.02, (n // 3, 3))
        c1 = rng.normal([0.4, 0.35, 0.25], 0.02, (n // 3, 3))
        c2 = rng.normal([0.05, 0.5, 0.45], 0.02, (n // 3, 3))
        return np.vstack([c0, c1, c2])

    def test_returns_dict_with_k_candidates(self):
        """validate_k() must return a dict keyed by each candidate K."""
        X = self._synthetic_X()
        scores = validate_k(X, k_candidates=[2, 3])
        assert set(scores.keys()) == {2, 3}

    def test_scores_are_floats_in_valid_range(self):
        """All silhouette scores must be floats in (-1, 1]."""
        X = self._synthetic_X()
        scores = validate_k(X, k_candidates=[2, 3, 4])
        for k, s in scores.items():
            assert isinstance(s, float), f"K={k} score is not float"
            assert -1.0 <= s <= 1.0, f"K={k} silhouette {s} out of range"

    def test_k3_scores_well_on_three_cluster_data(self):
        """K=3 must achieve silhouette > 0.5 on clearly-separated 3-cluster data."""
        X = self._synthetic_X(n=90)
        scores = validate_k(X, k_candidates=[3])
        assert scores[3] > 0.5, f"Expected silhouette > 0.5 for K=3, got {scores[3]}"


# ---------------------------------------------------------------------------
# run_clustering() — requires real SCF file
# ---------------------------------------------------------------------------


class TestRunClustering:
    """Integration test for the full clustering pipeline."""

    @_skip_no_scf
    def test_output_has_profile_label_column(self):
        """run_clustering() output must contain a 'profile_label' column."""
        from backend.ml.profiler.clustering import run_clustering

        df = run_clustering(save=False)
        assert "profile_label" in df.columns

    @_skip_no_scf
    def test_all_three_labels_present_in_output(self):
        """All three profile labels must appear in the clustered output."""
        from backend.ml.profiler.clustering import run_clustering

        df = run_clustering(save=False)
        assert set(df["profile_label"].unique()) == {
            LABEL_CONSERVATIVE,
            LABEL_MODERATE,
            LABEL_AGGRESSIVE,
        }
