"""
frontend/app.py
AI-Powered Robo-Advisor Platform
Programming in Finance II (2026) -- USI

W4 changes (Mon-Tue):
    - Portfolio Dashboard wired to HRP optimizer with mock fallback
    - Weights table with UCITS badges
    - Risk contribution bar chart
    - Stress regime banner
    - recommendation_id stored in session_state for Chat Advisor
"""

import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from backend.llm.narrator import NarratorClient
from backend.llm.validator import validate
from backend.schemas.mock_data import get_mock_payload
from frontend.style import (
    apply_plotly_theme,
    get_theme_tokens,
    inject_css,
    is_light,
    page_header,
    render_eu_note,
    render_global_footer,
)

# ---------------------------------------------------------------------------
# Page config -- must be the first Streamlit call in the file
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RoboAdvisor · USI 2026",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"
inject_css()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# MiFID II disclaimer shown above every financial output
DISCLAIMER = (
    "**Educational prototype** developed in an academic context. "
    "No content constitutes financial advice under MiFID II or any other "
    "regulatory framework. Market data may be inaccurate or delayed."
)

# UCITS-eligible tickers (primary universe — see ADR-001)
_UCITS_TICKERS: frozenset[str] = frozenset({"CSPX.L", "AGGH.MI", "XEON.MI"})

# Mock portfolio data (Phase A fallback)
_MOCK_WEIGHTS: dict[str, float] = {
    "CSPX.L":  0.30,
    "EFA":     0.15,
    "GLD":     0.10,
    "VNQ":     0.05,
    "AGGH.MI": 0.20,
    "TLT":     0.10,
    "TIP":     0.05,
    "XEON.MI": 0.05,
}

_MOCK_REGIME: str = "NORMAL"

# Maps the uppercase profile label from the backend to the lowercase key
# used by get_mock_payload()
_LABEL_TO_MOCK: dict[str, str] = {
    "CONSERVATIVE": "conservative",
    "MODERATE": "balanced",
    "AGGRESSIVE": "aggressive",
}

# Start date for the live market data download
_DATA_START: str = "2023-01-01"

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATH = ASSETS_DIR / "roboadvisor_robot_transparent.png"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Portfolio data loading
# Two paths:
#   Phase A (default) -- get_mock_payload(), instant, no network needed
#   Phase B (live)    -- download real prices, run HRP, detect regime
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _build_live_cluster_structure(prices, weights: dict[str, float]):
    """Compute a real ClusterStructure from live daily prices and HRP weights.

    Mirrors the four clusters used across the dashboard (risk assets, real
    assets, safe haven, cash) and fills each with its total weight, average
    intra-cluster correlation, and annualised volatility — so the "How your
    money is grouped" view shows live numbers instead of placeholders.
    """
    import numpy as np

    from backend.schemas.ground_truth import Cluster, ClusterStructure

    _ATTR_BY_TICKER = {
        "CSPX.L": "cluster_A_risk_assets", "EFA": "cluster_A_risk_assets",
        "GLD": "cluster_B_real_assets",    "VNQ": "cluster_B_real_assets",
        "AGGH.MI": "cluster_C_safe_haven", "TLT": "cluster_C_safe_haven",
        "TIP": "cluster_C_safe_haven",
        "XEON.MI": "cluster_D_cash",
    }
    attrs = [
        "cluster_A_risk_assets", "cluster_B_real_assets",
        "cluster_C_safe_haven", "cluster_D_cash",
    ]

    returns = prices.pct_change().dropna()
    corr = returns.corr()

    clusters: dict[str, Cluster] = {}
    for attr in attrs:
        members = [
            t for t in weights
            if _ATTR_BY_TICKER.get(t) == attr and t in returns.columns
        ]
        total_weight = float(sum(weights.get(t, 0.0) for t in members))

        # Average off-diagonal pairwise correlation within the cluster.
        if len(members) >= 2:
            pair_vals = [
                float(corr.loc[a, b])
                for i, a in enumerate(members)
                for b in members[i + 1:]
            ]
            icc = float(np.mean(pair_vals)) if pair_vals else None
        else:
            icc = None

        # Annualised volatility of the weight-blended cluster return.
        if members:
            w = np.array([weights.get(t, 0.0) for t in members], dtype=float)
            w = w / w.sum() if w.sum() > 0 else np.full(len(members), 1.0 / len(members))
            blended = returns[members].to_numpy() @ w
            cvol = (
                float(np.std(blended, ddof=1) * np.sqrt(252))
                if len(blended) > 1 else 0.0
            )
        else:
            cvol = 0.0

        clusters[attr] = Cluster(
            members=members,
            total_weight=min(max(total_weight, 0.0), 1.0),
            intra_cluster_correlation=(
                None if icc is None else max(-1.0, min(1.0, icc))
            ),
            cluster_volatility=max(cvol, 0.0),
        )

    return ClusterStructure(**clusters)


def _run_live_optimization(profile_label: str) -> dict:
    """
    Download market data and run the HRP optimizer.
    Result is cached for 5 minutes to avoid repeated yfinance calls.
    Returns a dict with weights, risk_contributions, volatility,
    recommendation_id, and stress regime.
    """
    from datetime import date

    from backend.data.loader import ValidatedDataLoader
    from backend.data.universe_config import get_cluster_map, get_primary_tickers
    from backend.optimizer.hrp import compute_covariance, optimize
    from backend.optimizer.regime_detector import detect_regime

    tickers = get_primary_tickers()
    cluster_map = get_cluster_map()
    end_date = date.today().isoformat()

    # Download and validate prices
    loader = ValidatedDataLoader()
    prices, report = loader.load(tickers=tickers, start=_DATA_START, end=end_date)

    # Detect market stress regime from the covariance matrix
    cov = compute_covariance(prices)
    regime_result = detect_regime(cov)

    # Run HRP optimizer
    result = optimize(
        prices=prices,
        profile=profile_label,  # type: ignore[arg-type]
        cluster_map=cluster_map,
        ucits_tickers=report.ucits_tickers_used,
        fallback_tickers=list(report.fallback_tickers_applied.keys()),
    )

    # Markowitz Max-Sharpe benchmark, computed from the SAME prices already
    # downloaded above. This guarantees HRP and MV are compared on identical
    # input data (same Ledoit-Wolf covariance) and costs no extra network call.
    # Risk contributions use the same marginal formula as HRP, so the two are
    # directly comparable. Defensive: a failure here must not break the HRP
    # recommendation — the comparison views fall back to an offline estimate.
    try:
        from backend.optimizer.markowitz import optimize_markowitz

        mv_result = optimize_markowitz(
            prices,
            ucits_tickers=report.ucits_tickers_used,
            fallback_tickers=list(report.fallback_tickers_applied.keys()),
        )
        mv_fields = {
            "mv_weights": mv_result["weights"],
            "mv_risk_contributions": mv_result["risk_contributions"],
            "mv_expected_volatility": mv_result["expected_volatility"],
            "mv_expected_return": mv_result["expected_return"],
            "mv_sharpe_ratio": mv_result["sharpe_ratio"],
        }
    except Exception:
        mv_fields = {}

    # Real cluster structure for the "How your money is grouped" view.
    # Defensive: a failure here must not break the whole live path — the
    # grouping view falls back gracefully when this is absent.
    try:
        cluster_structure = _build_live_cluster_structure(prices, result["weights"])
    except Exception:
        cluster_structure = None

    # Historical max drawdown of the (static-weight) portfolio over the loaded
    # price history, so the KPI card shows a real figure rather than a dash.
    try:
        import numpy as np

        _w = result["weights"]
        _cols = [t for t in _w if t in prices.columns]
        _rets = prices[_cols].pct_change().dropna()
        _wv = np.array([_w[t] for t in _cols], dtype=float)
        _wv = _wv / _wv.sum() if _wv.sum() > 0 else _wv
        _equity = np.cumprod(1.0 + (_rets.to_numpy() @ _wv))
        _max_drawdown = float((_equity / np.maximum.accumulate(_equity) - 1.0).min())
    except Exception:
        _max_drawdown = None

    return {
        "weights": result["weights"],
        "risk_contributions": result["risk_contributions"],
        "expected_volatility": result["expected_volatility"],
        "expected_return": result["expected_return"],
        "sharpe_ratio": result["sharpe_ratio"],
        "max_drawdown": _max_drawdown,
        "ucits_tickers_used": report.ucits_tickers_used,
        "fallback_tickers_applied": list(report.fallback_tickers_applied.keys()),
        "recommendation_id": str(uuid.uuid4()),
        "stress_regime": regime_result.regime,
        "avg_correlation": regime_result.avg_correlation,
        "cluster_structure": cluster_structure,
        "source": "live",
        **mv_fields,
    }


def _mock_optimization(profile_key: str) -> dict:
    """
    Build portfolio data from the Phase A mock payload.
    Always available -- no network call needed.

    Risk contributions are approximated as weight x cluster_volatility.
    Phase B replaces this with real marginal risk contributions from HRP.
    """
    payload = get_mock_payload(profile_key)
    weights = payload.portfolio.weights

    # Use cluster volatility as a proxy for per-asset risk contribution
    # This is a Phase A approximation -- Phase B uses the real optimizer output
    _CLUSTER_VOL: dict[str, float] = {
        "CSPX.L": 0.162, "EFA": 0.162,
        "GLD": 0.138,    "VNQ": 0.138,
        "AGGH.MI": 0.071, "TLT": 0.071, "TIP": 0.071,
        "XEON.MI": 0.003,
    }
    raw = {t: weights.get(t, 0.0) * _CLUSTER_VOL.get(t, 0.10) for t in weights}
    total = sum(raw.values()) or 1.0
    risk_contributions = {t: v / total for t, v in raw.items()}

    return {
        "weights": weights,
        "risk_contributions": risk_contributions,
        "expected_volatility": payload.risk_metrics.annual_volatility,
        "expected_return": payload.risk_metrics.expected_annual_return,
        "sharpe_ratio": payload.risk_metrics.sharpe_ratio,
        "max_drawdown": payload.risk_metrics.max_drawdown_historical,
        "ucits_tickers_used": payload.portfolio.ucits_tickers_used,
        "fallback_tickers_applied": payload.portfolio.fallback_tickers_applied,
        "recommendation_id": f"mock-{profile_key}-{uuid.uuid4().hex[:8]}",
        "stress_regime": "NORMAL",
        "avg_correlation": None,
        "source": "mock",
        "stress_scenarios": payload.stress_scenarios,
        "backtest": payload.backtest_summary,
        "regulatory_context": payload.regulatory_context,
        "cluster_structure": payload.cluster_structure,
    }


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGES = [
    "Questionnaire",
    "Portfolio Dashboard",
    "Compare Markowitz",
    "Chat Advisor",
    "Backtesting",
    "Settings",
]

_SHIELD_SVG = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
    "</svg>"
)

# Lucide-style line icons for the Compare Markowitz explanation card.
_ICON_BULB = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 18h6"/><path d="M10 22h4"/>'
    '<path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8'
    'A6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5.76.76 1.23 1.52 1.41 2.5"/>'
    "</svg>"
)
_ICON_SHIELD = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
    "</svg>"
)
_ICON_BARS = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="12" y1="20" x2="12" y2="10"/>'
    '<line x1="18" y1="20" x2="18" y2="4"/>'
    '<line x1="6" y1="20" x2="6" y2="16"/>'
    "</svg>"
)
_ICON_CAP = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 10 12 5 2 10l10 5 10-5z"/>'
    '<path d="M6 12v5c0 1 2.5 3 6 3s6-2 6-3v-5"/>'
    '<line x1="22" y1="10" x2="22" y2="16"/>'
    "</svg>"
)
_ICON_GLOBE = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/>'
    '<line x1="2" y1="12" x2="22" y2="12"/>'
    '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10'
    'A15.3 15.3 0 0 1 8 12a15.3 15.3 0 0 1 4-10z"/>'
    "</svg>"
)
_ICON_TREND = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
    '<polyline points="17 6 23 6 23 12"/>'
    "</svg>"
)


def main() -> None:
    # UNIFIED TOP NAVBAR (apple.com style) — replaces separate logo block
    # and nav row. Only this section was modified. Do not edit elsewhere.

    # Stable per-browser identifier. Kept in the URL as ?sid= so it survives a
    # page reload (st.session_state is reset on reload), and mirrored into
    # session_state. The questionnaire uses it to look up the saved profile.
    _sid = st.query_params.get("sid")
    if not _sid:
        _sid = st.session_state.get("session_token") or str(uuid.uuid4())
        st.query_params["sid"] = _sid
    st.session_state["session_token"] = _sid

    # Step 1: resolve active page from query params; st.button sets it directly
    _qp = unquote_plus(st.query_params.get("page", PAGES[0]))
    active = _qp if _qp in PAGES else PAGES[0]
    st.session_state.active_page = active

    # Step 2: embed logo as base64 for the fixed-position HTML element
    if LOGO_PATH.exists():
        import base64 as _b64
        _logo_b64 = _b64.b64encode(LOGO_PATH.read_bytes()).decode()
        _logo_tag = (
            f'<div style="'
            f'width:62px;height:62px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'background:rgba(124,92,252,0.13);'
            f'border:1.5px solid rgba(124,92,252,0.38);'
            f'border-radius:16px;'
            f'box-shadow:0 0 18px rgba(124,92,252,0.28),0 2px 8px rgba(0,0,0,0.35);'
            f'flex-shrink:0;">'
            f'<img src="data:image/png;base64,{_logo_b64}"'
            f' style="height:42px;width:auto;" alt="RoboAdvisor">'
            f'</div>'
        )
    else:
        _logo_tag = (
            '<div style="'
            'width:62px;height:62px;'
            'display:flex;align-items:center;justify-content:center;'
            'background:rgba(124,92,252,0.13);'
            'border:1.5px solid rgba(124,92,252,0.38);'
            'border-radius:16px;'
            'box-shadow:0 0 18px rgba(124,92,252,0.28),0 2px 8px rgba(0,0,0,0.35);'
            'flex-shrink:0;">'
            '<span style="font-size:1.6rem;font-weight:700;color:#f5f5f7;'
            "font-family:'Space Grotesk',sans-serif;\">R</span>"
            '</div>'
        )

    # Step 3: render brand HTML + CSS; nav buttons added as st.columns below
    # Theme-aware navbar tokens — light mode gets a translucent white premium bar
    # with a soft shadow/hairline; dark mode keeps the original glassy dark bar.
    if is_light():
        nav_bg = ("linear-gradient(180deg,"
                  "rgba(255,255,255,0.90) 0%, rgba(255,255,255,0.84) 100%)")
        nav_shadow = "0 8px 24px rgba(15,23,42,0.08)"
        nav_hairline = ("linear-gradient(90deg,"
                        "transparent 0%, rgba(124,77,255,0.35) 50%, transparent 100%)")
        nav_brand_grad = "linear-gradient(92deg, #1e1b4b 0%, #7c4dff 100%)"
        nav_brand_fallback = "#111827"
        nav_sub_color = "rgba(51,65,85,0.72)"
        nav_text = "#334155"
        nav_text_hover = "#111827"
        nav_hover_bg = "rgba(124,77,255,0.08)"
    else:
        nav_bg = ("linear-gradient(180deg,"
                  "rgba(22,28,46,0.92) 0%, rgba(13,17,28,0.88) 100%)")
        nav_shadow = "0 4px 30px rgba(0,0,0,0.45)"
        nav_hairline = ("linear-gradient(90deg,"
                        "transparent 0%, rgba(124,92,252,0.55) 50%, transparent 100%)")
        nav_brand_grad = "linear-gradient(92deg, #ffffff 0%, #c9bcff 100%)"
        nav_brand_fallback = "#f5f5f7"
        nav_sub_color = "rgba(245,245,247,0.44)"
        nav_text = "rgba(245,245,247,0.62)"
        nav_text_hover = "#f5f5f7"
        nav_hover_bg = "rgba(255,255,255,0.05)"
    st.markdown(
        f"""<style>
/* ── Reset Streamlit chrome ─────────────────────────────────────────── */
header[data-testid="stHeader"] {{ display: none !important; }}
[data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden; }}
section[data-testid="stMain"] > div:first-child {{
    padding-top: 88px !important;
}}
/* ── Top navbar ─────────────────────────────────────────────────────── */
@keyframes navSlideDown {{
    from {{ opacity: 0; transform: translateY(-10px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
.top-navbar {{
    position: fixed; top: 0; left: 0;
    width: 100%; height: 76px; z-index: 1000;
    background: {nav_bg};
    backdrop-filter: blur(30px) saturate(140%);
    -webkit-backdrop-filter: blur(30px) saturate(140%);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 40px; box-sizing: border-box;
    box-shadow: {nav_shadow};
    flex-wrap: nowrap;
    overflow: visible;
    animation: navSlideDown 0.5s cubic-bezier(0.16,1,0.3,1);
}}
/* Gradient hairline under the navbar for a subtle premium edge */
.top-navbar::after {{
    content: ""; position: absolute; left: 0; right: 0; bottom: 0;
    height: 1px;
    background: {nav_hairline};
}}
.top-navbar .brand {{
    display: flex; align-items: center; gap: 14px;
    min-width: 260px; flex-shrink: 0; text-decoration: none;
}}
.top-navbar .brand-name {{
    font-size: 19px; font-weight: 700;
    letter-spacing: -0.4px; line-height: 1.2;
    font-family: 'Space Grotesk', -apple-system, sans-serif;
    background: {nav_brand_grad};
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: {nav_brand_fallback};
}}
.top-navbar .brand-sub {{
    font-size: 9.5px; letter-spacing: 0.09em;
    color: {nav_sub_color}; text-transform: uppercase;
    line-height: 1.3; margin-top: 3px;
}}
/* ── Streamlit button row moved inside navbar by JS ─────────────────── */
.top-navbar [data-testid="stHorizontalBlock"] {{
    display: flex !important; align-items: center !important;
    flex: 1 1 auto !important; justify-content: flex-end !important;
    gap: 2px !important; background: transparent !important;
    padding: 0 !important; margin: 0 !important;
    flex-wrap: nowrap !important; min-width: 0 !important;
    overflow: visible !important; max-height: 76px !important;
}}
.top-navbar [data-testid="stHorizontalBlock"] > div {{
    flex: 0 0 auto !important; width: auto !important;
    min-width: unset !important; padding: 0 !important;
    max-height: 76px !important;
}}
.top-navbar .stButton > button {{
    position: relative !important;
    background: transparent !important;
    border: none !important; box-shadow: none !important;
    color: {nav_text} !important;
    font-size: 13px !important; font-weight: 500 !important;
    letter-spacing: -0.1px !important;
    padding: 7px 15px !important; border-radius: 9px !important;
    min-height: unset !important; height: 38px !important;
    white-space: nowrap !important;
    transition: color 0.18s ease, background 0.18s ease,
        transform 0.18s cubic-bezier(0.16,1,0.3,1) !important;
    font-family: -apple-system, 'Space Grotesk', sans-serif !important;
    display: inline-flex !important; align-items: center !important; gap: 7px !important;
}}
/* Animated underline that grows from the centre on hover */
.top-navbar .stButton > button::after {{
    content: ""; position: absolute; left: 50%; bottom: 4px;
    width: 0; height: 2px; border-radius: 2px;
    background: linear-gradient(90deg, #a78bfa, #7c5cfc);
    transform: translateX(-50%);
    transition: width 0.22s cubic-bezier(0.16,1,0.3,1);
}}
.top-navbar .stButton > button:hover {{
    color: {nav_text_hover} !important;
    background: {nav_hover_bg} !important;
    transform: translateY(-1px) !important;
}}
.top-navbar .stButton > button:hover::after {{ width: 42%; }}
.top-navbar [data-testid="stBaseButton-primary"],
.top-navbar [data-testid="baseButton-primary"],
.top-navbar .stButton > button[kind="primary"] {{
    color: #ffffff !important; font-weight: 600 !important;
    background: linear-gradient(135deg,
        rgba(124,92,252,0.95) 0%, rgba(109,40,217,0.95) 100%) !important;
    box-shadow: 0 2px 14px rgba(124,92,252,0.45),
        inset 0 1px 0 rgba(255,255,255,0.18) !important;
}}
.top-navbar [data-testid="stBaseButton-primary"]:hover,
.top-navbar [data-testid="baseButton-primary"]:hover,
.top-navbar .stButton > button[kind="primary"]:hover {{
    background: linear-gradient(135deg,
        rgba(138,108,255,1) 0%, rgba(124,58,237,1) 100%) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
}}
.top-navbar [data-testid="stBaseButton-primary"]::after,
.top-navbar [data-testid="baseButton-primary"]::after,
.top-navbar .stButton > button[kind="primary"]::after {{ width: 0 !important; }}
/* ── Responsive nav + content padding ───────────────────────────────── */
@media (max-width: 1080px) {{
    .top-navbar [data-testid="stHorizontalBlock"] {{
        display: none !important;
    }}
}}
@media (min-width: 1081px) {{
    .top-navbar [data-testid="stHorizontalBlock"] {{
        display: flex !important;
    }}
}}
@media (max-width: 1080px) {{
    section[data-testid="stMain"] > div:first-child {{
        padding-top: 80px !important;
    }}
}}
</style>
<nav class="top-navbar">
    <div class="brand">
        {_logo_tag}
        <div>
            <div class="brand-name">RoboAdvisor</div>
            <div class="brand-sub">
                USI &middot; Programming in Finance II &middot; 2026
            </div>
        </div>
    </div>
</nav>""",
        unsafe_allow_html=True,
    )

    # Step 4: native st.button() nav — JS moves this row into .top-navbar
    _nav_cols = st.columns(len(PAGES))
    for _nc, _page in zip(_nav_cols, PAGES):
        with _nc:
            _btype = "primary" if _page == active else "secondary"
            if st.button(
                _page,
                key=f"nav_{_page}",
                type=_btype,
                use_container_width=False,
            ):
                st.session_state.active_page = _page
                st.query_params["page"] = _page
                st.rerun()

    # Step 5: JS — move stHorizontalBlock into .top-navbar (no icon injection)
    import streamlit.components.v1 as _stc
    _stc.html(
        """<script>
(function () {
    function move() {
        var nav = window.parent.document.querySelector('.top-navbar');
        var block = window.parent.document.querySelector(
            '[data-testid="stHorizontalBlock"]'
        );
        if (nav && block) {
            if (!nav.contains(block)) { nav.appendChild(block); }
        } else {
            setTimeout(move, 50);
        }
    }
    move();
}());
</script>""",
        height=0,
    )

    # ── Pages ────────────────────────────────────────────────────────
    active = st.session_state.active_page
    if active == "Questionnaire":
        render_questionnaire()
    elif active == "Portfolio Dashboard":
        render_portfolio()
    elif active == "Chat Advisor":
        render_chat()
    elif active == "Backtesting":
        render_backtesting()
    elif active == "Compare Markowitz":
        render_compare()
    elif active == "Settings":
        render_settings()

    # Single discreet MiFID II footer, shown once at the bottom of every page.
    render_global_footer()


# ---------------------------------------------------------------------------
# Questionnaire data
# 10 questions from the Grable & Lytton (1999) Risk Tolerance Scale,
# adapted for MiFID II suitability requirements.
# ---------------------------------------------------------------------------

