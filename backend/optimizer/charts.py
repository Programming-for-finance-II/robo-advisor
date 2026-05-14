from __future__ import annotations

import plotly.graph_objects as go


# ---------------------------------------------------------------------------
# 1. Risk Contribution Bar Chart
# ---------------------------------------------------------------------------

def plot_risk_contributions(
    risk_contributions: dict[str, float],
    profile_label: str = "",
) -> go.Figure:
    """Horizontal bar chart of per-asset risk contributions.

    Args:
        risk_contributions: {ticker: risk_contribution} from OptimizationResult.
                            Values should sum to ~1.0.
        profile_label:      Optional profile label for the chart title.

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    tickers = list(risk_contributions.keys())
    values = [round(v * 100, 2) for v in risk_contributions.values()]

    fig = go.Figure(go.Bar(
        x=values,
        y=tickers,
        orientation="h",
        marker_color="steelblue",
        text=[f"{v:.1f}%" for v in values],
        textposition="outside",
    ))

    title = "Risk Contributions"
    if profile_label:
        title += f" — {profile_label}"

    fig.update_layout(
        title=title,
        xaxis_title="Risk Contribution (%)",
        yaxis_title="Asset",
        xaxis=dict(range=[0, max(values) * 1.2]),
        height=400,
        margin=dict(l=20, r=40, t=50, b=40),
    )

    return fig

# ---------------------------------------------------------------------------
# 2. HRP Dendrogram
# ---------------------------------------------------------------------------

def plot_dendrogram(
    linkage_matrix: list,
    tickers: list[str],
) -> go.Figure:
    """Dendrogram of HRP hierarchical clustering.

    Args:
        linkage_matrix: Output of scipy.cluster.hierarchy.linkage().
        tickers:        Asset ticker labels in the same order as the
                        distance matrix rows.

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    import numpy as np
    from scipy.cluster.hierarchy import dendrogram

    dendro = dendrogram(linkage_matrix, labels=tickers, no_plot=True)

    fig = go.Figure()

    for x, y in zip(dendro["icoord"], dendro["dcoord"]):
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line=dict(color="steelblue", width=1.5),
            showlegend=False,
        ))

    fig.update_layout(
        title="HRP Cluster Structure",
        xaxis=dict(
            tickvals=[dendro["leaves"][i] * 10 + 5 for i in range(len(tickers))],
            ticktext=dendro["ivl"],
            tickangle=-45,
        ),
        yaxis_title="Distance",
        height=400,
        margin=dict(l=20, r=20, t=50, b=80),
    )

    return fig

# ---------------------------------------------------------------------------
# 3. Drawdown Chart
# ---------------------------------------------------------------------------

def plot_drawdown(
    backtest_results: dict,
    scenario_key: str = "gfc_2008",
) -> go.Figure:
    """Drawdown chart for a backtest scenario.

    Args:
        backtest_results: Dict loaded from backtest JSON output.
                          Expected keys: 'dates', 'hrp', 'mv', 'equal_weight'
                          each containing a list of cumulative returns.
        scenario_key:     Which scenario to plot (gfc_2008, covid_2020,
                          rate_hike_2022).

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    import numpy as np

    scenario = backtest_results.get(scenario_key, {})
    dates = scenario.get("dates", [])

    fig = go.Figure()

    series = {
        "HRP":          ("steelblue",  scenario.get("hrp", [])),
        "Markowitz":    ("tomato",     scenario.get("mv", [])),
        "1/N":          ("gray",       scenario.get("equal_weight", [])),
    }

    for name, (color, cumret) in series.items():
        if not cumret:
            continue
        cumret_arr = np.array(cumret)
        rolling_max = np.maximum.accumulate(cumret_arr)
        drawdown = (cumret_arr - rolling_max) / rolling_max * 100

        fig.add_trace(go.Scatter(
            x=dates,
            y=drawdown.tolist(),
            mode="lines",
            name=name,
            line=dict(color=color, width=1.5),
        ))

    labels = {
        "gfc_2008":      "GFC 2008",
        "covid_2020":    "COVID 2020",
        "rate_hike_2022": "Rate Hike 2022",
    }

    fig.update_layout(
        title=f"Drawdown — {labels.get(scenario_key, scenario_key)}",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        height=400,
        margin=dict(l=20, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig
