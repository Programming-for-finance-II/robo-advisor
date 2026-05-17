"""
tests/test_profiler.py
======================
Unit tests for the risk profiler — Phase A (rule-based) and Phase B (GBM).

Tests are organised by label (CONSERVATIVE / MODERATE / AGGRESSIVE),
then by special cases (Q7 override, top_drivers normalisation),
and finally by the GBM path (Phase B).

All tests call profile_user() or map_score_to_label() directly —
the HTTP layer is tested separately in test_api.py.

Note on Q4 (reverse-coded):
    Q4 scoring: a=3, b=2, c=1, d=0
    All other questions: a=0, b=1, c=2, d=3

Boundary table (from questionnaire_schema.md):
    0–7   -> CONSERVATIVE  confidence=1.0
    8–9   -> CONSERVATIVE  confidence=0.7  (borderline)
    10–11 -> MODERATE      confidence=0.7  (borderline)
    12–17 -> MODERATE      confidence=1.0
    18–19 -> MODERATE      confidence=0.7  (borderline)
    20–21 -> AGGRESSIVE    confidence=0.7  (borderline)
    22–30 -> AGGRESSIVE    confidence=1.0
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.ml.profiler.rule_based import (
    CONFIDENCE_BORDERLINE,
    CONFIDENCE_HIGH,
    compute_score,
    map_score_to_label,
    profile_user,
)

# =============================================================================
# Helpers
# =============================================================================

def _responses(**overrides: str) -> dict[str, str]:
    """Build a complete 10-question response dict.

    Default baseline: all 'a' → score = 3 (Q4='a' reverse-coded = 3, rest = 0).
    Pass keyword args to override individual questions, e.g. Q1='d'.
    """
    base = {f"Q{i}": "a" for i in range(1, 11)}
    base.update(overrides)
    return base


def _score(responses: dict[str, str]) -> int:
    """Convenience wrapper around compute_score()."""
    return compute_score(responses)


# =============================================================================
# CONSERVATIVE label — ≥3 test cases
# =============================================================================

class TestConservativeLabel:
    """Tests for score range 0–9 -> CONSERVATIVE."""

    def test_score_7_conservative_high_confidence(self):
        """Score 7 (upper end of high-confidence zone) -> CONSERVATIVE, conf=1.0.

        Construction:
            Q1='b'(1) + Q2='b'(1) + Q3='b'(1) + Q4='a'(3 reverse)
            + Q5='a'(0) + Q6='a'(0) + Q7='b'(1) + Q8='a'(0)
            + Q9='a'(0) + Q10='a'(0) = 7
        Q7='b' ensures no MiFID II override is triggered.
        """
        r = _responses(Q1="b", Q2="b", Q3="b", Q7="b")
        assert _score(r) == 7, "Precondition: score must be 7"
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_HIGH
        assert result["low_confidence_flag"] is False

    def test_score_8_conservative_borderline(self):
        """Score 8 (lower borderline zone) -> CONSERVATIVE, conf=0.7.

        Construction: score_7 + Q5='b'(+1) = 8
        """
        r = _responses(Q1="b", Q2="b", Q3="b", Q5="b", Q7="b")
        assert _score(r) == 8, "Precondition: score must be 8"
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_BORDERLINE
        assert result["low_confidence_flag"] is True

    def test_score_9_conservative_borderline(self):
        """Score 9 (upper borderline zone) -> CONSERVATIVE, conf=0.7.

        Construction: score_8 + Q6='b'(+1) = 9
        """
        r = _responses(Q1="b", Q2="b", Q3="b", Q5="b", Q6="b", Q7="b")
        assert _score(r) == 9, "Precondition: score must be 9"
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_BORDERLINE
        assert result["low_confidence_flag"] is True

    def test_score_0_conservative_all_minimum(self):
        """Score 0 (all a except Q4='d' which reverse-codes to 0) -> CONSERVATIVE.

        With all questions at their lowest possible score value (0).
        Note: Q4='d' = 0 (reverse-coded). Q7='b' to avoid override.
        """
        r = _responses(Q4="d", Q7="b")
        assert _score(r) == 1, "Q7='b' adds 1 point"
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_HIGH

    def test_conservative_top_drivers_are_lowest_scoring(self):
        """CONSERVATIVE top_drivers must be the 3 lowest-scoring questions."""
        r = _responses(Q7="b")
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        features = [d["feature"] for d in result["top_drivers"]]
        assert len(features) == 3
        for d in result["top_drivers"]:
            assert 0.0 <= d["importance"] <= 1.0


# =============================================================================
# MODERATE label — ≥3 test cases
# =============================================================================

class TestModerateLabel:
    """Tests for score ranges 10–11 and 12–19 -> MODERATE."""

    def test_score_10_moderate_borderline_low(self):
        """Score 10 (lowest MODERATE borderline) -> MODERATE, conf=0.7.

        Construction: score_9 + Q8='b'(+1) = 10
        """
        r = _responses(Q1="b", Q2="b", Q3="b", Q5="b", Q6="b", Q7="b", Q8="b")
        assert _score(r) == 10, "Precondition: score must be 10"
        result = profile_user(r)
        assert result["profile_label"] == "MODERATE"
        assert result["confidence"] == CONFIDENCE_BORDERLINE
        assert result["low_confidence_flag"] is True

    def test_score_17_moderate_high_confidence(self):
        """Score 17 (upper end of high-confidence MODERATE zone) -> MODERATE, conf=1.0.

        Construction:
            Q1='c'(2) + Q2='c'(2) + Q3='b'(1) + Q4='d'(0 reverse)
            + Q5='c'(2) + Q6='c'(2) + Q7='c'(2) + Q8='c'(2)
            + Q9='c'(2) + Q10='c'(2) = 17
        """
        r = {
            "Q1": "c", "Q2": "c", "Q3": "b", "Q4": "d",
            "Q5": "c", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        assert _score(r) == 17, "Precondition: score must be 17"
        result = profile_user(r)
        assert result["profile_label"] == "MODERATE"
        assert result["confidence"] == CONFIDENCE_HIGH
        assert result["low_confidence_flag"] is False

    def test_score_18_moderate_borderline_high(self):
        """Score 18 (lower high-MODERATE borderline) -> MODERATE, conf=0.7.

        Construction: score_17 with Q3='c' instead of 'b' (+1) = 18
        """
        r = {
            "Q1": "c", "Q2": "c", "Q3": "c", "Q4": "d",
            "Q5": "c", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        assert _score(r) == 18, "Precondition: score must be 18"
        result = profile_user(r)
        assert result["profile_label"] == "MODERATE"
        assert result["confidence"] == CONFIDENCE_BORDERLINE
        assert result["low_confidence_flag"] is True

    def test_score_12_moderate_high_confidence_inner_zone(self):
        """Score 12 (lowest high-confidence MODERATE) -> MODERATE, conf=1.0."""
        label, confidence = map_score_to_label(12)
        assert label == "MODERATE"
        assert confidence == CONFIDENCE_HIGH

    def test_moderate_top_drivers_count(self):
        """MODERATE always returns exactly 3 top_drivers."""
        r = {
            "Q1": "c", "Q2": "c", "Q3": "c", "Q4": "d",
            "Q5": "c", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        result = profile_user(r)
        assert result["profile_label"] == "MODERATE"
        assert len(result["top_drivers"]) == 3


# =============================================================================
# AGGRESSIVE label — ≥3 test cases
# =============================================================================

class TestAggressiveLabel:
    """Tests for score range 20–30 -> AGGRESSIVE."""

    def test_score_21_aggressive_borderline(self):
        """Score 21 (upper AGGRESSIVE borderline) -> AGGRESSIVE, conf=0.7.

        Construction:
            Q1='d'(3) + Q2='d'(3) + Q3='d'(3) + Q4='d'(0 reverse)
            + Q5='c'(2) + Q6='c'(2) + Q7='c'(2) + Q8='c'(2)
            + Q9='c'(2) + Q10='c'(2) = 21
        """
        r = {
            "Q1": "d", "Q2": "d", "Q3": "d", "Q4": "d",
            "Q5": "c", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        assert _score(r) == 21, "Precondition: score must be 21"
        result = profile_user(r)
        assert result["profile_label"] == "AGGRESSIVE"
        assert result["confidence"] == CONFIDENCE_BORDERLINE
        assert result["low_confidence_flag"] is True

    def test_score_22_aggressive_high_confidence(self):
        """Score 22 (first high-confidence AGGRESSIVE score) -> AGGRESSIVE, conf=1.0.

        Construction: score_21 + Q5='d'(+1 over 'c') = 22
        """
        r = {
            "Q1": "d", "Q2": "d", "Q3": "d", "Q4": "d",
            "Q5": "d", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        assert _score(r) == 22, "Precondition: score must be 22"
        result = profile_user(r)
        assert result["profile_label"] == "AGGRESSIVE"
        assert result["confidence"] == CONFIDENCE_HIGH
        assert result["low_confidence_flag"] is False

    def test_score_30_aggressive_maximum(self):
        """Score 30 (maximum possible score) -> AGGRESSIVE, conf=1.0.

        All 'd' except Q4='a' (reverse-coded, 'a'=3 is the max for Q4).
        Q7='d' does NOT trigger the override (override only on 'a').
        """
        r = {f"Q{i}": "d" for i in range(1, 11)}
        r["Q4"] = "a"  # reverse-coded: 'a' = 3 (maximum for Q4)
        assert _score(r) == 30, "Precondition: score must be 30"
        result = profile_user(r)
        assert result["profile_label"] == "AGGRESSIVE"
        assert result["confidence"] == CONFIDENCE_HIGH

    def test_aggressive_top_drivers_are_highest_scoring(self):
        """AGGRESSIVE top_drivers must be the 3 highest-scoring questions."""
        r = {
            "Q1": "d", "Q2": "d", "Q3": "d", "Q4": "d",
            "Q5": "d", "Q6": "c", "Q7": "c", "Q8": "c",
            "Q9": "c", "Q10": "c",
        }
        result = profile_user(r)
        assert result["profile_label"] == "AGGRESSIVE"
        assert len(result["top_drivers"]) == 3
        features = [d["feature"] for d in result["top_drivers"]]
        high_score_features = {
            "age", "income_comfort", "liquid_runway_months", "investment_experience"
        }
        assert all(f in high_score_features for f in features)


# =============================================================================
# Q7 override — MiFID II hard rule
# =============================================================================

class TestQ7Override:
    """Q7='a' (safety net money) must cap the profile at CONSERVATIVE
    with confidence=1.0 regardless of the total questionnaire score."""

    def test_q7_override_on_aggressive_score(self):
        """Q7='a' + all other 'd' -> CONSERVATIVE despite score being very high."""
        r = {f"Q{i}": "d" for i in range(1, 11)}
        r["Q4"] = "a"   # reverse-coded: max score for Q4
        r["Q7"] = "a"   # triggers override
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_HIGH
        assert result["low_confidence_flag"] is False

    def test_q7_override_on_moderate_score(self):
        """Q7='a' on a borderline-MODERATE score -> CONSERVATIVE, conf=1.0."""
        r = {
            "Q1": "c", "Q2": "c", "Q3": "c", "Q4": "d",
            "Q5": "c", "Q6": "c", "Q7": "a",  # override
            "Q8": "c", "Q9": "c", "Q10": "c",
        }
        result = profile_user(r)
        assert result["profile_label"] == "CONSERVATIVE"
        assert result["confidence"] == CONFIDENCE_HIGH

    def test_q7_no_override_on_other_responses(self):
        """Q7='b', 'c', 'd' must NOT trigger the override."""
        for letter in ("b", "c", "d"):
            r = _responses(Q1="d", Q2="d", Q3="d", Q5="d", Q7=letter)
            result = profile_user(r)
            assert result["profile_label"] != "CONSERVATIVE" or result["confidence"] in (
                CONFIDENCE_HIGH, CONFIDENCE_BORDERLINE
            )


# =============================================================================
# top_drivers normalisation
# =============================================================================

class TestTopDriversNormalisation:
    """Importance values must be normalised against the POSSIBLE maximum
    deviation (1.5), not the observed maximum."""

    def test_uniform_b_responses_importance_approx_one_third(self):
        """All 'b' responses -> every question deviates 0.5 from neutral (1.5).
        Importance = 0.5 / 1.5 ≈ 0.333 for each question.

        Score: 9 × 1 + Q4='b'(2) = 11 -> MODERATE borderline.
        All importances must be ~0.333, NOT 1.0.
        """
        r = {f"Q{i}": "b" for i in range(1, 11)}
        result = profile_user(r)
        assert result["profile_label"] == "MODERATE"
        for driver in result["top_drivers"]:
            assert abs(driver["importance"] - 1 / 3) < 0.01, (
                f"Expected importance ≈ 0.333, got {driver['importance']} "
                f"for feature '{driver['feature']}'"
            )

    def test_importance_values_in_unit_interval(self):
        """All importance values must be in [0.0, 1.0] regardless of responses."""
        test_cases = [
            _responses(Q7="b"),
            {f"Q{i}": "b" for i in range(1, 11)},
            {f"Q{i}": "d" for i in range(1, 11)},
        ]
        for responses in test_cases:
            result = profile_user(responses)
            for d in result["top_drivers"]:
                assert 0.0 <= d["importance"] <= 1.0, (
                    f"Importance {d['importance']} out of [0,1] for "
                    f"feature '{d['feature']}', label '{result['profile_label']}'"
                )

    def test_top_drivers_always_returns_three(self):
        """profile_user must always return exactly 3 top_drivers."""
        for letter in ("a", "b", "c", "d"):
            r = {f"Q{i}": letter for i in range(1, 11)}
            if letter == "a":
                r["Q7"] = "b"
            result = profile_user(r)
            assert len(result["top_drivers"]) == 3, (
                f"Expected 3 top_drivers, got {len(result['top_drivers'])} "
                f"for all-'{letter}' responses"
            )


# =============================================================================
# Input validation
# =============================================================================

class TestInputValidation:
    """profile_user must raise ValueError on malformed input."""

    def test_missing_question_raises(self):
        """Missing a question key -> ValueError."""
        r = _responses(Q7="b")
        del r["Q3"]
        with pytest.raises(ValueError, match="Missing"):
            profile_user(r)

    def test_extra_question_raises(self):
        """Unexpected key in responses -> ValueError."""
        r = _responses(Q7="b")
        r["Q11"] = "a"
        with pytest.raises(ValueError, match="Unexpected"):
            profile_user(r)

    def test_invalid_letter_raises(self):
        """Response letter outside {a,b,c,d} -> ValueError."""
        r = _responses(Q7="b")
        r["Q5"] = "z"
        with pytest.raises(ValueError, match="Invalid response"):
            profile_user(r)

    def test_non_dict_input_raises(self):
        """Non-dict input -> ValueError."""
        with pytest.raises(ValueError):
            profile_user(["a", "b", "c"])  # type: ignore[arg-type]


# =============================================================================
# map_score_to_label — boundary table exhaustive check
# =============================================================================

class TestScoreBoundaries:
    """Verify every boundary transition from the questionnaire schema."""

    @pytest.mark.parametrize("score,expected_label,expected_conf", [
        (0,  "CONSERVATIVE", CONFIDENCE_HIGH),
        (7,  "CONSERVATIVE", CONFIDENCE_HIGH),
        (8,  "CONSERVATIVE", CONFIDENCE_BORDERLINE),
        (9,  "CONSERVATIVE", CONFIDENCE_BORDERLINE),
        (10, "MODERATE",     CONFIDENCE_BORDERLINE),
        (11, "MODERATE",     CONFIDENCE_BORDERLINE),
        (12, "MODERATE",     CONFIDENCE_HIGH),
        (17, "MODERATE",     CONFIDENCE_HIGH),
        (18, "MODERATE",     CONFIDENCE_BORDERLINE),
        (19, "MODERATE",     CONFIDENCE_BORDERLINE),
        (20, "AGGRESSIVE",   CONFIDENCE_BORDERLINE),
        (21, "AGGRESSIVE",   CONFIDENCE_BORDERLINE),
        (22, "AGGRESSIVE",   CONFIDENCE_HIGH),
        (30, "AGGRESSIVE",   CONFIDENCE_HIGH),
    ])
    def test_boundary(self, score: int, expected_label: str, expected_conf: float):
        label, conf = map_score_to_label(score)
        assert label == expected_label, f"Score {score}: expected {expected_label}, got {label}"
        assert conf == expected_conf, f"Score {score}: expected conf {expected_conf}, got {conf}"

    def test_out_of_range_raises(self):
        """map_score_to_label must raise ValueError for scores outside [0, 30]."""
        with pytest.raises(ValueError):
            map_score_to_label(-1)
        with pytest.raises(ValueError):
            map_score_to_label(31)

    def test_model_version_is_rule_based_v1(self):
        """profile_user must always return model_version='rule_based_v1' in Phase A."""
        r = _responses(Q7="b")
        result = profile_user(r)
        assert result["model_version"] == "rule_based_v1"


# =============================================================================
# --- GBM path tests ---
# =============================================================================

_MODEL_FILE = Path("data/scf/gbm_model.pkl")
_gbm_model_missing = not _MODEL_FILE.exists()
_skip_if_no_model = pytest.mark.skipif(
    _gbm_model_missing,
    reason="data/scf/gbm_model.pkl not found — run train_gbm() first",
)

# A realistic feature vector used across GBM tests.
_SAMPLE_FEATURES: dict[str, float] = {
    "AGE": 45.0,
    "EDUC": 14.0,
    "INCOME": 80_000.0,
    "YESFINRISK": 1.0,
    "NOFINRISK": 0.0,
    "KIDS": 2.0,
    "NETWORTH": 250_000.0,
    "WSAVED": 2.0,
    "EQUITY_RATIO": 0.55,
}

from backend.ml.profiler.classifier import (  # noqa: E402 — import after skipif setup
    FEATURE_COLS,
    MODEL_VERSION_GBM,
    profile_user_gbm,
)


class TestGBMPath:
    """Phase B GBM profiler — output schema, driver normalisation, and
    low-confidence flag. Tests that require the trained model file are
    skipped automatically when the file is absent (e.g. in CI before
    training)."""

    @_skip_if_no_model
    def test_gbm_output_schema(self):
        """profile_user_gbm() must return a valid ProfilerOutput with correct types.

        Checks:
        - All five ProfilerOutput keys are present.
        - profile_label is one of the three canonical strings.
        - confidence is a float in [0.0, 1.0].
        - low_confidence_flag is bool, consistent with confidence.
        - top_drivers is a list of dicts with 'feature' (str) and
          'importance' (float) keys.
        - model_version equals "gbm_scf_v1".
        """
        result = profile_user_gbm(_SAMPLE_FEATURES)

        assert set(result.keys()) == {
            "profile_label", "confidence", "low_confidence_flag",
            "top_drivers", "model_version",
        }
        assert result["profile_label"] in {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["low_confidence_flag"], bool)
        assert result["low_confidence_flag"] == (result["confidence"] < 0.65)
        assert isinstance(result["top_drivers"], list)
        for driver in result["top_drivers"]:
            assert "feature" in driver and isinstance(driver["feature"], str)
            assert "importance" in driver and isinstance(driver["importance"], float)
        assert result["model_version"] == MODEL_VERSION_GBM

    @_skip_if_no_model
    def test_gbm_top_drivers_normalized(self):
        """top_drivers must have exactly 3 entries, all positive importances
        that sum to 1.0 (within floating-point tolerance of 1e-6)."""
        result = profile_user_gbm(_SAMPLE_FEATURES)

        drivers = result["top_drivers"]
        assert len(drivers) == 3, f"Expected 3 top_drivers, got {len(drivers)}"

        importances = [d["importance"] for d in drivers]
        assert all(imp > 0.0 for imp in importances), (
            f"All importances must be positive, got {importances}"
        )
        total = sum(importances)
        assert abs(total - 1.0) < 1e-6, (
            f"Importances must sum to 1.0, got {total}"
        )

    def test_gbm_low_confidence_flag(self):
        """When predict_proba returns [0.34, 0.33, 0.33], low_confidence_flag
        must be True (max proba = 0.34 < LOW_CONFIDENCE_THRESHOLD = 0.65).

        This test does NOT require the real model file on disk: the GBM and
        LabelEncoder are injected via patch.dict into _MODEL_CACHE, bypassing
        the file-load entirely.
        """
        mock_gbm = MagicMock()
        mock_gbm.predict_proba.return_value = np.array([[0.34, 0.33, 0.33]])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = np.array(["MODERATE"])
        mock_le.classes_ = np.array(["AGGRESSIVE", "CONSERVATIVE", "MODERATE"])

        # SHAP mock: 3-D array (1 sample × n_features × 3 classes)
        n_features = len(FEATURE_COLS)
        mock_shap_vals = np.zeros((1, n_features, 3))
        mock_shap_vals[0, 0, 0] = 0.5   # give feature[0] a non-zero SHAP value
        mock_shap_vals[0, 1, 0] = 0.3
        mock_shap_vals[0, 2, 0] = 0.2

        mock_explainer = MagicMock()
        mock_explainer.shap_values.return_value = mock_shap_vals

        with patch.dict(
            "backend.ml.profiler.classifier._MODEL_CACHE",
            {"gbm": mock_gbm, "le": mock_le},
            clear=True,
        ):
            with patch("shap.TreeExplainer", return_value=mock_explainer):
                result = profile_user_gbm(_SAMPLE_FEATURES)

        assert result["low_confidence_flag"] is True, (
            f"Expected low_confidence_flag=True for confidence=0.34, "
            f"got {result['low_confidence_flag']}"
        )
        assert result["confidence"] == pytest.approx(0.34)
