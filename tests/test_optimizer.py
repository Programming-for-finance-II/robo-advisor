from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_optimization_result_has_required_fields() -> None:
    """OptimizationResult must contain all fields defined in design v3.1."""
    from backend.optimizer.hrp import OptimizationResult

    required = {
        "algorithm",
        "weights",
        "expected_return",
        "expected_volatility",
        "sharpe_ratio",
        "risk_contributions",
        "optimizer_version",
        "solver_status",
    }
    assert required.issubset(OptimizationResult.__annotations__.keys())


def test_compute_covariance_raises_on_empty_dataframe() -> None:
    """compute_covariance must raise AssertionError on empty input."""
    from backend.optimizer.hrp import compute_covariance

    with pytest.raises(AssertionError):
        compute_covariance(pd.DataFrame())

def test_compute_covariance_returns_dataframe_on_valid_input() -> None:
    """compute_covariance must return a PSD DataFrame after W2 implementation."""
    from backend.optimizer.hrp import compute_covariance
    prices = pd.DataFrame(
        np.random.rand(100, 8) + 1,
        columns=["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"],
    )
    cov = compute_covariance(prices)
    assert isinstance(cov, pd.DataFrame)
    assert cov.shape == (8, 8)
    assert list(cov.columns) == ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]

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
    """Synthetic random-walk prices — enough rows to pass the 60-obs assert."""
    rng = np.random.default_rng(42)
    daily_returns = rng.normal(0.0003, 0.01, size=(n_days, len(TICKERS)))
    prices = 100.0 * np.exp(np.cumsum(daily_returns, axis=0))
    return pd.DataFrame(prices, columns=TICKERS)

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
        prices=_make_prices(),
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

    prices = _make_prices()
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
        prices=_make_prices(),
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
    )

    vol = result["expected_volatility"]
    assert 0.01 <= vol <= 0.40, (
        f"annual volatility {vol:.4f} outside realistic range — "
        "possible annualisation bug"
    )
