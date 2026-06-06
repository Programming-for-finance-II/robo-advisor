from __future__ import annotations

import numpy as np
import pytest
from scipy.cluster.hierarchy import linkage
import plotly.graph_objects as go

from backend.optimizer.charts import (
    plot_risk_contributions,
    plot_dendrogram,
    plot_drawdown,
    plot_efficient_frontier,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def rc_four_assets() -> dict[str, float]:
    return {"SPY": 0.30, "AGG": 0.20, "GLD": 0.15, "VNQ": 0.35}


@pytest.fixture
def linkage_four() -> np.ndarray:
    """Valid Ward linkage for 4 synthetic observations."""
    np.random.seed(0)
    data = np.random.rand(4, 5)
    return linkage(data, method="ward")


@pytest.fixture
def tickers_four() -> list[str]:
    return ["SPY", "AGG", "GLD", "VNQ"]


@pytest.fixture
def backtest_full() -> dict:
    return {
        "gfc_2008": {
            "dates": ["2008-01-01", "2008-06-01", "2008-12-01"],
            "hrp":          [1.00, 0.85, 0.90],
            "mv":           [1.00, 0.80, 0.88],
            "equal_weight": [1.00, 0.82, 0.89],
        },
        "covid_2020": {
            "dates": ["2020-01-01", "2020-03-01", "2020-12-01"],
            "hrp":          [1.00, 0.75, 1.05],
            "mv":           [1.00, 0.70, 1.02],
            "equal_weight": [1.00, 0.72, 1.00],
        },
        "rate_hike_2022": {
            "dates": ["2022-01-01", "2022-06-01", "2022-12-01"],
            "hrp":          [1.00, 0.92, 0.95],
            "mv":           [1.00, 0.88, 0.91],
            "equal_weight": [1.00, 0.90, 0.93],
        },
    }


# ── plot_risk_contributions ───────────────────────────────────────────────

class TestPlotRiskContributions:
    def test_returns_figure(self, rc_four_assets):
        assert isinstance(plot_risk_contributions(rc_four_assets), go.Figure)

    def test_single_bar_trace(self, rc_four_assets):
        fig = plot_risk_contributions(rc_four_assets)
        assert len(fig.data) == 1

    def test_bar_count_equals_assets(self, rc_four_assets):
        fig = plot_risk_contributions(rc_four_assets)
        assert len(fig.data[0].y) == len(rc_four_assets)

    def test_values_are_percentages(self, rc_four_assets):
        fig = plot_risk_contributions(rc_four_assets)
        bar = fig.data[0]
        assert all(0.0 <= v <= 100.0 for v in bar.x)

    def test_values_sum_to_100(self, rc_four_assets):
        fig = plot_risk_contributions(rc_four_assets)
        total = sum(fig.data[0].x)
        assert total == pytest.approx(100.0, abs=0.1)

    def test_orientation_horizontal(self, rc_four_assets):
        fig = plot_risk_contributions(rc_four_assets)
        assert fig.data[0].orientation == "h"

    def test_title_no_profile(self, rc_four_assets):
        # Title is now rendered outside the chart (as a section header), so
        # the figure's own title text is empty — avoids duplication.
        fig = plot_risk_contributions(rc_four_assets)
        assert fig.layout.title.text in (None, "", "Risk Contributions")

    def test_title_with_profile_label(self, rc_four_assets):
        # Same: title removed from figure; profile_label still accepted for
        # backward compatibility but no longer embedded in the chart title.
        fig = plot_risk_contributions(rc_four_assets, profile_label="Balanced")
        assert isinstance(fig, go.Figure)

    def test_single_asset(self):
        fig = plot_risk_contributions({"SPY": 1.0})
        assert isinstance(fig, go.Figure)
        assert len(fig.data[0].y) == 1

    def test_labels_use_plain_names_with_ticker_fallback(self, rc_four_assets):
        # Labels are sorted ascending by risk contribution (smallest first so
        # the largest bar is at the top in a horizontal chart).  Known tickers
        # map to human-readable names; unknown ones fall back to the raw ticker.
        from backend.optimizer.charts import _TICKER_SHORT_NAME
        fig = plot_risk_contributions(rc_four_assets)
        # All labels must be plain names (or raw ticker as fallback)
        for label in fig.data[0].y:
            assert label in _TICKER_SHORT_NAME.values() or label in rc_four_assets
        # Raw tickers must still be available in customdata for hover tooltips
        assert set(fig.data[0].customdata) == set(rc_four_assets.keys())


# ── plot_dendrogram ───────────────────────────────────────────────────────

class TestPlotDendrogram:
    def test_returns_figure(self, linkage_four, tickers_four):
        assert isinstance(plot_dendrogram(linkage_four, tickers_four), go.Figure)

    def test_has_at_least_one_trace(self, linkage_four, tickers_four):
        fig = plot_dendrogram(linkage_four, tickers_four)
        assert len(fig.data) > 0

    def test_all_traces_are_scatter_lines(self, linkage_four, tickers_four):
        fig = plot_dendrogram(linkage_four, tickers_four)
        for trace in fig.data:
            assert isinstance(trace, go.Scatter)
            assert trace.mode == "lines"

    def test_title_contains_hrp(self, linkage_four, tickers_four):
        fig = plot_dendrogram(linkage_four, tickers_four)
        assert "HRP" in fig.layout.title.text

    def test_tick_labels_match_tickers(self, linkage_four, tickers_four):
        fig = plot_dendrogram(linkage_four, tickers_four)
        tick_texts = set(fig.layout.xaxis.ticktext)
        assert tick_texts == set(tickers_four)

    def test_n_branches_equals_n_assets_minus_1(self, linkage_four, tickers_four):
        # A dendrogram of n leaves has exactly n-1 internal nodes,
        # each drawn as an L-shape (one Scatter trace per node).
        fig = plot_dendrogram(linkage_four, tickers_four)
        assert len(fig.data) == len(tickers_four) - 1

    def test_y_axis_label(self, linkage_four, tickers_four):
        fig = plot_dendrogram(linkage_four, tickers_four)
        assert fig.layout.yaxis.title.text == "Distance"


# ── plot_drawdown ─────────────────────────────────────────────────────────

class TestPlotDrawdown:
    def test_returns_figure(self, backtest_full):
        assert isinstance(plot_drawdown(backtest_full, "gfc_2008"), go.Figure)

    def test_three_series_plotted(self, backtest_full):
        fig = plot_drawdown(backtest_full, "gfc_2008")
        assert len(fig.data) == 3

    def test_drawdown_values_non_positive(self, backtest_full):
        fig = plot_drawdown(backtest_full, "gfc_2008")
        for trace in fig.data:
            assert all(v <= 1e-9 for v in trace.y), \
                f"Drawdown must be ≤ 0, got positive values in trace '{trace.name}'"

    def test_all_three_scenarios(self, backtest_full):
        for key in ("gfc_2008", "covid_2020", "rate_hike_2022"):
            fig = plot_drawdown(backtest_full, key)
            assert len(fig.data) == 3

    def test_title_contains_scenario_label(self, backtest_full):
        fig = plot_drawdown(backtest_full, "covid_2020")
        assert "COVID" in fig.layout.title.text

    def test_default_scenario_is_gfc(self, backtest_full):
        fig = plot_drawdown(backtest_full)
        assert "GFC" in fig.layout.title.text

    def test_missing_series_skipped(self):
        results = {
            "gfc_2008": {
                "dates": ["2008-01-01", "2008-12-01"],
                "hrp": [1.0, 0.85],
                # mv and equal_weight absent
            }
        }
        fig = plot_drawdown(results, "gfc_2008")
        assert len(fig.data) == 1

    def test_unknown_scenario_returns_empty_figure(self):
        fig = plot_drawdown({}, "nonexistent")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_flat_cumret_gives_zero_drawdown(self):
        results = {
            "gfc_2008": {
                "dates": ["2008-01-01", "2008-06-01"],
                "hrp": [1.0, 1.0],
            }
        }
        fig = plot_drawdown(results, "gfc_2008")
        hrp_trace = fig.data[0]
        assert all(v == pytest.approx(0.0) for v in hrp_trace.y)


# ── plot_efficient_frontier ───────────────────────────────────────────────

class TestPlotEfficientFrontier:

    _base_kwargs = dict(
        frontier_vols=[0.08, 0.10, 0.12, 0.15],
        frontier_rets=[0.04, 0.06, 0.08, 0.10],
        hrp_vol=0.11,
        hrp_ret=0.07,
        mv_vol=0.12,
        mv_ret=0.08,
    )

    def test_returns_figure(self):
        assert isinstance(plot_efficient_frontier(**self._base_kwargs), go.Figure)

    def test_three_traces_present(self):
        fig = plot_efficient_frontier(**self._base_kwargs)
        names = [t.name for t in fig.data]
        assert "Efficient Frontier" in names
        assert "HRP" in names
        assert "Markowitz" in names

    def test_frontier_values_are_percentages(self):
        fig = plot_efficient_frontier(**self._base_kwargs)
        frontier = next(t for t in fig.data if t.name == "Efficient Frontier")
        assert frontier.x[0] == pytest.approx(8.0)   # 0.08 → 8%
        assert frontier.y[0] == pytest.approx(4.0)   # 0.04 → 4%

    def test_mv_ret_none_omits_mv_trace(self):
        kwargs = {**self._base_kwargs, "mv_ret": None}
        fig = plot_efficient_frontier(**kwargs)
        names = [t.name for t in fig.data]
        assert "Markowitz" not in names

    def test_hrp_ret_none_hrp_trace_still_present(self):
        kwargs = {**self._base_kwargs, "hrp_ret": None}
        fig = plot_efficient_frontier(**kwargs)
        names = [t.name for t in fig.data]
        assert "HRP" in names

    def test_hrp_marker_is_circle(self):
        fig = plot_efficient_frontier(**self._base_kwargs)
        hrp = next(t for t in fig.data if t.name == "HRP")
        assert hrp.marker.symbol == "circle"

    def test_mv_marker_is_diamond(self):
        fig = plot_efficient_frontier(**self._base_kwargs)
        mv = next(t for t in fig.data if t.name == "Markowitz")
        assert mv.marker.symbol == "diamond"

    def test_title_contains_hrp_and_markowitz(self):
        fig = plot_efficient_frontier(**self._base_kwargs)
        title = fig.layout.title.text
        assert "HRP" in title
        assert "Markowitz" in title
