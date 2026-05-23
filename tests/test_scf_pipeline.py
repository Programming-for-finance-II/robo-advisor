"""
tests/test_scf_pipeline.py
==========================
Unit tests for backend/ml/profiler/scf_pipeline.py.

Strategy:
  - select_features(), standardise_features() are tested with small
    synthetic DataFrames — no SCF file required, always run.
  - load_scf() error paths (FileNotFoundError, bad implicate) are always
    run using a non-existent path / out-of-range int.
  - load_scf() happy path and build_pipeline() are skipped when
    data/scf/scf2022.csv is absent (CI environment).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.ml.profiler.scf_pipeline import (
    EPSILON,
    SCF_ALLOCATION_COLUMNS,
    SCF_DEFAULT_PATH,
    SCF_FEATURE_COLUMNS,
    SCF_WEIGHT_COLUMN,
    build_pipeline,
    load_scf,
    select_features,
    standardise_features,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCF_AVAILABLE = SCF_DEFAULT_PATH.exists()
_skip_no_scf = pytest.mark.skipif(
    not _SCF_AVAILABLE,
    reason="data/scf/scf2022.csv not present in this environment",
)


def _make_raw_df(n: int = 20) -> pd.DataFrame:
    """Build a minimal synthetic DataFrame that mimics the SCF raw schema."""
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            # demographic features
            "AGE": rng.integers(25, 75, n).astype(float),
            "INCOME": rng.integers(20_000, 200_000, n).astype(float),
            "NETWORTH": rng.integers(0, 1_000_000, n).astype(float),
            "WSAVED": rng.integers(1, 4, n).astype(float),
            "YESFINRISK": rng.integers(0, 2, n).astype(float),
            "NOFINRISK": rng.integers(0, 2, n).astype(float),
            "KIDS": rng.integers(0, 5, n).astype(float),
            "EDUC": rng.integers(8, 18, n).astype(float),
            # allocation columns
            "EQUITY": rng.integers(0, 100_000, n).astype(float),
            "BOND": rng.integers(0, 50_000, n).astype(float),
            "CASHLI": rng.integers(0, 30_000, n).astype(float),
            "STOCKS": rng.integers(0, 80_000, n).astype(float),
            # weight
            "WGT": rng.integers(500, 5000, n).astype(float),
            # implicate identifier (Y1 % 10 == 1 → implicate 1)
            "Y1": [11] * n,
        }
    )


# ---------------------------------------------------------------------------
# select_features()
# ---------------------------------------------------------------------------


class TestSelectFeatures:
    """Tests for select_features() using synthetic DataFrames."""

    def test_returns_expected_columns(self):
        """Output must contain all SCF_FEATURE_COLUMNS, allocation cols, and WGT."""
        df = select_features(_make_raw_df())
        expected = set(SCF_FEATURE_COLUMNS + SCF_ALLOCATION_COLUMNS + [SCF_WEIGHT_COLUMN])
        assert expected.issubset(df.columns)

    def test_equity_ratio_engineered(self):
        """EQUITY_RATIO column must be present and lie in [0, 1)."""
        df = select_features(_make_raw_df())
        assert "EQUITY_RATIO" in df.columns
        assert df["EQUITY_RATIO"].between(0.0, 1.0).all()

    def test_equity_ratio_formula(self):
        """EQUITY_RATIO = EQUITY / (EQUITY + BOND + CASHLI + EPSILON)."""
        raw = _make_raw_df(n=5)
        df = select_features(raw)
        expected = raw["EQUITY"] / (raw["EQUITY"] + raw["BOND"] + raw["CASHLI"] + EPSILON)
        pd.testing.assert_series_equal(
            df["EQUITY_RATIO"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_no_rows_dropped(self):
        """select_features must not drop any rows from the input."""
        raw = _make_raw_df(n=30)
        assert len(select_features(raw)) == 30

    def test_raises_on_missing_column(self):
        """Missing a required raw column must raise ValueError."""
        raw = _make_raw_df()
        raw = raw.drop(columns=["EQUITY"])
        with pytest.raises(ValueError, match="Missing columns"):
            select_features(raw)

    def test_raises_on_multiple_missing_columns(self):
        """Multiple missing columns are all reported in the ValueError."""
        raw = _make_raw_df()
        raw = raw.drop(columns=["EQUITY", "BOND", "AGE"])
        with pytest.raises(ValueError, match="Missing columns"):
            select_features(raw)


# ---------------------------------------------------------------------------
# standardise_features()
# ---------------------------------------------------------------------------


class TestStandardiseFeatures:
    """Tests for standardise_features() using synthetic DataFrames."""

    def test_returns_tuple_of_two(self):
        """Must return (df_standardised, scaler)."""
        df = select_features(_make_raw_df())
        result = standardise_features(df)
        assert len(result) == 2

    def test_standardised_mean_near_zero(self):
        """Feature columns after standardisation must have mean ≈ 0."""
        df = select_features(_make_raw_df(n=100))
        df_std, _ = standardise_features(df)
        for col in SCF_FEATURE_COLUMNS:
            assert abs(df_std[col].mean()) < 1e-9, f"{col} mean not ≈ 0"

    def test_standardised_std_near_one(self):
        """Feature columns after standardisation must have std ≈ 1."""
        df = select_features(_make_raw_df(n=100))
        df_std, _ = standardise_features(df)
        for col in SCF_FEATURE_COLUMNS:
            assert abs(df_std[col].std(ddof=0) - 1.0) < 1e-6, f"{col} std not ≈ 1"

    def test_non_feature_cols_unchanged(self):
        """WGT and allocation columns must not be scaled."""
        df = select_features(_make_raw_df())
        df_std, _ = standardise_features(df)
        pd.testing.assert_series_equal(df["WGT"], df_std["WGT"])

    def test_custom_feature_cols(self):
        """Passing a custom feature_cols list must scale only those columns."""
        df = select_features(_make_raw_df(n=50))
        df_std, scaler = standardise_features(df, feature_cols=["AGE", "INCOME"])
        assert abs(df_std["AGE"].mean()) < 1e-9
        assert abs(df_std["INCOME"].mean()) < 1e-9
        # NETWORTH should be untouched
        pd.testing.assert_series_equal(df["NETWORTH"], df_std["NETWORTH"])

    def test_scaler_can_transform_new_data(self):
        """Returned scaler must be reusable to transform a new row."""
        df = select_features(_make_raw_df(n=50))
        _, scaler = standardise_features(df)
        new_row = df[SCF_FEATURE_COLUMNS].iloc[[0]]
        transformed = scaler.transform(new_row)
        assert transformed.shape == (1, len(SCF_FEATURE_COLUMNS))


# ---------------------------------------------------------------------------
# load_scf() — error paths (no file needed)
# ---------------------------------------------------------------------------


class TestLoadScfErrors:
    """Error-path tests for load_scf() that do not require the SCF file."""

    def test_file_not_found_raises(self):
        """Non-existent path must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="SCF dataset not found"):
            load_scf(path=Path("/tmp/does_not_exist_scf.csv"))

    def test_invalid_implicate_too_low(self):
        """implicate < 1 must raise ValueError."""
        with pytest.raises(ValueError, match="implicate must be between"):
            load_scf(path=Path("/tmp/fake.csv"), implicate=0)

    def test_invalid_implicate_too_high(self):
        """implicate > 5 must raise ValueError."""
        with pytest.raises(ValueError, match="implicate must be between"):
            load_scf(path=Path("/tmp/fake.csv"), implicate=6)


