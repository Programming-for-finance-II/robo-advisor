from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.optimizer.risk_metrics import (
    compute_risk_contributions,
    compute_annual_volatility,
    compute_max_drawdown,
    compute_var_cvar,
    compute_portfolio_returns,
    compute_all,
    TRADING_DAYS_PER_YEAR,
    CONFIDENCE_LEVEL,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def two_asset_cov() -> pd.DataFrame:
    """Minimal 2-asset daily covariance matrix."""
    data = np.array([[0.0001, 0.00005],
                     [0.00005, 0.0002]])
    return pd.DataFrame(data, index=["SPY", "AGG"], columns=["SPY", "AGG"])


@pytest.fixture
def two_asset_weights() -> dict[str, float]:
    return {"SPY": 0.6, "AGG": 0.4}


@pytest.fixture
def four_asset_cov() -> pd.DataFrame:
    tickers = ["SPY", "AGG", "GLD", "VNQ"]
    np.random.seed(42)
    A = np.random.rand(4, 4) * 0.0001
    cov = A @ A.T + np.eye(4) * 0.0001
    return pd.DataFrame(cov, index=tickers, columns=tickers)


@pytest.fixture
def four_asset_weights() -> dict[str, float]:
    return {"SPY": 0.25, "AGG": 0.25, "GLD": 0.25, "VNQ": 0.25}


@pytest.fixture
def declining_returns() -> pd.Series:
    """Return series with a clear drawdown then recovery."""
    np.random.seed(0)
    r = pd.Series([-0.01, -0.02, -0.015, 0.01, 0.02, -0.005, 0.01] * 10)
    return r


@pytest.fixture
def long_returns() -> pd.Series:
    """≥30 observations for VaR/CVaR."""
    np.random.seed(1)
    return pd.Series(np.random.normal(0.0005, 0.01, 250))


@pytest.fixture
def price_df() -> pd.DataFrame:
    """100 days of synthetic prices for 2 tickers."""
    np.random.seed(2)
    dates = pd.date_range("2022-01-01", periods=101, freq="B")
    prices = pd.DataFrame({
        "SPY": 400 * np.exp(np.cumsum(np.random.normal(0.0003, 0.01, 101))),
        "AGG": 100 * np.exp(np.cumsum(np.random.normal(0.0001, 0.005, 101))),
    }, index=dates)
    return prices


# ── compute_risk_contributions ────────────────────────────────────────────

class TestComputeRiskContributions:
    def test_returns_dict_with_correct_keys(self, two_asset_weights, two_asset_cov):
        rc = compute_risk_contributions(two_asset_weights, two_asset_cov)
        assert set(rc.keys()) == {"SPY", "AGG"}

    def test_sum_to_one(self, two_asset_weights, two_asset_cov):
        rc = compute_risk_contributions(two_asset_weights, two_asset_cov)
        assert sum(rc.values()) == pytest.approx(1.0, abs=1e-4)

    def test_all_values_positive(self, two_asset_weights, two_asset_cov):
        rc = compute_risk_contributions(two_asset_weights, two_asset_cov)
        assert all(v > 0 for v in rc.values())

    def test_four_assets(self, four_asset_weights, four_asset_cov):
        rc = compute_risk_contributions(four_asset_weights, four_asset_cov)
        assert sum(rc.values()) == pytest.approx(1.0, abs=1e-4)
        assert len(rc) == 4

    def test_assert_fewer_than_two_assets(self, two_asset_cov):
        with pytest.raises(AssertionError):
            compute_risk_contributions({"SPY": 1.0}, two_asset_cov)

    def test_assert_weights_not_summing_to_one(self, two_asset_cov):
        with pytest.raises(AssertionError):
            compute_risk_contributions({"SPY": 0.5, "AGG": 0.3}, two_asset_cov)


# ── compute_annual_volatility ─────────────────────────────────────────────

class TestComputeAnnualVolatility:
    def test_returns_positive_float(self, two_asset_weights, two_asset_cov):
        vol = compute_annual_volatility(two_asset_weights, two_asset_cov)
        assert isinstance(vol, float)
        assert vol > 0

    def test_annualisation_factor(self, two_asset_weights, two_asset_cov):
        """Manually verify annualisation: sqrt(daily_var * 252)."""
        tickers = list(two_asset_cov.columns)
        w = np.array([two_asset_weights[t] for t in tickers])
        daily_var = float(w @ two_asset_cov.values @ w)
        expected = float(np.sqrt(daily_var * TRADING_DAYS_PER_YEAR))
        vol = compute_annual_volatility(two_asset_weights, two_asset_cov)
        assert vol == pytest.approx(expected, rel=1e-5)

    def test_equal_weights_four_assets(self, four_asset_weights, four_asset_cov):
        vol = compute_annual_volatility(four_asset_weights, four_asset_cov)
        assert 0 < vol < 1   # reasonable annualised range

    def test_higher_cov_gives_higher_vol(self, two_asset_weights):
        low_cov = pd.DataFrame(
            [[0.00001, 0.000005], [0.000005, 0.00002]],
            index=["SPY", "AGG"], columns=["SPY", "AGG"],
        )
        high_cov = pd.DataFrame(
            [[0.001, 0.0005], [0.0005, 0.002]],
            index=["SPY", "AGG"], columns=["SPY", "AGG"],
        )
        assert (compute_annual_volatility(two_asset_weights, high_cov) >
                compute_annual_volatility(two_asset_weights, low_cov))


# ── compute_max_drawdown ──────────────────────────────────────────────────

class TestComputeMaxDrawdown:
    def test_returns_negative_float(self, declining_returns):
        dd = compute_max_drawdown(declining_returns)
        assert dd < 0

    def test_flat_returns_zero_drawdown(self):
        flat = pd.Series([0.0] * 50)
        assert compute_max_drawdown(flat) == pytest.approx(0.0, abs=1e-6)

    def test_monotonic_decline(self):
        """Continuously falling portfolio → large negative drawdown."""
        falling = pd.Series([-0.01] * 100)
        dd = compute_max_drawdown(falling)
        assert dd < -0.5

    def test_single_recovery(self):
        """Drop then full recovery → drawdown < 0 at trough."""
        r = pd.Series([-0.1, -0.1, 0.2, 0.2])
        dd = compute_max_drawdown(r)
        assert dd < 0

    def test_assert_empty_series(self):
        with pytest.raises(AssertionError):
            compute_max_drawdown(pd.Series([], dtype=float))

    def test_result_in_valid_range(self, declining_returns):
        dd = compute_max_drawdown(declining_returns)
        assert -1.0 <= dd <= 0.0


# ── compute_var_cvar ──────────────────────────────────────────────────────

class TestComputeVarCvar:
    def test_returns_tuple_of_two_floats(self, long_returns):
        result = compute_var_cvar(long_returns)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_both_negative(self, long_returns):
        var, cvar = compute_var_cvar(long_returns)
        assert var < 0
        assert cvar < 0

    def test_cvar_leq_var(self, long_returns):
        """CVaR (Expected Shortfall) must be ≤ VaR."""
        var, cvar = compute_var_cvar(long_returns)
        assert cvar <= var

    def test_custom_confidence(self, long_returns):
        var_95, _ = compute_var_cvar(long_returns, confidence=0.95)
        var_99, _ = compute_var_cvar(long_returns, confidence=0.99)
        assert var_99 <= var_95   # higher confidence → more extreme VaR

    def test_assert_too_few_observations(self):
        with pytest.raises(AssertionError, match="too few"):
            compute_var_cvar(pd.Series([0.01] * 10))

    def test_assert_invalid_confidence_high(self, long_returns):
        with pytest.raises(AssertionError):
            compute_var_cvar(long_returns, confidence=1.0)

    def test_assert_invalid_confidence_low(self, long_returns):
        with pytest.raises(AssertionError):
            compute_var_cvar(long_returns, confidence=0.0)

    def test_default_confidence_is_module_constant(self, long_returns):
        var_default, _ = compute_var_cvar(long_returns)
        var_explicit, _ = compute_var_cvar(long_returns, confidence=CONFIDENCE_LEVEL)
        assert var_default == pytest.approx(var_explicit)


# ── compute_portfolio_returns ─────────────────────────────────────────────

class TestComputePortfolioReturns:
    def test_returns_series(self, price_df, two_asset_weights):
        pr = compute_portfolio_returns(price_df, two_asset_weights)
        assert isinstance(pr, pd.Series)

    def test_length_is_prices_minus_one(self, price_df, two_asset_weights):
        pr = compute_portfolio_returns(price_df, two_asset_weights)
        assert len(pr) == len(price_df) - 1

    def test_no_nan_values(self, price_df, two_asset_weights):
        pr = compute_portfolio_returns(price_df, two_asset_weights)
        assert not pr.isna().any()

    def test_single_asset_full_weight(self, price_df):
        """With 100% in SPY, portfolio returns = SPY log returns."""
        weights = {"SPY": 1.0}
        pr = compute_portfolio_returns(price_df[["SPY"]], weights)
        spy_returns = np.log(price_df["SPY"] / price_df["SPY"].shift(1)).dropna()
        np.testing.assert_allclose(pr.values, spy_returns.values, rtol=1e-5)

    def test_weights_affect_output(self, price_df):
        w1 = {"SPY": 0.9, "AGG": 0.1}
        w2 = {"SPY": 0.1, "AGG": 0.9}
        pr1 = compute_portfolio_returns(price_df, w1)
        pr2 = compute_portfolio_returns(price_df, w2)
        assert not np.allclose(pr1.values, pr2.values)


# ── compute_all ───────────────────────────────────────────────────────────

class TestComputeAll:
    def test_returns_dict_with_expected_keys(
        self, two_asset_weights, two_asset_cov, price_df
    ):
        result = compute_all(two_asset_weights, two_asset_cov, price_df)
        expected_keys = {
            "expected_annual_return",
            "annual_volatility",
            "sharpe_ratio",
            "max_drawdown_historical",
            "var_95_daily",
            "cvar_95_daily",
            "risk_contributions",
        }
        assert set(result.keys()) == expected_keys

    def test_expected_return_and_sharpe_are_none(
        self, two_asset_weights, two_asset_cov, price_df
    ):
        result = compute_all(two_asset_weights, two_asset_cov, price_df)
        assert result["expected_annual_return"] is None
        assert result["sharpe_ratio"] is None

    def test_annual_volatility_positive(
        self, two_asset_weights, two_asset_cov, price_df
    ):
        result = compute_all(two_asset_weights, two_asset_cov, price_df)
        assert result["annual_volatility"] > 0

    def test_risk_contributions_sum_to_one(
        self, two_asset_weights, two_asset_cov, price_df
    ):
        result = compute_all(two_asset_weights, two_asset_cov, price_df)
        assert sum(result["risk_contributions"].values()) == pytest.approx(1.0, abs=1e-4)

    def test_drawdown_and_var_negative(
        self, two_asset_weights, two_asset_cov, price_df
    ):
        result = compute_all(two_asset_weights, two_asset_cov, price_df)
        assert result["max_drawdown_historical"] < 0
        assert result["var_95_daily"] < 0
        assert result["cvar_95_daily"] < 0