_QUESTIONS: list[dict] = [
    # Section A: financial capacity questions
    {
        "id": "Q1", "section": "Who You Are Financially",
        "text": "How old are you?",
        "options": ["Under 30", "30-45", "46-60", "Over 60"],
        "scores": [3, 2, 1, 0],
    },
    {
        "id": "Q2", "section": "Who You Are Financially",
        "text": "Which best describes your household income?",
        "options": [
            "Money is tight -- I cover essentials but have little left over.",
            "I'm comfortable -- I meet my needs and save occasionally.",
            "I'm in a solid position -- I save regularly.",
            "I have significant disposable income beyond living expenses.",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q3", "section": "Who You Are Financially",
        "text": (
            "If you had to live off savings starting tomorrow,"
            " how many months could you cover?"
        ),
        "options": ["Less than 3 months", "3-6 months", "6-12 months", "More than 12 months"],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q4", "section": "Who You Are Financially",
        "text": "Do you have financial dependents?",
        "options": [
            "No, I have no financial dependents.",
            "Yes, one dependent.",
            "Yes, two or three dependents.",
            "Yes, four or more dependents.",
        ],
        # Q4 is reverse-coded: more dependents = lower risk capacity
        "scores": [3, 2, 1, 0],
    },
    # Section B: investment behaviour and knowledge
    {
        "id": "Q5", "section": "How You Invest",
        "text": "How would you describe your investment experience?",
        "options": [
            "None -- I have never invested.",
            "Basic -- savings accounts or government bonds only.",
            "Intermediate -- I have invested in mutual funds or ETFs.",
            "Advanced -- I actively trade stocks or other complex instruments.",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q6", "section": "How You Invest",
        "text": "How would you rate your theoretical financial knowledge?",
        "options": [
            "Very limited -- I find financial topics confusing.",
            "Basic -- I understand how savings accounts and bonds work.",
            "Intermediate -- I'm comfortable with ETFs, diversification, volatility.",
            "Advanced -- I understand derivatives, leverage, portfolio construction.",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q7", "section": "How You Invest",
        "text": "What is the primary purpose of this investment?",
        "options": [
            "Safety net -- I may need this money at any time.",
            "A specific goal within the next 5 years.",
            "Long-term wealth building -- I won't need this for at least 10 years.",
            "Aggressive growth -- this is surplus capital with no planned withdrawal.",
        ],
        "scores": [0, 1, 2, 3],
        # MiFID II hard override: if Q7 = option 0, force CONSERVATIVE
        "override": True,
    },
    # Section C: behavioural reactions to losses
    {
        "id": "Q8", "section": "How You React",
        "text": "Your portfolio drops 20% in one month. What do you do?",
        "options": [
            "Sell everything immediately -- I cut my losses.",
            "Sell part of it to reduce risk.",
            "Hold and wait -- panic selling is the worst thing.",
            "Buy more at a discount -- this is an opportunity.",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q9", "section": "How You React",
        "text": (
            "Your portfolio drops 30% over 3 months."
            " How long are you willing to wait for recovery?"
        ),
        "options": [
            "A few months at most.",
            "Up to 6 months.",
            "One to three years.",
            "As long as it takes.",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q10", "section": "How You React",
        "text": "Which investment profile fits you best over a 10-year horizon?",
        "options": [
            "I'd lock in a guaranteed +2% per year -- modest but no surprises.",
            "Mostly stable -- I accept minor fluctuations for modest gains.",
            "Balanced -- I accept significant swings for stronger long-term returns.",
            "Aggressive -- I'm comfortable with large losses for high potential returns.",
        ],
        "scores": [0, 1, 2, 3],
    },
]

# Score boundaries from questionnaire_schema.md
_SCORE_CONSERVATIVE_MAX: int = 9
_SCORE_MODERATE_MAX: int = 19

# Scores that fall on a boundary between two profiles -- lower confidence
_CONFIDENCE_BORDERLINE_SCORES: set[int] = {8, 9, 10, 11, 18, 19, 20, 21}


def _compute_profile(answers: dict[str, int]) -> dict:
    """
    Compute the investor risk profile from questionnaire answers.
    Phase A: rule-based scoring (Grable & Lytton, 1999).
    Phase B: this will be replaced by the GBM classifier trained on SCF 2022.
    """
    # Check Q7 override before computing total score
    q7_override: bool = answers.get("Q7", -1) == 0

    score: int = sum(
        q["scores"][answers[q["id"]]] for q in _QUESTIONS if q["id"] in answers
    )

    if q7_override:
        # Safety net money -- MiFID II forces CONSERVATIVE regardless of score
        profile_label, confidence = "CONSERVATIVE", 1.0
    elif score <= _SCORE_CONSERVATIVE_MAX:
        profile_label = "CONSERVATIVE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.85
    elif score <= _SCORE_MODERATE_MAX:
        profile_label = "MODERATE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.82
    else:
        profile_label = "AGGRESSIVE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.88

    low_confidence_flag = confidence < 0.65

    # Top drivers: questions ranked by how strongly they influenced the score
    # Phase B will replace this with SHAP values from the GBM model
    scored_questions = sorted(
        [
            {"feature": q["id"], "importance": answers[q["id"]] / 3.0}
            for q in _QUESTIONS
            if q["id"] in answers
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )

    return {
        "profile_label": profile_label,
        "score": score,
        "confidence": confidence,
        "low_confidence_flag": low_confidence_flag,
        "top_drivers": scored_questions[:3],
        "q7_override_applied": q7_override,
    }


# ---------------------------------------------------------------------------
# Profile persistence
# The questionnaire profile is persisted in a dedicated SQLite table,
# `questionnaire_profiles`, keyed by the per-browser session token (kept in
# the URL as ?sid= so it survives a page reload). The table is append-only:
# each submission/reassessment inserts a new row and old rows are never
# overwritten, so the latest profile is simply the most recent row.
#
# The table is created on first use from here — it does NOT live in
# backend/data/schema.sql, so no backend module is modified.
# ---------------------------------------------------------------------------


def _profile_db_path() -> str:
    """Path to the SQLite file holding the questionnaire profiles.

    Defaults to robo_advisor.db at the repository root (same file the
    backend uses); overridable via the ROBO_ADVISOR_DB env var (tests).
    """
    override = os.environ.get("ROBO_ADVISOR_DB", "")
    if override:
        return override
    return str(Path(__file__).resolve().parent.parent / "robo_advisor.db")


def _profile_db_connect():
    """Open the profile DB and ensure the questionnaire_profiles table exists."""
    import sqlite3

    conn = sqlite3.connect(_profile_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_profiles (
            session_token TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            profile_label TEXT NOT NULL,
            profile_json  TEXT NOT NULL,
            answers_json  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qp_token_created "
        "ON questionnaire_profiles(session_token, created_at DESC)"
    )
    conn.commit()
    return conn


def _save_questionnaire_profile(token: str, result: dict, answers: dict) -> None:
    """Insert a new questionnaire-profile row (append-only audit trail)."""
    from datetime import datetime, timezone

    if not token:
        return
    try:
        conn = _profile_db_connect()
        conn.execute(
            "INSERT INTO questionnaire_profiles "
            "(session_token, created_at, profile_label, profile_json, answers_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                token,
                datetime.now(timezone.utc).isoformat(),
                result["profile_label"],
                json.dumps(result),
                json.dumps(answers),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        # Persistence is best-effort: never break the UI if the DB is
        # unavailable (e.g. a read-only filesystem). The session_state
        # copy still drives the 3-state UI within the current session.
        pass


def _load_questionnaire_profile(token: str) -> dict | None:
    """Return the most recent saved profile for a token, or None."""
    if not token:
        return None
    try:
        conn = _profile_db_connect()
        row = conn.execute(
            "SELECT profile_json, answers_json FROM questionnaire_profiles "
            "WHERE session_token = ? ORDER BY created_at DESC LIMIT 1",
            (token,),
        ).fetchone()
        conn.close()
    except Exception:
        return None
    if row is None:
        return None
    try:
        return {
            "profile": json.loads(row["profile_json"]),
            "answers": json.loads(row["answers_json"]),
        }
    except (TypeError, ValueError):
        return None


def _restore_persisted_profile() -> None:
    """Rehydrate a saved profile into session_state on page load.

    No-op if a profile is already in this session or nothing is saved for
    this session token. This is what makes the profile survive a reload.
    """
    if st.session_state.get("profile"):
        return
    token = st.session_state.get("session_token")
    saved = _load_questionnaire_profile(token)
    if saved:
        st.session_state["profile"] = saved["profile"]
        st.session_state["questionnaire_answers"] = saved["answers"]


def _render_profile_result_card(result: dict, show_dashboard_button: bool = True) -> None:
    """Render the investor-profile result card (shared by post-submit and
    read-only states). The "View my Portfolio Dashboard" button is optional:
    the read-only state hides it (a Reassess button is shown there instead)."""
    _RESULT_META = {
        "CONSERVATIVE": {
            "icon": "🛡️",
            "color": "#0dcfb0",
            "label": "Conservative",
            "desc": "Capital preservation focus · low-volatility, income-oriented assets",
            "bar_gradient": "linear-gradient(90deg,#0dcfb0,#22d3ee)",
        },
        "MODERATE": {
            "icon": "⚖️",
            "color": "#7c5cfc",
            "label": "Moderate",
            "desc": "Balanced growth and protection · diversified multi-asset allocation",
            "bar_gradient": "linear-gradient(90deg,#7c5cfc,#a78bfa)",
        },
        "AGGRESSIVE": {
            "icon": "🚀",
            "color": "#f87171",
            "label": "Aggressive",
            "desc": "Growth-oriented · higher volatility and drawdown accepted",
            "bar_gradient": "linear-gradient(90deg,#f87171,#fbbf24)",
        },
    }
    t = get_theme_tokens()
    rm = _RESULT_META.get(result["profile_label"], _RESULT_META["MODERATE"])
    score_pct = result["score"] / 30 * 100  # max possible = 10 × 3 = 30
    _chip_bg = t["accent_soft"] if is_light() else "rgba(255,255,255,0.06)"
    _metric_bg = t["bg_surface_alt"] if is_light() else "rgba(0,0,0,0.25)"

    # ── top drivers text ────────────────────────────────────────────────
    driver_labels = {
        "Q1": "Age", "Q2": "Income", "Q3": "Liquidity",
        "Q4": "Dependents", "Q5": "Experience", "Q6": "Knowledge",
        "Q7": "Investment purpose", "Q8": "Loss reaction",
        "Q9": "Recovery horizon", "Q10": "Self-assessment",
    }
    top3 = result.get("top_drivers", [])[:3]
    drivers_chips = "".join(
        f'<span style="background:{_chip_bg};border:1px solid {t["border"]};'
        f'border-radius:7px;padding:0.3rem 0.75rem;font-size:0.85rem;'
        f'font-weight:500;color:{t["text_secondary"]};">'
        + driver_labels.get(d["feature"], d["feature"]) + "</span>"
        for d in top3
    )
    # Pre-build the optional drivers block — avoids nested f-string inside the card
    drivers_block = (
        f'<div style="font-size:0.75rem;font-weight:600;letter-spacing:0.1em;'
        f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:0.55rem;">'
        f'Top scoring factors</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:0.5rem;">'
        + drivers_chips + "</div>"
    ) if top3 else ""

    conf_pct = int(result["confidence"] * 100)

    card_html = (
        f'<div style="background:linear-gradient(135deg,{rm["color"]}12,{rm["color"]}06);'
        f'border:1px solid {rm["color"]}45;border-radius:16px;'
        f'padding:1.5rem 1.75rem 1.4rem 1.75rem;margin:1.5rem 0 1rem 0;">'

        # ── header ──────────────────────────────────────────────────────
        f'<div style="display:flex;align-items:flex-start;gap:1.25rem;margin-bottom:1.35rem;">'
        f'<div style="font-size:2.8rem;line-height:1;flex-shrink:0;margin-top:0.1rem;">'
        f'{rm["icon"]}</div>'
        f'<div style="flex:1;">'
        f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:{rm["color"]}90;margin-bottom:0.3rem;">'
        f'YOUR INVESTOR RISK PROFILE</div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2.2rem;'
        f'font-weight:700;color:{rm["color"]};letter-spacing:-0.02em;line-height:1.1;">'
        f'{rm["label"]}</div>'
        f'<div style="font-size:0.9rem;color:{t["text_muted"]};'
        f'margin-top:0.4rem;">{rm["desc"]}</div>'
        f'</div></div>'

        # ── metrics row ──────────────────────────────────────────────────
        f'<div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.25rem;">'

        # score card
        f'<div style="flex:1;min-width:120px;background:{_metric_bg};'
        f'border:1px solid {t["border"]};border-radius:10px;padding:0.75rem 1.1rem;">'
        f'<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:{t["text_muted"]};margin-bottom:0.35rem;">Score</div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.7rem;'
        f'font-weight:700;color:{t["text_primary"]};line-height:1;">'
        f'{result["score"]}'
        f'<span style="font-size:0.85rem;color:{t["text_muted"]};font-weight:400;">/30</span></div>'
        f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;'
        f'background:{t["border"]};overflow:hidden;">'
        f'<div style="height:100%;width:{score_pct:.0f}%;'
        f'background:{rm["bar_gradient"]};border-radius:3px;"></div>'
        f'</div></div>'

        # confidence card
        f'<div style="flex:1;min-width:120px;background:{_metric_bg};'
        f'border:1px solid {t["border"]};border-radius:10px;padding:0.75rem 1.1rem;">'
        f'<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:{t["text_muted"]};margin-bottom:0.35rem;">Model Confidence</div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.7rem;'
        f'font-weight:700;color:{rm["color"]};line-height:1;">{conf_pct}%</div>'
        f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;'
        f'background:{t["border"]};overflow:hidden;">'
        f'<div style="height:100%;width:{conf_pct}%;'
        f'background:{rm["bar_gradient"]};border-radius:3px;"></div>'
        f'</div></div>'

        '</div>'  # end metrics row

        # ── drivers ──────────────────────────────────────────────────────
        + drivers_block +
        '</div>'  # end card
    )
    st.markdown(card_html, unsafe_allow_html=True)

    if result["low_confidence_flag"]:
        st.warning(
            "⚠️  Borderline score — your answers sit near the boundary between two "
            "profiles. Consider reviewing your responses for a more precise classification."
        )

    if result["q7_override_applied"]:
        st.info(
            "ℹ️  MiFID II override applied: capital earmarked as a safety net (Q7) "
            "forces your profile to **CONSERVATIVE** regardless of overall score."
        )

    if show_dashboard_button and st.button(
        "View my Portfolio Dashboard →",
        key="view_portfolio_btn",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.active_page = "Portfolio Dashboard"
        st.query_params["page"] = "Portfolio Dashboard"
        st.rerun()


# ---------------------------------------------------------------------------
# Page 1 -- Questionnaire
# ---------------------------------------------------------------------------

def render_questionnaire() -> None:
    page_header("Investor Profile Questionnaire", "Grable-Lytton Scale · 10 questions", icon="🧭")

    # Info card — Grable-Lytton explanation (native <details> for full style control)
    st.markdown(
        """
        <details class="qs-info-card">
          <summary>
            <span class="qs-info-title">What is the Grable-Lytton Scale?</span>
            <span class="qs-info-chevron">▾</span>
          </summary>
          <div class="qs-info-body">
            An academic risk-tolerance questionnaire (Grable &amp; Lytton, 1999) used to
            estimate how much financial risk an investor is willing and able to take.
            In this prototype it provides the rule-based baseline for the investor profile.
            The 10 items cover financial situation, investment behaviour and reactions to
            market stress — yielding a composite score mapped to a risk category.
          </div>
        </details>
        """,
        unsafe_allow_html=True,
    )

    # ── Determine which of the three states to render ────────────────────────
    # Try to rehydrate a previously saved profile for this session token, then
    # branch: read-only (profile exists) vs. form (first-time / reassessment).
    _restore_persisted_profile()
    existing = st.session_state.get("profile")
    reassessing = st.session_state.get("questionnaire_reassess", False)

    # ── State 2: READ-ONLY — a profile already exists for this session ────────
    if existing and not reassessing:
        st.markdown(
            '<div style="font-size:0.92rem;color:#64748b;margin:0 0 0.5rem 0;">'
            "You have already completed the questionnaire. Your saved investor "
            "profile is shown below. Start a reassessment to update your answers."
            "</div>",
            unsafe_allow_html=True,
        )
        _render_profile_result_card(existing, show_dashboard_button=True)
        if st.button(
            "↻ Reassess my profile",
            key="reassess_btn",
            use_container_width=True,
        ):
            st.session_state["questionnaire_reassess"] = True
            st.rerun()
        return

    # ── State 1 & 3: FIRST-TIME or REASSESSMENT — render the editable form ────
    if reassessing:
        st.info(
            "Reassessment in progress — review and update your answers below, "
            "then recalculate to replace your saved profile."
        )

    st.markdown(
        '<div style="font-size:0.92rem;color:#64748b;margin:0 0 1.5rem 0;">'
        "Complete the three sections below to generate your investor risk profile."
        "</div>",
        unsafe_allow_html=True,
    )

    answers: dict[str, int | None] = {}

    sections = [
        {
            "number": "01",
            "title": "Financial Situation",
            "subtitle": "Basic information about your financial background.",
            "key": "Who You Are Financially",
            "css_class": "qs-s1",
            "accent": "#60a5fa",
            "accent_bg": "rgba(59,130,246,0.13)",
            "accent_border": "rgba(59,130,246,0.28)",
        },
        {
            "number": "02",
            "title": "Investment Behaviour",
            "subtitle": "How you think about time horizon, return and uncertainty.",
            "key": "How You Invest",
            "css_class": "qs-s2",
            "accent": "#a78bfa",
            "accent_bg": "rgba(124,92,252,0.13)",
            "accent_border": "rgba(124,92,252,0.28)",
        },
        {
            "number": "03",
            "title": "Reaction to Risk",
            "subtitle": "How you would react under market stress.",
            "key": "How You React",
            "css_class": "qs-s3",
            "accent": "#fbbf24",
            "accent_bg": "rgba(245,158,11,0.13)",
            "accent_border": "rgba(245,158,11,0.28)",
        },
    ]

    # ── Section stepper ──────────────────────────────────────────────────────
    # align-items:flex-start + margin-top:1.4rem on connectors keeps the
    # gradient lines perfectly centred on the circles (circle height = 2.8rem,
    # centre = 1.4rem from top) regardless of the label below each circle.
    tk = get_theme_tokens()
    _step_bg = "#f1f4fa" if is_light() else "rgba(15,23,42,0.55)"
    _c_blue = "#2563eb" if is_light() else "#60a5fa"
    _c_purple = "#6d4deb" if is_light() else "#a78bfa"
    _c_amber = "#b45309" if is_light() else "#fbbf24"
    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-start;
            padding:1rem 1.5rem;margin:0 0 1.25rem 0;
            background:{_step_bg};
            border:1px solid {tk["border"]};border-radius:12px;">

          <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;">
            <div style="width:2.8rem;height:2.8rem;border-radius:50%;
              background:rgba(59,130,246,0.15);border:2px solid #3b82f6;
              display:flex;align-items:center;justify-content:center;
              font-family:'Space Grotesk',sans-serif;
              font-size:0.88rem;font-weight:700;color:{_c_blue};">01</div>
            <div style="font-size:0.75rem;font-weight:500;color:{_c_blue};
              white-space:nowrap;">Financial</div>
          </div>

          <div style="flex:1;height:2px;
            background:linear-gradient(to right,#3b82f6,#7c5cfc);
            margin:1.4rem 0.8rem 0 0.8rem;"></div>

          <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;">
            <div style="width:2.8rem;height:2.8rem;border-radius:50%;
              background:rgba(124,92,252,0.15);border:2px solid #7c5cfc;
              display:flex;align-items:center;justify-content:center;
              font-family:'Space Grotesk',sans-serif;
              font-size:0.88rem;font-weight:700;color:{_c_purple};">02</div>
            <div style="font-size:0.75rem;font-weight:500;color:{_c_purple};
              white-space:nowrap;">Behaviour</div>
          </div>

          <div style="flex:1;height:2px;
            background:linear-gradient(to right,#7c5cfc,#f59e0b);
            margin:1.4rem 0.8rem 0 0.8rem;"></div>

          <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;">
            <div style="width:2.8rem;height:2.8rem;border-radius:50%;
              background:rgba(245,158,11,0.15);border:2px solid #f59e0b;
              display:flex;align-items:center;justify-content:center;
              font-family:'Space Grotesk',sans-serif;
              font-size:0.88rem;font-weight:700;color:{_c_amber};">03</div>
            <div style="font-size:0.75rem;font-weight:500;color:{_c_amber};
              white-space:nowrap;">Reaction</div>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("questionnaire_form"):
        for section in sections:
            # Each section is its own independent card — siblings, not nested
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="qs-header {section['css_class']}">
                        <div class="qs-num">{section["number"]}</div>
                        <div>
                            <div class="qs-title">{section["title"]}</div>
                            <div class="qs-sub">{section["subtitle"]}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                for q in _QUESTIONS:
                    if q["section"] != section["key"]:
                        continue

                    st.markdown(
                        f"""
                        <div class="qs-q-row">
                            <span class="qs-q-badge" style="
                                color:{section['accent']};
                                background:{section['accent_bg']};
                                border-color:{section['accent_border']};">
                                {q["id"]}
                            </span>
                            <span class="qs-q-text">{q["text"]}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    saved_idx = st.session_state.get(
                        "questionnaire_answers", {}
                    ).get(q["id"])

                    # Indent radio options to align with the question text
                    # (badge ≈ 11% wide, remaining 89% starts under the text)
                    _spacer, _col = st.columns([0.11, 0.89])
                    with _col:
                        selected = st.radio(
                            label="",
                            options=q["options"],
                            index=saved_idx,
                            key=f"q_{q['id']}",
                            label_visibility="collapsed",
                        )

                    answers[q["id"]] = (
                        q["options"].index(selected) if selected is not None else None
                    )

        submitted = st.form_submit_button(
            "Calculate my profile",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if any(v is None for v in answers.values()):
            st.error("Please answer all questions before submitting.")
            return

        result = _compute_profile(answers)
        st.session_state["profile"] = result
        st.session_state["questionnaire_answers"] = answers
        st.session_state.pop("portfolio_data", None)
        # Reassessment complete — leave reassessment mode so the next rerun
        # shows the read-only state with the freshly computed profile.
        st.session_state["questionnaire_reassess"] = False
        # Persist so the profile survives a page reload (append-only row).
        _save_questionnaire_profile(
            st.session_state.get("session_token"), result, answers
        )

    if st.session_state.get("profile"):
        _render_profile_result_card(st.session_state["profile"])


# ---------------------------------------------------------------------------
# Page 2 -- Portfolio Dashboard
# ---------------------------------------------------------------------------

# Scoped CSS for the "profile required" gate empty-state. Injected once per
# gate render (only one gate shows at a time). Prefixed `pg-` to avoid clashes.
_GATE_CSS = """
<style>
@keyframes pg-orb-glow {
    0%,100% { box-shadow: 0 0 34px rgba(124,92,252,0.30),
                          inset 0 0 18px rgba(124,92,252,0.18); }
    50%     { box-shadow: 0 0 54px rgba(124,92,252,0.55),
                          inset 0 0 24px rgba(124,92,252,0.30); }
}
@keyframes pg-float {
    0%,100% { transform: translateY(0); }
    50%     { transform: translateY(-6px); }
}
@keyframes pg-rise {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
.pg-wrap {
    position: relative;
    max-width: 50rem;
    margin: 1.25rem auto 0;
    padding: 3rem 2.5rem 2.5rem;
    text-align: center;
    border-radius: 22px;
    border: 1px solid rgba(124,92,252,0.22);
    background:
        radial-gradient(120% 90% at 50% -10%, rgba(124,92,252,0.16) 0%, transparent 55%),
        linear-gradient(180deg, #111a2e 0%, #0c1322 100%);
    overflow: hidden;
    animation: pg-rise 0.5s cubic-bezier(0.16,1,0.3,1);
}
/* faint dot-grid texture */
.pg-wrap::before {
    content: "";
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(148,163,184,0.07) 1px, transparent 1px);
    background-size: 22px 22px;
    -webkit-mask-image: radial-gradient(120% 80% at 50% 0%, #000 30%, transparent 75%);
    mask-image: radial-gradient(120% 80% at 50% 0%, #000 30%, transparent 75%);
    pointer-events: none;
}
.pg-inner { position: relative; z-index: 1; }
.pg-orb {
    width: 84px; height: 84px; margin: 0 auto 1.4rem;
    border-radius: 24px;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.4rem; line-height: 1;
    background: radial-gradient(circle at 34% 28%,
        rgba(167,139,250,0.55) 0%, rgba(124,92,252,0.14) 62%, transparent 100%);
    border: 1.5px solid rgba(124,92,252,0.45);
    animation: pg-orb-glow 3.4s ease-in-out infinite,
               pg-float 5s ease-in-out infinite;
}
.pg-eyebrow {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: #a78bfa; margin-bottom: 0.7rem;
}
.pg-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.75rem; font-weight: 700;
    color: #f5f7fb; letter-spacing: -0.02em; line-height: 1.2;
    margin-bottom: 0.8rem;
}
.pg-body {
    font-size: 0.96rem; color: #9aa7bd; line-height: 1.7;
    max-width: 33rem; margin: 0 auto 1.9rem;
}
/* 3-step flow */
.pg-steps {
    display: flex; align-items: stretch; justify-content: center;
    gap: 0.5rem; flex-wrap: wrap; margin: 0 auto 1.9rem; max-width: 38rem;
}
.pg-step {
    flex: 1 1 0; min-width: 8.5rem;
    background: rgba(15,22,40,0.66);
    border: 1px solid #1e2640; border-radius: 13px;
    padding: 1rem 0.85rem;
    display: flex; flex-direction: column; align-items: center; gap: 0.45rem;
}
.pg-step-num {
    width: 1.7rem; height: 1.7rem; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: 'Space Grotesk', sans-serif; font-size: 0.78rem; font-weight: 700;
    color: #c4b5fd; background: rgba(124,92,252,0.16);
    border: 1px solid rgba(124,92,252,0.4);
}
.pg-step--active .pg-step-num {
    color: #0b1020; background: linear-gradient(135deg,#a78bfa,#7c5cfc);
    border-color: transparent;
}
.pg-step-label {
    font-family: 'Space Grotesk', sans-serif; font-size: 0.84rem;
    font-weight: 600; color: #e2e8f0;
}
.pg-step-sub { font-size: 0.72rem; color: #64748b; line-height: 1.4; }
.pg-step-arrow {
    display: flex; align-items: center; color: #3b475e;
    font-size: 1.1rem; flex: 0 0 auto;
}
.pg-chips {
    display: flex; align-items: center; justify-content: center;
    gap: 0.5rem; flex-wrap: wrap;
}
.pg-chip {
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-size: 0.74rem; font-weight: 500; color: #94a3b8;
    background: rgba(255,255,255,0.03);
    border: 1px solid #1e2640; border-radius: 999px;
    padding: 0.32rem 0.8rem;
}
.pg-chip svg { flex-shrink: 0; }
/* CTA button (Streamlit button wrapped in .pg-cta) */
.pg-cta { max-width: 22rem; margin: 1.6rem auto 0; }
.pg-cta .stButton > button {
    background: linear-gradient(135deg,
        rgba(124,92,252,0.96) 0%, rgba(109,40,217,0.96) 100%) !important;
    border: none !important; color: #fff !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important; font-size: 0.95rem !important;
    border-radius: 11px !important; padding: 0.7rem 1rem !important;
    box-shadow: 0 6px 22px rgba(124,92,252,0.4),
        inset 0 1px 0 rgba(255,255,255,0.18) !important;
    transition: transform 0.18s cubic-bezier(0.16,1,0.3,1),
        box-shadow 0.18s ease !important;
}
.pg-cta .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 30px rgba(124,92,252,0.55),
        inset 0 1px 0 rgba(255,255,255,0.22) !important;
}
</style>
"""

# Light-theme override for the profile-required gate. Appended AFTER _GATE_CSS
# (so it wins by source order) only when the light theme is active — flips the
# dark hero surfaces, step cards, chips and text to readable light values while
# keeping the purple orb glow and CTA gradient that read well on both themes.
_GATE_CSS_LIGHT = """
<style>
.pg-wrap {
    border: 1px solid #D8DEE9;
    background:
        radial-gradient(120% 90% at 50% -10%, rgba(124,77,255,0.10) 0%, transparent 55%),
        linear-gradient(180deg, #ffffff 0%, #f1f4fa 100%);
    box-shadow: 0 12px 32px rgba(15,23,42,0.08);
}
.pg-eyebrow { color: #6d4deb; }
.pg-title { color: #0f172a; }
.pg-body { color: #334155; }
.pg-step {
    background: #ffffff;
    border: 1px solid #D8DEE9;
    box-shadow: 0 4px 16px rgba(15,23,42,0.05);
}
.pg-step-num { color: #6d4deb; background: #EEE8FF; border-color: rgba(124,77,255,0.4); }
.pg-step--active .pg-step-num {
    color: #ffffff; background: linear-gradient(135deg,#8b6bff,#7c4dff);
    border-color: transparent;
}
.pg-step-label { color: #111827; }
.pg-step-sub { color: #64748B; }
.pg-step-arrow { color: #94A3B8; }
.pg-chip {
    color: #334155;
    background: #ffffff;
    border: 1px solid #D8DEE9;
}
</style>
"""

# Small inline icons for the feature chips.
_PG_ICON_CLOCK = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>'
)
_PG_ICON_LIST = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
    '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
    '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>'
)
_PG_ICON_SHIELD = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#a78bfa"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
)


def _render_profile_required_gate(
    title: str,
    subtitle: str,
    icon: str,
    body: str,
    key: str,
) -> None:
    """Empty-state shown when a page needs a risk profile that doesn't exist yet.

    Renders a premium "locked" hero: a glowing orb with the page icon, a short
    explanation of *why* the page is gated, a 3-step preview of the flow
    (questionnaire → profile → this page) and a styled call-to-action that
    routes to the questionnaire.
    """
    page_header(title, subtitle, icon=icon)
    st.markdown(_GATE_CSS, unsafe_allow_html=True)
    if is_light():
        st.markdown(_GATE_CSS_LIGHT, unsafe_allow_html=True)

    # The page the user is trying to reach becomes step 3's label.
    dest = title

    st.markdown(
        '<div class="pg-wrap"><div class="pg-inner">'
        f'<div class="pg-orb">{icon}</div>'
        '<div class="pg-eyebrow">Personalised · profile required</div>'
        '<div class="pg-title">Complete your questionnaire first</div>'
        f'<div class="pg-body">{body}</div>'
        # ── 3-step flow ──────────────────────────────────────────────
        '<div class="pg-steps">'
        '<div class="pg-step pg-step--active">'
        '<span class="pg-step-num">1</span>'
        '<span class="pg-step-label">Questionnaire</span>'
        '<span class="pg-step-sub">10 quick questions</span></div>'
        '<div class="pg-step-arrow">→</div>'
        '<div class="pg-step">'
        '<span class="pg-step-num">2</span>'
        '<span class="pg-step-label">Risk profile</span>'
        '<span class="pg-step-sub">Scored & explained</span></div>'
        '<div class="pg-step-arrow">→</div>'
        '<div class="pg-step">'
        '<span class="pg-step-num">3</span>'
        f'<span class="pg-step-label">{dest}</span>'
        '<span class="pg-step-sub">Unlocked for you</span></div>'
        '</div>'
        # ── feature chips ────────────────────────────────────────────
        '<div class="pg-chips">'
        f'<span class="pg-chip">{_PG_ICON_CLOCK}About 2 minutes</span>'
        f'<span class="pg-chip">{_PG_ICON_LIST}10 questions</span>'
        f'<span class="pg-chip">{_PG_ICON_SHIELD}Grable–Lytton scale</span>'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="pg-cta">', unsafe_allow_html=True)
    _, col_btn, _ = st.columns([1, 2, 1])
    with col_btn:
        if st.button(
            "Start the questionnaire  →",
            key=key,
            type="primary",
            use_container_width=True,
        ):
            st.session_state.active_page = "Questionnaire"
            st.query_params["page"] = "Questionnaire"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_portfolio() -> None:
    """
    Portfolio Dashboard with two tabs: HRP and Markowitz benchmark.

    Data source:
        Phase A (default): mock payload from backend/schemas/mock_data.py
        Phase B (live toggle on): ValidatedDataLoader + HRP + regime detector
    """
    _restore_persisted_profile()
    if not st.session_state.get("profile"):
        _render_profile_required_gate(
            "Portfolio Dashboard", "Personalised to your risk profile", "📊",
            "Your portfolio — the allocation, the statistics and the analysis — is "
            "built entirely from your risk profile. Answer the 10-question "
            "questionnaire and your personalised dashboard will appear here.",
            key="gate_dashboard_to_questionnaire",
        )
        return

    # Read profile first so we can use it in the header
    t = get_theme_tokens()
    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    confidence = profile_data.get("confidence", None)
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    page_header(
        "Portfolio Dashboard",
        f"HRP optimization · {profile_label.capitalize()} profile",
        icon="📊",
    )

    _ic_cluster = (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round">'
        '<path d="M12 6v6"/><path d="m12 12-7 6"/><path d="M12 12v6"/>'
        '<path d="m12 12 7 6"/>'
        '<circle cx="12" cy="4" r="2" fill="currentColor" stroke="none"/>'
        '<circle cx="5" cy="20" r="2" fill="currentColor" stroke="none"/>'
        '<circle cx="12" cy="20" r="2" fill="currentColor" stroke="none"/>'
        '<circle cx="19" cy="20" r="2" fill="currentColor" stroke="none"/></svg>'
    )
    _ic_pie = (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>'
        '<path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>'
    )
    _ic_scatter = (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polyline points="4 15 9 10 13 13 20 6"/>'
        '<circle cx="4" cy="15" r="1.5" fill="currentColor" stroke="none"/>'
        '<circle cx="9" cy="10" r="1.5" fill="currentColor" stroke="none"/>'
        '<circle cx="13" cy="13" r="1.5" fill="currentColor" stroke="none"/>'
        '<circle cx="20" cy="6" r="1.5" fill="currentColor" stroke="none"/></svg>'
    )
    _ic_lock = (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect width="18" height="11" x="3" y="11"'
        ' rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
    )
    _methods = [
        (_ic_cluster, "Correlation clustering",
         "Groups assets by similarity to improve diversification."),
        (_ic_pie, "Risk-balanced allocation",
         "Targets equal contribution to total portfolio risk."),
        (_ic_scatter, "Robust covariance",
         "Uses Ledoit-Wolf shrinkage for more stable estimates."),
        (_ic_lock, "Weight constraints",
         "5–40% per asset and 10–60% per cluster."),
    ]
    _circ = (
        f"width:2.6rem;height:2.6rem;flex-shrink:0;border-radius:50%;"
        f"background:{t['accent_soft']};border:1px solid {t['accent_border']};"
        f"color:{t['accent_text']};display:inline-flex;align-items:center;"
        f"justify-content:center;"
    )
    _mcard_bg = t["bg_surface"] if is_light() else "rgba(30,38,64,0.4)"
    _mcards = "".join(
        f'<div style="background:{_mcard_bg};border:1px solid {t["border"]};'
        f'border-radius:12px;padding:1rem;display:flex;gap:0.8rem;'
        f'align-items:flex-start;">'
        f'<div style="{_circ}">{ic}</div>'
        f'<div><div style="font-family:\'Space Grotesk\',sans-serif;'
        f'font-size:0.9rem;font-weight:600;color:{t["text_primary"]};'
        f'margin-bottom:0.25rem;">{ti}</div>'
        f'<div style="font-size:0.78rem;color:{t["text_secondary"]};line-height:1.5;">'
        f'{de}</div></div></div>'
        for ic, ti, de in _methods
    )
    _method_panel_bg = (
        "radial-gradient(circle at 1px 1px,rgba(124,77,255,0.08) 1px,"
        "transparent 0) 0 0/22px 22px,"
        "radial-gradient(130% 150% at 88% 12%,rgba(124,77,255,0.08) 0%,"
        "rgba(246,247,251,0) 55%),"
        "linear-gradient(135deg,#ffffff 0%,#f1f4fa 60%,#ffffff 100%)"
        if is_light() else
        "radial-gradient(circle at 1px 1px,rgba(124,92,252,0.10) 1px,"
        "transparent 0) 0 0/22px 22px,"
        "radial-gradient(130% 150% at 88% 12%,rgba(124,92,252,0.12) 0%,"
        "rgba(13,18,32,0) 55%),"
        "linear-gradient(135deg,#0d1220 0%,#11162a 60%,#0d1220 100%)"
    )
    st.markdown(
        f'<div style="border:1px solid {t["border"]};border-radius:14px;'
        f'padding:1.25rem 1.5rem;margin-bottom:1.25rem;'
        f'background:{_method_panel_bg};">'
        f'<div style="margin-bottom:0.9rem;">'
        f'<span style="font-family:\'Space Grotesk\',sans-serif;font-size:1.15rem;'
        f'font-weight:700;color:{t["text_primary"]};">HRP Methodology</span></div>'
        f'<div style="display:grid;'
        f'grid-template-columns:repeat(auto-fit,minmax(230px,1fr));'
        f'gap:0.85rem;">{_mcards}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Profile hero strip ───────────────────────────────────────────────────
    _PROFILE_META = {
        "CONSERVATIVE": {
            "icon": "🛡️", "color": "#0dcfb0", "label": "Conservative",
            "desc": (
                "Capital-preservation focus with low-volatility, income-oriented "
                "exposure across bonds, cash, and select alternatives."
            ),
        },
        "MODERATE": {
            "icon": "⚖️", "color": "#7c5cfc", "label": "Moderate",
            "desc": (
                "Balanced HRP allocation with diversified exposure across "
                "equity, bonds, alternatives, and cash."
            ),
        },
        "AGGRESSIVE": {
            "icon": "🚀", "color": "#f87171", "label": "Aggressive",
            "desc": (
                "Growth-oriented HRP allocation with higher equity exposure, "
                "accepting greater volatility for long-term return potential."
            ),
        },
    }
    pm = _PROFILE_META.get(profile_label, _PROFILE_META["MODERATE"])
    color = pm["color"]

    # Pre-compute optional confidence inline text
    conf_inline = (
        f'&nbsp;&middot;&nbsp;'
        f'<span style="color:{color};font-weight:600;">'
        f'Confidence {confidence:.0%}</span>'
        if confidence is not None else ""
    )

    # Small badges row
    _badge_style = (
        f'font-size:0.72rem;font-weight:600;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:{color}90;'
        f'background:{color}15;border:1px solid {color}30;'
        f'border-radius:6px;padding:0.2rem 0.55rem;'
    )
    badges_html = "".join(
        f'<span style="{_badge_style}">{b}</span>'
        for b in ["HRP", pm["label"], "Educational prototype"]
    )

    # Single self-contained block — no leading indentation that would
    # trigger Markdown's 4-space code-block rule
    st.markdown(
        f'<div style="display:flex;align-items:flex-start;gap:1rem;'
        f'background:linear-gradient(135deg,{color}12,{color}06);'
        f'border:1px solid {color}35;border-radius:12px;'
        f'padding:0.85rem 1.25rem;margin-bottom:1.25rem;">'
        f'<div style="font-size:1.6rem;flex-shrink:0;margin-top:0.1rem;">{pm["icon"]}</div>'
        f'<div style="min-width:0;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.05rem;'
        f'font-weight:700;color:{color};letter-spacing:0.03em;margin-bottom:0.25rem;">'
        f'{pm["label"]} Investor</div>'
        f'<div style="font-size:0.82rem;color:{t["text_secondary"]};'
        f'margin-bottom:0.5rem;line-height:1.5;">'
        f'{pm["desc"]}{conf_inline}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:0.35rem;">{badges_html}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # The dashboard always runs on live market data. Mock data is kept only as
    # an automatic fallback if the network or optimizer is unreachable, so the
    # app never breaks mid-demo — there is no user-facing data-source toggle.
    portfolio = st.session_state.get("portfolio_data", {})
    cached_label = st.session_state.get("portfolio_profile", "")

    if not portfolio or cached_label != profile_label:
        with st.spinner("Fetching live market data and running the HRP optimizer…"):
            try:
                portfolio = _run_live_optimization(profile_label)
            except Exception as exc:
                # Keep the dashboard usable if live prices can't be reached.
                st.warning(
                    f"Live market data is temporarily unavailable ({exc}). "
                    "Showing a reference allocation until prices can be fetched again."
                )
                portfolio = _mock_optimization(profile_key)
            st.session_state["portfolio_data"] = portfolio
            st.session_state["portfolio_profile"] = profile_label
            st.session_state["recommendation_id"] = portfolio["recommendation_id"]

    # Discreet data-source status line (no toggle — live is always preferred).
    if portfolio.get("source") == "live":
        st.markdown(
            f'<div style="font-size:0.8rem;color:{t["text_muted"]};margin:-0.2rem 0 0.3rem;">'
            f'<span style="color:#0dcfb0;">●</span> Live market data · prices via yfinance'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="font-size:0.8rem;color:{t["text_muted"]};margin:-0.2rem 0 0.3rem;">'
            f'<span style="color:#f59e0b;">●</span> Reference allocation · '
            f'live prices momentarily unavailable'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Show a red banner if the regime detector flagged HIGH_STRESS
    regime = portfolio.get("stress_regime", "NORMAL")
    if regime == "HIGH_STRESS":
        avg_corr = portfolio.get("avg_correlation", 0.0)
        st.error(
            f"HIGH STRESS REGIME -- Average pairwise correlation: "
            f"{avg_corr:.2f} (threshold: 0.75). "
            "Portfolio adjusted to minimum-variance ERC allocation."
        )

    st.markdown("---")

    _render_hrp_tab(portfolio)

    # EU Investor Note -- mandatory on every portfolio page (EU Awareness Rule 9)
    st.markdown("---")
    render_eu_note()


def _render_resilience_strip(profile_label: str) -> None:
    """
    Compact "crisis resilience" strip backed by REAL backtest results.

    Reads backtest_summary_{profile}.json and shows the HRP historical maximum
    drawdown across three stress scenarios, with the improvement vs the
    Mean-Variance benchmark. A button links to the full Backtesting page so we
    do not duplicate its equity-curve charts here.
    """
    summary_file = _BACKTEST_DIR / f"backtest_summary_{profile_label.lower()}.json"
    if not summary_file.exists():
        summary_file = _BACKTEST_DIR / "backtest_summary_moderate.json"
    if not summary_file.exists():
        st.caption("Backtest data unavailable — run scripts/run_backtest.py.")
        return

    with open(summary_file) as fh:
        summary = json.load(fh)

    _SHORT = {
        "gfc_2008": "GFC 2008",
        "covid_2020": "COVID 2020",
        "rate_hike_2022": "Rate Hike 2022",
    }

    t = get_theme_tokens()
    cards_html = '<div style="display:flex;gap:0.75rem;margin-bottom:1rem;">'
    for key, short in _SHORT.items():
        scen = summary.get(key)
        if not scen:
            continue
        hrp_dd = scen["strategies"]["HRP"]["max_drawdown"]
        mv_dd = scen["strategies"]["MV"]["max_drawdown"]
        # Both negative; HRP less negative => shallower drawdown => improvement > 0
        improvement = (hrp_dd - mv_dd) * 100
        better = improvement > 0
        delta_color = "#0dcfb0" if better else "#f87171"
        delta_sign = "+" if better else ""
        cards_html += (
            f'<div style="flex:1;background:{t["bg_card"]};border:1px solid {t["border"]};'
            f'border-radius:12px;padding:0.9rem 1rem;box-shadow:{t["shadow"]};">'
            f'<div style="font-size:0.72rem;font-weight:600;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:0.5rem;">{short}</div>'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.5rem;'
            f'font-weight:700;color:{t["text_primary"]};line-height:1;">{hrp_dd*100:.1f}%</div>'
            f'<div style="font-size:0.74rem;color:{t["text_muted"]};margin-top:0.35rem;">'
            f'HRP max drawdown</div>'
            f'<div style="font-size:0.72rem;color:{delta_color};font-weight:600;'
            f'margin-top:0.45rem;">{delta_sign}{improvement:.1f} pp vs MV</div>'
            f'</div>'
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    if st.button("View full backtesting  →", key="hrp_to_backtest"):
        st.session_state.active_page = "Backtesting"
        st.query_params["page"] = "Backtesting"
        st.rerun()


def _render_cluster_view(portfolio: dict, weights: dict[str, float]) -> None:
    """
    Honest cluster structure view driven by the Ground Truth payload.

    Replaces the previous dendrogram, whose pairwise correlation matrix was
    fabricated (0.70 / 0.10). Here every number — weight, intra-cluster
    correlation, cluster volatility — comes from cluster_structure when present,
    with a graceful fallback for the live path.
    """
    t = get_theme_tokens()
    cs = portfolio.get("cluster_structure")

    # name, attribute, colour, plain-language description, member fallback
    _CLUSTER_DEFS = [
        ("Risk Assets", "cluster_A_risk_assets", "#7c5cfc",
         "Stocks — the growth engine. Higher long-term reward, bigger swings.",
         ["CSPX.L", "EFA"]),
        ("Real Assets", "cluster_B_real_assets", "#0dcfb0",
         "Gold & property — inflation hedges that move on their own rhythm.",
         ["GLD", "VNQ"]),
        ("Safe Haven", "cluster_C_safe_haven", "#f59e0b",
         "High-quality bonds — ballast that cushions equity downturns.",
         ["AGGH.MI", "TLT", "TIP"]),
        ("Cash", "cluster_D_cash", "#3b82f6",
         "Cash-like — maximum stability and ready liquidity.",
         ["XEON.MI"]),
    ]

    def _diversification(corr: float | None) -> tuple[str, str]:
        """Plain-language label + colour from intra-cluster correlation."""
        if corr is None:
            return "Single asset", "#64748b"
        if corr < 0.30:
            return "Well diversified", "#0dcfb0"
        if corr < 0.60:
            return "Moderately diversified", "#f59e0b"
        return "Moves together", "#f87171"

    def _risk_level(vol: float | None) -> tuple[str, str]:
        """Plain-language risk label + colour from annualised volatility."""
        if vol is None:
            return "—", "#64748b"
        if vol < 0.06:
            return "Low", "#0dcfb0"
        if vol < 0.14:
            return "Medium", "#f59e0b"
        return "High", "#f87171"

    for name, attr, color, desc, fallback_members in _CLUSTER_DEFS:
        cl = getattr(cs, attr, None) if cs is not None else None
        members = list(cl.members) if cl is not None else fallback_members
        members = [m for m in members if m in weights] or members
        weight = (
            cl.total_weight if cl is not None
            else sum(weights.get(m, 0.0) for m in members)
        )
        corr = cl.intra_cluster_correlation if cl is not None else None
        vol = cl.cluster_volatility if cl is not None else None

        div_label, div_color = _diversification(corr)
        risk_label, risk_color = _risk_level(vol)
        corr_note = f"ρ {corr:.2f}" if corr is not None else "n/a"
        vol_note = f"{vol*100:.1f}% vol" if vol is not None else ""

        # Member chips use the plain asset name, ticker kept as a small tag.
        chips = "".join(
            f'<span style="display:inline-block;background:{t["bg_surface_alt"]};'
            f'border:1px solid {t["border"]};border-radius:6px;padding:0.12rem 0.5rem;'
            f'font-size:0.74rem;color:{t["text_secondary"]};margin:0 0.3rem 0.3rem 0;">'
            f'{_TICKER_DISPLAY_NAME.get(m, m)}</span>'
            for m in members
        )

        st.markdown(
            f'<div style="background:{t["bg_card"]};border:1px solid {t["border"]};'
            f'border-left:4px solid {color};border-radius:12px;'
            f'padding:1rem 1.2rem;margin-bottom:0.75rem;display:flex;'
            f'align-items:flex-start;gap:1.25rem;flex-wrap:wrap;box-shadow:{t["shadow"]};">'
            # Left: name + description + chips
            f'<div style="flex:2.4;min-width:240px;">'
            f'<div style="display:flex;align-items:center;gap:0.5rem;'
            f'margin-bottom:0.3rem;">'
            f'<span style="width:9px;height:9px;border-radius:50%;'
            f'background:{color};flex-shrink:0;"></span>'
            f'<span style="font-family:\'Space Grotesk\',sans-serif;'
            f'font-size:1.02rem;font-weight:600;color:{color};">{name}</span></div>'
            f'<div style="font-size:0.86rem;color:{t["text_secondary"]};line-height:1.55;'
            f'margin-bottom:0.6rem;">{desc}</div>'
            f'<div>{chips}</div></div>'
            # Middle: diversification + risk, plain words with the number small
            f'<div style="flex:1.5;min-width:170px;">'
            f'<div style="font-size:0.72rem;font-weight:600;letter-spacing:0.06em;'
            f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:0.15rem;">'
            f'Diversification</div>'
            f'<div style="font-size:0.95rem;font-weight:600;color:{div_color};'
            f'margin-bottom:0.7rem;">{div_label}'
            f'<span style="font-size:0.74rem;color:{t["text_muted"]};font-weight:400;'
            f'margin-left:0.4rem;">{corr_note}</span></div>'
            f'<div style="font-size:0.72rem;font-weight:600;letter-spacing:0.06em;'
            f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:0.15rem;">'
            f'Risk level</div>'
            f'<div style="font-size:0.95rem;font-weight:600;color:{risk_color};">'
            f'{risk_label}'
            f'<span style="font-size:0.74rem;color:{t["text_muted"]};font-weight:400;'
            f'margin-left:0.4rem;">{vol_note}</span></div></div>'
            # Right: weight
            f'<div style="flex:0.9;min-width:110px;text-align:right;">'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.75rem;'
            f'font-weight:700;color:{t["text_primary"]};line-height:1;">{weight*100:.0f}%</div>'
            f'<div style="font-size:0.72rem;color:{t["text_muted"]};text-transform:uppercase;'
            f'letter-spacing:0.06em;margin-top:0.25rem;">of portfolio</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Dashboard display constants (HRP cluster colours and profile palette)
# ---------------------------------------------------------------------------

_HRP_TICKER_CLUSTER: dict[str, str] = {
    "CSPX.L":  "Equity",
    "EFA":     "Equity",
    "GLD":     "Alternatives",
    "VNQ":     "Alternatives",
    "AGGH.MI": "Bonds",
    "TLT":     "Bonds",
    "TIP":     "Bonds",
    "XEON.MI": "Cash",
}

_HRP_CLUSTER_COLOR: dict[str, str] = {
    "Equity":       "#7c5cfc",
    "Alternatives": "#f59e0b",
    "Bonds":        "#0dcfb0",
    "Cash":         "#3b82f6",
}

_HRP_CLUSTER_BG: dict[str, str] = {
    "Equity":       "rgba(124,92,252,0.15)",
    "Alternatives": "rgba(245,158,11,0.15)",
    "Bonds":        "rgba(13,207,176,0.15)",
    "Cash":         "rgba(59,130,246,0.15)",
}

# Plain-language asset names so the allocation table reads clearly for a
# non-specialist. The raw ticker is still shown, but as a small subtitle.
_TICKER_DISPLAY_NAME: dict[str, str] = {
    "CSPX.L":  "US Large-Cap Equity",
    "EFA":     "Developed Markets ex-US Equity",
    "GLD":     "Gold",
    "VNQ":     "US Real Estate",
    "AGGH.MI": "Euro Aggregate Bonds",
    "TLT":     "US Long-Term Treasuries",
    "TIP":     "US Inflation-Linked Bonds",
    "XEON.MI": "Euro Cash (Overnight)",
}


def _render_allocation_table(
    weights: dict[str, float],
    risk_contributions: dict[str, float],
) -> None:
    """
    Readable allocation table: plain asset name with the ticker as a small
    subtitle, an asset-class colour dot, a proportional weight bar, and the
    risk contribution. Replaces the ticker-first st.dataframe (which also
    carried a UCITS column) so a non-specialist can read it at a glance.
    """
    t = get_theme_tokens()
    _bar_track = t["bg_surface_alt"] if is_light() else "#161d30"
    items = sorted(weights.items(), key=lambda kv: -kv[1])
    max_w = max((w for _, w in items), default=1.0) or 1.0

    header = (
        f'<div style="display:flex;align-items:center;padding:0 0.4rem 0.6rem;'
        f'border-bottom:1px solid {t["border"]};margin-bottom:0.1rem;">'
        f'<div style="flex:1.7;font-size:0.72rem;font-weight:600;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:{t["text_muted"]};">Asset</div>'
        f'<div style="flex:1.5;font-size:0.72rem;font-weight:600;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:{t["text_muted"]};">Weight</div>'
        f'<div style="flex:0.8;font-size:0.72rem;font-weight:600;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:{t["text_muted"]};text-align:right;">Risk Contr.</div>'
        f'</div>'
    )

    body = ""
    for ticker, w in items:
        cls = _HRP_TICKER_CLUSTER.get(ticker, "Other")
        color = _HRP_CLUSTER_COLOR.get(cls, "#64748b")
        name = _TICKER_DISPLAY_NAME.get(ticker, ticker)
        rc = risk_contributions.get(ticker, 0.0)
        bar_pct = max(4.0, w / max_w * 100.0)
        body += (
            f'<div style="display:flex;align-items:center;padding:0.62rem 0.4rem;'
            f'border-bottom:1px solid {t["border_soft"]};">'
            # Asset name + ticker subtitle
            f'<div style="flex:1.7;display:flex;align-items:center;gap:0.6rem;">'
            f'<span style="width:9px;height:9px;border-radius:50%;background:{color};'
            f'flex-shrink:0;"></span>'
            f'<div style="min-width:0;">'
            f'<div style="font-size:0.9rem;font-weight:600;color:{t["text_primary"]};'
            f'line-height:1.25;">{name}</div>'
            f'<div style="font-size:0.72rem;color:{t["text_muted"]};letter-spacing:0.02em;'
            f'font-family:\'Space Grotesk\',sans-serif;">{ticker}</div>'
            f'</div></div>'
            # Weight bar + value
            f'<div style="flex:1.5;display:flex;align-items:center;gap:0.55rem;'
            f'padding-right:0.8rem;">'
            f'<div style="flex:1;height:7px;background:{_bar_track};border-radius:4px;'
            f'overflow:hidden;">'
            f'<div style="width:{bar_pct:.1f}%;height:100%;background:{color};'
            f'border-radius:4px;"></div></div>'
            f'<span style="font-size:0.9rem;font-weight:600;color:{t["text_primary"]};'
            f'font-family:\'Space Grotesk\',sans-serif;min-width:3rem;'
            f'text-align:right;">{w*100:.1f}%</span>'
            f'</div>'
            # Risk contribution
            f'<div style="flex:0.8;font-size:0.85rem;color:{t["text_secondary"]};text-align:right;'
            f'font-family:\'Space Grotesk\',sans-serif;">{rc*100:.1f}%</div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:12px;'
        f'padding:0.9rem 1rem;box-shadow:{t["shadow"]};">' + header + body + '</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# ETF explorer ("What do these tickers mean?" section)
# Static per-ticker reference data. Live prices come from yfinance; everything
# below is curated metadata used by _render_etf_explorer().
# ---------------------------------------------------------------------------

# Cluster -> dot colour for the ticker selector pills
CLUSTER_COLORS: dict[str, str] = {
    "risk_assets": "#185FA5",
    "safe_haven":  "#0F6E56",
    "real_assets": "#BA7517",
    "cash":        "#888780",
}

ETF_METADATA: dict[str, dict] = {
    "CSPX.L": {
        "full_name": "iShares Core S&P 500 UCITS ETF",
        "issuer": "iShares (BlackRock)",
        "category": "Large Cap US Equity",
        "inception": "2010",
        "distribution": "Accumulating",
        "ter": "0.07%",
        "aum": "$52.1B",
        "description": (
            "Tracks the S&P 500 Index — 500 of the largest US companies across "
            "all major sectors. Physically replicated, UCITS-compliant, domiciled "
            "in Ireland. Same economic exposure as SPY but wrapped for European "
            "regulatory compliance. Primary equity position in the HRP portfolio."
        ),
        "key_stats": {
            "P/E ratio (underlying)": "22.4x",
            "P/B ratio": "4.1x",
            "Dividend yield": "1.31%",
            "Number of holdings": "503",
            "Weight in HRP portfolio": "18.2%",
        },
        "morningstar": 4,
        "esg": {"environmental": 6, "social": 5, "governance": 7, "total": 18, "risk": 4},
        "analyst": {"buy": 72, "hold": 20, "sell": 8},
        "financials": [
            {"label": "AUM", "value": "$52.1B",
             "trend": [3, 4, 4, 5, 5, 5, 5]},
            {"label": "Avg daily volume", "value": "$320M",
             "trend": [2, 3, 3, 4, 4, 5, 5]},
            {"label": "TER (expense ratio)", "value": "0.07%",
             "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "+23.1%",
             "trend": [2, 3, 3, 4, 5, 5, 5]},
            {"label": "Tracking error (ann.)", "value": "0.03%",
             "trend": [5, 5, 5, 5, 5, 5, 5]},
        ],
    },
    "EFA": {
        "full_name": "iShares MSCI EAFE ETF",
        "issuer": "iShares (BlackRock)",
        "category": "Developed Markets Ex-US",
        "inception": "2001",
        "distribution": "Distributing",
        "ter": "0.32%",
        "aum": "$48.3B",
        "description": (
            "Tracks the MSCI EAFE Index (Europe, Australasia, Far East) — ~900 "
            "stocks across 21 developed markets outside the US and Canada. Major "
            "exposures: Japan, UK, France, Switzerland, Germany. No UCITS equivalent "
            "with equivalent yfinance coverage; retained as-is in the v3.1 universe."
        ),
        "key_stats": {
            "P/E ratio (underlying)": "14.8x",
            "P/B ratio": "1.7x",
            "Dividend yield": "3.12%",
            "Number of holdings": "~900",
            "Weight in HRP portfolio": "14.8%",
        },
        "morningstar": 3,
        "esg": {"environmental": 5, "social": 6, "governance": 6, "total": 17, "risk": 3},
        "analyst": {"buy": 61, "hold": 28, "sell": 11},
        "financials": [
            {"label": "AUM", "value": "$48.3B", "trend": [4, 4, 4, 4, 4, 4, 4]},
            {"label": "Avg daily volume", "value": "$890M", "trend": [4, 4, 5, 5, 5, 5, 5]},
            {"label": "TER (expense ratio)", "value": "0.32%", "trend": [4, 4, 4, 4, 4, 4, 4]},
            {"label": "12m return (NAV)", "value": "+9.8%", "trend": [2, 2, 3, 3, 3, 4, 4]},
            {"label": "Tracking error (ann.)", "value": "0.18%", "trend": [4, 4, 4, 4, 4, 4, 4]},
        ],
    },
    "AGGH.MI": {
        "full_name": "iShares Core € Aggregate Bond UCITS ETF",
        "issuer": "iShares (BlackRock)",
        "category": "EUR Aggregate Bond",
        "inception": "2017",
        "distribution": "Accumulating",
        "ter": "0.10%",
        "aum": "€9.8B",
        "description": (
            "Tracks the Bloomberg Euro Aggregate Bond Index — EUR-denominated "
            "investment-grade bonds (government, corporate, securitised). The main "
            "fixed income position for EU investors: reduces FX risk vs USD-denominated "
            "bonds while maintaining broad duration exposure across the eurozone."
        ),
        "key_stats": {
            "Yield to maturity": "3.42%",
            "Modified duration": "6.8 yrs",
            "Credit quality (avg)": "AA-",
            "Number of holdings": "~2,400",
            "Weight in HRP portfolio": "12.1%",
        },
        "morningstar": 4,
        "esg": {"environmental": 7, "social": 6, "governance": 8, "total": 21, "risk": 5},
        "analyst": {"buy": 55, "hold": 35, "sell": 10},
        "financials": [
            {"label": "AUM", "value": "€9.8B", "trend": [3, 3, 4, 4, 4, 4, 5]},
            {"label": "Avg daily volume", "value": "€42M", "trend": [2, 3, 3, 3, 4, 4, 4]},
            {"label": "TER (expense ratio)", "value": "0.10%", "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "+2.1%", "trend": [1, 1, 2, 2, 3, 3, 4]},
            {"label": "Modified duration", "value": "6.8 yrs", "trend": [3, 3, 3, 3, 3, 3, 3]},
        ],
    },
    "TLT": {
        "full_name": "iShares 20+ Year Treasury Bond ETF",
        "issuer": "iShares (BlackRock)",
        "category": "US Long-Duration Treasuries",
        "inception": "2002",
        "distribution": "Distributing",
        "ter": "0.15%",
        "aum": "$58.2B",
        "description": (
            "US Treasury bonds with 20+ year maturities. The quintessential "
            "long-duration flight-to-quality instrument: prices rise when yields "
            "fall, especially in risk-off environments. Kept as USD-priced duration "
            "anchor for stress scenarios in the HRP portfolio."
        ),
        "key_stats": {
            "Yield to maturity": "4.81%",
            "Modified duration": "17.1 yrs",
            "SEC 30-day yield": "4.76%",
            "Number of holdings": "~40",
            "Weight in HRP portfolio": "10.4%",
        },
        "morningstar": 2,
        "esg": {"environmental": 9, "social": 8, "governance": 9, "total": 26, "risk": 5},
        "analyst": {"buy": 38, "hold": 40, "sell": 22},
        "financials": [
            {"label": "AUM", "value": "$58.2B", "trend": [5, 5, 5, 5, 5, 4, 3]},
            {"label": "Avg daily volume", "value": "$1.8B", "trend": [4, 5, 5, 5, 5, 5, 5]},
            {"label": "TER (expense ratio)", "value": "0.15%", "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "-4.2%", "trend": [4, 3, 3, 2, 2, 1, 2]},
            {"label": "Modified duration", "value": "17.1 yrs", "trend": [3, 3, 3, 3, 3, 3, 3]},
        ],
    },
    "GLD": {
        "full_name": "SPDR Gold Shares",
        "issuer": "State Street (SPDR)",
        "category": "Physical Gold",
        "inception": "2004",
        "distribution": "Non-distributing",
        "ter": "0.40%",
        "aum": "$62.4B",
        "description": (
            "Physically-backed gold ETF — each share ≈ 1/10 troy oz held in HSBC "
            "vaults in London. Gold is USD-priced globally; no UCITS equivalent changes "
            "the economic exposure. Acts as inflation hedge, tail-risk hedge, and "
            "currency diversifier in the HRP portfolio."
        ),
        "key_stats": {
            "Gold spot price": "$3,368/oz",
            "Physical gold held": "876 tonnes",
            "Custody bank": "HSBC London",
            "Correlation vs S&P500": "+0.04",
            "Weight in HRP portfolio": "13.7%",
        },
        "morningstar": 3,
        "esg": {"environmental": 4, "social": 5, "governance": 6, "total": 15, "risk": 3},
        "analyst": {"buy": 65, "hold": 27, "sell": 8},
        "financials": [
            {"label": "AUM", "value": "$62.4B", "trend": [3, 3, 4, 4, 5, 5, 5]},
            {"label": "Avg daily volume", "value": "$1.2B", "trend": [3, 3, 4, 4, 5, 5, 5]},
            {"label": "TER (expense ratio)", "value": "0.40%", "trend": [3, 3, 3, 3, 3, 3, 3]},
            {"label": "12m return (NAV)", "value": "+28.4%", "trend": [2, 2, 3, 4, 5, 5, 5]},
            {"label": "Gold held per share", "value": "0.0929 oz", "trend": [3, 3, 3, 3, 3, 3, 3]},
        ],
    },
    "VNQ": {
        "full_name": "Vanguard Real Estate ETF",
        "issuer": "Vanguard",
        "category": "US Real Estate / REITs",
        "inception": "2004",
        "distribution": "Distributing",
        "ter": "0.13%",
        "aum": "$35.1B",
        "description": (
            "Tracks the MSCI US Investable Market Real Estate 25/50 Index — US REITs "
            "across residential, commercial, industrial, and specialty segments. Provides "
            "inflation linkage via real asset rents and mandated 90%+ dividend distribution. "
            "Intentionally US-focused; EU REIT markets have lower liquidity and shorter histories."
        ),
        "key_stats": {
            "P/FFO ratio": "18.2x",
            "Dividend yield": "4.12%",
            "Largest holding": "Prologis 7.1%",
            "Number of holdings": "162",
            "Weight in HRP portfolio": "9.8%",
        },
        "morningstar": 3,
        "esg": {"environmental": 5, "social": 4, "governance": 6, "total": 15, "risk": 3},
        "analyst": {"buy": 52, "hold": 33, "sell": 15},
        "financials": [
            {"label": "AUM", "value": "$35.1B", "trend": [4, 4, 4, 4, 4, 3, 3]},
            {"label": "Avg daily volume", "value": "$420M", "trend": [3, 4, 4, 4, 4, 4, 4]},
            {"label": "TER (expense ratio)", "value": "0.13%", "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "+4.8%", "trend": [3, 2, 2, 3, 3, 3, 4]},
            {"label": "Distribution yield", "value": "4.12%", "trend": [4, 4, 4, 4, 4, 4, 4]},
        ],
    },
    "TIP": {
        "full_name": "iShares TIPS Bond ETF",
        "issuer": "iShares (BlackRock)",
        "category": "US Inflation-Linked Bonds",
        "inception": "2003",
        "distribution": "Distributing",
        "ter": "0.19%",
        "aum": "$18.6B",
        "description": (
            "US Treasury Inflation-Protected Securities (TIPS) across the full maturity "
            "range. Principal and interest adjust with CPI, providing direct inflation "
            "breakeven exposure. Retained alongside AGGH.MI to capture the US inflation "
            "breakeven spread — a distinct risk factor from EUR aggregate duration."
        ),
        "key_stats": {
            "Real yield (10y TIPS)": "1.82%",
            "Modified duration": "6.2 yrs",
            "CPI linkage": "US CPI-U",
            "Number of holdings": "49",
            "Weight in HRP portfolio": "10.1%",
        },
        "morningstar": 3,
        "esg": {"environmental": 9, "social": 8, "governance": 9, "total": 26, "risk": 5},
        "analyst": {"buy": 48, "hold": 42, "sell": 10},
        "financials": [
            {"label": "AUM", "value": "$18.6B", "trend": [3, 3, 4, 4, 4, 3, 3]},
            {"label": "Avg daily volume", "value": "$195M", "trend": [3, 3, 3, 3, 3, 3, 3]},
            {"label": "TER (expense ratio)", "value": "0.19%", "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "+3.8%", "trend": [2, 2, 3, 3, 4, 4, 4]},
            {"label": "Inflation breakeven (5y)", "value": "2.34%", "trend": [3, 3, 3, 4, 4, 4, 4]},
        ],
    },
    "XEON.MI": {
        "full_name": "Xtrackers EUR Overnight Rate Swap UCITS ETF",
        "issuer": "Xtrackers (DWS)",
        "category": "EUR Money Market / Overnight",
        "inception": "2007",
        "distribution": "Accumulating",
        "ter": "0.10%",
        "aum": "€6.2B",
        "description": (
            "Tracks the ESTER overnight rate via total return swap — EUR equivalent of "
            "a T-Bill money market fund in ETF form. Replaces USD BIL in the v3.1 universe "
            "to avoid EUR/USD FX risk for EU investors. Minimal duration, minimal credit risk, "
            "daily compounding of the ECB overnight rate."
        ),
        "key_stats": {
            "Effective duration": "< 1 day",
            "Credit risk": "Minimal (swap)",
            "ESTER reference rate": "2.15%",
            "Replication method": "Synthetic (swap)",
            "Weight in HRP portfolio": "10.9%",
        },
        "morningstar": 5,
        "esg": {"environmental": 8, "social": 7, "governance": 9, "total": 24, "risk": 5},
        "analyst": {"buy": 80, "hold": 18, "sell": 2},
        "financials": [
            {"label": "AUM", "value": "€6.2B", "trend": [2, 2, 3, 4, 5, 5, 5]},
            {"label": "Avg daily volume", "value": "€18M", "trend": [2, 3, 3, 4, 4, 5, 5]},
            {"label": "TER (expense ratio)", "value": "0.10%", "trend": [5, 5, 5, 5, 5, 5, 5]},
            {"label": "12m return (NAV)", "value": "+3.9%", "trend": [3, 3, 4, 4, 4, 5, 5]},
            {"label": "ESTER rate (current)", "value": "2.15%", "trend": [5, 5, 5, 5, 5, 4, 3]},
        ],
    },
}


def _section_header(number: str, title: str) -> None:
    t = get_theme_tokens()
    prefix = f"{number}. " if number else ""
    st.markdown(
        f'<div style="border-left:3px solid {t["accent"]};'
        f'padding-left:0.9rem;margin-bottom:0.8rem;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;'
        f'font-size:1.2rem;font-weight:700;color:{t["text_primary"]};letter-spacing:-0.01em;">'
        f'{prefix}{title}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _section_desc(text: str) -> None:
    t = get_theme_tokens()
    st.markdown(
        f'<div style="font-size:0.95rem;color:{t["text_secondary"]};line-height:1.6;'
        f'margin-bottom:1.35rem;">{text}</div>',
        unsafe_allow_html=True,
    )


def _v_spacer(rem: float = 2.0) -> None:
    st.markdown(f'<div style="height:{rem}rem"></div>', unsafe_allow_html=True)


def _kpi_cards(items: list[dict]) -> None:
    """Render a row of styled KPI cards.

    Replaces the anonymous, colourless ``st.metric`` boxes with branded cards:
    each has a coloured top accent, an icon chip, an uppercase label, a large
    Space-Grotesk value, and a one-line hint — so the headline portfolio
    statistics read as a deliberate, scannable summary rather than as filler.

    Each item dict: {label, value, accent, bg, icon (inner SVG markup), hint}.
    """
    t = get_theme_tokens()
    card_bg = (
        t["bg_surface"] if is_light()
        else "linear-gradient(160deg,rgba(30,38,64,0.55),rgba(17,24,39,0.55))"
    )
    cards = ""
    for it in items:
        accent = it["accent"]
        cards += (
            f'<div style="flex:1 1 140px;min-width:140px;'
            f'background:{card_bg};border:1px solid {t["border"]};'
            f'border-top:2px solid {accent};border-radius:14px;'
            f'padding:1rem 1.1rem;box-shadow:{t["shadow"]};">'
            f'<div style="width:2.1rem;height:2.1rem;border-radius:9px;'
            f'background:{it["bg"]};border:1px solid {accent}55;'
            f'display:flex;align-items:center;justify-content:center;'
            f'margin-bottom:0.7rem;">'
            f'<svg width="16" height="16" viewBox="0 0 18 18" fill="none" '
            f'stroke="{accent}" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{it["icon"]}</svg></div>'
            f'<div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:{t["text_muted"]};margin-bottom:0.3rem;">'
            f'{it["label"]}</div>'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;'
            f'font-size:1.6rem;font-weight:700;color:{t["text_primary"]};line-height:1;">'
            f'{it["value"]}</div>'
            f'<div style="font-size:0.7rem;color:{t["text_muted"]};margin-top:0.35rem;">'
            f'{it["hint"]}</div></div>'
        )
    st.markdown(
        f'<div style="display:flex;gap:0.85rem;flex-wrap:wrap;'
        f'margin-bottom:0.5rem;">{cards}</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_price_history(ticker: str) -> pd.DataFrame:
    """
    Download 2 years of daily prices for a single ticker via yfinance.
    Cached for 1 hour (keyed on the ticker symbol) so flipping between
    pills or reruns does not re-hit the network.
    """
    df = yf.download(
        ticker,
        period="2y",
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    return df


def _close_series(df: pd.DataFrame) -> "pd.Series":
    """Extract a flat Close price Series from a yfinance download frame."""
    close = df["Close"]
    # Single-ticker downloads can return a MultiIndex column frame
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()


def _slice_price_range(close: "pd.Series", rng: str) -> "pd.Series":
    """Slice the 2y Close series to the selected time-range option."""
    if close.empty:
        return close
    if rng == "YTD":
        from datetime import date
        start = pd.Timestamp(date.today().year, 1, 1)
        idx_tz = getattr(close.index, "tz", None)
        if idx_tz is not None:
            start = start.tz_localize(idx_tz)
        return close[close.index >= start]
    # Approximate trading-day windows; "2y"/"5y" use the full download
    rows: dict[str, int] = {
        "2h": 16, "1d": 1, "1w": 5, "1m": 21,
        "3m": 63, "6m": 126, "1y": 252,
    }
    n = rows.get(rng)
    if n is None:  # "2y", "5y"
        return close
    return close.iloc[-n:]


def _render_etf_explorer() -> None:
    """
    Three-panel ETF explorer rendered inside the "What do these tickers mean?"
    expander: ticker selector pills, a live yfinance price chart, a description
    card, and a static financial-data block (Morningstar/ESG, analyst
    consensus, key financials).
    """
    from backend.data.universe_config import ETF_UNIVERSE

    thm = get_theme_tokens()
    tickers = [e.primary_ticker for e in ETF_UNIVERSE]
    cluster_by_ticker = {e.primary_ticker: e.cluster for e in ETF_UNIVERSE}
    etf_by_ticker = {e.primary_ticker: e for e in ETF_UNIVERSE}

    if "selected_ticker" not in st.session_state:
        st.session_state["selected_ticker"] = tickers[0]

    selected = st.session_state["selected_ticker"]
    if selected not in tickers:
        selected = tickers[0]
        st.session_state["selected_ticker"] = selected

    # ── Panel 1: ticker selector pills ───────────────────────────────────
    # Per-pill CSS: cluster-coloured dot + active (navy) / inactive (grey).
    # Streamlit tags each keyed widget's container with `st-key-<key>`.
    _pill_bg = "#f1f4fa" if is_light() else "rgba(255,255,255,0.05)"
    _pill_border = "#D8DEE9" if is_light() else "rgba(255,255,255,0.10)"
    _pill_color = "#334155" if is_light() else "#94a3b8"
    css_rules = [
        'div[class*="st-key-pill_"] button {'
        f' background: {_pill_bg} !important;'
        f' border: 1px solid {_pill_border} !important;'
        f' color: {_pill_color} !important; border-radius: 18px !important;'
        " font-family: 'Space Grotesk', sans-serif !important;"
        ' font-size: 0.8rem !important; font-weight: 600 !important;'
        ' padding: 0.3rem 0.4rem !important; box-shadow: none !important; }',
        'div[class*="st-key-pill_"] button::before {'
        ' content: ""; display: inline-block; width: 8px; height: 8px;'
        ' border-radius: 50%; margin-right: 7px; vertical-align: middle; }',
    ]
    for t in tickers:
        safe = t.replace(".", "_")
        dot = CLUSTER_COLORS.get(cluster_by_ticker[t], "#888780")
        css_rules.append(
            f".st-key-pill_{safe} button::before {{ background: {dot} !important; }}"
        )
    active_safe = selected.replace(".", "_")
    css_rules.append(
        f".st-key-pill_{active_safe} button {{ background: #042C53 !important;"
        f" color: #ffffff !important; border-color: #042C53 !important; }}"
    )
    st.markdown("<style>" + "\n".join(css_rules) + "</style>", unsafe_allow_html=True)

    pill_cols = st.columns(len(tickers))
    for col, t in zip(pill_cols, tickers):
        with col:
            safe = t.replace(".", "_")
            if st.button(t, key=f"pill_{safe}", use_container_width=True):
                st.session_state["selected_ticker"] = t
                st.rerun()

    selected = st.session_state["selected_ticker"]
    meta = ETF_METADATA[selected]
    etf = etf_by_ticker[selected]

    # ── Panel 2 (Section 1): live price chart ────────────────────────────
    _section_header("1", "Price chart")
    rng = st.radio(
        "range",
        ["2h", "1d", "1w", "1m", "3m", "6m", "1y", "2y", "5y", "YTD"],
        index=7,
        horizontal=True,
        label_visibility="collapsed",
        key=f"etf_range_{selected}",
    )

    period_return: float | None = None
    try:
        raw = _fetch_price_history(selected)
        close = _close_series(raw)
        sliced = _slice_price_range(close, rng)
        if len(sliced) >= 1:
            up = float(sliced.iloc[-1]) >= float(sliced.iloc[0])
            line_color = "#185FA5" if up else "#E24B4A"
            fill_color = (
                "rgba(24,95,165,0.07)" if up else "rgba(226,75,74,0.07)"
            )
            if len(sliced) >= 2:
                period_return = (
                    float(sliced.iloc[-1]) / float(sliced.iloc[0]) - 1.0
                ) * 100.0

            # Plot the FULL downloaded series, but open on the selected window.
            # fixedrange=False keeps the rest reachable by zooming/panning out
            # (the previous version plotted only the slice, so zoom-out showed
            # empty space). The y-range is fitted to the window so the initial
            # view stays well-scaled rather than flattened by the full history.
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=close.index, y=close.values,
                mode="lines",
                line=dict(color=line_color, width=2),
                fill="tozeroy", fillcolor=fill_color,
                name=selected,
            ))
            x_range = [sliced.index[0], close.index[-1]]
            sv = sliced.astype(float)
            y_lo, y_hi = float(sv.min()), float(sv.max())
            y_pad = (y_hi - y_lo) * 0.08 or (abs(y_hi) * 0.02 or 1.0)
            fig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0),
                height=220,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                hovermode="x",
                xaxis=dict(
                    showgrid=False, color="#64748b",
                    range=x_range, fixedrange=False,
                ),
                yaxis=dict(
                    side="right", showgrid=True,
                    gridcolor="#e2e8f0" if is_light() else "rgba(255,255,255,0.05)",
                    color="#64748b",
                    range=[y_lo - y_pad, y_hi + y_pad], fixedrange=False,
                ),
                modebar_remove=[
                    "select2d", "lasso2d", "autoScale2d",
                    "hoverClosestCartesian", "hoverCompareCartesian",
                    "toggleSpikelines", "zoomIn2d", "zoomOut2d",
                ],
                modebar_add=["resetScale2d"],
                dragmode="pan",
            )
            chart_config = {"displaylogo": False}
            st.plotly_chart(
                fig, use_container_width=True, config=chart_config,
                key=f"etf_price_{selected}",
            )
        else:
            st.caption(f"No price data available for {selected}.")
    except Exception as exc:
        st.caption(f"Price chart unavailable: {exc}")

    pr_str = f"{period_return:+.2f}%" if period_return is not None else "—"
    st.markdown(
        f'<div style="font-size:0.8rem;color:{thm["text_secondary"]};margin:0.25rem 0 0.5rem 0;">'
        f'Period return: <span style="color:{thm["text_primary"]};font-weight:600;">{pr_str}</span>'
        f' &nbsp;|&nbsp; TER: <span style="color:{thm["text_primary"]};font-weight:600;">'
        f'{meta["ter"]}</span>'
        f' &nbsp;|&nbsp; AUM: <span style="color:{thm["text_primary"]};font-weight:600;">'
        f'{meta["aum"]}</span></div>',
        unsafe_allow_html=True,
    )

    _v_spacer(1.5)

    # ── Panel 3 (Section 2): description card ────────────────────────────
    _section_header("2", "What this ETF holds")
    stats_rows = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:1rem;'
        f'padding:0.4rem 0;border-bottom:1px solid {thm["border_soft"]};">'
        f'<span style="font-size:0.78rem;color:{thm["text_muted"]};">{k}</span>'
        f'<span style="font-size:0.78rem;color:{thm["text_primary"]};font-weight:600;">{v}</span>'
        f'</div>'
        for k, v in meta["key_stats"].items()
    )
    ucits_tag = "UCITS-eligible" if etf.is_ucits else "US-listed (non-UCITS)"
    st.markdown(
        f'<div style="background:{thm["accent_soft"]};'
        f'border:1px solid {thm["accent_border"]};border-radius:12px;'
        f'padding:1.1rem 1.25rem;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.05rem;'
        f'font-weight:700;color:{thm["text_primary"]};">{meta["full_name"]}</div>'
        f'<div style="font-size:0.74rem;color:{thm["text_muted"]};margin:0.3rem 0 0.85rem 0;">'
        f'{meta["issuer"]} &middot; {meta["category"]} &middot; '
        f'Inception {meta["inception"]} &middot; {meta["distribution"]} &middot; '
        f'{etf.currency} &middot; {ucits_tag}</div>'
        f'<div style="font-size:0.84rem;color:{thm["text_secondary"]};line-height:1.6;'
        f'margin-bottom:0.6rem;">{meta["description"]}</div>'
        f'<div style="font-size:0.8rem;color:{thm["text_muted"]};font-style:italic;'
        f'line-height:1.55;margin-bottom:1rem;">Universe rationale: '
        f'{etf.rationale}</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;'
        f'gap:0 1.5rem;">{stats_rows}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _v_spacer(1.5)

    # ── Panel 4 (Section 3): financial data ──────────────────────────────
    _section_header("3", "Financial data")

    # (a) Morningstar & ESG ----------------------------------------------
    st.markdown(
        f'<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:{thm["accent_text"]};margin-bottom:0.5rem;">'
        f'Morningstar &amp; ESG</div>',
        unsafe_allow_html=True,
    )
    ms = meta["morningstar"]
    esg = meta["esg"]
    esg_rating = esg["risk"]
    ms_html = (
        f'<span style="color:#BA7517;">{"★" * ms}</span>'
        f'<span style="color:#475569;">{"☆" * (5 - ms)}</span>'
    )
    esg_html = (
        f'<span style="color:#0F6E56;">{"●" * esg_rating}</span>'
        f'<span style="color:#475569;">{"○" * (5 - esg_rating)}</span>'
    )
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(
            f'<div style="font-size:0.72rem;color:#64748b;'
            f'margin-bottom:0.2rem;">Morningstar rating</div>'
            f'<div style="font-size:1.3rem;letter-spacing:2px;">{ms_html}</div>',
            unsafe_allow_html=True,
        )
    with rc2:
        st.markdown(
            f'<div style="font-size:0.72rem;color:#64748b;'
            f'margin-bottom:0.2rem;">ESG globe rating</div>'
            f'<div style="font-size:1.3rem;letter-spacing:2px;">{esg_html}</div>',
            unsafe_allow_html=True,
        )
    eg1, eg2, eg3 = st.columns(3)
    eg1.metric("Environmental", f'{esg["environmental"]}/10')
    eg2.metric("Social", f'{esg["social"]}/10')
    eg3.metric("Governance", f'{esg["governance"]}/10')

    st.divider()

    # (b) Analyst consensus ----------------------------------------------
    st.markdown(
        f'<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:{thm["accent_text"]};margin-bottom:0.5rem;">'
        f'Analyst consensus</div>',
        unsafe_allow_html=True,
    )
    an = meta["analyst"]
    ac1, ac2, ac3 = st.columns(3)
    ac1.metric("Buy", f'{an["buy"]}%')
    ac2.metric("Hold", f'{an["hold"]}%')
    ac3.metric("Sell", f'{an["sell"]}%')
    st.markdown(
        f'<div style="width:100%;border-radius:5px;overflow:hidden;'
        f'margin:0.4rem 0 0.3rem 0;font-size:0;">'
        f'<span style="display:inline-block;height:8px;width:{an["buy"]}%;'
        f'background:#0F6E56;"></span>'
        f'<span style="display:inline-block;height:8px;width:{an["hold"]}%;'
        f'background:#BA7517;"></span>'
        f'<span style="display:inline-block;height:8px;width:{an["sell"]}%;'
        f'background:#E24B4A;"></span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption("Based on underlying holdings consensus estimates.")

    st.divider()

    # (c) Key financials table -------------------------------------------
    st.markdown(
        f'<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:{thm["accent_text"]};margin-bottom:0.5rem;">'
        f'Key financials</div>',
        unsafe_allow_html=True,
    )
    fin_rows = [
        {
            "Metric": f["label"],
            "Value": f["value"],
        }
        for f in meta["financials"]
    ]
    st.dataframe(
        pd.DataFrame(fin_rows),
        hide_index=True,
        use_container_width=True,
    )


def _render_hrp_tab(portfolio: dict) -> None:
    weights: dict[str, float] = portfolio["weights"]
    risk_contributions: dict[str, float] = portfolio["risk_contributions"]
    vol: float = portfolio.get("expected_volatility", 0.0)
    exp_ret = portfolio.get("expected_return")
    max_dd = portfolio.get("max_drawdown")
    sharpe = portfolio.get("sharpe_ratio")

    profile_label: str = (
        st.session_state.get("profile", {}).get("profile_label", "MODERATE").upper()
    )

    # ── Section 1: Portfolio Allocation ────────────────────────────────────
    _section_header("1", "Portfolio Allocation")
    _section_desc(
        "The chart below shows how capital is distributed across the portfolio's assets. "
        "HRP balances risk — not capital — so assets with higher historical volatility "
        "receive a proportionally smaller weight. This spreads risk contributions evenly "
        "across equities, fixed income, commodities, and cash-equivalent positions."
    )

    # Cluster allocation pills — asset-class breakdown of the current portfolio
    cluster_totals: dict[str, float] = {}
    for ticker, w in weights.items():
        cl = _HRP_TICKER_CLUSTER.get(ticker, "Other")
        cluster_totals[cl] = cluster_totals.get(cl, 0.0) + w

    st.markdown(
        '<div style="font-size:0.72rem;font-weight:600;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#64748b;margin-bottom:0.5rem;">'
        'Current allocation by asset class</div>',
        unsafe_allow_html=True,
    )
    pills_html = '<div style="display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:1.25rem;">'
    for cl in ["Equity", "Bonds", "Alternatives", "Cash"]:
        pct = cluster_totals.get(cl, 0.0)
        if pct < 0.001:
            continue
        c = _HRP_CLUSTER_COLOR[cl]
        bg = _HRP_CLUSTER_BG[cl]
        pills_html += (
            f'<div style="display:flex;align-items:center;gap:0.4rem;'
            f'background:{bg};border:1px solid {c}40;border-radius:20px;'
            f'padding:0.3rem 0.75rem;">'
            f'<span style="width:8px;height:8px;border-radius:50%;'
            f'background:{c};flex-shrink:0;"></span>'
            f'<span style="font-size:0.75rem;color:{c};font-weight:600;'
            f'font-family:\'Space Grotesk\',sans-serif;">{cl}</span>'
            f'<span style="font-size:0.75rem;color:#94a3b8;">{pct:.0%}</span>'
            f'</div>'
        )
    pills_html += "</div>"
    st.markdown(pills_html, unsafe_allow_html=True)

    col_donut, col_table = st.columns([1.05, 1], gap="large")

    with col_donut:
        try:
            from backend.optimizer.charts import plot_weights_donut
            fig_donut = plot_weights_donut(weights)
            fig_donut = apply_plotly_theme(fig_donut)
            # Re-assert the donut's own layout: apply_plotly_theme()
            # overwrites margin (and would clip the bottom colour legend) and
            # the layout font. The per-slice textfont set in charts.py is not
            # touched, so the white in-slice labels survive.
            fig_donut.update_layout(
                height=360,
                margin=dict(l=10, r=10, t=12, b=38),
            )
            st.plotly_chart(
                fig_donut,
                use_container_width=True,
                config={"displaylogo": False, "responsive": False},
                key="hrp_allocation_donut",
            )
        except Exception as exc:
            st.caption(f"Allocation chart unavailable: {exc}")

    with col_table:
        _render_allocation_table(weights, risk_contributions)

    _v_spacer(1.5)

    with st.expander("🔍 Explore ETFs in detail — price, ESG, analyst ratings"):
        _render_etf_explorer()

    _v_spacer(1.5)
    st.markdown("---")

    # ── Section 2: How your money is grouped ───────────────────────────────
    _section_header("2", "How your money is grouped")
    _section_desc(
        "Before deciding the weights, HRP sorts the assets into four families that "
        "tend to behave alike. It then balances risk inside each family and across "
        "them. For each family you can see its share of the portfolio, how "
        "diversified it is, and how much it tends to move."
    )

    _render_cluster_view(portfolio, weights)

    st.caption(
        "“Diversification” reflects how closely the assets in a family move together — "
        "well-diversified families spread risk better. “Risk level” reflects how much "
        "the family tends to swing. The small ρ and vol figures are the underlying "
        "technical values for the curious."
    )

    _v_spacer(2.5)

    # ── KPI Cards ──────────────────────────────────────────────────────────
    _section_header("3", "Key Portfolio Metrics")
    _kpi_cards([
        {
            "label": "Expected Return",
            "value": f"{exp_ret:.1%}" if exp_ret is not None else "—",
            "accent": "#0dcfb0", "bg": "rgba(13,207,176,0.13)",
            "icon": '<polyline points="2,13 7,8 11,11 16,4"/>'
                    '<polyline points="12,4 16,4 16,8"/>',
            "hint": "Annualised estimate",
        },
        {
            "label": "Volatility",
            "value": f"{vol:.1%}",
            "accent": "#f59e0b", "bg": "rgba(245,158,11,0.13)",
            "icon": '<polyline points="2,9 5,9 7,3 11,15 13,9 16,9"/>',
            "hint": "Annualised std. dev.",
        },
        {
            "label": "Sharpe Ratio",
            "value": f"{sharpe:.2f}" if sharpe is not None else "—",
            "accent": "#7c5cfc", "bg": "rgba(124,92,252,0.13)",
            "icon": '<polygon points="9,2 4,10 8,10 7,16 13,8 9,8"/>',
            "hint": "Return per unit of risk",
        },
        {
            "label": "Max Drawdown",
            "value": f"{max_dd:.1%}" if max_dd is not None else "—",
            "accent": "#f87171", "bg": "rgba(248,113,113,0.13)",
            "icon": '<polyline points="2,4 7,9 11,6 16,13"/>'
                    '<polyline points="12,13 16,13 16,9"/>',
            "hint": "Worst peak-to-trough",
        },
    ])

    _v_spacer(1.5)
    st.markdown("---")

    # ── Section 3: Risk Contributions ──────────────────────────────────────
    _section_header("4", "Risk Contributions")
    _section_desc(
        "Each bar shows the percentage of total portfolio risk attributed to that asset. "
        "HRP targets an even spread of risk across positions — no single asset should "
        "dominate the overall volatility budget."
    )

    try:
        from backend.optimizer.charts import plot_risk_contributions
        fig_risk = plot_risk_contributions(
            risk_contributions,
            profile_label=profile_label,
        )
        fig_risk = apply_plotly_theme(fig_risk)
        # The "Risk Contributions" section header above already titles this chart
        # (outside the dark plot background), so drop the duplicate in-figure title.
        fig_risk.update_layout(title_text="")
        st.plotly_chart(fig_risk, use_container_width=True, config={"displaylogo": False})
    except Exception as exc:
        st.caption(f"Risk contribution chart unavailable: {exc}")

    _v_spacer(1.5)
    st.markdown("---")

    # ── Section 4: Historical Resilience ───────────────────────────────────
    _section_header("5", "Historical Resilience")
    _section_desc(
        "How the HRP strategy weathered three historical stress periods — the maximum "
        "peak-to-trough loss in each, compared against the Mean-Variance benchmark. "
        "These are real walk-forward backtest results; the full equity curves and "
        "strategy comparison live on the Backtesting page."
    )
    _render_resilience_strip(profile_label)



# ---------------------------------------------------------------------------
# Chat Advisor helpers
# ---------------------------------------------------------------------------

# Scoped CSS for the native chat (st.chat_message / st.chat_input).
# Aligned with the app-wide design tokens defined in frontend/style.py.
_CHAT_CSS = """
<style>
/* ════════════════════════════════════════════════════════════════════════
   Chat Advisor — framed "screen" with colour-coded roles.
   Purple = you, teal = assistant. Everything lives inside one bordered shell.
   ════════════════════════════════════════════════════════════════════════ */
@keyframes ca-rise {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── The screen frame (st.container(border=True, key="ca_screen")) ───────── */
div[class*="st-key-ca_screen"] {
    border: 1px solid rgba(124,92,252,0.30) !important;
    border-radius: 18px !important;
    background:
        radial-gradient(135% 80% at 50% -12%, rgba(124,92,252,0.13) 0%, transparent 55%),
        linear-gradient(180deg, #111a2e 0%, #0d1322 100%) !important;
    box-shadow: 0 18px 48px rgba(7,11,22,0.55),
                inset 0 1px 0 rgba(255,255,255,0.04) !important;
    padding: 1.1rem 1.15rem !important;
}

/* ── Header bar: identity + colour-coded status pills ───────────────────── */
.ca-head {
    display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap;
    padding: 0.7rem 0.85rem; margin-bottom: 1rem;
    border-radius: 12px;
    background: linear-gradient(135deg, #15203f 0%, #1d1944 55%, #111a35 100%);
    border: 1px solid rgba(124,92,252,0.22);
}
.ca-orb {
    flex-shrink: 0; width: 2.25rem; height: 2.25rem; border-radius: 10px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 1.1rem; color: #ffffff;
    background: linear-gradient(135deg, #7c5cfc, #5b8def);
    box-shadow: 0 6px 16px rgba(124,92,252,0.42);
}
.ca-head-meta { display: flex; flex-direction: column; min-width: 0; }
.ca-head-name {
    font-family: 'Space Grotesk', sans-serif; font-size: 0.95rem; font-weight: 700;
    color: #f3f6fb; line-height: 1.2; letter-spacing: -0.01em;
}
.ca-head-sub { font-size: 0.73rem; color: #8a97ad; margin-top: 0.12rem; }
.ca-pills { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-left: auto; }
.ca-pill {
    display: inline-flex; align-items: center; gap: 0.34rem;
    font-family: 'Space Grotesk', sans-serif; font-size: 0.7rem; font-weight: 600;
    border-radius: 999px; padding: 0.26rem 0.62rem; white-space: nowrap;
    border: 1px solid transparent;
}
.ca-pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; }
.ca-pill--profile {
    color: #c4b5fd; background: rgba(124,92,252,0.15);
    border-color: rgba(124,92,252,0.36);
}
.ca-pill--profile::before { background: #a78bfa; }
.ca-pill--model {
    color: #93c5fd; background: rgba(59,130,246,0.14);
    border-color: rgba(59,130,246,0.34);
}
.ca-pill--model::before { background: #3b82f6; }
.ca-pill--guard {
    color: #5eead4; background: rgba(13,207,176,0.14);
    border-color: rgba(13,207,176,0.34);
}
.ca-pill--guard::before { background: #0dcfb0; }

/* ── Footer: always-visible safety pipeline ─────────────────────────────── */
.ca-foot {
    display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;
    margin-top: 1rem; padding: 0.62rem 0.85rem;
    border-radius: 10px;
    border: 1px solid rgba(124,92,252,0.16);
    background: rgba(10,15,28,0.45);
}
.ca-step {
    font-family: 'Space Grotesk', sans-serif; font-size: 0.66rem; font-weight: 600;
    color: #aab4c5; background: rgba(124,92,252,0.1);
    border: 1px solid rgba(124,92,252,0.24);
    border-radius: 6px; padding: 0.18rem 0.46rem;
}
.ca-arrow { color: #5b6678; font-size: 0.72rem; }
.ca-foot-note { font-size: 0.72rem; color: #6b7689; margin-left: 0.3rem; }

/* ── Empty-state hero ───────────────────────────────────────────────────── */
.ca-hero { text-align: center; padding: 1.4rem 0 0.3rem; animation: ca-rise 0.4s ease; }
.ca-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 54px; height: 54px; border-radius: 16px; margin-bottom: 1rem;
    font-size: 1.55rem; color: #ffffff;
    background: linear-gradient(135deg, #7c5cfc 0%, #5b8def 100%);
    box-shadow: 0 10px 26px rgba(124,92,252,0.38);
}
.ca-hero-title {
    font-family: 'Space Grotesk', sans-serif; font-size: 1.4rem; font-weight: 700;
    color: #f1f5f9; letter-spacing: -0.02em; margin-bottom: 0.45rem;
}
.ca-hero-sub {
    font-size: 0.91rem; color: #8a97ad; max-width: 440px;
    margin: 0 auto; line-height: 1.6;
}
.ca-eyebrow {
    font-family: 'Space Grotesk', sans-serif; font-size: 0.61rem; font-weight: 600;
    letter-spacing: 0.16em; text-transform: uppercase; color: #6b7689;
    text-align: left; margin: 1.5rem 0 0.8rem;
}

/* ── Suggestions (stacked, minimal) — targeted by st-key ────────────────── */
div[class*="st-key-chat_suggest"] button {
    position: relative; width: 100%;
    background: rgba(124,92,252,0.06) !important;
    border: 1px solid rgba(124,92,252,0.2) !important; border-radius: 11px !important;
    color: #cdd6e3 !important; font-family: 'DM Sans', sans-serif !important;
    font-size: 0.88rem !important; font-weight: 500 !important;
    text-align: left !important; white-space: normal !important;
    padding: 0.72rem 2.5rem 0.72rem 1rem !important; line-height: 1.4 !important;
    min-height: 0 !important;
    transition: border-color 0.16s ease, background 0.16s ease,
                transform 0.16s ease, color 0.16s ease !important;
}
div[class*="st-key-chat_suggest"] button::after {
    content: "→"; position: absolute; right: 1rem; top: 50%;
    transform: translateY(-50%); color: #7c5cfc; font-size: 0.95rem;
    transition: transform 0.16s ease, color 0.16s ease;
}
div[class*="st-key-chat_suggest"] button:hover {
    border-color: rgba(124,92,252,0.55) !important;
    background: rgba(124,92,252,0.13) !important; color: #e9d5ff !important;
    transform: translateY(-1px) !important;
}
div[class*="st-key-chat_suggest"] button:hover::after {
    color: #a78bfa; transform: translateY(-50%) translateX(3px);
}
div[class*="st-key-chat_suggest"] button p {
    text-align: left !important; margin: 0 !important; font-weight: 500 !important;
}

/* ── Conversation thread — boxed, colour-coded, labelled ────────────────── */
.ca-thread { padding: 0.3rem 0 0.2rem; }
[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important; box-shadow: none !important;
    /* Top padding reserves space for the absolutely-positioned role label that
       floats above each bubble, keeping it visible without affecting inner layout. */
    padding: 1.45rem 0 0 !important; margin-bottom: 0.75rem !important;
    width: 100% !important; max-width: 100% !important; display: block !important;
    animation: ca-rise 0.25s ease;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessageAvatarCustom"] { display: none !important; }

/* Assistant: LEFT, teal-accented box */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
[data-testid="stChatMessageContent"] {
    position: relative !important;
    width: 92% !important; margin-left: 0 !important; margin-right: auto !important;
    background: linear-gradient(135deg,
        rgba(13,207,176,0.09), rgba(16,26,42,0.65)) !important;
    border: 1px solid rgba(13,207,176,0.22) !important;
    border-left: 3px solid #0dcfb0 !important;
    border-radius: 4px 13px 13px 13px !important;
    padding: 0.7rem 1rem !important; box-sizing: border-box !important;
    overflow-wrap: break-word !important; word-break: break-word !important;
}
/* Label floats above the top-left corner of the box — outside the flow */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
[data-testid="stChatMessageContent"]::before {
    content: "✦ Assistant";
    position: absolute; top: -1.25rem; left: 0.45rem;
    font-family: 'Space Grotesk', sans-serif; font-size: 0.64rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; color: #5eead4;
    white-space: nowrap;
}
/* User: RIGHT, purple-accented box, hugs its text */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] {
    position: relative !important;
    width: fit-content !important; max-width: 82% !important;
    margin-left: auto !important; margin-right: 0 !important;
    background: linear-gradient(135deg,
        rgba(124,92,252,0.2), rgba(124,92,252,0.11)) !important;
    border: 1px solid rgba(124,92,252,0.32) !important;
    border-left: 3px solid #7c5cfc !important;
    border-radius: 13px 13px 4px 13px !important;
    padding: 0.65rem 0.95rem !important; box-sizing: border-box !important;
    overflow-wrap: break-word !important; word-break: break-word !important;
}
/* Label floats above the top-right corner of the box — outside the flow */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"]::before {
    content: "You";
    position: absolute; top: -1.25rem; right: 0.45rem;
    font-family: 'Space Grotesk', sans-serif; font-size: 0.64rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; color: #c4b5fd;
    white-space: nowrap;
}
[data-testid="stChatMessage"] p {
    font-family: 'DM Sans', sans-serif !important; font-size: 0.93rem !important;
    line-height: 1.66 !important; color: #d6dee9 !important;
    margin-top: 0 !important; margin-bottom: 0.55rem !important;
    text-align: left !important;
}
[data-testid="stChatMessage"] p:last-child { margin-bottom: 0 !important; }
[data-testid="stChatMessage"] em { color: #6b7689 !important; font-size: 0.82rem !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #e8edf4 !important; font-size: 0.98rem !important;
    margin: 0.5rem 0 0.35rem !important;
}
[data-testid="stChatMessage"] strong { color: #ede9fe !important; }
[data-testid="stChatMessage"] code {
    background: rgba(124,92,252,0.14) !important; color: #c4b5fd !important;
    padding: 0.05rem 0.35rem !important; border-radius: 4px !important;
    font-size: 0.85rem !important;
}
[data-testid="stChatMessage"] table {
    border-collapse: collapse !important; margin: 0.4rem 0 !important;
}
[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td {
    border: 1px solid rgba(124,92,252,0.2) !important; padding: 0.35rem 0.7rem !important;
    font-size: 0.84rem !important; color: #9aa6b8 !important;
}
[data-testid="stChatMessage"] th {
    background: rgba(124,92,252,0.1) !important; color: #a78bfa !important;
    font-family: 'Space Grotesk', sans-serif !important; font-weight: 600 !important;
}

/* ── Input ──────────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    background: transparent !important; border: none !important; padding-top: 0.5rem !important;
}
[data-testid="stChatInput"] > div {
    background: #0c1120 !important; border: 1px solid rgba(124,92,252,0.24) !important;
    border-radius: 13px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: rgba(124,92,252,0.6) !important;
    box-shadow: 0 0 0 3px rgba(124,92,252,0.14) !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important; color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.93rem !important; line-height: 1.55 !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #5b6678 !important; }
[data-testid="stChatInput"] button {
    background: #7c5cfc !important; border: none !important;
    border-radius: 10px !important; color: #ffffff !important;
}
[data-testid="stChatInput"] button:hover { background: #6b4ce0 !important; }

/* ── Clear conversation (danger-tinted bordered button) ─────────────────── */
div[class*="st-key-ca_clear"] button {
    background: rgba(239,68,68,0.07) !important;
    border: 1px solid rgba(239,68,68,0.28) !important;
    border-radius: 8px !important; color: #f87171 !important;
    font-family: 'DM Sans', sans-serif !important; font-size: 0.77rem !important;
    font-weight: 500 !important; padding: 0.32rem 0.8rem !important;
    min-height: 0 !important; box-shadow: none !important;
    transition: background 0.15s ease, border-color 0.15s ease,
                color 0.15s ease !important;
}
div[class*="st-key-ca_clear"] button:hover {
    background: rgba(239,68,68,0.16) !important;
    border-color: rgba(239,68,68,0.55) !important;
    color: #fca5a5 !important;
}
</style>
"""
# Light-theme override for the chat page. Appended AFTER _CHAT_CSS (so it wins by
# source order) only when the light theme is active — flips the dark surfaces,
# borders, and near-white text to readable light-mode values.
_CHAT_CSS_LIGHT = """
<style>
div[class*="st-key-ca_screen"] {
    border-color: #D8DEE9 !important;
    background:
        radial-gradient(135% 80% at 50% -12%, rgba(124,77,255,0.07) 0%, transparent 55%),
        #ffffff !important;
    box-shadow: 0 10px 30px rgba(15,23,42,0.08) !important;
}
.ca-head {
    background: linear-gradient(135deg, #f8fafc 0%, #ede9fe 55%, #f1f4fa 100%);
    border-color: #ddd6fe;
}
.ca-head-name { color: #111827; }
.ca-head-sub { color: #64748B; }
.ca-pill--profile { color: #6d4deb; background: #efeafe; border-color: #ddd6fe; }
.ca-pill--model { color: #2563eb; background: #e7effe; border-color: #c7dafc; }
.ca-pill--guard { color: #0f9e87; background: #e3faf5; border-color: #bdf0e6; }
.ca-foot { background: #f8fafc; border-color: #E5E9F0; }
.ca-step { color: #4b5563; background: #f4f1fe; border-color: #ddd6fe; }
.ca-arrow { color: #94a3b8; }
.ca-foot-note { color: #64748B; }
.ca-hero-title { color: #111827; }
.ca-hero-sub { color: #64748B; }
.ca-eyebrow { color: #94a3b8; }
div[class*="st-key-chat_suggest"] button {
    background: #faf9ff !important; border-color: #e4ddfb !important; color: #334155 !important;
}
div[class*="st-key-chat_suggest"] button:hover {
    background: #f1ecfe !important;
    border-color: rgba(124,77,255,0.45) !important; color: #5b2bd9 !important;
}
div[class*="st-key-chat_suggest"] button::after { color: #7C4DFF !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
[data-testid="stChatMessageContent"] {
    background: #f3fdfb !important; border-color: rgba(13,207,176,0.3) !important;
    border-left-color: #0f9e87 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
[data-testid="stChatMessageContent"]::before { color: #0f9e87 !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"] {
    background: #f1ecfe !important; border-color: rgba(124,77,255,0.32) !important;
    border-left-color: #7C4DFF !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"]::before { color: #6d4deb !important; }
[data-testid="stChatMessage"] p {
    color: #334155 !important; margin-top: 0 !important; margin-bottom: 0.55rem !important;
}
[data-testid="stChatMessage"] p:last-child { margin-bottom: 0 !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 { color: #111827 !important; }
[data-testid="stChatMessage"] strong { color: #5b2bd9 !important; }
[data-testid="stChatMessage"] code { background: #f4f1fe !important; color: #6d4deb !important; }
[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td { border-color: #D8DEE9 !important; color: #334155 !important; }
[data-testid="stChatMessage"] th { color: #6d4deb !important; background: #f4f1fe !important; }
[data-testid="stChatInput"] > div {
    background: #ffffff !important; border-color: #D8DEE9 !important;
}
[data-testid="stChatInput"] textarea { background: #ffffff !important; color: #111827 !important; }
[data-testid="stChatInput"] textarea::placeholder { color: #94a3b8 !important; }
div[class*="st-key-ca_clear"] button {
    background: #fef2f2 !important; border: 1px solid #fecaca !important;
    border-radius: 8px !important; color: #ef4444 !important;
    padding: 0.32rem 0.8rem !important; min-height: 0 !important;
}
div[class*="st-key-ca_clear"] button:hover {
    background: #fee2e2 !important; border-color: #f87171 !important;
    color: #dc2626 !important;
}
</style>
"""
# No custom avatars — user vs assistant distinction is conveyed by CSS color.
_CHAT_AVATARS: dict[str, None] = {"assistant": None, "user": None}

# Example prompts shown in the empty state. A leading emoji gives each card a
# small visual anchor (the chevron is added in CSS via ::before).
_CHAT_SUGGESTIONS: list[str] = [
    "Explain my risk profile in plain English",
    "Why is my portfolio split this way?",
    "How would it hold up in a market crash?",
    "What's the EU investor caveat about?",
]


def _build_chat_payload(profile_key: str):
    """Ground the chat in the SAME portfolio the user sees on the dashboard.

    Starts from the mock Ground Truth payload for the user's profile, then —
    when a live HRP optimisation is cached in this session — overrides the
    weights, headline risk metrics and cluster structure with those live
    numbers and rebuilds the `allowed_numbers` whitelist so the validator
    accepts them. This keeps the advisor's figures consistent with the
    Portfolio Dashboard instead of quoting static mock values.

    Falls back to the untouched mock payload on any error or when no live
    data is available, so the chat can never break because of this.
    """
    base = get_mock_payload(profile_key)

    live = st.session_state.get("portfolio_data")
    if not live or live.get("source") != "live" or not live.get("weights"):
        return base

    try:
        from backend.schemas.ground_truth import (
            GroundTruthPayload,
            LLMConstraints,
            Portfolio,
            RiskMetrics,
            build_allowed_numbers,
        )

        # Normalise live weights so they validate (must sum to 1.0).
        raw = {t: float(w) for t, w in live["weights"].items() if w is not None}
        total = sum(raw.values()) or 1.0
        weights = {t: round(w / total, 4) for t, w in raw.items()}
        # Fix any rounding residue on the largest holding.
        drift = round(1.0 - sum(weights.values()), 4)
        if weights and abs(drift) >= 0.0001:
            top = max(weights, key=weights.get)
            weights[top] = round(weights[top] + drift, 4)

        ucits = live.get("ucits_tickers_used") or base.portfolio.ucits_tickers_used
        portfolio = Portfolio(
            weights=weights,
            guardrail_applied=False,
            clipped_assets=[],
            clip_note=None,
            ucits_tickers_used=[t for t in ucits if t in weights],
            fallback_tickers_applied=live.get("fallback_tickers_applied", []),
        )

        # Headline risk metrics from the live run; keep mock VaR/CVaR (not
        # computed live) so those fields stay populated and plausible.
        mdd = live.get("max_drawdown")
        risk = RiskMetrics(
            expected_annual_return=live.get("expected_return"),
            annual_volatility=live.get("expected_volatility")
            or base.risk_metrics.annual_volatility,
            sharpe_ratio=live.get("sharpe_ratio"),
            max_drawdown_historical=(
                mdd if isinstance(mdd, (int, float)) and mdd <= 0
                else base.risk_metrics.max_drawdown_historical
            ),
            var_95_daily=base.risk_metrics.var_95_daily,
            cvar_95_daily=base.risk_metrics.cvar_95_daily,
        )

        cluster_structure = live.get("cluster_structure") or base.cluster_structure

        # Rebuild the allowed-number whitelist from the overridden payload.
        partial = {
            "metadata": base.metadata.model_dump(),
            "profiler": base.profiler.model_dump(),
            "portfolio": portfolio.model_dump(),
            "risk_metrics": risk.model_dump(),
            "cluster_structure": cluster_structure.model_dump(),
            "stress_scenarios": base.stress_scenarios.model_dump(),
            "backtest_summary": base.backtest_summary.model_dump(),
            "regulatory_context": base.regulatory_context.model_dump(),
        }
        constraints = LLMConstraints(
            allowed_numbers=build_allowed_numbers(partial),
            forbidden_phrases=base.llm_constraints.forbidden_phrases,
            disclaimer_required=True,
        )

        return GroundTruthPayload(
            metadata=base.metadata,
            profiler=base.profiler,
            portfolio=portfolio,
            risk_metrics=risk,
            cluster_structure=cluster_structure,
            stress_scenarios=base.stress_scenarios,
            backtest_summary=base.backtest_summary,
            llm_constraints=constraints,
            regulatory_context=base.regulatory_context,
        )
    except Exception:
        # Any mismatch in live data shape must never break the chat.
        return base


# First sentence of MANDATORY_DISCLAIMER — used to detect and strip the legal
# footer from chat bubbles. Specific enough never to appear in a real answer.
_CHAT_DISCLAIMER_MARKER: str = "This is an educational prototype"


def _strip_chat_disclaimer(text: str) -> str:
    """Remove the trailing MiFID II disclaimer from a chat reply for display.

    The disclaimer is still enforced by the validator (it stays in the validated
    text) and is shown once via the page-level footer (render_global_footer), so
    repeating it inside every chat bubble only lengthens the conversation. This
    strips the final disclaimer block — and any partial prefix still arriving
    mid-stream — so bubbles stay focused on the answer.
    """
    marker = _CHAT_DISCLAIMER_MARKER
    idx = text.find(marker)
    if idx != -1:
        return text[:idx].rstrip(" \n*")
    # While streaming, the disclaimer arrives token-by-token at the very end.
    # Hide a partial prefix of the marker still sitting at the tail so it does
    # not flash into view and then vanish. Require >= 8 chars to avoid false cuts.
    overlap_max = min(len(text), len(marker))
    for n in range(overlap_max, 7, -1):
        if text[-n:] == marker[:n]:
            return text[:-n].rstrip(" \n*")
    return text


def _chat_stream_reply(
    text: str,
    profile_key: str,
    placeholder: "st.delta_generator.DeltaGenerator",
) -> str:
    """
    Stream a validated advisor reply token-by-token into a Streamlit placeholder.

    Runs the full chat pipeline — input sanitiser → streaming NarratorClient →
    5-step validator — yielding tokens live so the user sees the response appear
    word-by-word instead of waiting for the full round trip. Falls back to a
    single blocking narrate() call when streaming is unavailable or fails, so the
    chat never raises and never crashes the page.

    The placeholder is updated on every chunk with a blinking-cursor suffix (▌).
    After the stream ends, the validator runs on the full collected text and the
    placeholder is replaced with the final validated output (cursor removed).

    Args:
        text:        Raw user message from the chat input.
        profile_key: Mock-data key for the active profile ("balanced", etc.).
        placeholder: A ``st.empty()`` element inside a ``st.chat_message`` block.

    Returns:
        The final validated response string (also already written to placeholder).
    """
    from backend.llm.input_sanitiser import sanitise
    from backend.llm.narrator import NarratorError

    san = sanitise(text)
    if san.blocked:
        msg = (
            "Your question could not be processed — it looked like an unsafe "
            "instruction. Please rephrase it."
        )
        placeholder.markdown(msg)
        return msg

    try:
        narrator = NarratorClient()
    except NarratorError:
        msg = (
            "⚠️ The chat advisor is not configured: no `ANTHROPIC_API_KEY` was "
            "found. Add it under **Manage app → Settings → Secrets** on Streamlit "
            "Cloud, or in a local `.streamlit/secrets.toml`, then reload the page."
        )
        placeholder.markdown(msg)
        return msg

    payload = _build_chat_payload(profile_key)

    # ── Try to stream tokens live, but degrade gracefully ────────────────
    # Streaming is an enhancement, not a requirement. If the deployed
    # NarratorClient predates narrate_stream (stale deploy) or the streaming
    # call fails for any reason, we silently fall back to the proven blocking
    # narrate() path below — the chat must never crash the page.
    full_text = ""
    streamed = False
    if hasattr(narrator, "narrate_stream"):
        try:
            for chunk in narrator.narrate_stream(payload, san.sanitised_input):
                full_text += chunk
                placeholder.markdown(_strip_chat_disclaimer(full_text) + "▌")
            streamed = bool(full_text)
        except Exception:  # noqa: BLE001 — any streaming failure → blocking path
            full_text = ""
            streamed = False

    # ── Blocking fallback (also the path when streaming is unavailable) ──
    if not streamed:
        placeholder.markdown("_Thinking…_")
        try:
            nresp = narrator.narrate(payload, san.sanitised_input)
        except NarratorError:
            msg = "⚠️ The chat advisor is not configured."
            placeholder.markdown(msg)
            return msg
        if nresp.injection_blocked:
            msg = "Your question could not be processed. Please rephrase it."
            placeholder.markdown(msg)
            return msg
        if nresp.api_error:
            msg = (
                "I could not reach the advisor right now. "
                "Please try again in a moment."
            )
            placeholder.markdown(msg)
            return msg
        full_text = nresp.raw_text

    # Validate the complete response (disclaimer stays enforced in safe_text),
    # then display a decluttered version: the legal footer is dropped from the
    # bubble because the page already shows it once via render_global_footer().
    result = validate(
        response_text=full_text,
        allowed_numbers=payload.llm_constraints.allowed_numbers,
        forbidden_phrases=payload.llm_constraints.forbidden_phrases,
        eu_awareness_required=False,
    )
    display_text = _strip_chat_disclaimer(result.safe_text)
    placeholder.markdown(display_text)
    return display_text


def _chat_header_html(profile_label: str, model_label: str = "Claude Sonnet 4.6") -> str:
    """Top bar of the chat screen: assistant identity + colour-coded status pills.

    Replaces the old collapsible dropdown with the status pills the user
    preferred — profile (purple), model (blue), validator (teal).
    """
    return (
        '<div class="ca-head">'
        '<span class="ca-orb">✦</span>'
        '<div class="ca-head-meta">'
        '<span class="ca-head-name">RoboAdvisor Assistant</span>'
        '<span class="ca-head-sub">Grounded in your portfolio · '
        'here to explain, never to advise</span>'
        '</div>'
        '<div class="ca-pills">'
        f'<span class="ca-pill ca-pill--profile">{profile_label}</span>'
        f'<span class="ca-pill ca-pill--model">{model_label}</span>'
        '<span class="ca-pill ca-pill--guard">Validated · 5 checks</span>'
        '</div>'
        '</div>'
    )


def _chat_footer_html() -> str:
    """Bottom bar of the chat screen: always-visible 5-step safety pipeline."""
    return (
        '<div class="ca-foot">'
        '<span class="ca-step">Sanitise</span><span class="ca-arrow">›</span>'
        '<span class="ca-step">Narrate</span><span class="ca-arrow">›</span>'
        '<span class="ca-step">Validate</span>'
        '<span class="ca-foot-note">every reply passes a 5-step safety check '
        'before display</span>'
        '</div>'
    )


def _render_mv_tab(portfolio: dict, profile_key: str) -> None:
    """
    Markowitz tab: HRP vs MV weight comparison, efficient frontier,
    stress scenario table, backtest summary.

    Phase A: uses mock MV weights + synthetic frontier for illustration.
    Phase B: runs optimize_markowitz() on live prices for real comparison.
    """
    from backend.optimizer.charts import plot_efficient_frontier

    st.subheader("Markowitz Mean-Variance — Benchmark Comparison")

    mv_weights: dict[str, float] | None = None
    mv_vol: float | None = None
    mv_ret: float | None = None
    mv_sharpe: float | None = None

    if portfolio.get("source") == "live":
        try:
            from datetime import date

            from backend.data.loader import ValidatedDataLoader
            from backend.data.universe_config import get_primary_tickers
            from backend.optimizer.markowitz import optimize_markowitz

            tickers = get_primary_tickers()
            loader = ValidatedDataLoader()
            prices, _ = loader.load(
                tickers=tickers,
                start=_DATA_START,
                end=date.today().isoformat(),
            )
            mv_result = optimize_markowitz(prices)
            mv_weights = mv_result["weights"]
            mv_vol = mv_result["expected_volatility"]
            mv_ret = mv_result["expected_return"]
            mv_sharpe = mv_result["sharpe_ratio"]
        except Exception as exc:
            st.caption(f"Live MV optimizer unavailable: {exc}. Showing mock comparison.")

    if mv_weights is None:
        hrp_w = portfolio.get("weights", {})
        mv_weights = {t: 0.0 for t in hrp_w}
        if hrp_w:
            tickers_list = list(hrp_w.keys())
            for t in tickers_list:
                if t in {"AGGH.MI", "TLT", "TIP"}:
                    mv_weights[t] = min(0.40, hrp_w.get(t, 0.10) * 1.8)
                elif t in {"CSPX.L", "EFA"}:
                    mv_weights[t] = max(0.03, hrp_w.get(t, 0.20) * 0.7)
                else:
                    mv_weights[t] = hrp_w.get(t, 0.10)
            total = sum(mv_weights.values()) or 1.0
            mv_weights = {t: round(w / total, 4) for t, w in mv_weights.items()}
        mv_vol = portfolio.get("expected_volatility", 0.08) * 0.92
        mv_ret = None
        mv_sharpe = None

    hrp_vol = portfolio.get("expected_volatility", 0.0)
    hrp_ret = portfolio.get("expected_return")
    hrp_sharpe = portfolio.get("sharpe_ratio")

    st.markdown("**Key Metrics — HRP vs Markowitz**")
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Annual Volatility",
        f"{hrp_vol:.1%}" if hrp_vol else "—",
        delta=f"MV: {mv_vol:.1%}" if mv_vol else None,
        delta_color="inverse",
    )
    col2.metric(
        "Expected Return",
        f"{hrp_ret:.1%}" if hrp_ret else "HRP: N/A",
        delta=f"MV: {mv_ret:.1%}" if mv_ret else None,
    )
    col3.metric(
        "Sharpe Ratio",
        f"{hrp_sharpe:.2f}" if hrp_sharpe else "HRP: N/A",
        delta=f"MV: {mv_sharpe:.2f}" if mv_sharpe else None,
    )
    st.caption(
        "HRP does not produce a reliable expected return estimate (no μ). "
        "MV maximises Sharpe explicitly but is sensitive to estimation error."
    )

    st.markdown("---")

    st.markdown("**Weight Comparison — HRP vs Markowitz**")
    hrp_weights = portfolio.get("weights", {})
    tickers_sorted = sorted(hrp_weights.keys(), key=lambda t: -hrp_weights.get(t, 0))
    comparison_rows = []
    for ticker in tickers_sorted:
        h = hrp_weights.get(ticker, 0.0)
        m = mv_weights.get(ticker, 0.0)
        comparison_rows.append({
            "Ticker": ticker,
            "HRP": f"{h:.1%}",
            "Markowitz": f"{m:.1%}",
            "Difference": f"{abs(h - m):.1%}",
            "UCITS": "EU" if ticker in _UCITS_TICKERS else "—",
        })
    st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, use_container_width=True)
    st.caption(
        "Markowitz typically produces more concentrated portfolios. "
        "HRP avoids corner solutions by construction."
    )

    st.markdown("---")

    st.markdown("**Efficient Frontier — HRP vs Markowitz**")
    try:
        frontier_vols = list(np.linspace(0.04, 0.20, 30))
        frontier_rets = [v * 0.5 + 0.01 for v in frontier_vols]
        fig_frontier = plot_efficient_frontier(
            frontier_vols=frontier_vols,
            frontier_rets=frontier_rets,
            hrp_vol=hrp_vol or 0.10,
            hrp_ret=hrp_ret,
            mv_vol=mv_vol or 0.08,
            mv_ret=mv_ret,
        )
        fig_frontier = apply_plotly_theme(fig_frontier)
        st.plotly_chart(fig_frontier, use_container_width=True)
        if portfolio.get("source") != "live":
            st.caption(
                "Frontier shown is illustrative (Phase A mock). "
                "Enable live data for real frontier."
            )
    except Exception as exc:
        st.caption(f"Frontier chart unavailable: {exc}")

    st.markdown("---")

    stress = portfolio.get("stress_scenarios")
    if stress is None:
        try:
            payload = get_mock_payload(profile_key)
            stress = payload.stress_scenarios
        except Exception:
            stress = None

    if stress is not None:
        st.markdown("**Historical Stress Scenarios — HRP drawdown vs benchmark**")
        scenario_rows = [
            {
                "Scenario": "COVID-19 crash (Mar 2020)",
                "HRP drawdown": f"{stress.covid_march_2020.portfolio_drawdown:.1%}",
                "Benchmark": f"{stress.covid_march_2020.benchmark_drawdown:.1%}",
            },
            {
                "Scenario": "Ukraine invasion (Feb 2022)",
                "HRP drawdown": f"{stress.ukraine_feb_2022.portfolio_drawdown:.1%}",
                "Benchmark": f"{stress.ukraine_feb_2022.benchmark_drawdown:.1%}",
            },
            {
                "Scenario": "Rate hike cycle (2022)",
                "HRP drawdown": f"{stress.rates_hike_2022.portfolio_drawdown:.1%}",
                "Benchmark": f"{stress.rates_hike_2022.benchmark_drawdown:.1%}",
            },
        ]
        st.dataframe(pd.DataFrame(scenario_rows), hide_index=True, use_container_width=True)
        st.caption(
            "Benchmark = equal-weight 60/40 portfolio. "
            "Phase A values are from mock data. "
            "Phase B will use real backtested values from backtest.py."
        )

    backtest = portfolio.get("backtest")
    if backtest is None:
        try:
            payload = get_mock_payload(profile_key)
            backtest = payload.backtest_summary
        except Exception:
            backtest = None

    if backtest is not None:
        st.markdown("**Backtest Summary (mock — Phase A)**")
        bt_cols = st.columns(4)
        bt_cols[0].metric("Period", backtest.period)
        bt_cols[1].metric("CAGR", f"{backtest.cagr:.1%}")
        bt_cols[2].metric("Sharpe", f"{backtest.sharpe:.2f}")
        bt_cols[3].metric("Max DD", f"{backtest.max_drawdown:.1%}")


# ---------------------------------------------------------------------------
# Page 3 -- Chat Advisor
# ---------------------------------------------------------------------------

def render_chat() -> None:
    """
    Chat Advisor — native Streamlit chat (st.chat_message + st.chat_input).

    Pipeline per turn: input sanitiser -> Claude narrator -> 5-step validator.
    The advisor only explains the current Ground Truth payload; it never gives
    buy/sell advice and cannot invent numbers.
    """
    _restore_persisted_profile()
    if not st.session_state.get("profile"):
        _render_profile_required_gate(
            "Chat Advisor", "Ask about your portfolio", "💬",
            "The advisor answers questions about your own personalised portfolio, so "
            "it needs your risk profile first. Complete the questionnaire and you can "
            "start chatting about your allocation here.",
            key="gate_chat_to_questionnaire",
        )
        return

    page_header(
        "Chat Advisor",
        "Grounded in your portfolio · validated answers",
        icon="💬",
    )
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)
    if is_light():
        st.markdown(_CHAT_CSS_LIGHT, unsafe_allow_html=True)

    profile_data = st.session_state.get("profile", {})
    raw_label = profile_data.get("profile_label", "MODERATE")
    profile_key = _LABEL_TO_MOCK.get(raw_label, "balanced")

    # Make the Anthropic key from st.secrets visible to NarratorClient (env-based).
    if "ANTHROPIC_API_KEY" not in os.environ:
        try:
            os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            pass

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    history: list[dict] = st.session_state["chat_history"]

    # Grab any pending prompt (submitted via the inline input or a suggestion).
    # The user message is added to history immediately so it appears in the
    # thread; the assistant reply is streamed live below.
    pending = st.session_state.pop("_pending_prompt", None)
    if pending:
        history.append({"role": "user", "content": pending})

    # Centered column holding one bordered "screen" that frames the whole chat.
    _, mid, _ = st.columns([1, 5, 1])
    with mid, st.container(border=True, key="ca_screen"):
        # Header bar: assistant identity + colour-coded status pills.
        st.markdown(_chat_header_html(raw_label), unsafe_allow_html=True)

        if not history:
            st.markdown(
                '<div class="ca-hero">'
                '<div class="ca-mark">✦</div>'
                '<div class="ca-hero-title">Ask me about your portfolio</div>'
                '<div class="ca-hero-sub">'
                "I explain your allocation, your risk, and how your portfolio held "
                'up through past crises — in plain English, using only the real '
                'numbers behind your dashboard.'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="ca-eyebrow">Try asking</div>', unsafe_allow_html=True
            )
            for i, txt in enumerate(_CHAT_SUGGESTIONS):
                if st.button(txt, key=f"chat_suggest_{i}", use_container_width=True):
                    st.session_state["_pending_prompt"] = txt
                    st.rerun()
        else:
            st.markdown('<div class="ca-thread">', unsafe_allow_html=True)
            for msg in history:
                with st.chat_message(
                    msg["role"], avatar=_CHAT_AVATARS.get(msg["role"])
                ):
                    st.markdown(msg["content"])

            # If a new user message was just submitted, stream the reply live.
            if pending:
                with st.chat_message(
                    "assistant", avatar=_CHAT_AVATARS.get("assistant")
                ):
                    _stream_placeholder = st.empty()
                reply = _chat_stream_reply(pending, profile_key, _stream_placeholder)
                history.append({"role": "assistant", "content": reply})

            st.markdown('</div>', unsafe_allow_html=True)

            # Ghost "Clear conversation" link below the thread.
            if st.button("Clear conversation", key="ca_clear_btn"):
                st.session_state["chat_history"] = []
                st.rerun()

        # Inline chat input — kept inside the screen so it renders in normal flow.
        typed = st.chat_input("Ask about your portfolio…")
        if typed:
            st.session_state["_pending_prompt"] = typed
            st.rerun()

        # Footer bar: always-visible safety pipeline (replaces the dropdown).
        st.markdown(_chat_footer_html(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page 4 -- Backtesting
# ---------------------------------------------------------------------------

_BACKTEST_DIR = Path(__file__).parent.parent / "backtest_output"

_SCENARIO_LABELS: dict[str, str] = {
    "gfc_2008":       "Global Financial Crisis (2008)",
    "covid_2020":     "COVID-19 Crash (2020)",
    "rate_hike_2022": "Rate Hike Cycle (2022)",
}

_STRATEGY_COLORS: dict[str, str] = {
    "HRP": "#7c5cfc",
    "MV":  "#f87171",
    "1/N": "#94a3b8",
}


def render_backtesting() -> None:
    _restore_persisted_profile()
    if not st.session_state.get("profile"):
        _render_profile_required_gate(
            "Backtesting", "Walk-forward simulation · HRP vs MV vs 1/N", "📈",
            "The backtesting results are tailored to your risk profile (Conservative, "
            "Moderate or Aggressive). Complete the questionnaire and the historical "
            "stress-scenario analysis will appear here.",
            key="gate_backtest_to_questionnaire",
        )
        return

    t = get_theme_tokens()
    page_header("Backtesting", "Walk-forward simulation · HRP vs MV vs 1/N", icon="📈")

    st.markdown(
        """
        <details class="qs-info-card">
          <summary>
            <span class="qs-info-title">What is backtesting?</span>
            <span class="qs-info-chevron">▾</span>
          </summary>
          <div class="qs-info-body">
            Backtesting replays each strategy on real historical prices to see how
            it would have performed in the past — including during market crashes.
            Pick a stress scenario below to compare how HRP, Mean-Variance (MV) and
            an equal-weight (1/N) portfolio held up.
          </div>
        </details>
        """,
        unsafe_allow_html=True,
    )

    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE").lower()

    summary_file = _BACKTEST_DIR / f"backtest_summary_{profile_label}.json"

    if not summary_file.exists():
        st.warning(
            f"Backtest data for **{profile_label.upper()}** profile not found. "
            "Run `scripts/run_backtest.py` to generate it."
        )
        # Try to fall back to moderate if available
        fallback_file = _BACKTEST_DIR / "backtest_summary_moderate.json"
        if fallback_file.exists():
            st.caption("Showing MODERATE profile data as fallback.")
            summary_file = fallback_file
            profile_label = "moderate"
        else:
            return

    with open(summary_file) as fh:
        summary = json.load(fh)

    selected = st.segmented_control(
        "Stress scenario",
        options=list(_SCENARIO_LABELS.keys()),
        format_func=lambda k: _SCENARIO_LABELS[k],
        default=list(_SCENARIO_LABELS.keys())[0],
        required=True,
    )
    if selected is None:
        return

    st.markdown("---")

    # ── Metrics comparison table ─────────────────────────────────────────────
    st.markdown("**Strategy comparison**")
    rows = []
    for strat, m in summary[selected]["strategies"].items():
        rows.append({
            "Strategy":   strat,
            "CAGR":       f"{m['cagr']:.1%}",
            "Volatility": f"{m['annualised_volatility']:.1%}",
            "Sharpe":     f"{m['sharpe_ratio']:.2f}",
            "Max DD":     f"{m['max_drawdown']:.1%}",
            "Calmar":     f"{m['calmar_ratio']:.2f}",
            "TC (bps)":   f"{m['total_transaction_cost']*10_000:.1f}",
        })
    _cols = ["Strategy", "CAGR", "Volatility", "Sharpe", "Max DD", "Calmar", "TC (bps)"]
    _head = "".join(
        f'<th style="padding:0.6rem 0.85rem;'
        f'text-align:{"left" if i == 0 else "right"};'
        f'font-family:\'Space Grotesk\',sans-serif;font-size:0.7rem;'
        f'font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'color:{t["accent_text"]};white-space:nowrap;">{c}</th>'
        for i, c in enumerate(_cols)
    )
    _body = ""
    for r in rows:
        cells = "".join(
            f'<td style="padding:0.55rem 0.85rem;'
            f'text-align:{"left" if i == 0 else "right"};font-size:0.82rem;'
            f'color:{t["text_primary"] if i == 0 else t["text_secondary"]};'
            f'font-weight:{"600" if i == 0 else "400"};'
            f'border-top:1px solid {t["border"]};white-space:nowrap;">{r[c]}</td>'
            for i, c in enumerate(_cols)
        )
        _body += f"<tr>{cells}</tr>"
    _head_bg = (
        "linear-gradient(135deg,#f8fafc 0%,#ede9fe 55%,#f1f4fa 100%)"
        if is_light() else
        "linear-gradient(135deg,#0f172a 0%,#1e1b4b 55%,#0d1220 100%)"
    )
    st.markdown(
        f'<div style="overflow-x:auto;border:1px solid {t["border"]};'
        f'border-radius:12px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:{_head_bg};'
        f'border-bottom:1px solid {t["border"]};">{_head}</tr></thead>'
        f"<tbody>{_body}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    # ── Key metrics for HRP ──────────────────────────────────────────────────
    hrp = summary[selected]["strategies"]["HRP"]
    mv  = summary[selected]["strategies"]["MV"]
    m_cols = st.columns(4)
    m_cols[0].metric("HRP CAGR",       f"{hrp['cagr']:.1%}",
                     delta=f"{(hrp['cagr'] - mv['cagr']):.1%} vs MV")
    m_cols[1].metric("HRP Sharpe",     f"{hrp['sharpe_ratio']:.2f}",
                     delta=f"{(hrp['sharpe_ratio'] - mv['sharpe_ratio']):.2f} vs MV")
    m_cols[2].metric("HRP Max DD",     f"{hrp['max_drawdown']:.1%}",
                     delta=f"{(hrp['max_drawdown'] - mv['max_drawdown']):.1%} vs MV",
                     delta_color="inverse")
    m_cols[3].metric("HRP Volatility", f"{hrp['annualised_volatility']:.1%}")

    st.markdown("---")

    # ── Equity curve chart ───────────────────────────────────────────────────
    scenario_file = _BACKTEST_DIR / f"backtest_{selected}_{profile_label}.json"
    if scenario_file.exists():
        with open(scenario_file) as fh:
            detail = json.load(fh)

        fig = go.Figure()
        for strat, strat_data in detail["strategies"].items():
            ec = strat_data["equity_curve"]
            fig.add_trace(go.Scatter(
                x=[e["date"] for e in ec],
                y=[e["portfolio_value"] for e in ec],
                mode="lines",
                name=strat,
                line=dict(color=_STRATEGY_COLORS.get(strat, "#64748b"), width=2),
                hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
            ))
        fig.add_hline(y=1.0, line_dash="dot", line_color="#475569", line_width=1)
        fig.update_layout(
            title=f"Equity Curve — {_SCENARIO_LABELS[selected]}",
            xaxis_title="Date",
            yaxis_title="Portfolio value (start = 1.0)",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig = apply_plotly_theme(fig)
        fig.update_layout(
            margin=dict(t=56),
            modebar_remove=[
                "select2d", "lasso2d", "autoScale2d",
                "hoverClosestCartesian", "hoverCompareCartesian",
                "toggleSpikelines", "zoomIn2d", "zoomOut2d",
            ],
            modebar_add=["resetScale2d"],
            dragmode="pan",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

        # ── Drawdown chart ───────────────────────────────────────────────────
        _DD_FILL: dict[str, str] = {
            "HRP": "rgba(124,92,252,0.08)",
            "MV":  "rgba(248,113,113,0.08)",
            "1/N": "rgba(148,163,184,0.08)",
        }
        fig_dd = go.Figure()
        for strat, strat_data in detail["strategies"].items():
            ec = strat_data["equity_curve"]
            vals = np.array([e["portfolio_value"] for e in ec])
            dates_dd = [e["date"] for e in ec]
            rolling_max = np.maximum.accumulate(vals)
            dd = (vals - rolling_max) / rolling_max * 100
            fig_dd.add_trace(go.Scatter(
                x=dates_dd, y=dd.tolist(),
                mode="lines", name=strat,
                line=dict(color=_STRATEGY_COLORS.get(strat, "#64748b"), width=1.5),
                fill="tozeroy",
                fillcolor=_DD_FILL.get(strat, "rgba(0,0,0,0)"),
                hovertemplate="%{y:.1f}%<extra>%{fullData.name}</extra>",
            ))
        fig_dd.update_layout(
            title="Drawdown (%)",
            xaxis_title="Date",
            yaxis_title="Drawdown (%)",
            height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig_dd = apply_plotly_theme(fig_dd)
        fig_dd.update_layout(
            margin=dict(t=56),
            modebar_remove=[
                "select2d", "lasso2d", "autoScale2d",
                "hoverClosestCartesian", "hoverCompareCartesian",
                "toggleSpikelines", "zoomIn2d", "zoomOut2d",
            ],
            modebar_add=["resetScale2d"],
            dragmode="pan",
        )
        st.plotly_chart(fig_dd, use_container_width=True, config={"displaylogo": False})

    st.caption(
        f"Profile: {profile_label.upper()} · Rebalancing: monthly · TC: 10 bps/rebalance · "
        "Lookback: 252 trading days"
    )


# ---------------------------------------------------------------------------
# Page 5 -- Compare MV
# ---------------------------------------------------------------------------

# Mock MV weights for Phase A (Markowitz concentrates in low-vol assets)
_MOCK_MV_WEIGHTS: dict[str, float] = {
    "CSPX.L":  0.08,
    "EFA":     0.04,
    "GLD":     0.07,
    "VNQ":     0.01,
    "AGGH.MI": 0.38,
    "TLT":     0.27,
    "TIP":     0.10,
    "XEON.MI": 0.05,
}


def render_compare() -> None:
    _restore_persisted_profile()
    if not st.session_state.get("profile"):
        _render_profile_required_gate(
            "Compare Markowitz", "Deep-dive analysis · HRP vs Markowitz", "⚖",
            "This page compares your own personalised portfolio against the classic "
            "Markowitz method, so it needs your risk profile first. Complete the "
            "questionnaire and the comparison will appear here.",
            key="gate_compare_to_questionnaire",
        )
        return

    thm = get_theme_tokens()
    page_header("Compare Markowitz", "Deep-dive analysis · HRP vs Markowitz", icon="🆚")

    _badge = (
        f"width:2.4rem;height:2.4rem;flex-shrink:0;border-radius:50%;"
        f"background:{thm['accent_soft']};border:1px solid {thm['accent_border']};"
        f"color:{thm['accent_text']};display:inline-flex;align-items:center;justify-content:center;"
    )
    _card = (
        f"background:{thm['accent_soft']};border:1px solid {thm['accent_border']};"
        f"border-radius:10px;padding:0.85rem 0.95rem;display:flex;gap:0.7rem;"
        f"align-items:flex-start;"
    )
    st.markdown(
        f"""
        <details class="qs-info-card">
          <summary>
            <span class="qs-info-title">Why compare HRP with Markowitz?</span>
            <span class="qs-info-chevron">▾</span>
          </summary>
          <div class="qs-info-body">
            <div style="font-size:0.82rem;color:{thm["text_secondary"]};line-height:1.55;
            margin-bottom:1rem;">
                HRP is our default optimizer. Markowitz is shown as the
                academic benchmark to explain why HRP is more robust for
                this robo-advisor.
            </div>
            <div style="display:grid;
            grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
            gap:0.75rem;margin-bottom:1rem;">
                <div style="{_card}">
                    <div style="{_badge}">{_ICON_SHIELD}</div>
                    <div>
                        <div style="font-family:'Space Grotesk',sans-serif;
                        font-size:0.82rem;font-weight:600;color:{thm["text_primary"]};
                        margin-bottom:0.3rem;">HRP is more robust</div>
                        <div style="font-size:0.76rem;color:{thm["text_secondary"]};
                        line-height:1.5;">No covariance matrix inversion. Less
                        sensitive to estimation errors.</div>
                    </div>
                </div>
                <div style="{_card}">
                    <div style="{_badge}">{_ICON_BARS}</div>
                    <div>
                        <div style="font-family:'Space Grotesk',sans-serif;
                        font-size:0.82rem;font-weight:600;color:{thm["text_primary"]};
                        margin-bottom:0.3rem;">Markowitz is the benchmark</div>
                        <div style="font-size:0.76rem;color:{thm["text_secondary"]};
                        line-height:1.5;">Useful to compare diversification,
                        concentration and stability.</div>
                    </div>
                </div>
                <div style="{_card}">
                    <div style="{_badge}">{_ICON_CAP}</div>
                    <div>
                        <div style="font-family:'Space Grotesk',sans-serif;
                        font-size:0.82rem;font-weight:600;color:{thm["text_primary"]};
                        margin-bottom:0.3rem;">Educational value</div>
                        <div style="font-size:0.76rem;color:{thm["text_secondary"]};
                        line-height:1.5;">Users see why the app recommends HRP,
                        not only the final weights.</div>
                    </div>
                </div>
            </div>
            <div style="text-align:center;">
                <span style="display:inline-block;
                font-family:'Space Grotesk',sans-serif;font-size:0.78rem;
                font-weight:600;color:{thm["accent_text"]};
                background:rgba(124,92,252,0.10);
                border:1px solid rgba(124,92,252,0.28);border-radius:999px;
                padding:0.4rem 1rem;">
                    HRP = recommendation &middot; Markowitz = comparison
                </span>
            </div>
          </div>
        </details>
        """,
        unsafe_allow_html=True,
    )

    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    portfolio = st.session_state.get("portfolio_data") or _mock_optimization(profile_key)
    hrp_weights: dict[str, float] = portfolio["weights"]
    hrp_rc: dict[str, float] = portfolio["risk_contributions"]
    _MAX_DD_FALLBACK = {"CONSERVATIVE": -0.112, "MODERATE": -0.187, "AGGRESSIVE": -0.312}
    hrp_vol: float = portfolio.get("expected_volatility") or 0.094
    hrp_ret: float = portfolio.get("expected_return") or 0.068
    hrp_max_dd: float = portfolio.get("max_drawdown") or _MAX_DD_FALLBACK.get(profile_label, -0.187)

    mv_weights: dict[str, float] = _MOCK_MV_WEIGHTS
    mv_vol: float = hrp_vol * 0.92
    mv_ret: float = hrp_ret * 0.78
    mv_max_dd: float = hrp_max_dd * 0.85

    _CLUSTER_VOL: dict[str, float] = {
        "CSPX.L": 0.162, "EFA": 0.162,
        "GLD": 0.138, "VNQ": 0.138,
        "AGGH.MI": 0.071, "TLT": 0.071, "TIP": 0.071,
        "XEON.MI": 0.003,
    }
    mv_raw_rc = {t: mv_weights.get(t, 0.0) * _CLUSTER_VOL.get(t, 0.10) for t in mv_weights}
    mv_total = sum(mv_raw_rc.values()) or 1.0
    mv_rc: dict[str, float] = {t: v / mv_total for t, v in mv_raw_rc.items()}

    # Prefer the real Markowitz risk contributions computed on live prices
    # (same covariance and same marginal formula as HRP — a fair comparison).
    # The weight x cluster-vol figures above remain only as an offline fallback.
    _mv_rc_live = portfolio.get("mv_risk_contributions")
    mv_rc_is_live = bool(_mv_rc_live)
    if mv_rc_is_live:
        mv_rc = _mv_rc_live

    st.markdown(f"**Active profile: {profile_label}**")
    st.markdown("---")

    # ── 1. Radar chart ────────────────────────────────────────────────────────
    _section_header("1", "Portfolio Quality Comparison")
    st.markdown(
        f"<p style='color:{thm['text_secondary']};font-size:0.82rem;"
        "line-height:1.55;margin-bottom:0.5rem;'>"
        "This chart summarizes the trade-offs between the recommended HRP portfolio and the "
        "classical Markowitz benchmark. Each dimension is normalized from 0 to 1, where higher "
        "values indicate a stronger result. The goal is to help users understand whether the HRP "
        "allocation is more diversified, more defensive, or more robust than the traditional "
        "mean-variance alternative."
        "</p>",
        unsafe_allow_html=True,
    )

    def _hhi(w: dict) -> float:
        return sum(v ** 2 for v in w.values())

    def _ucits_cov(w: dict) -> float:
        return sum(v for t, v in w.items() if t in _UCITS_TICKERS)

    hrp_scores = [
        max(0.0, 1.0 - (hrp_vol - 0.03) / 0.17),
        1.0 - _hhi(hrp_weights),
        _ucits_cov(hrp_weights),
        max(0.0, 1.0 + hrp_max_dd),
        min(1.0, hrp_ret / 0.12),
    ]
    mv_scores = [
        max(0.0, 1.0 - (mv_vol - 0.03) / 0.17),
        1.0 - _hhi(mv_weights),
        _ucits_cov(mv_weights),
        max(0.0, 1.0 + mv_max_dd),
        min(1.0, mv_ret / 0.12),
    ]

    categories = [
        "Low Risk",
        "Diversification",
        "UCITS Coverage",
        "Drawdown Protection",
        "Return Potential",
    ]

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=hrp_scores + [hrp_scores[0]],
        theta=categories + [categories[0]],
        fill="toself",
        name="HRP (default)",
        line=dict(color="#7c5cfc", width=2),
        fillcolor="rgba(124,92,252,0.15)",
    ))
    fig_radar.add_trace(go.Scatterpolar(
        r=mv_scores + [mv_scores[0]],
        theta=categories + [categories[0]],
        fill="toself",
        name="Markowitz MV",
        line=dict(color="#f87171", width=2),
        fillcolor="rgba(248,113,113,0.15)",
    ))
    fig_radar.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickvals=[0.5, 1.0],
                color="#475569",
                gridcolor="#1e2640",
                tickfont=dict(size=8, color="#475569"),
            ),
            angularaxis=dict(color="#94a3b8", gridcolor="#1e2640"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="center", x=0.5),
        height=440,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    fig_radar = apply_plotly_theme(fig_radar)
    _grid = "#e2e8f0" if is_light() else "#1e2640"
    fig_radar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            radialaxis=dict(gridcolor=_grid),
            angularaxis=dict(gridcolor=_grid),
        ),
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
    )
    _indicators = [
        ("#34d399", _ICON_BARS, "Diversification"),
        ("#94a3b8", _ICON_SHIELD, "Low Risk (Volatility)"),
        ("#a78bfa", _ICON_TREND, "Return Potential"),
        ("#f87171", _ICON_SHIELD, "Drawdown Protection"),
        ("#60a5fa", _ICON_GLOBE, "UCITS Coverage"),
    ]
    _ind_rows = "".join(
        f'<div style="display:flex;align-items:center;gap:0.55rem;'
        f'padding:0.5rem 0;border-top:1px solid {thm["border"]};">'
        f'<span style="width:1.7rem;height:1.7rem;flex-shrink:0;border-radius:7px;'
        f'display:inline-flex;align-items:center;justify-content:center;'
        f'background:{color}1a;border:1px solid {color}40;color:{color};">{icon}</span>'
        f'<span style="flex:1;font-size:0.8rem;color:{thm["text_secondary"]};">{label}</span>'
        f'<span style="font-size:0.72rem;font-weight:600;color:{thm["text_muted"]};">Higher</span>'
        f'</div>'
        for color, icon, label in _indicators
    )

    _col_chart, _col_ind = st.columns(
        [2, 1], gap="medium", vertical_alignment="center"
    )
    with _col_chart:
        st.plotly_chart(
            fig_radar, use_container_width=True, config={"displaylogo": False}
        )
    with _col_ind:
        _ind_head_bg = (
            "linear-gradient(135deg,#f8fafc 0%,#ede9fe 55%,#f1f4fa 100%)"
            if is_light() else
            "linear-gradient(135deg,#0f172a 0%,#1e1b4b 55%,#0d1220 100%)"
        )
        st.markdown(
            f'<div style="background:{thm["bg_card"]};border:1px solid {thm["border"]};'
            f'border-radius:14px;overflow:hidden;box-shadow:{thm["shadow"]};">'
            f'<div style="display:flex;align-items:center;gap:0.65rem;'
            f'padding:0.85rem 1.05rem;background:{_ind_head_bg};'
            f'border-bottom:1px solid {thm["border"]};">'
            f'<span style="font-family:\'Space Grotesk\',sans-serif;'
            f'font-size:0.78rem;font-weight:700;color:{thm["accent_text"]};'
            f'background:rgba(124,92,252,0.18);'
            f'border:1px solid rgba(124,92,252,0.3);border-radius:6px;'
            f'min-width:1.85rem;height:1.85rem;display:inline-flex;'
            f'align-items:center;justify-content:center;flex-shrink:0;">i</span>'
            f'<span style="font-family:\'Space Grotesk\',sans-serif;'
            f'font-size:0.92rem;font-weight:600;color:{thm["text_primary"]};">Indicators</span>'
            f'</div>'
            f'<div style="padding:0.9rem 1.05rem 1rem;">'
            f'<div style="display:flex;align-items:center;'
            f'justify-content:space-between;font-family:\'Space Grotesk\',sans-serif;'
            f'font-size:0.62rem;letter-spacing:0.14em;text-transform:uppercase;'
            f'color:{thm["text_muted"]};font-weight:600;margin-bottom:0.2rem;">'
            f'<span>Indicator</span><span>Better</span></div>'
            f'{_ind_rows}'
            f'<div style="font-size:0.68rem;color:{thm["text_muted"]};margin-top:0.6rem;'
            f'line-height:1.45;">Scores normalised to [0, 1]; 1 = best.</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    st.caption(
        "All axes normalised to [0, 1]. "
        "Low Risk = 1 − σ (normalised). "
        "Diversification = 1 − HHI (Herfindahl index). "
        "Drawdown Protection = 1 − |max DD|. "
        "Figures shown are illustrative."
    )

    # ── 2. Risk contributions ─────────────────────────────────────────────────
    st.markdown("---")
    _section_header("2", "Risk Contributions")
    st.markdown(
        f"<p style='color:{thm['text_secondary']};font-size:0.82rem;"
        "line-height:1.55;margin-bottom:0.5rem;'>"
        "Portfolio weights do not always reveal where risk really comes from. This chart shows "
        "each ETF's contribution to total portfolio risk and compares whether HRP and Markowitz "
        "distribute volatility evenly or concentrate it in a few assets."
        "</p>",
        unsafe_allow_html=True,
    )

    all_tickers = sorted(
        set(hrp_rc) | set(mv_rc),
        key=lambda t: -hrp_rc.get(t, 0.0),
    )
    hrp_rc_vals = [hrp_rc.get(t, 0.0) * 100 for t in all_tickers]
    mv_rc_vals = [mv_rc.get(t, 0.0) * 100 for t in all_tickers]

    # Plain-language, data-driven takeaway shown above the chart. Asset names
    # are made readable (e.g. "Gold (GLD)") and the wording adapts to the real
    # gap, so it never claims "HRP spreads / MV concentrates" when the numbers
    # disagree (e.g. if both happen to be evenly balanced for some profile).
    def _nice_asset(t: str) -> str:
        name = _TICKER_DISPLAY_NAME.get(t)
        return f"{name} ({t})" if name else t

    hrp_top_t = max(hrp_rc, key=hrp_rc.get) if hrp_rc else None
    mv_top_t = max(mv_rc, key=mv_rc.get) if mv_rc else None
    hrp_top = hrp_rc.get(hrp_top_t, 0.0) * 100 if hrp_top_t else 0.0
    mv_top = mv_rc.get(mv_top_t, 0.0) * 100 if mv_top_t else 0.0

    if mv_top - hrp_top >= 8:
        _headline = (
            f"Markowitz puts {mv_top:.0f}% of all portfolio risk in a single ETF "
            f"({_nice_asset(mv_top_t)}). HRP spreads it out — its largest "
            f"contributor is just {hrp_top:.0f}%."
        )
    elif hrp_top - mv_top >= 8:
        _headline = (
            f"HRP puts {hrp_top:.0f}% of all portfolio risk in a single ETF "
            f"({_nice_asset(hrp_top_t)}), while Markowitz's largest contributor "
            f"is {mv_top:.0f}%."
        )
    else:
        _headline = (
            f"Both methods spread risk fairly evenly — the largest single "
            f"contributor is {hrp_top:.0f}% (HRP) vs {mv_top:.0f}% (Markowitz)."
        )

    st.markdown(
        f"<div style='display:flex;gap:0.55rem;align-items:flex-start;"
        f"background:{thm['accent_soft']};border:1px solid {thm['accent_border']};"
        f"border-radius:12px;padding:0.7rem 0.9rem;margin-bottom:0.9rem;'>"
        f"<span style='color:{thm['accent_text']};font-size:1.1rem;line-height:1.3;"
        f"flex-shrink:0;'>&#9679;</span>"
        f"<span style='color:{thm['text_primary']};font-size:0.9rem;"
        f"line-height:1.5;'>{_headline}</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Overview: 100%-stacked risk, one row per method ──────────────────────
    # An immediate read of concentration: a wide segment (Markowitz on gold) vs
    # many slices (HRP). Coloured by the Portfolio Dashboard's asset-class
    # palette so the two pages stay visually consistent; same-class neighbours
    # are split by a thin separator and each asset is labelled inside its
    # segment. The legend sits above so it never overlaps the % axis below.
    _SEG_SHORT: dict[str, str] = {
        "CSPX.L": "US equity", "EFA": "Intl equity", "VNQ": "Real estate",
        "GLD": "Gold", "AGGH.MI": "Euro bonds", "TLT": "Treasuries",
        "TIP": "Infl. bonds", "XEON.MI": "Cash",
    }
    _CLASS_ORDER = {"Equity": 0, "Alternatives": 1, "Bonds": 2, "Cash": 3}
    _seg_order = sorted(
        all_tickers,
        key=lambda t: (_CLASS_ORDER.get(_HRP_TICKER_CLUSTER.get(t, "Cash"), 9),
                       -hrp_rc.get(t, 0.0)),
    )
    _methods = ["HRP", "Markowitz"]
    _seen_cls: set[str] = set()
    fig_stack = go.Figure()
    for t in _seg_order:
        cls = _HRP_TICKER_CLUSTER.get(t, "Cash")
        color = _HRP_CLUSTER_COLOR.get(cls, "#64748b")
        h = hrp_rc.get(t, 0.0) * 100
        m = mv_rc.get(t, 0.0) * 100
        short = _SEG_SHORT.get(t, t)
        disp = _TICKER_DISPLAY_NAME.get(t, t)
        # Label a segment inline only when it is wide enough to hold the text.
        seg_text = [
            f"{short} {h:.0f}%" if h >= 11 else "",
            f"{short} {m:.0f}%" if m >= 11 else "",
        ]
        fig_stack.add_trace(go.Bar(
            name=cls,
            legendgroup=cls,
            showlegend=cls not in _seen_cls,
            y=_methods,
            x=[h, m],
            orientation="h",
            marker=dict(color=color, line=dict(color="#0b1220", width=1.5)),
            text=seg_text,
            textposition="inside",
            insidetextanchor="middle",
            insidetextfont=dict(size=11, color="#f8fafc"),
            cliponaxis=False,
            hovertemplate=f"{disp} ({t}) — %{{x:.1f}}%<extra>%{{y}}</extra>",
        ))
        _seen_cls.add(cls)
    fig_stack = apply_plotly_theme(fig_stack)
    fig_stack.update_layout(
        barmode="stack",
        height=220,
        margin=dict(l=8, r=8, t=44, b=44),
        legend=dict(orientation="h", yanchor="bottom", y=1.04,
                    xanchor="center", x=0.5, font=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        dragmode=False,
    )
    fig_stack.update_xaxes(range=[0, 100], ticksuffix="%")
    fig_stack.update_yaxes(autorange="reversed")  # HRP row on top
    st.plotly_chart(fig_stack, use_container_width=True, config={"displaylogo": False})
    st.caption(
        "Each bar is 100% of that method's risk, split by asset and coloured by "
        "asset class — a wide segment means risk is piled into one holding. "
        "Below: the same figures per asset."
    )

    n_assets = len(all_tickers)
    equal_risk = 100.0 / n_assets if n_assets else 0.0

    fig_rc = go.Figure()
    fig_rc.add_trace(go.Bar(
        name="HRP · recommended",
        y=all_tickers,
        x=hrp_rc_vals,
        orientation="h",
        marker_color="#7c5cfc",
        text=[f"{v:.1f}%" for v in hrp_rc_vals],
        textposition="outside",
        textfont=dict(size=11),
        cliponaxis=False,
        hovertemplate="%{y} — risk %{x:.1f}%<extra>HRP</extra>",
    ))
    fig_rc.add_trace(go.Bar(
        name="Markowitz MV · benchmark",
        y=all_tickers,
        x=mv_rc_vals,
        orientation="h",
        marker_color="#f87171",
        text=[f"{v:.1f}%" for v in mv_rc_vals],
        textposition="outside",
        textfont=dict(size=11),
        cliponaxis=False,
        hovertemplate="%{y} — risk %{x:.1f}%<extra>MV</extra>",
    ))
    fig_rc.update_layout(
        barmode="group",
        xaxis_title="Share of total portfolio risk (%)",
        height=380,
        margin=dict(l=8, r=48, t=24, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    # "Equal risk" reference line: where every asset would sit if risk were split
    # perfectly evenly across the universe. HRP hugs it; MV departs from it.
    fig_rc.add_vline(
        x=equal_risk,
        line_width=1,
        line_dash="dash",
        line_color="#94a3b8",
        annotation_text=f"equal risk · {equal_risk:.0f}%",
        annotation_position="top",
        annotation_font=dict(size=11, color="#94a3b8"),
    )
    fig_rc = apply_plotly_theme(fig_rc)
    fig_rc.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
    )
    st.plotly_chart(fig_rc, use_container_width=True, config={"displaylogo": False})
    _rc_note = (
        ""
        if mv_rc_is_live
        else " Markowitz figures shown are an illustrative offline estimate."
    )
    st.caption(
        "Each bar is an asset's share of total portfolio risk; the bars for each "
        "method sum to 100%. The dashed line marks an equal split across all "
        "assets — HRP stays close to it, a balanced-risk design." + _rc_note
    )

    with st.expander("How is risk contribution calculated?"):
        st.markdown(
            "A **weight** tells you how much *money* you put in an asset; its "
            "**risk contribution** tells you how much *volatility* it adds to the "
            "whole portfolio — these are not the same thing."
        )
        st.latex(r"RC_i = \frac{w_i\,(\Sigma w)_i}{w^{\top}\Sigma w}")
        st.markdown(
            "where w are the portfolio weights and Σ is the covariance matrix. "
            "The values sum to 100%, so every bar is a slice of total risk. "
            "HRP and Markowitz use this same formula on the same covariance "
            "matrix, so the comparison is fair (Maillard et al., 2010)."
        )

    # ── 3. Correlation heatmap ────────────────────────────────────────────────
    st.markdown("---")
    _section_header("3", "Asset Correlation Matrix")
    st.markdown(
        f"<p style='color:{thm['text_secondary']};font-size:0.82rem;"
        "line-height:1.55;margin-bottom:0.5rem;'>"
        "Diversification is not only about holding many ETFs, but about combining assets that "
        "behave differently. This matrix shows the correlation structure of the ETF universe and "
        "explains why HRP groups some assets together while separating others."
        "</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        "How to read it: values in the matrix close to 1 indicate assets moving together, "
        "while values near 0 or below 0 indicate stronger diversification potential."
    )

    _TICKERS_HM = ["CSPX.L", "EFA", "GLD", "VNQ", "AGGH.MI", "TLT", "TIP", "XEON.MI"]
    _CORR = np.array([
        [ 1.00,  0.85,  0.05,  0.55, -0.15, -0.20, -0.05,  0.02],
        [ 0.85,  1.00,  0.08,  0.52, -0.12, -0.18, -0.03,  0.01],
        [ 0.05,  0.08,  1.00,  0.18,  0.22,  0.28,  0.30,  0.02],
        [ 0.55,  0.52,  0.18,  1.00, -0.02,  0.05,  0.10,  0.01],
        [-0.15, -0.12,  0.22, -0.02,  1.00,  0.82,  0.78,  0.05],
        [-0.20, -0.18,  0.28,  0.05,  0.82,  1.00,  0.75,  0.04],
        [-0.05, -0.03,  0.30,  0.10,  0.78,  0.75,  1.00,  0.03],
        [ 0.02,  0.01,  0.02,  0.01,  0.05,  0.04,  0.03,  1.00],
    ])

    fig_hm = go.Figure(go.Heatmap(
        z=_CORR.tolist(),
        x=_TICKERS_HM,
        y=_TICKERS_HM,
        colorscale=[
            [0.00, "#f87171"],
            [0.50, "#f1f4fa" if is_light() else "#111827"],
            [1.00, "#7c5cfc"],
        ],
        zmin=-1,
        zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in _CORR],
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="%{y} / %{x}: %{z:.2f}<extra></extra>",
        colorbar=dict(
            title="ρ",
            tickvals=[-1, -0.5, 0, 0.5, 1],
            thickness=12,
            len=0.85,
        ),
    ))
    fig_hm.update_layout(height=420, margin=dict(l=8, r=8, t=8, b=8))
    fig_hm = apply_plotly_theme(fig_hm)
    fig_hm.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        modebar_remove=[
            "select2d", "lasso2d", "autoScale2d",
            "hoverClosestCartesian", "hoverCompareCartesian",
            "toggleSpikelines", "zoomIn2d", "zoomOut2d",
        ],
        modebar_add=["resetScale2d"],
        dragmode="pan",
    )
    st.plotly_chart(fig_hm, use_container_width=True, config={"displaylogo": False})
    st.caption(
        "Correlation matrix used by HRP to build the hierarchical cluster tree. "
        "Negative equity–bond correlation (flight-to-quality) is the key diversification driver. "
        "The matrix shown is a stylised illustration."
    )


# ---------------------------------------------------------------------------
# Page 6 -- Settings
# ---------------------------------------------------------------------------

def _team_img_b64(filename: str) -> str:
    """Return a base64 data-URI for a team photo, or empty string if missing."""
    import base64 as _b64
    path = ASSETS_DIR / "team" / filename
    if path.exists():
        return "data:image/png;base64," + _b64.b64encode(path.read_bytes()).decode()
    return ""


def render_team_section() -> None:
    """Render the Team section on the Settings page."""
    _TEAM = [
        {
            "img": "p1_sabrina.png",
            "name": "Sabrina Virgillito",
            "role": "Backend Developer",
            "resp": "API · database design · data pipeline",
            "color": "#7c5cfc",
        },
        {
            "img": "p2_emma.png",
            "name": "Emma Erba",
            "role": "Quantitative Analyst",
            "resp": "Portfolio optimization · HRP · risk models",
            "color": "#0dcfb0",
        },
        {
            "img": "p3_matteo.png",
            "name": "Matteo Buttiglieri",
            "role": "ML Engineer",
            "resp": "ML profiling · model training · evaluation",
            "color": "#f87171",
        },
        {
            "img": "p4_elena.png",
            "name": "Elena Trombini",
            "role": "Frontend / LLM / Docs",
            "resp": "UI/UX · dashboard · LLM advisor · documentation",
            "color": "#fbbf24",
        },
    ]

    t = get_theme_tokens()
    cards_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:1rem;'
        'margin-top:0.75rem;justify-content:center;">'
    )
    for m in _TEAM:
        src = _team_img_b64(m["img"])
        img_tag = (
            f'<div style="width:100px;height:100px;border-radius:50%;'
            f'background:#ffffff;border:2px solid {m["color"]}55;'
            f'overflow:hidden;margin-bottom:0.65rem;flex-shrink:0;">'
            f'<img src="{src}" alt="{m["name"]}" '
            f'style="width:100%;height:100%;object-fit:cover;display:block;">'
            f'</div>'
            if src else
            f'<div style="width:100px;height:100px;border-radius:50%;'
            f'background:#ffffff;border:2px solid {m["color"]}55;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:1.5rem;margin-bottom:0.65rem;">👤</div>'
        )
        cards_html += (
            f'<div style="flex:1 1 200px;max-width:260px;'
            f'background:{t["bg_card"]};border:1px solid {t["border"]};'
            f'border-top:2px solid {m["color"]};border-radius:12px;'
            f'padding:1.1rem 1rem;display:flex;flex-direction:column;'
            f'align-items:center;text-align:center;box-shadow:{t["shadow"]};">'
            f'{img_tag}'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:0.9rem;'
            f'font-weight:600;color:{t["text_primary"]};margin-bottom:0.2rem;">{m["name"]}</div>'
            f'<div style="font-size:0.75rem;font-weight:600;color:{m["color"]};'
            f'letter-spacing:0.03em;margin-bottom:0.4rem;">{m["role"]}</div>'
            f'<div style="font-size:0.73rem;color:{t["text_muted"]};'
            f'line-height:1.5;">{m["resp"]}</div>'
            f'</div>'
        )
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)


def render_settings() -> None:
    """Platform configuration and status page."""
    _gear_svg = (
        '<svg width="44" height="44" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="1.5"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83'
        'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0'
        'v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83'
        '-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4'
        'h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83'
        '-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0'
        'v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83'
        ' 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4'
        'h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
        "</svg>"
    )
    _wave_svg = (
        '<svg style="position:absolute;inset:0;width:100%;height:100%;'
        'opacity:0.6;" preserveAspectRatio="none" viewBox="0 0 800 220" fill="none">'
        '<path d="M300 150 C 380 100,460 165,540 120 S 700 80,830 120" '
        'stroke="#7c5cfc" stroke-opacity="0.28" stroke-width="1"/>'
        '<path d="M320 128 C 400 88,480 138,560 102 S 720 66,850 102" '
        'stroke="#a78bfa" stroke-opacity="0.20" stroke-width="1"/>'
        '<path d="M300 172 C 390 130,470 182,560 140 S 730 102,860 140" '
        'stroke="#6d5ae0" stroke-opacity="0.22" stroke-width="1"/>'
        '<path d="M340 108 C 420 76,500 118,580 86 S 740 54,870 86" '
        'stroke="#8b5cf6" stroke-opacity="0.16" stroke-width="1"/>'
        '<path d="M360 192 C 440 156,520 200,600 162 S 760 128,880 162" '
        'stroke="#7c5cfc" stroke-opacity="0.14" stroke-width="1"/>'
        "</svg>"
    )
    t = get_theme_tokens()
    hero_bg = (
        "radial-gradient(120% 160% at 88% 50%,rgba(124,77,255,0.12) 0%,"
        "rgba(246,247,251,0) 48%),linear-gradient(135deg,#ffffff 0%,#f1f4fa 60%,#ffffff 100%)"
        if is_light() else
        "radial-gradient(120% 160% at 88% 50%,rgba(124,92,252,0.16) 0%,"
        "rgba(13,18,32,0) 48%),linear-gradient(135deg,#0d1220 0%,#141a30 60%,#0d1220 100%)"
    )
    st.markdown(
        f'<div style="position:relative;overflow:hidden;border:1px solid {t["border"]};'
        f'border-radius:16px;padding:2rem 2.25rem;margin-bottom:1.5rem;'
        f'background:{hero_bg};box-shadow:{t["shadow"]};'
        f'display:flex;align-items:center;justify-content:space-between;'
        f'gap:1.5rem;flex-wrap:wrap;">'
        f'{_wave_svg}'
        f'<div style="position:relative;z-index:1;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:0.72rem;'
        f'font-weight:700;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{t["accent_text"]};margin-bottom:0.5rem;">Configuration</div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2.4rem;'
        f'font-weight:700;color:{t["text_primary"]};letter-spacing:-0.02em;'
        f'line-height:1.1;">Settings</div>'
        f'<div style="font-size:0.95rem;color:{t["text_secondary"]};margin-top:0.4rem;">'
        f'Platform configuration</div>'
        f'</div>'
        f'<div style="position:relative;z-index:1;width:5rem;height:5rem;'
        f'flex-shrink:0;border-radius:16px;color:{t["accent"]};'
        f'background:radial-gradient(circle at 50% 40%,'
        f'rgba(124,92,252,0.35),rgba(124,92,252,0.06));'
        f'border:1px solid rgba(124,92,252,0.4);'
        f'box-shadow:0 0 32px rgba(124,92,252,0.32);'
        f'display:inline-flex;align-items:center;justify-content:center;">'
        f'{_gear_svg}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _badge = (
        f"width:2.4rem;height:2.4rem;flex-shrink:0;border-radius:9px;"
        f"background:{t['accent_soft']};border:1px solid {t['accent_border']};"
        f"color:{t['accent_text']};display:inline-flex;align-items:center;"
        f"justify-content:center;"
    )
    _db_icon = (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
        "</svg>"
    )

    st.markdown("---")

    _section_header("", "Appearance")
    current_theme = st.session_state.get("theme", "dark")
    col_theme, _ = st.columns([2, 3])
    with col_theme:
        theme_choice = st.radio(
            "Color mode",
            options=["Dark", "Light"],
            index=0 if current_theme == "dark" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
    if (theme_choice == "Light") != (current_theme == "light"):
        st.session_state["theme"] = "light" if theme_choice == "Light" else "dark"
        st.rerun()

    st.markdown("---")

    _section_header("", "Data Source")
    st.markdown(
        f'<div style="background:{t["bg_card"]};border:1px solid {t["border"]};'
        f'border-radius:12px;padding:1rem 1.15rem;display:flex;gap:0.85rem;'
        f'align-items:center;box-shadow:{t["shadow"]};">'
        f'<div style="{_badge}">{_db_icon}</div>'
        f'<div style="font-size:0.82rem;color:{t["text_secondary"]};line-height:1.6;">'
        f'The Portfolio Dashboard always uses live market data (prices via '
        f'yfinance) and runs the HRP optimizer on the latest available history. '
        f'If the network is briefly unreachable it falls back to a cached '
        f'reference allocation so the app keeps working.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    _section_header("", "API Status")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            api_key = ""
    if api_key:
        st.success("Claude API key configured ✓")
    else:
        st.error("Claude API key not found — Chat Advisor will not work.")

    st.markdown("---")
    _section_header("", "Team")
    render_team_section()

    st.markdown("---")
    _section_header("", "About")
    st.markdown(
        f'<div style="background:{t["bg_card"]};border:1px solid {t["border"]};'
        f'border-radius:12px;padding:1rem 1.15rem;display:flex;gap:0.85rem;'
        f'align-items:center;box-shadow:{t["shadow"]};">'
        f'<div style="width:2.4rem;height:2.4rem;flex-shrink:0;border-radius:9px;'
        f'background:linear-gradient(135deg,#7c5cfc 0%,#5b3fd1 100%);'
        f'display:inline-flex;align-items:center;justify-content:center;'
        f'font-family:\'Space Grotesk\',sans-serif;font-size:1.1rem;'
        f'font-weight:700;color:#ffffff;">R</div>'
        f'<div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:0.88rem;'
        f'font-weight:600;color:{t["text_primary"]};margin-bottom:0.2rem;">'
        f'AI-Powered Robo-Advisor Platform</div>'
        f'<div style="font-size:0.76rem;color:{t["text_muted"]};line-height:1.55;">'
        f'USI Programming in Finance II · 2026<br>'
        f'Design v3.1 · HRP + LLM Narrator + EU Awareness</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
main()
