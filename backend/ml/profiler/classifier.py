"""
classifier.py
-------------
Phase B GBM-based risk profiler trained on Fed SCF 2022.

Responsibilities:
    - Train a GradientBoostingClassifier on the labeled SCF dataset produced
      by clustering.py (data/scf/scf_labeled.parquet).
    - Use SCF sample weights (WGT) to correct for the survey's oversampling
      of high-net-worth households.
    - Expose profile_user_gbm() as a drop-in replacement for profile_user()
      from rule_based.py — same ProfilerOutput schema.
    - Compute SHAP TreeExplainer values for per-prediction explainability.

References:
    - Federal Reserve (2022). Survey of Consumer Finances.
    - Lundberg, S.M., Lee, S.-I. (2017). A Unified Approach to Interpreting
      Model Predictions. NeurIPS 2017.
    - sklearn GradientBoostingClassifier docs.

Related ADR:
    docs/adr/ADR-003-gbm-profiler.md (to be written)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, cast

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder

from backend.ml.profiler.rule_based import ProfilerOutput, TopDriver

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

LOW_CONFIDENCE_THRESHOLD: float = 0.65
N_TOP_DRIVERS: int = 3
MODEL_PATH: Path = Path("data/scf/gbm_model.pkl")
LABELED_DATA_PATH: Path = Path("data/scf/scf_labeled.parquet")

FEATURE_COLS: list[str] = [
    "AGE",
    "EDUC",
    "INCOME",
    "YESFINRISK",
    "NOFINRISK",
    "KIDS",
    "NETWORTH",
    "WSAVED",
    "EQUITY_RATIO",
]

TARGET_COL: str = "profile_label"
WEIGHT_COL: str = "WGT"
MODEL_VERSION_GBM: str = "gbm_scf_v1"

# GBM hyperparameters — fixed for reproducibility
GBM_N_ESTIMATORS: int = 200
GBM_MAX_DEPTH: int = 4
GBM_LEARNING_RATE: float = 0.05
GBM_RANDOM_STATE: int = 42

CV_N_FOLDS: int = 3

# Module-level cache so the model is loaded from disk only once per process.
_MODEL_CACHE: dict[str, Any] = {}


# =============================================================================
# Training
# =============================================================================

def train_gbm() -> GradientBoostingClassifier:
    """Train a GBM risk profiler on the labeled SCF 2022 dataset.

    Loads ``data/scf/scf_labeled.parquet`` (produced by clustering.py),
    trains a GradientBoostingClassifier with SCF sample weights, evaluates
    a LogisticRegression baseline for comparison, and persists the fitted
    GBM + LabelEncoder to ``data/scf/gbm_model.pkl``.

    Parameters
    ----------
    None

    Returns
    -------
    GradientBoostingClassifier
        The fitted GBM model.

    Raises
    ------
    FileNotFoundError
        If ``data/scf/scf_labeled.parquet`` does not exist.
        Run ``python -m backend.ml.profiler.clustering`` first.

    Notes
    -----
    SCF sample weights (WGT) are mandatory: the survey oversamples
    high-net-worth households, so un-weighted training would produce a
    model biased towards AGGRESSIVE profiles.
    """
    if not LABELED_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Labeled dataset not found at: {LABELED_DATA_PATH}\n"
            "Run clustering.py first: python -m backend.ml.profiler.clustering"
        )

    logger.info("Loading labeled SCF dataset from %s...", LABELED_DATA_PATH)
    df = pd.read_parquet(LABELED_DATA_PATH)

    X = df[FEATURE_COLS].to_numpy()
    y_raw: np.ndarray = df[TARGET_COL].to_numpy()
    weights: np.ndarray = df[WEIGHT_COL].to_numpy()

    le = LabelEncoder()
    y: np.ndarray = le.fit_transform(y_raw)
    logger.info("Classes: %s → encoded as %s", le.classes_, list(range(len(le.classes_))))

    # --- GBM ---
    gbm = GradientBoostingClassifier(
        n_estimators=GBM_N_ESTIMATORS,
        max_depth=GBM_MAX_DEPTH,
        learning_rate=GBM_LEARNING_RATE,
        random_state=GBM_RANDOM_STATE,
    )
    logger.info("Training GBM (n_estimators=%d)...", GBM_N_ESTIMATORS)
    gbm.fit(X, y, sample_weight=weights)

    train_acc = gbm.score(X, y, sample_weight=weights)
    print(f"GBM train accuracy (weighted): {train_acc:.4f}")

    cv = StratifiedKFold(n_splits=CV_N_FOLDS, shuffle=True, random_state=GBM_RANDOM_STATE)
    cv_scores = cross_val_score(gbm, X, y, cv=cv, scoring="accuracy")
    print(f"GBM cross-val accuracy ({CV_N_FOLDS}-fold): {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # --- LogisticRegression baseline ---
    lr = LogisticRegression(max_iter=1000, random_state=GBM_RANDOM_STATE)
    lr.fit(X, y, sample_weight=weights)
    lr_train_acc = lr.score(X, y, sample_weight=weights)
    lr_cv = cross_val_score(lr, X, y, cv=cv, scoring="accuracy")
    print(f"LR  train accuracy (weighted): {lr_train_acc:.4f}")
    print(f"LR  cross-val accuracy ({CV_N_FOLDS}-fold): {lr_cv.mean():.4f} ± {lr_cv.std():.4f}")

    # --- Persist ---
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"gbm": gbm, "le": le}, MODEL_PATH)
    logger.info("Model saved to %s", MODEL_PATH)
    print(f"Model saved to: {MODEL_PATH}")

    # Update the module-level cache so subsequent calls in the same process
    # pick up the freshly trained model without re-reading from disk.
    _MODEL_CACHE["gbm"] = gbm
    _MODEL_CACHE["le"] = le

    return gbm


# =============================================================================
# Inference
# =============================================================================

def _load_model() -> tuple[GradientBoostingClassifier, LabelEncoder]:
    """Load GBM + LabelEncoder from disk into the module-level cache.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[GradientBoostingClassifier, LabelEncoder]
        Cached or freshly loaded model pair.

    Raises
    ------
    FileNotFoundError
        If ``data/scf/gbm_model.pkl`` does not exist.
    """
    if "gbm" not in _MODEL_CACHE:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Trained model not found at: {MODEL_PATH}\n"
                "Run train_gbm() first: python backend/ml/profiler/classifier.py"
            )
        payload = joblib.load(MODEL_PATH)
        _MODEL_CACHE["gbm"] = payload["gbm"]
        _MODEL_CACHE["le"] = payload["le"]
        logger.info("GBM model loaded from %s", MODEL_PATH)

    return _MODEL_CACHE["gbm"], _MODEL_CACHE["le"]


def profile_user_gbm(user_features: dict[str, float]) -> ProfilerOutput:
    """Classify a user's risk profile using the trained GBM + SHAP explainability.

    Parameters
    ----------
    user_features : dict[str, float]
        Feature values keyed by name. Must contain exactly the keys in
        ``FEATURE_COLS``:
        ``AGE, EDUC, INCOME, YESFINRISK, NOFINRISK, KIDS, NETWORTH,
        WSAVED, EQUITY_RATIO``.

    Returns
    -------
    ProfilerOutput
        Profile label, confidence (max predict_proba), low-confidence flag,
        top-3 SHAP drivers normalised to sum=1.0, and
        ``model_version="gbm_scf_v1"``.

    Raises
    ------
    FileNotFoundError
        If the model file does not exist (train_gbm() has not been run).

    Notes
    -----
    SHAP values are computed via ``shap.TreeExplainer`` for the predicted
    class. Importances are the absolute SHAP values of the top-3 features,
    normalised so they sum to 1.0 — matching the ``TopDriver`` contract
    from Phase A.
    """
    gbm, le = _load_model()

    X_input = pd.DataFrame([user_features])[FEATURE_COLS]

    proba: np.ndarray = gbm.predict_proba(X_input)[0]
    confidence = float(np.max(proba))
    pred_class_idx = int(np.argmax(proba))
    pred_label: str = le.inverse_transform([pred_class_idx])[0]

    # SHAP — TreeExplainer for multi-class GBM
    explainer = shap.TreeExplainer(gbm)
    shap_vals = explainer.shap_values(X_input)

    # shap_vals is either a list [cls0_arr, cls1_arr, cls2_arr] (older shap)
    # or a 3-D array (n_samples, n_features, n_classes) (newer shap).
    if isinstance(shap_vals, list):
        sv_for_class: np.ndarray = np.array(shap_vals[pred_class_idx])[0]
    else:
        sv_for_class = np.array(shap_vals)[0, :, pred_class_idx]

    abs_shap = np.abs(sv_for_class)
    top_idx: np.ndarray = np.argsort(abs_shap)[::-1][:N_TOP_DRIVERS]
    total = float(abs_shap[top_idx].sum())

    if total > 0:
        top_drivers: list[TopDriver] = [
            TopDriver(
                feature=FEATURE_COLS[int(i)],
                importance=float(abs_shap[int(i)] / total),
            )
            for i in top_idx
        ]
    else:
        # Degenerate case: all SHAP values zero (should not occur in practice)
        top_drivers = [
            TopDriver(feature=FEATURE_COLS[int(i)], importance=round(1.0 / N_TOP_DRIVERS, 6))
            for i in top_idx
        ]

    return ProfilerOutput(
        profile_label=cast(Literal["CONSERVATIVE", "MODERATE", "AGGRESSIVE"], pred_label),
        confidence=confidence,
        low_confidence_flag=confidence < LOW_CONFIDENCE_THRESHOLD,
        top_drivers=top_drivers,
        model_version=MODEL_VERSION_GBM,
    )


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    train_gbm()
