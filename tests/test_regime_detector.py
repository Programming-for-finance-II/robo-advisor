"""
tests/test_regime_detector.py
==============================
Unit tests for backend/ml/regime_detector.py (Phase B stub).

These tests verify the output contract of detect_regime() — schema,
types, and the Phase B default values — without requiring any external
data or model files.
"""

from __future__ import annotations

from backend.ml.regime_detector import detect_regime


class TestDetectRegime:
    """Tests for detect_regime() — Phase B stub always returns normal."""

    def test_returns_normal_regime_by_default(self):
        """detect_regime() with no args must return stress_regime=False."""
        result = detect_regime()
        assert result["stress_regime"] is False

    def test_regime_label_is_normal(self):
        """regime_label must equal 'normal' in Phase B stub."""
        result = detect_regime()
        assert result["regime_label"] == "normal"

    def test_vix_proxy_is_none(self):
        """vix_proxy must be None — VIX detection not yet implemented."""
        result = detect_regime()
        assert result["vix_proxy"] is None

    def test_output_schema_keys(self):
        """Result must contain exactly the three RegimeOutput keys."""
        result = detect_regime()
        assert set(result.keys()) == {"stress_regime", "regime_label", "vix_proxy"}

    def test_output_types(self):
        """Each field must have the correct type."""
        result = detect_regime()
        assert isinstance(result["stress_regime"], bool)
        assert isinstance(result["regime_label"], str)
        # vix_proxy is None (float | None) — check it is None or float
        assert result["vix_proxy"] is None or isinstance(result["vix_proxy"], float)

    def test_market_data_arg_ignored(self):
        """Passing market_data must not change the output (stub ignores it)."""
        result_none = detect_regime(market_data=None)
        result_dict = detect_regime(market_data={"vix": 30.0, "spy_ret": -0.02})
        assert result_none == result_dict

    def test_regime_label_not_stress(self):
        """regime_label must not be 'stress' in Phase B stub."""
        result = detect_regime()
        assert result["regime_label"] != "stress"
