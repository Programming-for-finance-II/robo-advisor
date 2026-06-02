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

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from backend.llm.narrator import NarratorClient
from backend.llm.validator import validate
from backend.schemas.mock_data import get_mock_payload
from frontend.style import (
    apply_plotly_dark_theme,
    inject_css,
    page_header,
    render_disclaimer,
    render_eu_note,
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
LOGO_PATH = ASSETS_DIR / "logo.png"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def show_disclaimer() -> None:
    # Show the mandatory MiFID II disclaimer at the top of every page
    render_disclaimer()  # use HTML custom of style.py


# ---------------------------------------------------------------------------
# Portfolio data loading
# Two paths:
#   Phase A (default) -- get_mock_payload(), instant, no network needed
#   Phase B (live)    -- download real prices, run HRP, detect regime
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
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

    return {
        "weights": result["weights"],
        "risk_contributions": result["risk_contributions"],
        "expected_volatility": result["expected_volatility"],
        "expected_return": result["expected_return"],
        "sharpe_ratio": result["sharpe_ratio"],
        "ucits_tickers_used": report.ucits_tickers_used,
        "fallback_tickers_applied": list(report.fallback_tickers_applied.keys()),
        "recommendation_id": str(uuid.uuid4()),
        "stress_regime": regime_result.regime,
        "avg_correlation": regime_result.avg_correlation,
        "source": "live",
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

_NAV_SVGS: dict[str, str] = {
    "Questionnaire": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="8" y="2" width="8" height="4" rx="1"/>'
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6'
        'a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
        '<line x1="12" y1="11" x2="16" y2="11"/>'
        '<line x1="12" y1="16" x2="16" y2="16"/>'
        '<circle cx="8" cy="11" r="1" fill="currentColor" stroke="none"/>'
        '<circle cx="8" cy="16" r="1" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
    "Portfolio Dashboard": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>'
        '<path d="M22 12A10 10 0 0 0 12 2v10z"/>'
        "</svg>"
    ),
    "Chat Advisor": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14'
        'a2 2 0 0 1 2 2z"/>'
        "</svg>"
    ),
    "Backtesting": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
        '<polyline points="17 6 23 6 23 12"/>'
        "</svg>"
    ),
    "Compare Markowitz": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="12" y1="2" x2="12" y2="22"/>'
        '<path d="M5 7 2 14h6z"/>'
        '<path d="M19 7 22 14h-6z"/>'
        '<line x1="5" y1="7" x2="19" y2="7"/>'
        '<line x1="9" y1="2" x2="15" y2="2"/>'
        "</svg>"
    ),
    "Settings": (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2"'
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
    ),
}

_SHIELD_SVG = (
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
    "</svg>"
)