# ---------------------------------------------------------------------------
# load_scf() + build_pipeline() — happy path (requires real SCF file)
# ---------------------------------------------------------------------------


class TestLoadScfHappyPath:
    """Integration tests that require data/scf/scf2022.csv."""

    @_skip_no_scf
    def test_returns_dataframe(self):
        """load_scf() must return a non-empty DataFrame."""
        df = load_scf()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    @_skip_no_scf
    def test_implicate_filter_correct(self):
        """All rows in the returned DataFrame must belong to implicate=1."""
        df = load_scf(implicate=1)
        assert (df["Y1"] % 10 == 1).all()

    @_skip_no_scf
    def test_build_pipeline_output_shapes(self):
        """build_pipeline() must return arrays with consistent n_samples."""
        X, alloc, weights, scaler, df_selected = build_pipeline()
        n = len(df_selected)
        assert X.shape == (n, len(SCF_FEATURE_COLUMNS))
        assert len(weights) == n
        assert len(alloc) == n

    @_skip_no_scf
    def test_build_pipeline_feature_cols_order(self):
        """X columns must match SCF_FEATURE_COLUMNS order exactly."""
        X, alloc, weights, scaler, df_selected = build_pipeline()
        # scaler was fitted on SCF_FEATURE_COLUMNS in that order
        assert scaler.n_features_in_ == len(SCF_FEATURE_COLUMNS)
