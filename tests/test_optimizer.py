from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.optimizer.regime_detector import detect_regime

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TICKERS = ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]

CLUSTER_MAP: dict[str, str] = {
    "CSPX.L":   "risk_assets",
    "EFA":      "risk_assets",
    "AGGH.MI":  "safe_haven",
    "TLT":      "safe_haven",
    "GLD":      "real_assets",
    "VNQ":      "real_assets",
    "TIP":      "safe_haven",
    "XEON.MI":  "cash",
}

def _make_prices(n_days: int = 252) -> pd.DataFrame:
    """Synthetic prices — uniform volatility, sufficient rows for covariance."""
    rng = np.random.default_rng(42)
    daily_ret = rng.normal(0.0003, 0.01, size=(n_days, len(TICKERS)))
    prices = 100.0 * np.exp(np.cumsum(daily_ret, axis=0))
    return pd.DataFrame(prices, columns=TICKERS)
    
def _make_prices_with_varied_vol(n_days: int = 252) -> pd.DataFrame:
    """
    Prices with clearly different volatilities per asset class.
    Required for the tilt test: MinVar must prefer low-vol assets (bonds/cash)
    and ERC must spread risk more evenly — producing visibly different weights.
    """
    rng = np.random.default_rng(42)
    # equity ~1.5%, bonds ~0.4%, gold ~1%, cash ~0.1%
    vols = [0.015, 0.012, 0.004, 0.004, 0.010, 0.014, 0.004, 0.001]
    daily_ret = rng.normal(0.0003, 1.0, size=(n_days, len(TICKERS))) * vols
    prices = 100.0 * np.exp(np.cumsum(daily_ret, axis=0))
    return pd.DataFrame(prices, columns=TICKERS)

# ---------------------------------------------------------------------------
# Structural tests (W1)
# ---------------------------------------------------------------------------

def test_optimization_result_has_required_fields() -> None:
    """OptimizationResult must contain all fields defined in design v3.1."""
    from backend.optimizer.hrp import OptimizationResult

    required = {
        "algorithm", "weights", "expected_return", "expected_volatility",
        "sharpe_ratio", "risk_contributions", "optimizer_version", "solver_status",
    }
    assert required.issubset(OptimizationResult.__annotations__.keys())


def test_compute_covariance_raises_on_empty_dataframe() -> None:
    """compute_covariance must raise AssertionError on empty input."""
    from backend.optimizer.hrp import compute_covariance

    with pytest.raises(AssertionError):
        compute_covariance(pd.DataFrame())


def test_compute_covariance_returns_dataframe_on_valid_input() -> None:
    """compute_covariance must return a PSD DataFrame."""
    from backend.optimizer.hrp import compute_covariance

    cov = compute_covariance(_make_prices())
    assert isinstance(cov, pd.DataFrame)
    assert cov.shape == (8, 8)
    assert list(cov.columns) == TICKERS

# ---------------------------------------------------------------------------
# Functional tests (W2)
# ---------------------------------------------------------------------------

def test_optimize_weights_sum_to_one_and_box_constraints() -> None:
    """
    optimize() must return weights that sum to 1.0 and respect
    per-asset box constraints (0.03 <= w_i <= 0.40).
    """
    from backend.optimizer.hrp import ASSET_MAX, ASSET_MIN, optimize

    result = optimize(
        prices = _make_prices_with_varied_vol(),
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
    )

    weights = result["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "weights do not sum to 1"
    for ticker, w in weights.items():
        assert ASSET_MIN <= w <= ASSET_MAX + 1e-6, (
            f"{ticker} weight {w:.4f} violates [{ASSET_MIN}, {ASSET_MAX}]"
        )


def test_optimize_profile_tilt_produces_different_weights() -> None:
    """
    CONSERVATIVE and AGGRESSIVE profiles must produce different weight vectors.
    The tilt formula (0.7·HRP + 0.3·MinVar vs 0.7·HRP + 0.3·ERC) guarantees
    this on any non-trivial covariance structure.
    """
    from backend.optimizer.hrp import optimize

    prices = _make_prices_with_varied_vol()   
    w_cons = optimize(prices=prices, profile="CONSERVATIVE", cluster_map=CLUSTER_MAP)["weights"]
    w_agg  = optimize(prices=prices, profile="AGGRESSIVE",   cluster_map=CLUSTER_MAP)["weights"]

    diffs = [abs(w_cons[t] - w_agg[t]) for t in TICKERS]
    assert max(diffs) > 1e-4, "CONSERVATIVE and AGGRESSIVE weights are identical — tilt not applied"


def test_optimize_annual_volatility_in_realistic_range() -> None:
    """
    Annualised portfolio volatility must be in [1%, 40%].
    This catches the sqrt(252) double-annualisation bug: without the
    frequency=1 fix the value would exceed 100% on typical ETF data.
    """
    from backend.optimizer.hrp import optimize

    result = optimize(
        prices= _make_prices_with_varied_vol(),
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
    )

    vol = result["expected_volatility"]
    assert 0.01 <= vol <= 0.40, (
        f"annual volatility {vol:.4f} outside realistic range — "
        "possible annualisation bug"
    )

# ---------------------------------------------------------------------------
# Regime Detector Tests
# ---------------------------------------------------------------------------

class TestRegimeDetector:
    """Tests for regime_detector.detect_regime()."""

    def _make_cov(self, correlation: float, n: int = 4) -> pd.DataFrame:
        """Build synthetic covariance matrix with uniform off-diagonal correlation."""
        tickers = [f"A{i}" for i in range(n)]
        corr = np.full((n, n), correlation)
        np.fill_diagonal(corr, 1.0)
        # vol = 1% daily for all assets
        vols = np.full(n, 0.01)
        cov = corr * np.outer(vols, vols)
        return pd.DataFrame(cov, index=tickers, columns=tickers)

    def test_high_corr_triggers_high_stress(self):
        """avg_corr > 0.75 → HIGH_STRESS, corr_triggered=True."""
        cov = self._make_cov(correlation=0.85)
        result = detect_regime(cov)
        assert result.regime == "HIGH_STRESS"
        assert result.corr_triggered is True
        assert result.vix_triggered is False

    def test_low_corr_normal_regime(self):
        """avg_corr < 0.75, no VIX → NORMAL."""
        cov = self._make_cov(correlation=0.30)
        result = detect_regime(cov)
        assert result.regime == "NORMAL"
        assert result.corr_triggered is False
        assert result.vix_triggered is False

    def test_vix_alone_triggers_high_stress(self):
        """avg_corr < 0.75 but VIX > 30 → HIGH_STRESS, vix_triggered=True."""
        cov = self._make_cov(correlation=0.30)
        result = detect_regime(cov, vix_level=35.0)
        assert result.regime == "HIGH_STRESS"
        assert result.vix_triggered is True
        assert result.corr_triggered is False
