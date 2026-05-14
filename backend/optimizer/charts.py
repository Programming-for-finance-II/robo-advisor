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