def main() -> None:
    # UNIFIED TOP NAVBAR (apple.com style) — replaces separate logo block
    # and nav row. Only this section was modified. Do not edit elsewhere.

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
            f'width:44px;height:44px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'background:rgba(124,92,252,0.10);'
            f'border:1px solid rgba(124,92,252,0.28);'
            f'border-radius:12px;'
            f'box-shadow:0 0 12px rgba(124,92,252,0.18);'
            f'flex-shrink:0;">'
            f'<img src="data:image/png;base64,{_logo_b64}"'
            f' style="height:30px;width:auto;" alt="RoboAdvisor">'
            f'</div>'
        )
    else:
        _logo_tag = (
            '<div style="'
            'width:44px;height:44px;'
            'display:flex;align-items:center;justify-content:center;'
            'background:rgba(124,92,252,0.10);'
            'border:1px solid rgba(124,92,252,0.28);'
            'border-radius:12px;'
            'box-shadow:0 0 12px rgba(124,92,252,0.18);'
            'flex-shrink:0;">'
            '<span style="font-size:1.3rem;font-weight:700;color:#f5f5f7;'
            "font-family:'Space Grotesk',sans-serif;\">R</span>"
            '</div>'
        )

    # Step 3: render brand HTML + CSS; nav buttons added as st.columns below
    st.markdown(
        f"""<style>
/* ── Reset Streamlit chrome ─────────────────────────────────────────── */
header[data-testid="stHeader"] {{ display: none !important; }}
[data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden; }}
section[data-testid="stMain"] > div:first-child {{
    padding-top: 72px !important;
}}
/* ── Apple-style top navbar ─────────────────────────────────────────── */
.top-navbar {{
    position: fixed; top: 0; left: 0;
    width: 100%; height: 60px; z-index: 1000;
    background: rgba(29,29,31,0.88);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 40px; box-sizing: border-box;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    flex-wrap: nowrap;
    overflow: visible;
}}
.top-navbar .brand {{
    display: flex; align-items: center; gap: 12px;
    min-width: 240px; flex-shrink: 0; text-decoration: none;
}}
.top-navbar .brand-name {{
    font-size: 16px; font-weight: 700; color: #f5f5f7;
    letter-spacing: -0.3px; line-height: 1.2;
    font-family: 'Space Grotesk', -apple-system, sans-serif;
}}
.top-navbar .brand-sub {{
    font-size: 9.5px; letter-spacing: 0.09em;
    color: rgba(245,245,247,0.42); text-transform: uppercase;
    line-height: 1.3; margin-top: 2px;
}}
/* ── Streamlit button row moved inside navbar by JS ─────────────────── */
.top-navbar [data-testid="stHorizontalBlock"] {{
    display: flex !important; align-items: center !important;
    flex: 1 1 auto !important; justify-content: flex-end !important;
    gap: 4px !important; background: transparent !important;
    padding: 0 !important; margin: 0 !important;
    flex-wrap: nowrap !important; min-width: 0 !important;
    overflow: visible !important; max-height: 60px !important;
}}
.top-navbar [data-testid="stHorizontalBlock"] > div {{
    flex: 0 0 auto !important; width: auto !important;
    min-width: unset !important; padding: 0 !important;
    max-height: 60px !important;
}}
.top-navbar .stButton > button {{
    background: transparent !important;
    border: none !important; box-shadow: none !important;
    color: rgba(245,245,247,0.68) !important;
    font-size: 13px !important; font-weight: 400 !important;
    letter-spacing: -0.1px !important;
    padding: 5px 11px !important; border-radius: 6px !important;
    min-height: unset !important; height: 32px !important;
    white-space: nowrap !important;
    transition: color 0.18s ease, background 0.18s ease !important;
    font-family: -apple-system, 'Space Grotesk', sans-serif !important;
}}
.top-navbar .stButton > button:hover {{
    color: #f5f5f7 !important;
    background: rgba(255,255,255,0.07) !important;
}}
.top-navbar [data-testid="baseButton-primary"] {{
    color: #f5f5f7 !important; font-weight: 500 !important;
    background: rgba(255,255,255,0.10) !important;
}}
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
        padding-top: 64px !important;
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

    # Step 5: JS — move stHorizontalBlock into .top-navbar, then watch overflow
    import streamlit.components.v1 as _stc
    _stc.html(
        """<script>
(function () {
    /* Move the nav button row into the fixed .top-navbar element. */
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
# Page 1 -- Questionnaire
# ---------------------------------------------------------------------------

def render_questionnaire() -> None:
    page_header("Investor Profile Questionnaire", "Grable-Lytton Scale · 10 questions", icon="🧭")
    render_disclaimer()

    # Info card — Grable-Lytton explanation (native <details> for full style control)
    st.markdown(
        """
        <details class="qs-info-card">
          <summary>
            <span class="qs-info-icon">🎓</span>
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
    st.markdown(
        """
        <div style="display:flex;align-items:flex-start;
            padding:1rem 1.5rem;margin:0 0 1.25rem 0;
            background:rgba(15,23,42,0.55);
            border:1px solid #1e2640;border-radius:12px;">

          <div style="display:flex;flex-direction:column;align-items:center;gap:0.4rem;">
            <div style="width:2.8rem;height:2.8rem;border-radius:50%;
              background:rgba(59,130,246,0.15);border:2px solid #3b82f6;
              display:flex;align-items:center;justify-content:center;
              font-family:'Space Grotesk',sans-serif;
              font-size:0.88rem;font-weight:700;color:#60a5fa;">01</div>
            <div style="font-size:0.75rem;font-weight:500;color:#60a5fa;
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
              font-size:0.88rem;font-weight:700;color:#a78bfa;">02</div>
            <div style="font-size:0.75rem;font-weight:500;color:#a78bfa;
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
              font-size:0.88rem;font-weight:700;color:#fbbf24;">03</div>
            <div style="font-size:0.75rem;font-weight:500;color:#fbbf24;
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

    if st.session_state.get("profile"):
        result = st.session_state["profile"]

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
        rm = _RESULT_META.get(result["profile_label"], _RESULT_META["MODERATE"])
        score_pct = result["score"] / 30 * 100  # max possible = 10 × 3 = 30

        # ── top drivers text ────────────────────────────────────────────────
        driver_labels = {
            "Q1": "Age", "Q2": "Income", "Q3": "Liquidity",
            "Q4": "Dependents", "Q5": "Experience", "Q6": "Knowledge",
            "Q7": "Investment purpose", "Q8": "Loss reaction",
            "Q9": "Recovery horizon", "Q10": "Self-assessment",
        }
        top3 = result.get("top_drivers", [])[:3]
        drivers_chips = "".join(
            '<span style="background:rgba(255,255,255,0.06);border:1px solid #2d3a52;'
            'border-radius:7px;padding:0.3rem 0.75rem;font-size:0.85rem;'
            'font-weight:500;color:#94a3b8;">'
            + driver_labels.get(d["feature"], d["feature"]) + "</span>"
            for d in top3
        )
        # Pre-build the optional drivers block — avoids nested f-string inside the card
        drivers_block = (
            '<div style="font-size:0.75rem;font-weight:600;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#64748b;margin-bottom:0.55rem;">'
            'Top scoring factors</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:0.5rem;">'
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
            f'<div style="font-size:0.9rem;color:#64748b;margin-top:0.4rem;">{rm["desc"]}</div>'
            f'</div></div>'

            # ── metrics row ──────────────────────────────────────────────────
            f'<div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.25rem;">'

            # score card
            f'<div style="flex:1;min-width:120px;background:rgba(0,0,0,0.25);'
            f'border:1px solid #1e2640;border-radius:10px;padding:0.75rem 1.1rem;">'
            f'<div style="font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'
            f'color:#475569;margin-bottom:0.35rem;">Score</div>'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.7rem;'
            f'font-weight:700;color:#f1f5f9;line-height:1;">'
            f'{result["score"]}'
            f'<span style="font-size:0.85rem;color:#475569;font-weight:400;">/30</span></div>'
            f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;'
            f'background:#1e2640;overflow:hidden;">'
            f'<div style="height:100%;width:{score_pct:.0f}%;'
            f'background:{rm["bar_gradient"]};border-radius:3px;"></div>'
            f'</div></div>'

            # confidence card
            f'<div style="flex:1;min-width:120px;background:rgba(0,0,0,0.25);'
            f'border:1px solid #1e2640;border-radius:10px;padding:0.75rem 1.1rem;">'
            f'<div style="font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'
            f'color:#475569;margin-bottom:0.35rem;">Model Confidence</div>'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.7rem;'
            f'font-weight:700;color:{rm["color"]};line-height:1;">{conf_pct}%</div>'
            f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;'
            f'background:#1e2640;overflow:hidden;">'
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

        if st.button(
            "View my Portfolio Dashboard →",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.active_page = "Portfolio Dashboard"
            st.query_params["page"] = "Portfolio Dashboard"
            st.rerun()


# ---------------------------------------------------------------------------
# Page 2 -- Portfolio Dashboard
# ---------------------------------------------------------------------------

def render_portfolio() -> None:
    """
    Portfolio Dashboard with two tabs: HRP and Markowitz benchmark.

    Data source:
        Phase A (default): mock payload from backend/schemas/mock_data.py
        Phase B (live toggle on): ValidatedDataLoader + HRP + regime detector
    """
    # Read profile first so we can use it in the header
    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    confidence = profile_data.get("confidence", None)
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    page_header(
        "Portfolio Dashboard",
        f"HRP optimization · {profile_label.capitalize()} profile",
        icon="📊",
    )
    render_disclaimer()

    st.markdown(
        """
        <div style="background:rgba(30,38,64,0.5);border:1px solid #1e2640;
        border-radius:10px;padding:0.9rem 1rem;margin-bottom:1.25rem;
        display:flex;gap:0.875rem;align-items:flex-start;">
            <div style="width:2rem;height:2rem;flex-shrink:0;
            background:rgba(124,92,252,0.12);border:1px solid rgba(124,92,252,0.25);
            border-radius:7px;display:inline-flex;align-items:center;
            justify-content:center;font-size:0.95rem;">📐</div>
            <div>
                <div style="font-family:'Space Grotesk',sans-serif;font-size:0.9rem;
                font-weight:600;color:#e2e8f0;margin-bottom:0.25rem;">
                    Hierarchical Risk Parity (HRP)
                </div>
                <div style="font-size:0.79rem;color:#64748b;line-height:1.55;">
                    HRP (López de Prado, 2016) clusters assets by correlation, then allocates
                    weights so that each cluster contributes equally to total portfolio risk.
                    Unlike Markowitz, it requires no expected-return estimates and avoids
                    corner solutions. Covariance is shrunk via Ledoit-Wolf.
                    Weights are constrained to 5–40% per asset and 10–60% per cluster.
                </div>
            </div>
        </div>
        """,
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
        f'font-size:0.68rem;font-weight:600;letter-spacing:0.06em;'
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
        f'<div style="font-size:0.82rem;color:#94a3b8;margin-bottom:0.5rem;line-height:1.5;">'
        f'{pm["desc"]}{conf_inline}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:0.35rem;">{badges_html}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    default_live = (
        st.session_state.get("default_data_mode", "")
        == "Live market data (Phase B — requires network)"
    )

    # Toggle between mock data (Phase A) and live optimizer (Phase B)
    use_live = st.toggle(
        "Use live market data",
        value=default_live,
        help=(
            "When disabled, the dashboard uses stable mock data for demonstration. "
            "When enabled, it attempts to load current market prices via yfinance "
            "and runs the HRP optimizer. Takes about 10 seconds on first load."
        ),
    )

    # Load portfolio data, either from cache or by running the optimizer
    portfolio = st.session_state.get("portfolio_data", {})
    cached_label = st.session_state.get("portfolio_profile", "")

    if use_live and (not portfolio or cached_label != profile_label):
        # Run the live optimizer and store the result in session_state
        with st.spinner("Downloading data and running HRP optimizer..."):
            try:
                portfolio = _run_live_optimization(profile_label)
                st.session_state["portfolio_data"] = portfolio
                st.session_state["portfolio_profile"] = profile_label
                st.session_state["recommendation_id"] = portfolio["recommendation_id"]
            except Exception as exc:
                # Live data failed -- fall back to mock so the app keeps working
                st.warning(f"Live data unavailable ({exc}). Using mock data instead.")
                portfolio = _mock_optimization(profile_key)
                st.session_state["portfolio_data"] = portfolio
                st.session_state["portfolio_profile"] = profile_label
                st.session_state["recommendation_id"] = portfolio["recommendation_id"]
    elif not portfolio or cached_label != profile_label:
        # Default path: load mock data (Phase A, always works)
        portfolio = _mock_optimization(profile_key)
        st.session_state["portfolio_data"] = portfolio
        st.session_state["portfolio_profile"] = profile_label
        st.session_state["recommendation_id"] = portfolio["recommendation_id"]

    # Show where the data comes from
    if portfolio.get("source") == "live":
        st.success("Live market data loaded successfully.")
    else:
        st.caption("Showing mock data (Phase A). Enable the toggle above for live prices.")

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


def _build_perf_chart(exp_ret: float, vol: float, n_days: int, seed: int = 42):
    """
    Build a synthetic cumulative-return line chart (HRP vs 60/40 benchmark).
    Uses a fixed-seed RNG so the chart is stable across Streamlit reruns.
    """
    from datetime import date, timedelta

    import numpy as np
    import plotly.graph_objects as go

    rng = np.random.default_rng(seed)
    daily_mean = exp_ret / 252
    daily_std = vol / np.sqrt(252)

    hrp_cum = 100.0 * np.cumprod(1.0 + rng.normal(daily_mean, daily_std, n_days))

    rng_bm = np.random.default_rng(seed + 1)
    bm_cum = 100.0 * np.cumprod(1.0 + rng_bm.normal(0.05 / 252, 0.09 / np.sqrt(252), n_days))

    end = date.today()
    dates = [end - timedelta(days=n_days - i) for i in range(n_days)]

    all_vals = np.concatenate([hrp_cum, bm_cum])
    y_min = float(all_vals.min())
    y_max = float(all_vals.max())
    y_pad = (y_max - y_min) * 0.05

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=hrp_cum.tolist(),
        mode="lines", name="HRP Portfolio",
        line=dict(color="#7c5cfc", width=2),
        fill="tozeroy",
        fillcolor="rgba(124,92,252,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=bm_cum.tolist(),
        mode="lines", name="60/40 Benchmark",
        line=dict(color="#94a3b8", width=2, dash="dot"),
    ))
    fig.update_layout(
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(
            title="Portfolio value (base 100)",
            range=[y_min - y_pad, y_max + y_pad],
        ),
        hovermode="x unified",
    )
    return fig


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

_PROFILE_COLOR: dict[str, str] = {
    "CONSERVATIVE": "#0dcfb0",
    "MODERATE":     "#7c5cfc",
    "AGGRESSIVE":   "#f87171",
}

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


def _sparkline(trend: list[int]) -> str:
    """Convert a list of 1–7 integers into a Unicode bar sparkline."""
    bars = "▁▂▃▄▅▆▇"
    mx = max(trend) or 1
    return "".join(bars[round((v / mx) * 6)] for v in trend)


def _section_header(number: str, title: str) -> None:
    st.markdown(
        f'<div style="border-left:3px solid #7c5cfc;padding-left:0.875rem;margin-bottom:0.75rem;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;'
        f'font-size:1.05rem;font-weight:600;color:#f1f5f9;">{number}. {title}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _section_desc(text: str) -> None:
    st.markdown(
        f'<div style="font-size:0.82rem;color:#64748b;line-height:1.65;'
        f'margin-bottom:1.25rem;">{text}</div>',
        unsafe_allow_html=True,
    )


def _v_spacer(rem: float = 2.0) -> None:
    st.markdown(f'<div style="height:{rem}rem"></div>', unsafe_allow_html=True)


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
    css_rules = [
        'div[class*="st-key-pill_"] button {'
        ' background: rgba(255,255,255,0.05) !important;'
        ' border: 1px solid rgba(255,255,255,0.10) !important;'
        ' color: #94a3b8 !important; border-radius: 18px !important;'
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

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=sliced.index, y=sliced.values,
                mode="lines",
                line=dict(color=line_color, width=2),
                fill="tozeroy", fillcolor=fill_color,
                name=selected,
            ))
            fig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0),
                height=220,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                hovermode="x",
                xaxis=dict(showgrid=False, color="#64748b"),
                yaxis=dict(
                    side="right", showgrid=True,
                    gridcolor="rgba(255,255,255,0.05)", color="#64748b",
                ),
            )
            chart_config = {
                "modeBarButtonsToRemove": [
                    "select2d", "lasso2d", "autoScale2d",
                    "hoverClosestCartesian", "hoverCompareCartesian",
                    "toggleSpikelines",
                ],
                "modeBarButtonsToAdd": [
                    "zoomIn2d", "zoomOut2d", "pan2d", "resetScale2d", "toImage",
                ],
                "displaylogo": False,
            }
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
        f'<div style="font-size:0.8rem;color:#94a3b8;margin:0.25rem 0 0.5rem 0;">'
        f'Period return: <span style="color:#f1f5f9;font-weight:600;">{pr_str}</span>'
        f' &nbsp;|&nbsp; TER: <span style="color:#f1f5f9;font-weight:600;">'
        f'{meta["ter"]}</span>'
        f' &nbsp;|&nbsp; AUM: <span style="color:#f1f5f9;font-weight:600;">'
        f'{meta["aum"]}</span></div>',
        unsafe_allow_html=True,
    )

    _v_spacer(1.5)

    # ── Panel 3 (Section 2): description card ────────────────────────────
    _section_header("2", "What this ETF holds")
    stats_rows = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:1rem;'
        f'padding:0.4rem 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
        f'<span style="font-size:0.78rem;color:#64748b;">{k}</span>'
        f'<span style="font-size:0.78rem;color:#e2e8f0;font-weight:600;">{v}</span>'
        f'</div>'
        for k, v in meta["key_stats"].items()
    )
    ucits_tag = "UCITS-eligible" if etf.is_ucits else "US-listed (non-UCITS)"
    st.markdown(
        f'<div style="background:rgba(124,92,252,0.05);'
        f'border:1px solid rgba(124,92,252,0.18);border-radius:12px;'
        f'padding:1.1rem 1.25rem;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.05rem;'
        f'font-weight:700;color:#f1f5f9;">{meta["full_name"]}</div>'
        f'<div style="font-size:0.74rem;color:#64748b;margin:0.3rem 0 0.85rem 0;">'
        f'{meta["issuer"]} &middot; {meta["category"]} &middot; '
        f'Inception {meta["inception"]} &middot; {meta["distribution"]} &middot; '
        f'{etf.currency} &middot; {ucits_tag}</div>'
        f'<div style="font-size:0.84rem;color:#cbd5e1;line-height:1.6;'
        f'margin-bottom:0.6rem;">{meta["description"]}</div>'
        f'<div style="font-size:0.76rem;color:#7c8aa0;font-style:italic;'
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
        '<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        'text-transform:uppercase;color:#a78bfa;margin-bottom:0.5rem;">'
        'Morningstar &amp; ESG</div>',
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
        '<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        'text-transform:uppercase;color:#a78bfa;margin-bottom:0.5rem;">'
        'Analyst consensus</div>',
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
        '<div style="font-size:0.8rem;font-weight:700;letter-spacing:0.06em;'
        'text-transform:uppercase;color:#a78bfa;margin-bottom:0.5rem;">'
        'Key financials</div>',
        unsafe_allow_html=True,
    )
    fin_rows = [
        {
            "Metric": f["label"],
            "Value": f["value"],
            "Trend": _sparkline(f["trend"]),
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
    ucits_used: list[str] = portfolio.get("ucits_tickers_used", [])
    vol: float = portfolio.get("expected_volatility", 0.0)
    exp_ret = portfolio.get("expected_return")
    max_dd = portfolio.get("max_drawdown")

    profile_label: str = (
        st.session_state.get("profile", {}).get("profile_label", "MODERATE").upper()
    )
    profile_color: str = _PROFILE_COLOR.get(profile_label, "#7c5cfc")

    # ── Profile badge ───────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:inline-flex;align-items:center;gap:0.5rem;'
        f'background:rgba(124,92,252,0.1);border:1px solid {profile_color}40;'
        f'border-radius:20px;padding:0.35rem 1rem;margin-bottom:1.25rem;">'
        f'<span style="width:8px;height:8px;border-radius:50%;'
        f'background:{profile_color};flex-shrink:0;"></span>'
        f'<span style="font-size:0.8rem;color:{profile_color};font-weight:600;'
        f'font-family:\'Space Grotesk\',sans-serif;">{profile_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── KPI Cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Value", "$100,000")
    c2.metric("Expected Return (1Y)", f"{exp_ret:.1%}" if exp_ret is not None else "—")
    c3.metric("Risk Score", f"{vol:.1%}")
    c4.metric("Historical Max Drawdown", f"{max_dd:.1%}" if max_dd is not None else "—")

    _v_spacer(2.5)

    # ── Section 1: Portfolio Performance ───────────────────────────────────
    _section_header("1", "Portfolio Performance")
    _section_desc(
        "The chart tracks the growth of a $100,000 notional investment in the HRP portfolio "
        "over the selected time window, compared to a 60/40 equity-bond benchmark. "
        "Values are indexed to 100 at the start of the selected period. "
        "Use the period selector to zoom in on shorter or longer horizons. "
        "Past performance is simulated and does not guarantee future results."
    )

    _PERIOD_DAYS: dict[str, int] = {
        "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "3Y": 756, "All": 1764,
    }
    period = st.radio(
        "period",
        list(_PERIOD_DAYS.keys()),
        index=3,
        horizontal=True,
        label_visibility="collapsed",
    )
    n_days = _PERIOD_DAYS[period]

    try:
        fig_perf = _build_perf_chart(
            exp_ret=exp_ret if exp_ret is not None else 0.06,
            vol=vol if vol > 0 else 0.10,
            n_days=n_days,
        )
        fig_perf = apply_plotly_dark_theme(fig_perf)
        st.plotly_chart(fig_perf, use_container_width=True)
    except Exception as exc:
        st.caption(f"Performance chart unavailable: {exc}")

    _v_spacer(2.5)

    # ── Section 2: Portfolio Allocation ────────────────────────────────────
    _section_header("2", "Portfolio Allocation")
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

    try:
        from backend.optimizer.charts import plot_weights_donut
        fig_donut = plot_weights_donut(weights)
        fig_donut = apply_plotly_dark_theme(fig_donut)
        st.plotly_chart(fig_donut, use_container_width=True)
    except Exception as exc:
        st.caption(f"Allocation chart unavailable: {exc}")

    _v_spacer(1.0)

    ucits_set = set(ucits_used) | _UCITS_TICKERS
    rows = []
    for ticker, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        rows.append({
            "Ticker": ticker,
            "Cluster": _HRP_TICKER_CLUSTER.get(ticker, "Other"),
            "Weight (%)": round(w * 100, 2),
            "UCITS": "EU ✓" if ticker in ucits_set else "—",
            "Risk Contribution": f"{risk_contributions.get(ticker, 0.0):.1%}",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Weight (%)": st.column_config.ProgressColumn(
                "Weight (%)", format="%.1f%%", min_value=0, max_value=100,
            ),
        },
    )

    with st.expander("What do these tickers mean?"):
        _render_etf_explorer()

    _v_spacer(2.5)

    # ── Section 3: Risk Contributions ──────────────────────────────────────
    _section_header("3", "Risk Contributions")
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
        fig_risk = apply_plotly_dark_theme(fig_risk)
        st.plotly_chart(fig_risk, use_container_width=True)
    except Exception as exc:
        st.caption(f"Risk contribution chart unavailable: {exc}")

    _v_spacer(2.5)

    # ── Section 4: Cluster Structure ───────────────────────────────────────
    _section_header("4", "Cluster Structure")
    _section_desc(
        "HRP groups assets by return-correlation before allocating weights. "
        "Assets that move together are linked early (bottom of the chart); "
        "distinct groups join higher up. Risk is balanced first within each cluster, "
        "then across clusters — reducing concentration without requiring return forecasts."
    )

    _DEND_CLUSTERS = [
        {
            "name": "Risk Assets",
            "color": "#7c5cfc",
            "bg": "rgba(124,92,252,0.15)",
            "tickers": ["CSPX.L", "EFA"],
            "group": 0,
        },
        {
            "name": "Real Assets",
            "color": "#0dcfb0",
            "bg": "rgba(13,207,176,0.15)",
            "tickers": ["GLD", "VNQ"],
            "group": 1,
        },
        {
            "name": "Safe Haven",
            "color": "#f59e0b",
            "bg": "rgba(245,158,11,0.15)",
            "tickers": ["AGGH.MI", "TLT", "TIP"],
            "group": 2,
        },
        {
            "name": "Cash",
            "color": "#3b82f6",
            "bg": "rgba(59,130,246,0.15)",
            "tickers": ["XEON.MI"],
            "group": 3,
        },
    ]

    _chips_items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:0.35rem;'
        f'background:{cl["bg"]};border:1px solid {cl["color"]}50;'
        f'border-radius:20px;padding:0.25rem 0.65rem;">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{cl["color"]};'
        f'flex-shrink:0;display:inline-block;"></span>'
        f'<span style="font-size:0.7rem;color:{cl["color"]};font-weight:600;">'
        f'{cl["name"]}</span>'
        f'</span>'
        for cl in _DEND_CLUSTERS
    )
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.45rem;'
        'flex-wrap:wrap;margin-bottom:0.85rem;">'
        '<span style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#475569;margin-right:0.25rem;">Clusters</span>'
        f'{_chips_items}'
        '</div>',
        unsafe_allow_html=True,
    )

    _dend_col, _info_col = st.columns([3, 1.2])

    with _dend_col:
        try:
            import numpy as np
            from scipy.cluster.hierarchy import linkage
            from scipy.spatial.distance import squareform

            from backend.optimizer.charts import plot_dendrogram

            tickers_list = list(weights.keys())
            n = len(tickers_list)

            _ticker_group: dict[str, int] = {
                t: cl["group"]
                for cl in _DEND_CLUSTERS
                for t in cl["tickers"]
            }
            corr = np.eye(n)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        ci = _ticker_group.get(tickers_list[i], -1)
                        cj = _ticker_group.get(tickers_list[j], -1)
                        corr[i, j] = 0.70 if ci == cj else 0.10

            dist = np.sqrt(0.5 * (1 - corr))
            np.fill_diagonal(dist, 0.0)
            condensed = squareform(dist, checks=False)
            link = linkage(condensed, method="ward")

            fig_dend = plot_dendrogram(link, tickers_list)
            fig_dend = apply_plotly_dark_theme(fig_dend)
            fig_dend.update_traces(line=dict(color="#a78bfa", width=2))
            fig_dend.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=50, r=20, t=50, b=90),
                height=350,
                xaxis=dict(
                    tickangle=-35,
                    tickfont=dict(color="#94a3b8", size=11),
                    showgrid=False,
                ),
                yaxis=dict(
                    title=dict(text="Distance", font=dict(color="#64748b", size=11)),
                    tickfont=dict(color="#64748b", size=10),
                ),
            )
            st.plotly_chart(fig_dend, use_container_width=True)

        except Exception as exc:
            st.caption(f"Dendrogram unavailable: {exc}")

    with _info_col:
        _HOW_TO_POINTS = [
            ("Branch height", "The higher two assets join, the less correlated they are."),
            ("Early linkage", "Assets merged near the bottom share similar return patterns."),
            ("Cluster balance", "HRP divides risk equally within each subtree before scaling up."),
            ("No forecasts", "Uses only historical correlations — no return predictions."),
            (
                "Line colour",
                "All branches share a single colour — the dendrogram encodes distance "
                "through height, not colour. The chips above label economic asset groups.",
            ),
        ]
        _pts_html = "".join(
            f'<div style="display:flex;gap:0.55rem;margin-bottom:0.6rem;">'
            f'<span style="color:#7c5cfc;font-size:0.75rem;margin-top:0.1rem;'
            f'flex-shrink:0;">▸</span>'
            f'<div>'
            f'<div style="font-size:0.75rem;font-weight:600;color:#c4b5fd;'
            f'margin-bottom:0.1rem;">{title}</div>'
            f'<div style="font-size:0.72rem;color:#64748b;line-height:1.55;">{body}</div>'
            f'</div>'
            f'</div>'
            for title, body in _HOW_TO_POINTS
        )
        st.markdown(
            '<div style="background:rgba(124,92,252,0.06);'
            'border:1px solid rgba(124,92,252,0.18);border-radius:10px;'
            'padding:1rem 1rem 0.5rem;">'
            '<div style="font-family:\'Space Grotesk\',sans-serif;font-size:0.8rem;'
            'font-weight:700;color:#a78bfa;letter-spacing:0.04em;'
            'text-transform:uppercase;margin-bottom:0.75rem;">How to read this</div>'
            f'{_pts_html}'
            '</div>',
            unsafe_allow_html=True,
        )



