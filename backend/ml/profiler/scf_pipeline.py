"""
scf_pipeline.py
---------------
Preprocessing pipeline for the Survey of Consumer Finances (Fed, 2022).

Responsibilities:
    - Load the SCF 2022 Summary Extract (CSV, implicate=1)
    - Select relevant features for the ML profiler
    - Apply sample weights (wgt) for population representativeness
    - Standardise features → output ready for clustering.py

References:
    - Federal Reserve (2022). Survey of Consumer Finances — Codebook and
      Methodology. https://www.federalreserve.gov/econres/scfindex.htm
    - Grable, J.E., Lytton, R.H. (1999). Financial risk tolerance revisited.
      Financial Services Review.

Implementation notes (W1 — stub):
    The SCF 2022 Summary Extract dataset has not yet been downloaded locally.
    Functions contain the correct structure and documentation of preprocessing
    choices. Real implementation takes place in W2.

Related ADR:
    docs/adr/ADR-002-scf-preprocessing.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — no magic numbers in code
# ---------------------------------------------------------------------------

# Expected path of the SCF 2022 Summary Extract (CSV)
SCF_DEFAULT_PATH = Path("data/scf/scf2022.csv")

# First SCF implicate (1–5). We use implicate=1 for simplicity.
# Rationale: see ADR-002-scf-preprocessing.md
SCF_IMPLICATE = 1

# Columns selected from the SCF for the profiler
# Source: SCF 2022 Codebook — demographic and behavioural variables
SCF_FEATURE_COLUMNS: list[str] = [
    "AGE",        # Age of the reference person
    "INCOME",     # Annual family income (Fed-normalised)
    "NETWORTH",   # Family net worth
    "WSAVED",     # Self-reported saving propensity
    "YESFINRISK", # Willing to take financial risk (1=yes, 0=no)
    "NOFINRISK",  # Unwilling to take any financial risk (1=yes, 0=no)
    "KIDS",       # Number of children (proxy for family composition)
    "EDUC",       # Education level (proxy for financial experience)
]

# Columns describing observed portfolio allocation (label source for clustering)
SCF_ALLOCATION_COLUMNS: list[str] = [
    "EQUITY",    # Total value held in equity (stocks + equity mutual funds)
    "BOND",      # Total value held in bonds
    "CASHLI",    # Value held in cash and liquid assets
    "STOCKS",    # Direct stock holdings (subset of EQUITY)
]

# Mandatory sample weight column (SCF uses stratified sampling design)
SCF_WEIGHT_COLUMN = "WGT"

# Minimum number of observations required to proceed
MIN_OBSERVATIONS = 1_000


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def load_scf(
    path: Path = SCF_DEFAULT_PATH,
    implicate: int = SCF_IMPLICATE,
) -> pd.DataFrame:
    """Load the SCF 2022 Summary Extract and filter by implicate number.

    The SCF uses 5 multiple imputations for missing data. For academic
    simplicity we use implicate=1 (first imputation). This choice is
    documented as a limitation in ADR-002-scf-preprocessing.md.

    Args:
        path: Path to the SCF Summary Extract CSV file.
        implicate: Implicate number to use (1–5). Default: 1.

    Returns:
        DataFrame with all SCF columns for the selected implicate.

    Raises:
        FileNotFoundError: If the CSV file is not found at the given path.
        ValueError: If implicate is not in range [1, 5].
    """
    if not 1 <= implicate <= 5:
        raise ValueError(f"implicate must be between 1 and 5, got: {implicate}")

    if not path.exists():
        raise FileNotFoundError(
            f"SCF dataset not found at: {path}\n"
            "Download the 2022 Summary Extract from:\n"
            "https://www.federalreserve.gov/econres/scfindex.htm"
        )

    logger.info("Loading SCF from %s (implicate=%d)...", path, implicate)

    # TODO (W2): implement real loading
    # The SCF CSV has a column 'Y1' whose last digit identifies the implicate
    # df = pd.read_csv(path, low_memory=False)
    # df = df[df["Y1"] % 10 == implicate].reset_index(drop=True)

    raise NotImplementedError(
        "load_scf() — W2 implementation pending. "
        "The SCF 2022 dataset must be downloaded before proceeding."
    )


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """Select and retain relevant columns from the raw SCF DataFrame.

    Keeps demographic/behavioural feature columns, allocation columns
    (for clustering), and the sample weight column.

    Args:
        df: Raw SCF DataFrame returned by load_scf().

    Returns:
        DataFrame with only the columns required by the pipeline.

    Raises:
        ValueError: If any required columns are missing from the DataFrame.
    """
    required = SCF_FEATURE_COLUMNS + SCF_ALLOCATION_COLUMNS + [SCF_WEIGHT_COLUMN]
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing columns in SCF dataset: {missing}\n"
            "Check the SCF 2022 Codebook for correct variable names."
        )

    logger.info(
        "Selecting %d feature columns + %d allocation columns + weight.",
        len(SCF_FEATURE_COLUMNS), len(SCF_ALLOCATION_COLUMNS),
    )

    # TODO (W2): add engineered features if needed
    # e.g. EQUITY_RATIO = EQUITY / (EQUITY + BOND + CASHLI)

    return df[required].copy()


def standardise_features(
    df: pd.DataFrame,
    feature_cols: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, StandardScaler]:
    """Standardise numeric features to zero mean and unit variance.

    Sample weights (WGT) and allocation columns are not standardised —
    they remain in the DataFrame as auxiliary columns.

    Args:
        df: DataFrame with selected columns (output of select_features()).
        feature_cols: List of columns to standardise.
                      Default: SCF_FEATURE_COLUMNS.

    Returns:
        Tuple (df_standardised, scaler) where scaler is fitted and can
        be reused to transform new user inputs at inference time.
    """
    if feature_cols is None:
        feature_cols = SCF_FEATURE_COLUMNS

    cols_to_scale = [col for col in feature_cols if col in df.columns]

    scaler = StandardScaler()
    df_out = df.copy()
    df_out[cols_to_scale] = scaler.fit_transform(df[cols_to_scale])

    logger.info("Standardisation complete on %d columns.", len(cols_to_scale))

    return df_out, scaler


def build_pipeline(
    path: Path = SCF_DEFAULT_PATH,
    implicate: int = SCF_IMPLICATE,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, StandardScaler]:
    """Main entry point for the SCF preprocessing pipeline.

    Executes in sequence: load -> select -> standardise.

    Args:
        path: Path to the SCF CSV file.
        implicate: Implicate to use (default: 1).

    Returns:
        Tuple (X, alloc, weights, scaler) where:
            X       -- standardised features (n_samples x n_features)
            alloc   -- raw allocation columns for clustering (n_samples x 4)
            weights -- SCF sample weights (n_samples,)
            scaler  -- StandardScaler fitted on X

    Example:
        >>> X, alloc, weights, scaler = build_pipeline()
        >>> # X is ready for clustering.py
        >>> # alloc is ready to build labels via K-Means / GMM
    """
    df_raw = load_scf(path=path, implicate=implicate)
    df_selected = select_features(df_raw)
    df_std, scaler = standardise_features(df_selected)

    if len(df_std) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Too few observations after filtering: {len(df_std)} "
            f"(minimum required: {MIN_OBSERVATIONS})"
        )

    X = df_std[SCF_FEATURE_COLUMNS].to_numpy()
    alloc = df_selected[SCF_ALLOCATION_COLUMNS]
    weights = df_selected[SCF_WEIGHT_COLUMN].to_numpy()

    logger.info(
        "SCF pipeline complete: %d observations, %d features.",
        len(X), X.shape[1],
    )

    return X, alloc, weights, scaler
