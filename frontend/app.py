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
    "Chat Advisor",
    "Backtesting",
    "Compare (MV)",
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
    "Compare (MV)": (
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
            f'<img src="data:image/png;base64,{_logo_b64}"'
            ' style="height:28px;width:auto;" alt="RoboAdvisor">'
        )
    else:
        _logo_tag = (
            '<span style="font-size:1.1rem;font-weight:700;color:#f5f5f7;'
            "font-family:'Space Grotesk',sans-serif;\">RoboAdvisor</span>"
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
    display: flex; align-items: center; gap: 10px;
    min-width: 220px; flex-shrink: 0; text-decoration: none;
}}
.top-navbar .brand-name {{
    font-size: 15px; font-weight: 600; color: #f5f5f7;
    letter-spacing: -0.2px;
    font-family: 'Space Grotesk', -apple-system, sans-serif;
}}
.top-navbar .brand-sub {{
    font-size: 9px; letter-spacing: 0.10em;
    color: rgba(245,245,247,0.35); text-transform: uppercase;
    line-height: 1.2;
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
    elif active == "Compare (MV)":
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
    # (EU note moved to bottom — avoid duplicate banners at top)

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

    # Two tabs: HRP (default) and Markowitz benchmark
    tab_hrp, tab_mv = st.tabs(["HRP Portfolio", "Markowitz Benchmark"])

    with tab_hrp:
        _render_hrp_tab(portfolio)

    with tab_mv:
        _render_mv_tab(portfolio, profile_key)

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

    _TICKER_GLOSSARY = [
        {
            "Ticker": "CSPX.L",
            "Name": "S&P 500 UCITS ETF",
            "Asset Class": "Equity",
            "Role": "US large-cap equity exposure",
            "UCITS / EU Note": "UCITS-eligible",
        },
        {
            "Ticker": "EFA",
            "Name": "International developed markets equity ETF",
            "Asset Class": "Equity",
            "Role": "Non-US developed equity exposure",
            "UCITS / EU Note": "US-listed / non-UCITS in this prototype",
        },
        {
            "Ticker": "GLD",
            "Name": "Gold ETF",
            "Asset Class": "Alternatives",
            "Role": "Gold exposure / real asset diversifier",
            "UCITS / EU Note": "US-listed / non-UCITS in this prototype",
        },
        {
            "Ticker": "VNQ",
            "Name": "US real estate ETF",
            "Asset Class": "Alternatives",
            "Role": "US REIT / real estate exposure",
            "UCITS / EU Note": "US-listed / non-UCITS in this prototype",
        },
        {
            "Ticker": "AGGH.MI",
            "Name": "Euro Aggregate Bond ETF",
            "Asset Class": "Bonds",
            "Role": "Broad EUR bond exposure",
            "UCITS / EU Note": "UCITS-eligible",
        },
        {
            "Ticker": "TLT",
            "Name": "Long-term US Treasury ETF",
            "Asset Class": "Bonds",
            "Role": "Long-duration government bond exposure",
            "UCITS / EU Note": "US-listed / non-UCITS in this prototype",
        },
        {
            "Ticker": "TIP",
            "Name": "US inflation-linked bond ETF",
            "Asset Class": "Bonds",
            "Role": "Inflation-linked Treasury exposure",
            "UCITS / EU Note": "US-listed / non-UCITS in this prototype",
        },
        {
            "Ticker": "XEON.MI",
            "Name": "EUR overnight rate ETF",
            "Asset Class": "Cash",
            "Role": "Cash-like EUR exposure",
            "UCITS / EU Note": "UCITS-eligible",
        },
    ]
    with st.expander("What do these tickers mean?"):
        st.dataframe(
            pd.DataFrame(_TICKER_GLOSSARY),
            hide_index=True,
            use_container_width=True,
        )

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


def _render_mv_tab(portfolio: dict, profile_key: str) -> None:
    """
    Markowitz tab: HRP vs MV weight comparison, efficient frontier,
    stress scenario table, backtest summary.

    Phase A: uses mock MV weights + synthetic frontier for illustration.
    Phase B: runs optimize_markowitz() on live prices for real comparison.
    """
    st.subheader("Markowitz Mean-Variance — Benchmark Comparison")

    from backend.optimizer.charts import (
        plot_efficient_frontier,
    )

    # ── Try to run live MV optimizer (Phase B) ────────────────────────────
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

    # ── Phase A fallback: use approximate MV mock weights ─────────────────
    if mv_weights is None:
        # Approximate Max-Sharpe MV weights for illustration
        # (concentrated in high-Sharpe assets — typical MV corner solution)
        hrp_w = portfolio.get("weights", {})
        mv_weights = {t: 0.0 for t in hrp_w}
        # MV typically over-weights bonds and under-weights alternatives
        if hrp_w:
            tickers_list = list(hrp_w.keys())
            # Simple illustration: shift weight toward safe_haven assets
            for t in tickers_list:
                if t in {"AGGH.MI", "TLT", "TIP"}:
                    mv_weights[t] = min(0.40, hrp_w.get(t, 0.10) * 1.8)
                elif t in {"CSPX.L", "EFA"}:
                    mv_weights[t] = max(0.03, hrp_w.get(t, 0.20) * 0.7)
                else:
                    mv_weights[t] = hrp_w.get(t, 0.10)
            total = sum(mv_weights.values()) or 1.0
            mv_weights = {t: round(w / total, 4) for t, w in mv_weights.items()}
        mv_vol = portfolio.get("expected_volatility", 0.08) * 0.92  # MV typically lower vol
        mv_ret = None   # not estimated in Phase A
        mv_sharpe = None

    # ── Metrics comparison row ────────────────────────────────────────────
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

    # ── Side-by-side weights table ────────────────────────────────────────
    st.markdown("**Weight Comparison — HRP vs Markowitz**")

    hrp_weights = portfolio.get("weights", {})
    tickers_sorted = sorted(hrp_weights.keys(), key=lambda t: -hrp_weights.get(t, 0))

    comparison_rows = []
    for ticker in tickers_sorted:
        h = hrp_weights.get(ticker, 0.0)
        m = mv_weights.get(ticker, 0.0)
        delta_pp = (h - m) * 100
        comparison_rows.append({
            "Ticker": ticker,
            "Asset Class": _HRP_TICKER_CLUSTER.get(ticker, "Other"),
            "HRP (%)": round(h * 100, 2),
            "Markowitz (%)": round(m * 100, 2),
            "Δ (HRP − MV, pp)": f"{delta_pp:+.1f} pp",
            "UCITS": "EU ✓" if ticker in _UCITS_TICKERS else "—",
        })

    st.dataframe(
        pd.DataFrame(comparison_rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "HRP (%)": st.column_config.ProgressColumn(
                "HRP (%)", format="%.1f%%", min_value=0, max_value=100,
            ),
            "Markowitz (%)": st.column_config.ProgressColumn(
                "Markowitz (%)", format="%.1f%%", min_value=0, max_value=100,
            ),
        },
    )
    st.caption(
        "Δ (HRP − MV) is in percentage points. "
        "Positive values mean HRP allocates more to that asset than Markowitz; "
        "negative values mean Markowitz allocates more. "
        "Markowitz typically produces more concentrated portfolios; "
        "HRP avoids corner solutions by construction."
    )

    st.markdown("---")

    # ── Efficient Frontier chart ──────────────────────────────────────────
    st.markdown("**Efficient Frontier — HRP vs Markowitz**")

    try:
        # Synthetic frontier for illustration (Phase A)
        # Phase B: compute frontier from pypfopt EfficientFrontier parametric sweep
        import numpy as np
        frontier_vols = list(np.linspace(0.04, 0.20, 30))
        # Approximate return/risk tradeoff using historical Sharpe ~0.5
        frontier_rets = [v * 0.5 + 0.01 for v in frontier_vols]

        fig_frontier = plot_efficient_frontier(
            frontier_vols=frontier_vols,
            frontier_rets=frontier_rets,
            hrp_vol=hrp_vol or 0.10,
            hrp_ret=hrp_ret,
            mv_vol=mv_vol or 0.08,
            mv_ret=mv_ret,
        )
        fig_frontier = apply_plotly_dark_theme(fig_frontier)
        st.plotly_chart(fig_frontier, use_container_width=True)
        if portfolio.get("source") != "live":
            st.caption("Frontier shown is illustrative (Phase A mock)."
                       "Enable live data for real frontier."
                      )
    except Exception as exc:
        st.caption(f"Frontier chart unavailable: {exc}")

    st.markdown("---")

    # ── Stress scenarios table (existing P4 code, kept) ───────────────────
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
        st.dataframe(
            pd.DataFrame(scenario_rows),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Benchmark = equal-weight 60/40 portfolio. "
            "Phase A values are from mock data. "
            "Phase B will use real backtested values from backtest.py."
        )

    # ── Backtest summary (existing P4 code, kept) ─────────────────────────
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
    page_header("Compare (MV)", "HRP vs Markowitz mean-variance", icon="⚖")
    render_disclaimer()

    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    portfolio = st.session_state.get("portfolio_data") or _mock_optimization(profile_key)
    hrp_weights = portfolio["weights"]

    st.markdown("---")

    # ── Side-by-side weights table ───────────────────────────────────────────
    st.markdown("**Portfolio weights — HRP vs Markowitz (mock)**")

    tickers = sorted(set(hrp_weights) | set(_MOCK_MV_WEIGHTS))
    rows = []
    for t in sorted(tickers, key=lambda x: -hrp_weights.get(x, 0)):
        hrp_w = hrp_weights.get(t, 0.0)
        mv_w  = _MOCK_MV_WEIGHTS.get(t, 0.0)
        diff  = hrp_w - mv_w
        rows.append({
            "Ticker": t,
            "HRP":    f"{hrp_w:.1%}",
            "MV":     f"{mv_w:.1%}",
            "HRP − MV": f"+{diff:.1%}" if diff > 0 else f"{diff:.1%}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.markdown("---")

    # ── Bar chart: HRP vs MV weights ─────────────────────────────────────────
    col_bar, col_frontier = st.columns(2)

    with col_bar:
        st.markdown("**Weight allocation**")
        fig_bar = go.Figure()
        ticker_order = [r["Ticker"] for r in rows]
        fig_bar.add_trace(go.Bar(
            name="HRP",
            x=ticker_order,
            y=[hrp_weights.get(t, 0.0) * 100 for t in ticker_order],
            marker_color="#7c5cfc",
        ))
        fig_bar.add_trace(go.Bar(
            name="MV",
            x=ticker_order,
            y=[_MOCK_MV_WEIGHTS.get(t, 0.0) * 100 for t in ticker_order],
            marker_color="#f87171",
        ))
        fig_bar.update_layout(
            barmode="group",
            yaxis_title="Weight (%)",
            height=340,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig_bar = apply_plotly_dark_theme(fig_bar)
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_frontier:
        st.markdown("**Efficient frontier (mock)**")
        import numpy as np
        # Generate a plausible mock frontier parabola
        vols_f = np.linspace(0.04, 0.22, 60).tolist()
        rets_f = [max(0.0, -2.5 * v**2 + 1.1 * v + 0.01) for v in vols_f]

        hrp_vol = portfolio.get("expected_volatility", 0.085)
        hrp_ret = portfolio.get("expected_return") or 0.062
        mv_vol  = 0.068   # MV mock: lower vol, lower return
        mv_ret  = 0.048

        from backend.optimizer.charts import plot_efficient_frontier
        fig_ef = plot_efficient_frontier(
            frontier_vols=vols_f,
            frontier_rets=rets_f,
            hrp_vol=hrp_vol,
            hrp_ret=hrp_ret,
            mv_vol=mv_vol,
            mv_ret=mv_ret,
        )
        fig_ef.update_layout(height=340)
        fig_ef = apply_plotly_dark_theme(fig_ef)
        st.plotly_chart(fig_ef, use_container_width=True)

    st.caption(
        "MV weights are mock (Phase A). Phase B will run the live Markowitz optimizer "
        "via the /compare endpoint and compare against the real HRP result."
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