# ---------------------------------------------------------------------------
# Chat Advisor helpers
# ---------------------------------------------------------------------------

# Scoped CSS for the native chat (st.chat_message / st.chat_input).
# Aligned with the app-wide design tokens defined in frontend/style.py.
_CHAT_CSS = """
<style>
/* ── Chat container ──────────────────────────────────────────────────────── */
.ca-page {
    margin-top: -0.3rem;
}

/* ── Status strip: model + validator + active profile ───────────────────── */
.ca-status {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
}
.ca-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    background: rgba(10,15,30,0.7);
    border: 1px solid #1e2640;
    border-radius: 999px;
    padding: 0.32rem 0.85rem;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.74rem;
    font-weight: 500;
    color: #94a3b8;
    letter-spacing: 0.02em;
}
.ca-pill .ca-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
}
.ca-pill--profile {
    color: #a78bfa;
    border-color: rgba(124,92,252,0.32);
    background: rgba(124,92,252,0.1);
}
.ca-pill--profile .ca-dot {
    background: #7c5cfc;
    box-shadow: 0 0 0 3px rgba(124,92,252,0.18);
}
.ca-pill--model {
    color: #93c5fd;
    border-color: rgba(59,130,246,0.30);
    background: rgba(59,130,246,0.08);
}
.ca-pill--model .ca-dot   { background: #3b82f6; }
.ca-pill--guard {
    color: #5eead4;
    border-color: rgba(13,207,176,0.30);
    background: rgba(13,207,176,0.08);
}
.ca-pill--guard .ca-dot {
    background: #0dcfb0;
    box-shadow: 0 0 0 3px rgba(13,207,176,0.15);
}

/* ── Chat shell ──────────────────────────────────────────────────────────── */
.ca-shell {
    background: #0f1628;
    border: 1px solid #1e2640;
    border-radius: 14px;
    overflow: hidden;
}
.ca-shell-head {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.85rem 1.1rem;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0d1220 100%);
    border-bottom: 1px solid #1e2640;
}
.ca-shell-head-icon {
    width: 2rem;
    height: 2rem;
    background: rgba(124,92,252,0.15);
    border: 1px solid rgba(124,92,252,0.3);
    border-radius: 9px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.95rem;
    flex-shrink: 0;
}
.ca-shell-head-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    color: #f1f5f9;
    line-height: 1.2;
}
.ca-shell-head-sub {
    font-size: 0.72rem;
    color: #64748b;
    letter-spacing: 0.02em;
    margin-top: 0.1rem;
}

/* ── Empty state hero ────────────────────────────────────────────────────── */
.ca-hero {
    text-align: center;
    padding: 2.25rem 1.5rem 1rem;
}
.ca-hero-orb {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background: radial-gradient(
        circle at 35% 30%,
        rgba(167,139,250,0.55) 0%,
        rgba(124,92,252,0.15) 60%,
        transparent 100%
    );
    border: 1px solid rgba(124,92,252,0.4);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.85rem;
    font-size: 1.55rem;
    box-shadow: 0 0 32px rgba(124,92,252,0.18);
}
.ca-hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.25rem;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.01em;
    margin-bottom: 0.4rem;
}
.ca-hero-sub {
    font-size: 0.87rem;
    color: #64748b;
    max-width: 420px;
    margin: 0 auto;
    line-height: 1.6;
}
.ca-hero-eyebrow {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #475569;
    margin: 1.5rem 0 0.6rem;
}

/* ── Suggestion chips (st.button cards) ─────────────────────────────────── */
.ca-suggest {
    padding: 0 1.1rem 1.4rem;
}
.ca-suggest .stButton > button {
    background: rgba(15,22,40,0.7) !important;
    border: 1px solid #1e2640 !important;
    border-left: 3px solid rgba(124,92,252,0.3) !important;
    border-radius: 10px !important;
    color: #cbd5e1 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    white-space: normal !important;
    line-height: 1.4 !important;
    min-height: 3.5rem !important;
    padding: 0.85rem 1rem !important;
    transition: border-color 0.18s ease, background 0.18s ease,
                color 0.18s ease, transform 0.18s ease !important;
}
.ca-suggest .stButton > button:hover {
    border-color: rgba(124,92,252,0.55) !important;
    border-left-color: #7c5cfc !important;
    background: rgba(124,92,252,0.1) !important;
    color: #e9d5ff !important;
    transform: translateY(-1px) !important;
}
.ca-suggest .stButton > button p { text-align: left !important; }

/* ── Conversation thread ─────────────────────────────────────────────────── */
.ca-thread { padding: 1.1rem 1.1rem 0.35rem; }

[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0.35rem 0 !important;
    margin-bottom: 0.85rem !important;
    animation: ca-fade 0.28s ease-out;
}
@keyframes ca-fade {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
}
/* Avatar bubbles */
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarCustom"] {
    border-radius: 50% !important;
    width: 2.05rem !important;
    height: 2.05rem !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex-shrink: 0 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageAvatarUser"] {
    background: rgba(124,92,252,0.18) !important;
    border: 1px solid rgba(124,92,252,0.35) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
[data-testid="stChatMessageAvatarAssistant"] {
    background: rgba(13,207,176,0.15) !important;
    border: 1px solid rgba(13,207,176,0.3) !important;
}

/* Message bubble = the rendered markdown container next to the avatar */
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"] > div > div:not([data-testid*="Avatar"]) {
    background: #131c30 !important;
    border: 1px solid #1e2640 !important;
    border-radius: 12px !important;
    padding: 0.7rem 1rem !important;
    box-shadow: 0 1px 0 rgba(0,0,0,0.15);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
[data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
> div > div:not([data-testid*="Avatar"]) {
    background: rgba(124,92,252,0.09) !important;
    border-color: rgba(124,92,252,0.28) !important;
}
[data-testid="stChatMessage"] p {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    line-height: 1.65 !important;
    color: #cbd5e1 !important;
    margin-bottom: 0.5rem !important;
}
[data-testid="stChatMessage"] p:last-child { margin-bottom: 0 !important; }
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #e2e8f0 !important;
    font-size: 0.95rem !important;
    margin: 0.4rem 0 0.3rem !important;
}
[data-testid="stChatMessage"] strong { color: #e9d5ff !important; }
[data-testid="stChatMessage"] code {
    background: rgba(124,92,252,0.12) !important;
    color: #c4b5fd !important;
    padding: 0.05rem 0.35rem !important;
    border-radius: 4px !important;
    font-size: 0.84rem !important;
}
[data-testid="stChatMessage"] table {
    border-collapse: collapse !important;
    margin: 0.3rem 0 !important;
}
[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td {
    border: 1px solid #1e2640 !important;
    padding: 0.35rem 0.7rem !important;
    font-size: 0.83rem !important;
    color: #94a3b8 !important;
}
[data-testid="stChatMessage"] th {
    background: rgba(124,92,252,0.08) !important;
    color: #a78bfa !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
}

/* ── Chat input ──────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    background: transparent !important;
    border-top: 1px solid #1e2640 !important;
    padding-top: 0.6rem !important;
}
[data-testid="stChatInput"] > div {
    background: #0d1220 !important;
    border: 1px solid #1e2640 !important;
    border-radius: 12px !important;
    transition: border-color 0.15s ease !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: rgba(124,92,252,0.55) !important;
    box-shadow: 0 0 0 3px rgba(124,92,252,0.12) !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    line-height: 1.55 !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #64748b !important; }
[data-testid="stChatInput"] button {
    background: rgba(124,92,252,0.18) !important;
    border: 1px solid rgba(124,92,252,0.35) !important;
    border-radius: 9px !important;
    color: #c4b5fd !important;
}
[data-testid="stChatInput"] button:hover {
    background: rgba(124,92,252,0.3) !important;
    border-color: #7c5cfc !important;
}

/* ── Clear chat link button (small, ghost) ──────────────────────────────── */
.ca-clear .stButton > button {
    background: transparent !important;
    border: 1px solid #1e2640 !important;
    color: #64748b !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.74rem !important;
    font-weight: 500 !important;
    padding: 0.3rem 0.75rem !important;
    border-radius: 7px !important;
    min-height: 1.9rem !important;
    height: 1.9rem !important;
    transition: color 0.15s ease, border-color 0.15s ease !important;
}
.ca-clear .stButton > button:hover {
    border-color: rgba(248,113,113,0.45) !important;
    color: #fca5a5 !important;
}

/* ── Info side card ──────────────────────────────────────────────────────── */
.ca-info {
    background: #0f1628;
    border: 1px solid #1e2640;
    border-radius: 14px;
    overflow: hidden;
}
.ca-info-head {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.85rem 1.05rem;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0d1220 100%);
    border-bottom: 1px solid #1e2640;
}
.ca-info-head-num {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    color: #a78bfa;
    background: rgba(124,92,252,0.18);
    border: 1px solid rgba(124,92,252,0.3);
    border-radius: 6px;
    min-width: 1.85rem;
    height: 1.85rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.ca-info-head-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.92rem;
    font-weight: 600;
    color: #f1f5f9;
}
.ca-info-body { padding: 1rem 1.1rem 1.1rem; }
.ca-info-section-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #475569;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.ca-info-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.45rem 0;
}
.ca-info-row + .ca-info-row { border-top: 1px dashed #1a2236; }
.ca-info-row span.label {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82rem;
    color: #cbd5e1;
}
.ca-info-divider { margin: 0.9rem 0 0.6rem; border-top: 1px solid #1a2236; }

.ca-info-footer {
    margin-top: 0.85rem;
    padding-top: 0.75rem;
    border-top: 1px solid #1a2236;
    font-size: 0.72rem;
    color: #64748b;
    line-height: 1.55;
    display: flex;
    align-items: flex-start;
    gap: 0.55rem;
}
.ca-info-footer svg { flex-shrink: 0; margin-top: 0.12rem; }

/* ── Pipeline strip inside info card ─────────────────────────────────────── */
.ca-pipeline {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
    margin-top: 0.4rem;
}
.ca-pipeline-step {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.67rem;
    letter-spacing: 0.03em;
    color: #94a3b8;
    background: rgba(15,22,40,0.7);
    border: 1px solid #1e2640;
    border-radius: 6px;
    padding: 0.22rem 0.5rem;
}
.ca-pipeline-arrow { color: #475569; font-size: 0.75rem; }
</style>
"""

