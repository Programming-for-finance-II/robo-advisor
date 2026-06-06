from __future__ import annotations

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# 0. Portfolio Weights Donut Chart
# ---------------------------------------------------------------------------

_CLUSTER_COLORS: dict[str, str] = {
    "Equity":       "#7c5cfc",
    "Alternatives": "#f59e0b",
    "Bonds":        "#0dcfb0",
    "Cash":         "#3b82f6",
}

_TICKER_CLUSTER: dict[str, str] = {
    "CSPX.L":  "Equity",
    "EFA":     "Equity",
    "GLD":     "Alternatives",
    "VNQ":     "Alternatives",
    "AGGH.MI": "Bonds",
    "TLT":     "Bonds",
    "TIP":     "Bonds",
    "XEON.MI": "Cash",
}

# Short, plain-language names for chart labels. Full names live in the
# allocation table; here they must stay compact enough for pie slices and
# bar ticks. The raw ticker is kept in the hover tooltip for reference.
_TICKER_SHORT_NAME: dict[str, str] = {
    "CSPX.L":  "US Equity",
    "EFA":     "Intl Equity",
    "GLD":     "Gold",
    "VNQ":     "Real Estate",
    "AGGH.MI": "Euro Bonds",
    "TLT":     "US Treasuries",
    "TIP":     "Inflation Bonds",
    "XEON.MI": "Euro Cash",
}


def _short_name(ticker: str) -> str:
    """Plain-language chart label for a ticker, falling back to the ticker."""
    return _TICKER_SHORT_NAME.get(ticker, ticker)


_CLUSTER_ORDER: dict[str, int] = {
    "Equity": 0,
    "Alternatives": 1,
    "Bonds": 2,
    "Cash": 3,
}


def plot_weights_donut(weights: dict[str, float]) -> go.Figure:
    """Donut chart of portfolio weights coloured by asset cluster.

    Design notes (rework):
      * Slices are sorted by cluster then descending weight, so same-coloured
        assets sit together and the ring reads as four clean colour arcs.
      * Labels live *inside* the slices, horizontally oriented, so they never
        rotate or spill outside the chart. Slices too small to fit their label
        simply hide it (``uniformtext`` ``mode="hide"``) — the name is still in
        the hover tooltip and the colour legend — which removes the crooked /
        overflowing text and the layout flicker of the previous outside labels.
      * A center label summarises the holding count; a single-line colour
        legend sits below.

    Args:
        weights: {ticker: weight} from OptimizationResult. Values sum to ~1.0.

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    items = sorted(
        weights.items(),
        key=lambda kv: (
            _CLUSTER_ORDER.get(_TICKER_CLUSTER.get(kv[0], ""), 9),
            -kv[1],
        ),
    )
    tickers = [t for t, _ in items]
    values = [w for _, w in items]
    labels = [_short_name(t) for t in tickers]
    colors = [_CLUSTER_COLORS.get(_TICKER_CLUSTER.get(t, ""), "#64748b") for t in tickers]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        customdata=tickers,
        hole=0.62,
        sort=False,
        direction="clockwise",
        rotation=0,
        marker=dict(colors=colors, line=dict(color="#0d1220", width=2.5)),
        texttemplate="%{label}<br>%{percent}",
        textposition="inside",
        insidetextorientation="horizontal",
        textfont=dict(size=12, color="#ffffff", family="Space Grotesk, sans-serif"),
        hovertemplate="<b>%{label}</b> (%{customdata})<br>Weight: %{percent}<extra></extra>",
    ))

    cluster_legend = "&nbsp;&nbsp;&nbsp;".join(
        f'<span style="color:{c}">●</span> '
        f'<span style="color:#cbd5e1">{cl}</span>'
        for cl, c in _CLUSTER_COLORS.items()
    )

    fig.update_layout(
        showlegend=False,
        height=340,
        margin=dict(l=10, r=10, t=12, b=38),
        uniformtext=dict(minsize=10, mode="hide"),
        annotations=[
            dict(
                text=(
                    f'<span style="font-size:24px;color:#f1f5f9;font-weight:700;'
                    f'font-family:Space Grotesk">{len(tickers)}</span>'
                    f'<br><span style="font-size:10px;color:#64748b;'
                    f'letter-spacing:0.12em">HOLDINGS</span>'
                ),
                x=0.5, y=0.5,
                xanchor="center", yanchor="middle",
                showarrow=False,
                xref="paper", yref="paper",
            ),
            dict(
                text=cluster_legend,
                x=0.5, y=-0.04,
                xanchor="center", yanchor="top",
                showarrow=False,
                font=dict(size=11),
                xref="paper", yref="paper",
            ),
        ],
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
    )

    return fig


# ---------------------------------------------------------------------------
# 1. Risk Contribution Bar Chart
# ---------------------------------------------------------------------------

def plot_risk_contributions(
    risk_contributions: dict[str, float],
    profile_label: str = "",
) -> go.Figure:
    """Horizontal bar chart of per-asset risk contributions.

    Bars are coloured by cluster (matching the donut palette) and sorted
    descending so the biggest risk driver is always at the top. A vertical
    reference line marks the equal-risk level (100 / n assets), making it
    immediately obvious which positions dominate the risk budget.

    Args:
        risk_contributions: {ticker: risk_contribution} from OptimizationResult.
                            Values should sum to ~1.0.
        profile_label:      Optional profile label for the chart subtitle.

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    # Sort descending by risk contribution
    sorted_items = sorted(risk_contributions.items(), key=lambda kv: kv[1])
    tickers = [t for t, _ in sorted_items]
    values  = [round(v * 100, 2) for _, v in sorted_items]
    labels  = [_short_name(t) for t in tickers]
    colors  = [
        _CLUSTER_COLORS.get(_TICKER_CLUSTER.get(t, ""), "#64748b")
        for t in tickers
    ]

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    face_colors = [_hex_to_rgba(c, 0.75) for c in colors]

    equal_risk = round(100.0 / max(len(tickers), 1), 1)

    fig = go.Figure()

    # Reference line: equal-risk distribution
    fig.add_vline(
        x=equal_risk,
        line=dict(color="#475569", width=1.2, dash="dot"),
        annotation_text=f"Equal risk ({equal_risk:.1f}%)",
        annotation_position="top right",
        annotation_font=dict(size=10, color="#64748b"),
    )

    fig.add_trace(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(
            color=face_colors,
            line=dict(color=colors, width=1.5),
        ),
        text=[f"<b>{v:.1f}%</b>" for v in values],
        textposition="inside",
        insidetextanchor="end",
        textfont=dict(size=11, color="#ffffff"),
        customdata=tickers,
        hovertemplate=(
            "<b>%{y}</b> (%{customdata})<br>"
            "Risk contribution: <b>%{x:.1f}%</b><br>"
            f"Equal share would be: {equal_risk:.1f}%"
            "<extra></extra>"
        ),
    ))

    x_max = max(values) * 1.15 if values else 30.0

    fig.update_layout(
        xaxis=dict(
            title="Risk contribution (%)",
            range=[0, x_max],
            showgrid=True,
            gridcolor="#1e2640",
            ticksuffix="%",
        ),
        yaxis=dict(
            title="",
            automargin=True,
            tickfont=dict(size=12),
        ),
        bargap=0.35,
        height=max(280, len(tickers) * 46 + 60),
        margin=dict(l=10, r=30, t=16, b=44),
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
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
    from scipy.cluster.hierarchy import dendrogram

    dendro = dendrogram(linkage_matrix, labels=tickers, no_plot=True)

    fig = go.Figure()

    for x, y in zip(dendro["icoord"], dendro["dcoord"]):
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line=dict(color="#7c5cfc", width=2),
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
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
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
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
    )

    return fig

