from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from backend.optimizer.backtest import (
    SCENARIOS,
    TC_BPS,
    ScenarioResult,
    StrategyResult,
    _compute_performance_metrics,
    _equal_weights,
    export_results_json,
    run_scenario,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TICKERS = ["SPY", "AGG", "GLD", "VNQ", "TLT", "TIP", "EFA", "BIL"]

CLUSTER_MAP: dict[str, str] = {
    "SPY": "risk_assets",
    "EFA": "risk_assets",
    "GLD": "real_assets",
    "VNQ": "real_assets",
    "AGG": "safe_haven",
    "TLT": "safe_haven",
    "TIP": "safe_haven",
    "BIL": "cash",
}


def _make_prices(
    n_days: int = 600,
    seed: int = 42,
    end_date: str = "2020-12-31",
) -> pd.DataFrame:
    """
    Generate synthetic price series with varied volatility per asset.

    Returns a DatetimeIndex DataFrame suitable for passing to backtest
    functions without network access.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=end_date, periods=n_days)

    vols = [0.15, 0.05, 0.12, 0.18, 0.08, 0.06, 0.14, 0.01]
    prices = pd.DataFrame(index=dates, columns=TICKERS, dtype=float)

    for ticker, vol in zip(TICKERS, vols):
        daily_vol = vol / np.sqrt(252)
        log_returns = rng.normal(0.0003, daily_vol, n_days)
        prices[ticker] = 100.0 * np.exp(np.cumsum(log_returns))

    return prices


# ---------------------------------------------------------------------------
# Tests — helper functions
# ---------------------------------------------------------------------------

def test_equal_weights_sum_to_one() -> None:
    """_equal_weights must return weights summing to 1.0."""
    w = _equal_weights(TICKERS)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(abs(v - 1.0 / len(TICKERS)) < 1e-9 for v in w.values())


def test_equal_weights_all_tickers_present() -> None:
    """_equal_weights must include every ticker passed in."""
    w = _equal_weights(TICKERS)
    assert set(w.keys()) == set(TICKERS)


def test_compute_performance_metrics_positive_trend() -> None:
    """
    On a steadily rising return series, CAGR > 0 and max_drawdown == 0.
    """
    daily_rets = pd.Series([0.001] * 252)
    cagr, vol, sharpe, max_dd, calmar = _compute_performance_metrics(daily_rets)

    assert cagr > 0.0, "CAGR should be positive on rising returns"
    assert vol >= 0.0
    assert max_dd == pytest.approx(0.0, abs=1e-6), (
        "Max drawdown should be 0 on a monotonically rising series"
    )


def test_compute_performance_metrics_negative_trend() -> None:
    """
    On a steadily declining return series, CAGR < 0 and max_drawdown < 0.
    """
    daily_rets = pd.Series([-0.002] * 252)
    cagr, vol, sharpe, max_dd, calmar = _compute_performance_metrics(daily_rets)

    assert cagr < 0.0
    assert max_dd < 0.0


def test_scenarios_dict_has_required_keys() -> None:
    """SCENARIOS must define all three required stress scenarios."""
    assert "gfc_2008" in SCENARIOS
    assert "covid_2020" in SCENARIOS
    assert "rate_hike_2022" in SCENARIOS

    for key, meta in SCENARIOS.items():
        assert "label" in meta, f"{key} missing 'label'"
        assert "test_start" in meta, f"{key} missing 'test_start'"
        assert "test_end" in meta, f"{key} missing 'test_end'"
        assert pd.Timestamp(meta["test_start"]) < pd.Timestamp(meta["test_end"]), (
            f"{key}: test_start must be before test_end"
        )


def test_tc_bps_is_ten() -> None:
    """Transaction cost must be exactly 10 bps — project spec requirement."""
    assert TC_BPS == 10, (
        f"TC_BPS must be 10 per design spec, got {TC_BPS}"
    )


# ---------------------------------------------------------------------------
# Tests — run_scenario (synthetic data, no network)
# ---------------------------------------------------------------------------

def test_run_scenario_returns_three_strategies() -> None:
    """
    run_scenario must return results for HRP, MV, and 1/N.
    """
    prices = _make_prices(n_days=600, end_date="2020-12-31")

    result = run_scenario(
        prices=prices,
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
        scenario_key="covid_2020",
    )

    assert isinstance(result, ScenarioResult)
    assert set(result.strategies.keys()) == {"HRP", "MV", "1/N"}


def test_run_scenario_equity_curve_starts_at_one() -> None:
    """
    Every strategy equity curve must start at portfolio_value = 1.0.
    """
    prices = _make_prices(n_days=600, end_date="2020-12-31")

    result = run_scenario(
        prices=prices,
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
        scenario_key="covid_2020",
    )

    for strategy, sr in result.strategies.items():
        assert len(sr.equity_curve) > 0, f"{strategy}: empty equity curve"
        first_value = sr.equity_curve[0].portfolio_value
        assert abs(first_value - 1.0) < 0.01, (
            f"{strategy}: equity curve starts at {first_value}, expected ~1.0"
        )


def test_run_scenario_transaction_costs_are_positive() -> None:
    """
    HRP and MV must incur positive transaction costs when rebalancing.
    1/N is excluded: equal weights produce zero turnover in this model.
    """
    prices = _make_prices(n_days=600, end_date="2020-12-31")

    result = run_scenario(
        prices=prices,
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
        scenario_key="covid_2020",
    )

    for strategy in ("HRP", "MV"):
        sr = result.strategies[strategy]
        assert sr.total_transaction_cost > 0.0, (
            f"{strategy}: expected positive transaction costs after rebalancing"
        )


def test_run_scenario_1n_weights_are_equal() -> None:
    """
    1/N strategy must hold equal weights at every rebalance event.
    """
    prices = _make_prices(n_days=600, end_date="2020-12-31")

    result = run_scenario(
        prices=prices,
        profile="MODERATE",
        cluster_map=CLUSTER_MAP,
        scenario_key="covid_2020",
    )

    expected_w = 1.0 / len(TICKERS)
    for event in result.strategies["1/N"].rebalance_log:
        for ticker, w in event.weights.items():
            assert abs(w - expected_w) < 1e-4, (
                f"1/N weight for {ticker} is {w:.6f}, expected {expected_w:.6f}"
            )


# ---------------------------------------------------------------------------
# Tests — export_results_json
# ---------------------------------------------------------------------------

def test_export_results_json_creates_files(tmp_path: Path) -> None:
    """
    export_results_json must write one file per scenario plus a summary.
    """

    from backend.optimizer.backtest import DailyReturn

    # Build minimal mock results without running a full backtest
    mock_sr = StrategyResult(
        strategy="1/N",
        cagr=0.05,
        annualised_volatility=0.10,
        sharpe_ratio=0.50,
        max_drawdown=-0.10,
        calmar_ratio=0.50,
        total_transaction_cost=0.001,
        n_rebalances=3,
        equity_curve=[DailyReturn(date="2020-01-02", portfolio_value=1.0)],
        rebalance_log=[],
    )

    mock_results = {
        "covid_2020": ScenarioResult(
            scenario_key="covid_2020",
            scenario_label="COVID-19 Crash (2020)",
            test_start="2020-01-02",
            test_end="2020-12-31",
            profile="MODERATE",
            tickers_used=TICKERS,
            strategies={"HRP": mock_sr, "MV": mock_sr, "1/N": mock_sr},
        )
    }

    export_results_json(mock_results, output_dir=tmp_path, profile="MODERATE")

    assert (tmp_path / "backtest_covid_2020_moderate.json").exists()
    assert (tmp_path / "backtest_summary_moderate.json").exists()


# ---------------------------------------------------------------------------
# Consistency: the chat/dashboard mock payload must quote the SAME stress
# drawdowns as the real backtest, so the Chat Advisor never contradicts the
# Backtesting page (regression guard for the mock-vs-real drift bug).
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402

from backend.schemas.mock_data import get_mock_payload  # noqa: E402

_BT_DIR = Path(__file__).resolve().parents[1] / "backtest_output"
# (mock profile, backtest profile, payload field, backtest scenario key)
_STRESS_PAIRS = [
    ("conservative", "conservative", "covid_march_2020", "covid_2020"),
    ("balanced", "moderate", "covid_march_2020", "covid_2020"),
    ("aggressive", "aggressive", "covid_march_2020", "covid_2020"),
    ("conservative", "conservative", "rates_hike_2022", "rate_hike_2022"),
    ("balanced", "moderate", "rates_hike_2022", "rate_hike_2022"),
    ("aggressive", "aggressive", "rates_hike_2022", "rate_hike_2022"),
]


@pytest.mark.parametrize("mock_p, bt_p, field, scenario", _STRESS_PAIRS)
def test_mock_stress_matches_real_backtest(mock_p, bt_p, field, scenario) -> None:
    summary = _json.loads((_BT_DIR / f"backtest_summary_{bt_p}.json").read_text())
    real_dd = summary[scenario]["strategies"]["HRP"]["max_drawdown"]
    payload = get_mock_payload(mock_p)
    quoted = getattr(payload.stress_scenarios, field).portfolio_drawdown
    assert abs(quoted - round(min(real_dd, 0.0), 4)) < 1e-6, (
        f"{mock_p}/{field}: chat payload quotes {quoted:+.4f} but the backtest "
        f"shows {real_dd:+.4f} — the Chat Advisor would contradict the "
        "Backtesting page"
    )