# Avatars for the two chat roles. st.chat_message only accepts a real emoji,
# an image URL, or None — arbitrary unicode glyphs (e.g. "✦") are rejected on
# Streamlit Cloud because they fall through to the image loader and crash.
_CHAT_AVATARS: dict[str, str] = {"assistant": "✨", "user": "🧑"}

# Example prompts shown in the empty state.
_CHAT_SUGGESTIONS: list[str] = [
    "Why is my bond allocation high?",
    "Explain my risk profile",
    "What is the EU investor caveat?",
]


def _chat_get_reply(text: str, raw_label: str, profile_key: str) -> str:
    """
    Produce a validated advisor reply for a user message.

    Runs the deployed pipeline directly (no FastAPI hop, which does not exist on
    Streamlit Cloud): input sanitiser -> NarratorClient -> 5-step validator.
    Never raises — returns a user-facing string for every failure mode.
    """
    from backend.llm.input_sanitiser import sanitise
    from backend.llm.narrator import NarratorError

    san = sanitise(text)
    if san.blocked:
        return (
            "Your question could not be processed — it looked like an unsafe "
            "instruction. Please rephrase it."
        )

    try:
        narrator = NarratorClient()
    except NarratorError:
        return (
            "⚠️ The chat advisor is not configured: no `ANTHROPIC_API_KEY` was "
            "found. Add it under **Manage app → Settings → Secrets** on Streamlit "
            "Cloud, or in a local `.streamlit/secrets.toml`, then reload the page."
        )

    payload = get_mock_payload(profile_key)
    nresp = narrator.narrate(payload, san.sanitised_input)

    if nresp.injection_blocked:
        return "Your question could not be processed. Please rephrase it."
    if nresp.api_error:
        return (
            "I could not reach the advisor right now. Please try again in a moment."
        )

    result = validate(
        response_text=nresp.raw_text,
        allowed_numbers=payload.llm_constraints.allowed_numbers,
        forbidden_phrases=payload.llm_constraints.forbidden_phrases,
        eu_awareness_required=payload.regulatory_context.profiler_us_centric_caveat,
    )
    return result.safe_text