# ---------------------------------------------------------------------------
# 4. Efficient Frontier
# ---------------------------------------------------------------------------

def plot_efficient_frontier(
    frontier_vols: list[float],
    frontier_rets: list[float],
    hrp_vol: float,
    hrp_ret: float | None,
    mv_vol: float,
    mv_ret: float | None,
) -> go.Figure:
    """Efficient frontier scatter with HRP and MV portfolio markers.

    Args:
        frontier_vols: Annualised volatilities along the MV frontier.
        frontier_rets: Expected returns along the MV frontier.
        hrp_vol:       HRP portfolio annualised volatility.
        hrp_ret:       HRP expected return (None if not estimated).
        mv_vol:        MV portfolio annualised volatility.
        mv_ret:        MV expected return (None if not estimated).

    Returns:
        Plotly Figure ready for st.plotly_chart().
    """
    fig = go.Figure()

    # Frontier line
    fig.add_trace(go.Scatter(
        x=[v * 100 for v in frontier_vols],
        y=[r * 100 for r in frontier_rets],
        mode="lines",
        name="Efficient Frontier",
        line=dict(color="#475569", width=1.5, dash="dash"),
    ))

    # MV portfolio marker
    if mv_ret is not None:
        fig.add_trace(go.Scatter(
            x=[mv_vol * 100],
            y=[mv_ret * 100],
            mode="markers+text",
            name="Markowitz",
            marker=dict(color="#f59e0b", size=13, symbol="diamond",
                        line=dict(color="#fcd34d", width=1)),
            text=["Markowitz"],
            textposition="top center",
            textfont=dict(color="#fcd34d", size=11),
        ))

    # HRP portfolio marker
    y_hrp = [hrp_ret * 100] if hrp_ret is not None else [0]
    fig.add_trace(go.Scatter(
        x=[hrp_vol * 100],
        y=y_hrp,
        mode="markers+text",
        name="HRP",
        marker=dict(color="#7c5cfc", size=13, symbol="circle",
                    line=dict(color="#a78bfa", width=1)),
        text=["HRP"],
        textposition="top center",
        textfont=dict(color="#a78bfa", size=11),
    ))

    fig.update_layout(
        title="Efficient Frontier — HRP vs Markowitz",
        xaxis_title="Annualised Volatility (%)",
        yaxis_title="Expected Return (%)",
        height=420,
        margin=dict(l=20, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
    )

    return fig