def _render_chat_info_panel() -> None:
    """Right-hand panel: scope of the advisor + safety pipeline."""
    chk = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        'stroke="#0dcfb0" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
    )
    xmk = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        'stroke="#f87171" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/></svg>'
    )
    shield = (
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" '
        'stroke="#7c5cfc" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<polyline points="9 12 11 14 15 10"/></svg>'
    )

    can_items = [
        "Portfolio weights",
        "Risk clusters",
        "Historical drawdowns",
        "EU / UCITS caveats",
    ]
    cant_items = [
        "Buy / sell recommendations",
        "Future return predictions",
    ]
    can_rows = "".join(
        f'<div class="ca-info-row">{chk}<span class="label">{x}</span></div>'
        for x in can_items
    )
    cant_rows = "".join(
        f'<div class="ca-info-row">{xmk}<span class="label">{x}</span></div>'
        for x in cant_items
    )

    pipeline = (
        '<div class="ca-pipeline">'
        '<span class="ca-pipeline-step">Sanitise</span>'
        '<span class="ca-pipeline-arrow">›</span>'
        '<span class="ca-pipeline-step">Narrate</span>'
        '<span class="ca-pipeline-arrow">›</span>'
        '<span class="ca-pipeline-step">Validate</span>'
        '</div>'
    )

    st.markdown(
        '<div class="ca-info">'
        '<div class="ca-info-head">'
        '<span class="ca-info-head-num">i</span>'
        '<span class="ca-info-head-title">Advisor scope</span>'
        '</div>'
        '<div class="ca-info-body">'
        '<div class="ca-info-section-label">Can explain</div>'
        f'{can_rows}'
        '<div class="ca-info-divider"></div>'
        '<div class="ca-info-section-label">Cannot do</div>'
        f'{cant_rows}'
        '<div class="ca-info-divider"></div>'
        '<div class="ca-info-section-label">Safety pipeline</div>'
        f'{pipeline}'
        '<div class="ca-info-footer">'
        f'{shield}'
        '<span>All responses are grounded in approved data and pass a '
        '5-step safety validator before display.</span>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


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
    page_header(
        "Chat Advisor",
        "LLM Narrator · Validated responses",
        icon="💬",
    )
    render_disclaimer()
    st.markdown(_CHAT_CSS, unsafe_allow_html=True)
    st.markdown('<div class="ca-page">', unsafe_allow_html=True)

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

    # Input is pinned to the bottom of the page regardless of call position.
    typed = st.chat_input("Ask about your portfolio…")
    pending = typed or st.session_state.pop("_pending_prompt", None)
    if pending:
        history.append({"role": "user", "content": pending})
        with st.spinner("Thinking…"):
            reply = _chat_get_reply(pending, raw_label, profile_key)
        history.append({"role": "assistant", "content": reply})

    # Status strip: profile + model + validator
    st.markdown(
        f'<div class="ca-status">'
        f'<span class="ca-pill ca-pill--profile"><span class="ca-dot"></span>'
        f'Active profile · {raw_label}</span>'
        f'<span class="ca-pill ca-pill--model"><span class="ca-dot"></span>'
        f'Claude Sonnet 4</span>'
        f'<span class="ca-pill ca-pill--guard"><span class="ca-dot"></span>'
        f'Validator · 5 checks</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_chat, col_info = st.columns([5, 2], gap="large")

    with col_info:
        _render_chat_info_panel()

    with col_chat:
        # Chat shell: gradient header + body
        st.markdown(
            '<div class="ca-shell">'
            '<div class="ca-shell-head">'
            '<span class="ca-shell-head-icon">✦</span>'
            '<div>'
            '<div class="ca-shell-head-title">Conversation</div>'
            '<div class="ca-shell-head-sub">'
            'Ask anything about your portfolio · responses validated</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        if not history:
            st.markdown(
                '<div class="ca-hero">'
                '<div class="ca-hero-orb">✦</div>'
                '<div class="ca-hero-title">'
                "Hi — I'm your AI Finance Assistant."
                '</div>'
                '<div class="ca-hero-sub">'
                'Ask a question about your portfolio allocation, risk clusters, '
                'or the EU investor caveat. Every answer is grounded in the '
                'ground-truth data computed by the backend.'
                '</div>'
                '<div class="ca-hero-eyebrow">Try one of these</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="ca-suggest">', unsafe_allow_html=True)
            chip_cols = st.columns(len(_CHAT_SUGGESTIONS))
            for i, (cc, txt) in enumerate(zip(chip_cols, _CHAT_SUGGESTIONS)):
                with cc:
                    if st.button(txt, key=f"chat_suggest_{i}", use_container_width=True):
                        st.session_state["_pending_prompt"] = txt
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="ca-thread">', unsafe_allow_html=True)
            for msg in history:
                with st.chat_message(
                    msg["role"], avatar=_CHAT_AVATARS.get(msg["role"])
                ):
                    st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

            # Ghost "Clear chat" button below the thread
            st.markdown('<div class="ca-clear">', unsafe_allow_html=True)
            _, clr = st.columns([5, 1])
            with clr:
                if st.button("Clear", key="ca_clear_btn", use_container_width=True):
                    st.session_state["chat_history"] = []
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Close .ca-shell
        st.markdown('</div>', unsafe_allow_html=True)

    # Close .ca-page
    st.markdown('</div>', unsafe_allow_html=True)


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
    page_header("Backtesting", "Walk-forward simulation · HRP vs MV vs 1/N", icon="📈")
    render_disclaimer()

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
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

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
        fig = apply_plotly_dark_theme(fig)
        fig.update_layout(margin=dict(t=56))
        st.plotly_chart(fig, use_container_width=True)

        # ── Drawdown chart ───────────────────────────────────────────────────
        import numpy as np

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
        fig_dd = apply_plotly_dark_theme(fig_dd)
        fig_dd.update_layout(margin=dict(t=56))
        st.plotly_chart(fig_dd, use_container_width=True)

    st.caption(
        "Profile: MODERATE · Rebalancing: monthly · TC: 10 bps/rebalance · "
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
    page_header("Compare Markowitz", "Deep-dive analysis · HRP vs Markowitz", icon="⚖")
    render_disclaimer()

    st.markdown(
        """
        <div style="background:rgba(30,38,64,0.5);border:1px solid #1e2640;
        border-radius:10px;padding:0.9rem 1rem;margin-bottom:1.25rem;
        display:flex;gap:0.875rem;align-items:flex-start;">
            <div style="width:2rem;height:2rem;flex-shrink:0;
            background:rgba(248,113,113,0.10);border:1px solid rgba(248,113,113,0.25);
            border-radius:7px;display:inline-flex;align-items:center;
            justify-content:center;font-size:0.95rem;">⚖️</div>
            <div>
                <div style="font-family:'Space Grotesk',sans-serif;font-size:0.9rem;
                font-weight:600;color:#e2e8f0;margin-bottom:0.25rem;">
                    Markowitz Mean-Variance (MV) — benchmark
                </div>
                <div style="font-size:0.79rem;color:#64748b;line-height:1.55;">
                    Markowitz (1952) maximises the Sharpe ratio given expected returns
                    and a covariance matrix. It typically produces concentrated portfolios
                    sensitive to estimation error ("corner solutions"). Used here as a
                    benchmark to highlight the diversification benefits of HRP.
                    Phase A values are mock; enable live data for real MV weights.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    import numpy as np

    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    portfolio = st.session_state.get("portfolio_data") or _mock_optimization(profile_key)
    hrp_weights: dict[str, float] = portfolio["weights"]
    hrp_rc: dict[str, float] = portfolio["risk_contributions"]
    hrp_vol: float = portfolio.get("expected_volatility") or 0.094
    hrp_ret: float = portfolio.get("expected_return") or 0.068
    hrp_max_dd: float = portfolio.get("max_drawdown") or -0.187

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

    st.markdown(f"**Active profile: {profile_label}**")
    st.markdown("---")

    # ── 1. Radar chart ────────────────────────────────────────────────────────
    st.markdown("**Multi-dimensional comparison**")

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
        name="HRP",
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
                color="#475569",
                gridcolor="#1e2640",
                tickfont=dict(size=9, color="#475569"),
            ),
            angularaxis=dict(color="#94a3b8", gridcolor="#1e2640"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="center", x=0.5),
        height=440,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    fig_radar = apply_plotly_dark_theme(fig_radar)
    fig_radar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_radar, use_container_width=True)
    st.caption(
        "All axes normalised to [0, 1]. "
        "Low Risk = 1 − σ (normalised). "
        "Diversification = 1 − HHI (Herfindahl index). "
        "Drawdown Protection = 1 − |max DD|. "
        "Phase A: volatility and return from mock data."
    )

    # ── 2. Risk contributions ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Risk contributions — who drives portfolio risk?**")

    all_tickers = sorted(
        set(hrp_rc) | set(mv_rc),
        key=lambda t: -hrp_rc.get(t, 0.0),
    )
    hrp_rc_vals = [hrp_rc.get(t, 0.0) * 100 for t in all_tickers]
    mv_rc_vals = [mv_rc.get(t, 0.0) * 100 for t in all_tickers]

    fig_rc = go.Figure()
    fig_rc.add_trace(go.Bar(
        name="HRP",
        y=all_tickers,
        x=hrp_rc_vals,
        orientation="h",
        marker_color="#7c5cfc",
        hovertemplate="%{y}: %{x:.1f}%<extra>HRP</extra>",
    ))
    fig_rc.add_trace(go.Bar(
        name="Markowitz MV",
        y=all_tickers,
        x=mv_rc_vals,
        orientation="h",
        marker_color="#f87171",
        hovertemplate="%{y}: %{x:.1f}%<extra>MV</extra>",
    ))
    fig_rc.update_layout(
        barmode="group",
        xaxis_title="Risk contribution (%)",
        height=360,
        margin=dict(l=8, r=24, t=24, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig_rc = apply_plotly_dark_theme(fig_rc)
    fig_rc.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_rc, use_container_width=True)
    st.caption(
        "HRP targets equal risk contributions across assets. "
        "MV concentrates risk in low-volatility assets (bonds), "
        "which can reduce diversification benefits in a stress regime."
    )

    # ── 3. Correlation heatmap ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Asset correlation matrix**")

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
            [0.50, "#111827"],
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
    fig_hm = apply_plotly_dark_theme(fig_hm)
    fig_hm.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_hm, use_container_width=True)
    st.caption(
        "Correlation matrix used by HRP to build the hierarchical cluster tree. "
        "Negative equity–bond correlation (flight-to-quality) is the key diversification driver. "
        "Phase A: stylised static matrix. Phase B: computed from 2-year rolling prices."
    )


# ---------------------------------------------------------------------------
# Page 6 -- Settings
# ---------------------------------------------------------------------------

def render_settings() -> None:
    """Platform configuration and status page."""
    page_header("Settings", "Platform configuration")
    render_disclaimer()
    st.markdown("---")

    st.markdown("**Data Source**")
    st.radio(
        "Default data mode for Portfolio Dashboard",
        ["Mock data (Phase A — always works)", "Live market data (Phase B — requires network)"],
        index=0,
        key="default_data_mode",
    )

    st.markdown("---")
    st.markdown("**API Status**")
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
    st.markdown("**About**")
    st.caption("AI-Powered Robo-Advisor Platform · USI Programming in Finance II 2026")
    st.caption("Design v3.1 · HRP + LLM Narrator + EU Awareness")
    st.caption("Team: P1 Backend · P2 Quant · P3 ML · P4 Frontend/LLM/Docs")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
main()
