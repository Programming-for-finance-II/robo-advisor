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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.llm.narrator import NarratorClient, NarratorError
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
    initial_sidebar_state="expanded",
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
    if "active_page" not in st.session_state:
        st.session_state.active_page = PAGES[0]

    # ── Sidebar ──────────────────────────────────────────────────────
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.markdown("### RoboAdvisor")

        st.markdown(
            """
            <div style="
                text-align: center;
                margin-top: -0.5rem;
                margin-bottom: 1rem;
                font-size: 0.65rem;
                letter-spacing: 0.1em;
                color: #475569;
                text-transform: uppercase;
            ">
                USI · Programming in Finance II · 2026
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<hr style='border-color:#1e2640; margin: 0.5rem 0 0.6rem 0;'>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='font-size:0.58rem;letter-spacing:0.12em;color:#475569;"
            "text-transform:uppercase;padding:0 0.85rem 0.5rem;font-weight:600;'>"
            "NAVIGATION</div>",
            unsafe_allow_html=True,
        )

        active = st.session_state.active_page
        for page_name in PAGES:
            btn_type = "primary" if page_name == active else "secondary"
            wrap_cls = "nav-svg-wrap active" if page_name == active else "nav-svg-wrap"
            col_icon, col_btn = st.columns([0.15, 0.85])
            with col_icon:
                st.markdown(
                    f'<div class="{wrap_cls}">{_NAV_SVGS[page_name]}</div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    page_name,
                    key=f"nav_{page_name}",
                    use_container_width=True,
                    type=btn_type,
                ):
                    st.session_state.active_page = page_name
                    st.rerun()

        st.markdown(
            f"""
            <div style="
                background: rgba(124,92,252,0.08);
                border: 1px solid rgba(124,92,252,0.2);
                border-radius: 10px;
                padding: 0.75rem 0.875rem;
                margin: 1.5rem 0 0 0;
            ">
                <div style="
                    display:flex;align-items:center;gap:0.4rem;
                    font-size:0.7rem;font-weight:600;color:#a78bfa;margin-bottom:0.3rem;
                ">{_SHIELD_SVG} Educational Prototype</div>
                <div style="font-size:0.67rem;color:#64748b;line-height:1.5;">
                    This is an educational prototype and not financial advice.
                </div>
                <div style="font-size:0.63rem;color:#475569;margin-top:0.3rem;">
                    Market data may be delayed or inaccurate.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
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
        "options": ["Over 60", "46-60", "30-45", "Under 30"],
        "scores": [0, 1, 2, 3],
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
    page_header("Investor Profile Questionnaire", "Grable-Lytton Scale · 10 questions")
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
            f'<div style="font-size:2.8rem;line-height:1;flex-shrink:0;margin-top:0.1rem;">{rm["icon"]}</div>'
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
            f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;background:#1e2640;overflow:hidden;">'
            f'<div style="height:100%;width:{score_pct:.0f}%;background:{rm["bar_gradient"]};border-radius:3px;"></div>'
            f'</div></div>'

            # confidence card
            f'<div style="flex:1;min-width:120px;background:rgba(0,0,0,0.25);'
            f'border:1px solid #1e2640;border-radius:10px;padding:0.75rem 1.1rem;">'
            f'<div style="font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'
            f'color:#475569;margin-bottom:0.35rem;">Model Confidence</div>'
            f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.7rem;'
            f'font-weight:700;color:{rm["color"]};line-height:1;">{conf_pct}%</div>'
            f'<div style="margin-top:0.55rem;height:5px;border-radius:3px;background:#1e2640;overflow:hidden;">'
            f'<div style="height:100%;width:{conf_pct}%;background:{rm["bar_gradient"]};border-radius:3px;"></div>'
            f'</div></div>'

            f'</div>'  # end metrics row

            # ── drivers ──────────────────────────────────────────────────────
            + drivers_block +
            f'</div>'  # end card
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
    )
    render_disclaimer()
    # (EU note moved to bottom — avoid duplicate banners at top)

    # ── Profile hero strip ───────────────────────────────────────────────────
    _PROFILE_META = {
        "CONSERVATIVE": {"icon": "🛡️", "color": "#0dcfb0", "label": "Conservative"},
        "MODERATE":     {"icon": "⚖️",  "color": "#7c5cfc", "label": "Moderate"},
        "AGGRESSIVE":   {"icon": "🚀", "color": "#f87171", "label": "Aggressive"},
    }
    pm = _PROFILE_META.get(profile_label, _PROFILE_META["MODERATE"])
    conf_html = (
        f'<div style="font-size:0.8rem;color:#94a3b8;margin-top:2px;">'
        f'Confidence&nbsp;<span style="color:{pm["color"]};font-weight:600;">'
        f'{confidence:.0%}</span></div>'
        if confidence is not None else ""
    )
    st.markdown(
        f"""
        <div style="
            display:flex;align-items:center;gap:1rem;
            background:linear-gradient(135deg,{pm['color']}12,{pm['color']}06);
            border:1px solid {pm['color']}35;
            border-radius:12px;padding:0.85rem 1.25rem;
            margin-bottom:1.25rem;">
            <div style="font-size:1.6rem;flex-shrink:0;">{pm['icon']}</div>
            <div>
                <div style="
                    font-family:'Space Grotesk',sans-serif;
                    font-size:1.05rem;font-weight:700;
                    color:{pm['color']};letter-spacing:0.03em;">
                    {pm['label']} Investor
                </div>
                {conf_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    default_live = (
        st.session_state.get("default_data_mode", "")
        == "Live market data (Phase B — requires network)"
    )

    # Toggle between mock data (Phase A) and live optimizer (Phase B)
    use_live = st.toggle(
        "Load live market data",
        value=default_live,
        help=(
            "Downloads real prices from yfinance and runs the HRP optimizer. "
            "Takes about 10 seconds on first load."
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
    st.info(
        "EU Investor Note -- The risk profile model is trained on "
        "US Federal Reserve SCF data (2022). Results may not fully reflect "
        "the behaviour of European retail investors. "
        "The ECB Household Finance and Consumption Survey (HFCS) would be a "
        "more geographically appropriate training source. "
        "(EU Awareness Rule 9 -- Design v3.1)"
    )


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


def _render_hrp_tab(portfolio: dict) -> None:
    """
    HRP tab: cluster breakdown, key metrics, weights table, colored risk chart.
    """
    profile_label = st.session_state.get("profile", {}).get("profile_label", "MODERATE")
    profile_color = _PROFILE_COLOR.get(profile_label, "#7c5cfc")

    # ── Section header ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1.25rem;">
            <div style="
                font-family:'Space Grotesk',sans-serif;font-size:1.1rem;
                font-weight:600;color:#f1f5f9;">
                Hierarchical Risk Parity
            </div>
            <div style="
                font-family:'Space Grotesk',sans-serif;font-size:0.7rem;
                font-weight:700;color:{profile_color};
                background:rgba(124,92,252,0.1);
                border:1px solid {profile_color}40;
                border-radius:5px;padding:0.1rem 0.5rem;letter-spacing:0.06em;">
                {profile_label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    weights: dict[str, float] = portfolio["weights"]
    risk_contributions: dict[str, float] = portfolio["risk_contributions"]
    ucits_used: list[str] = portfolio.get("ucits_tickers_used", [])
    vol: float = portfolio.get("expected_volatility", 0.0)
    exp_ret = portfolio.get("expected_return")
    sharpe = portfolio.get("sharpe_ratio")
    max_dd = portfolio.get("max_drawdown")

    # ── Cluster breakdown pills ──────────────────────────────────────────────
    cluster_totals: dict[str, float] = {}
    for ticker, w in weights.items():
        cl = _HRP_TICKER_CLUSTER.get(ticker, "Other")
        cluster_totals[cl] = cluster_totals.get(cl, 0.0) + w

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

    # ── Key metrics row ──────────────────────────────────────────────────────
    metrics = [("Annual Volatility", f"{vol:.1%}")]
    if exp_ret is not None:
        metrics.append(("Exp. Return (hist.)", f"{exp_ret:.1%}"))
    if sharpe is not None:
        metrics.append(("Sharpe Ratio", f"{sharpe:.2f}"))
    if max_dd is not None:
        metrics.append(("Max Drawdown (hist.)", f"{max_dd:.1%}"))

    m_cols = st.columns(len(metrics))
    for col, (label, value) in zip(m_cols, metrics):
        col.metric(label, value)

    st.markdown("---")

    # ── Donut chart + weights table ──────────────────────────────────────────
    col_donut, col_table = st.columns([1, 1.1])

    with col_donut:
        st.markdown("**Portfolio Allocation**")
        try:
            from backend.optimizer.charts import plot_weights_donut
            fig_donut = plot_weights_donut(weights)
            fig_donut = apply_plotly_dark_theme(fig_donut)
            fig_donut.update_layout(
                title={"text": ""},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_donut, use_container_width=True)
        except Exception as exc:
            st.caption(f"Chart unavailable: {exc}")

    with col_table:
        st.markdown("**Portfolio Weights**")
        ucits_set = set(ucits_used) | _UCITS_TICKERS
        rows = []
        for ticker, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            rows.append({
                "Ticker": ticker,
                "Weight": w,
                "UCITS": "EU ✓" if ticker in ucits_set else "—",
            })
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Weight": st.column_config.ProgressColumn(
                    "Weight", format="%.1f%%", min_value=0, max_value=1,
                ),
            },
        )

    # ── Risk contribution bar chart — colored by cluster ─────────────────────
    tickers_sorted = sorted(
        risk_contributions.keys(),
        key=lambda t: risk_contributions[t],
    )
    bar_colors = [
        _HRP_CLUSTER_COLOR.get(_HRP_TICKER_CLUSTER.get(t, ""), "#64748b")
        for t in tickers_sorted
    ]
    rc_values = [risk_contributions[t] * 100 for t in tickers_sorted]
    equal_risk = 100.0 / len(tickers_sorted) if tickers_sorted else 0

    fig_rc = go.Figure()
    fig_rc.add_trace(go.Bar(
        x=rc_values,
        y=tickers_sorted,
        orientation="h",
        marker=dict(
            color=bar_colors,
            line=dict(color="#0d1220", width=1),
        ),
        text=[f"{v:.1f}%" for v in rc_values],
        textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
    ))
    fig_rc.add_vline(
        x=equal_risk,
        line_dash="dot",
        line_color="#475569",
        line_width=1.5,
        annotation_text="1/N",
        annotation_font_color="#475569",
        annotation_font_size=10,
    )

    profile_str = st.session_state.get("profile", {}).get("profile_label", "")
    fig_rc.update_layout(
        title=f"Risk Contributions — {profile_str}" if profile_str else "Risk Contributions",
        xaxis_title="Risk Contribution (%)",
        xaxis=dict(range=[0, max(rc_values) * 1.25]),
        height=380,
        margin=dict(l=8, r=40, t=50, b=40),
    )
    fig_rc = apply_plotly_dark_theme(fig_rc)
    fig_rc.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_rc, use_container_width=True)

    # --- Dendrogram ---
    try:
        import numpy as np
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform

        from backend.optimizer.charts import plot_dendrogram

        tickers_list = list(weights.keys())
        n = len(tickers_list)

        _CLUSTER_GROUPS = {
            "CSPX.L": 0, "EFA": 0,
            "GLD": 1, "VNQ": 1,
            "AGGH.MI": 2, "TLT": 2, "TIP": 2,
            "XEON.MI": 3,
        }
        corr = np.eye(n)
        for i in range(n):
            for j in range(n):
                if i != j:
                    ci = _CLUSTER_GROUPS.get(tickers_list[i], -1)
                    cj = _CLUSTER_GROUPS.get(tickers_list[j], -1)
                    corr[i, j] = 0.70 if ci == cj else 0.10

        dist = np.sqrt(0.5 * (1 - corr))
        np.fill_diagonal(dist, 0.0)
        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="ward")

        st.markdown("**Cluster Structure (Dendrogram)**")
        fig_dend = plot_dendrogram(link, tickers_list)
        fig_dend = apply_plotly_dark_theme(fig_dend)
        fig_dend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_dend, use_container_width=True)

    except Exception as exc:
        st.caption(f"Dendrogram unavailable: {exc}")


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
        comparison_rows.append({
            "Ticker": ticker,
            "HRP": f"{h:.1%}",
            "Markowitz": f"{m:.1%}",
            "Difference": f"{abs(h - m):.1%}",
            "UCITS": "EU" if ticker in _UCITS_TICKERS else "—",
        })

    st.dataframe(
        pd.DataFrame(comparison_rows),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Markowitz typically produces more concentrated portfolios. "
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
# Page 3 -- Chat Advisor
# ---------------------------------------------------------------------------

def render_chat() -> None:
    """
    Chat Advisor: two-column layout.
    Left  — unified chat panel (empty state / active bubbles + input form)
    Right — info panel (capabilities, disclaimer footer)
    """
    from datetime import datetime
    import streamlit.components.v1 as components
    import httpx as _httpx

    # ── Fixed top section: title · disclaimer · divider · profile bar ─────
    page_header("Chat Advisor", "LLM Narrator · Validated responses")
    render_disclaimer()
    st.markdown("---")

    profile_data = st.session_state.get("profile", {})
    raw_label    = profile_data.get("profile_label", "MODERATE")
    profile_key  = _LABEL_TO_MOCK.get(raw_label, "balanced")

    st.info(f"Active profile: **{raw_label}**")

    # ── Session state ──────────────────────────────────────────────────────
    _now = datetime.now().strftime("%H:%M")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [
            {
                "role": "assistant",
                "content": (
                    "Hi! I'm your AI Finance Assistant. "
                    "How can I help you with your portfolio today?"
                ),
                "timestamp": _now,
            }
        ]

    # ── API key ────────────────────────────────────────────────────────────
    if "ANTHROPIC_API_KEY" not in os.environ:
        try:
            os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            pass

    # ── Backend helper ─────────────────────────────────────────────────────
    def _call_backend(text: str) -> str:
        """Call FastAPI /advice; fall back to direct NarratorClient. Never raises."""
        try:
            resp = _httpx.post(
                "http://localhost:8000/advice",
                json={"question": text, "profile": raw_label},
                timeout=10.0,
            )
            if resp.status_code == 503:
                return (
                    "I'm currently unavailable — the backend is still starting up. "
                    "Please try again in a moment."
                )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("answer") or data.get("safe_text") or str(data)
        except Exception:
            pass
        # Direct NarratorClient fallback
        try:
            payload  = get_mock_payload(profile_key)
            narrator = NarratorClient()
            nresp    = narrator.narrate(payload, text)
            if nresp.injection_blocked:
                return "Your question could not be processed. Please rephrase it."
            if nresp.api_error:
                return "Sorry, I could not reach the advisor. Please try again."
            result = validate(
                response_text=nresp.raw_text,
                allowed_numbers=payload.llm_constraints.allowed_numbers,
                forbidden_phrases=payload.llm_constraints.forbidden_phrases,
                eu_awareness_required=payload.regulatory_context.profiler_us_centric_caveat,
            )
            return result.safe_text
        except Exception:
            return "Sorry, I could not reach the advisor. Please try again."

    # ── CSS ────────────────────────────────────────────────────────────────
    st.markdown("""
<style>
.ca-card {
    background: #0f1628;
    border: .5px solid #1e2d4a;
    border-radius: 12px;
    overflow: hidden;
}
/* chip pills */
.ca-chip button {
    background: #0a1020 !important;
    border: 1px solid #1e2d4a !important;
    border-radius: 20px !important;
    color: #6a8aaa !important;
    font-size: 10.5px !important;
    padding: 5px 14px !important;
    height: auto !important;
    min-height: 0 !important;
    line-height: 1.4 !important;
    box-shadow: none !important;
    width: auto !important;
}
.ca-chip button:hover {
    background: #131c30 !important;
    color: #90aace !important;
    border-color: #2e4a6a !important;
}
/* input text box */
.ca-input input[type="text"] {
    background: #0a0f1e !important;
    border: 1px solid #1e2d4a !important;
    color: #c0d0f0 !important;
    border-radius: 8px !important;
}
.ca-input input[type="text"]::placeholder { color: #3a4a6a !important; }
/* remove hidden-label gap so button aligns with input field */
.ca-input div[data-testid="stTextInput"] > label { display: none !important; }
.ca-input div[data-testid="stTextInput"] { margin-bottom: 0 !important; padding-top: 0 !important; }
/* send button */
.ca-input div[data-testid="stButton"] > button {
    height: 38px !important;
    width: 100% !important;
    margin-top: 0 !important;
    padding: 0 !important;
    background: #185FA5 !important;
    border: none !important;
    border-radius: 8px !important;
    color: white !important;
    font-size: 16px !important;
    box-shadow: none !important;
}
.ca-input div[data-testid="stButton"] > button:hover { background: #1a70c0 !important; }
</style>
""", unsafe_allow_html=True)

    # ── Layout ─────────────────────────────────────────────────────────────
    col_left, col_right = st.columns([5, 1])
    history  = st.session_state["chat_history"]
    is_empty = len(history) == 1   # only the greeting

    # ══════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — chat panel
    # ══════════════════════════════════════════════════════════════════════
    with col_left:

        # ── Empty state ────────────────────────────────────────────────
        if is_empty:
            st.markdown('<div class="ca-card" style="padding:24px 20px 16px;">',
                        unsafe_allow_html=True)
            st.markdown("""
<div style="text-align:center;padding:20px 0 12px;">
  <div style="width:46px;height:46px;background:#131c30;border-radius:50%;
              display:inline-flex;align-items:center;justify-content:center;
              margin-bottom:10px;">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#6a8aaa"
         stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="8" width="18" height="12" rx="2"/>
      <path d="M12 8V5"/><circle cx="12" cy="4" r="1"/>
      <rect x="7" y="12" width="2" height="2"/>
      <rect x="15" y="12" width="2" height="2"/>
      <path d="M9 17h6"/>
    </svg>
  </div>
  <div style="font-size:13px;color:#c0d0f0;font-weight:600;margin-bottom:6px;">
    Hi! I'm your AI Finance Assistant.
  </div>
  <div style="font-size:11px;color:#3a4a6a;max-width:300px;margin:0 auto;line-height:1.5;">
    Ask a question about your portfolio, market trends, or investment strategy.
  </div>
</div>
<div style="font-size:10px;color:#3a4a6a;text-align:center;margin-bottom:10px;">
  Try asking...
</div>
""", unsafe_allow_html=True)

            _CHIPS = [
                "Why is my bond allocation high?",
                "Explain my risk profile",
                "EU investor caveat?",
            ]
            chip_cols = st.columns(len(_CHIPS))
            for _i, (_cc, _ctxt) in enumerate(zip(chip_cols, _CHIPS)):
                with _cc:
                    st.markdown('<div class="ca-chip">', unsafe_allow_html=True)
                    if st.button(_ctxt, key=f"chip_{_i}"):
                        _ts = datetime.now().strftime("%H:%M")
                        st.session_state["chat_history"].append(
                            {"role": "user", "content": _ctxt, "timestamp": _ts}
                        )
                        with st.spinner("Thinking..."):
                            _reply = _call_backend(_ctxt)
                        _ts2 = datetime.now().strftime("%H:%M")
                        st.session_state["chat_history"].append(
                            {"role": "assistant", "content": _reply, "timestamp": _ts2}
                        )
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

        # ── Active chat state ──────────────────────────────────────────
        else:
            _DISC_HTML = (
                '<div style="font-size:9px;color:#3a4a6a;margin-top:5px;">'
                "This is an educational prototype. "
                "No content constitutes financial advice under MiFID II."
                "</div>"
            )
            first_ts   = history[0]["timestamp"]
            msgs_html  = (
                f'<div style="text-align:center;font-size:10px;color:#3a4a6a;'
                f'margin-bottom:12px;">Today · {first_ts}</div>'
            )
            for _msg in history:
                _safe = (
                    _msg["content"]
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>")
                )
                if _msg["role"] == "assistant":
                    msgs_html += (
                        f'<div style="display:flex;align-items:flex-start;gap:8px;'
                        f'margin-bottom:12px;">'
                        f'<div style="width:28px;height:28px;background:#0d2a4a;'
                        f'border-radius:50%;display:flex;align-items:center;'
                        f'justify-content:center;flex-shrink:0;font-size:10px;'
                        f'color:#60aaff;font-weight:600;">RA</div>'
                        f'<div style="background:#131c2e;border:1px solid #1e2d45;'
                        f'border-radius:4px 10px 10px 10px;padding:8px 12px;'
                        f'color:#c8d8f0;font-size:12px;max-width:85%;line-height:1.5;">'
                        f'{_safe}{_DISC_HTML}</div></div>'
                    )
                else:
                    msgs_html += (
                        f'<div style="display:flex;align-items:flex-start;gap:8px;'
                        f'margin-bottom:12px;justify-content:flex-end;">'
                        f'<div style="background:#0a2018;border:1px solid #0f3a28;'
                        f'border-radius:10px 10px 4px 10px;padding:8px 12px;'
                        f'color:#80c8a0;font-size:12px;max-width:85%;line-height:1.5;">'
                        f'{_safe}</div>'
                        f'<div style="width:28px;height:28px;background:#0f3d2e;'
                        f'border-radius:50%;display:flex;align-items:center;'
                        f'justify-content:center;flex-shrink:0;font-size:10px;'
                        f'color:#1D9E75;font-weight:600;">U</div></div>'
                    )

            components.html(
                f"""<!DOCTYPE html><html><head><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#0f1628;font-family:'DM Sans',system-ui,sans-serif;}}
#m{{height:380px;overflow-y:auto;padding:16px;}}
#m::-webkit-scrollbar{{width:4px;}}
#m::-webkit-scrollbar-track{{background:#0a0f1e;}}
#m::-webkit-scrollbar-thumb{{background:#1e2d4a;border-radius:2px;}}
</style></head><body>
<div id="m">{msgs_html}</div>
<script>var e=document.getElementById('m');e.scrollTop=e.scrollHeight;</script>
</body></html>""",
                height=412,
                scrolling=False,
            )

        # ── Input row (shared by both states) ─────────────────────────
        st.markdown(
            '<div class="ca-input" style="background:#0d1220;'
            'border-top:1px solid #1a2240;padding:8px 12px 10px;'
            'border-radius:0 0 12px 12px;">',
            unsafe_allow_html=True,
        )

        _col_i, _col_b = st.columns([11, 1])
        with _col_i:
            _user_input = st.text_input(
                "",
                placeholder="Ask about your portfolio...",
                max_chars=500,
                label_visibility="collapsed",
                key="_chat_input",
            )
            _cur_len = len(st.session_state.get("_chat_input", "") or "")
            if _cur_len > 400:
                st.caption(f"{_cur_len}/500")
        with _col_b:
            st.markdown("<div style='margin-top:2px'>", unsafe_allow_html=True)
            _send_clicked = st.button("➤", key="send_btn", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Process send
        if _send_clicked and _user_input and _user_input.strip():
            _pending = _user_input.strip()
            st.session_state["_chat_input"] = ""  # clear input
            _ts = datetime.now().strftime("%H:%M")
            st.session_state["chat_history"].append(
                {"role": "user", "content": _pending, "timestamp": _ts}
            )
            with st.spinner("Thinking..."):
                _reply = _call_backend(_pending)
            _ts2 = datetime.now().strftime("%H:%M")
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": _reply, "timestamp": _ts2}
            )
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # RIGHT COLUMN — info panel
    # ══════════════════════════════════════════════════════════════════════
    with col_right:
        _chk = (
            '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"'
            ' stroke="#1D9E75" stroke-width="2.5">'
            '<polyline points="20 6 9 17 4 12"/></svg>'
        )
        _xmk = (
            '<svg width="11" height="11" viewBox="0 0 24 24" fill="none"'
            ' stroke="#A32D2D" stroke-width="2.5">'
            '<line x1="18" y1="6" x2="6" y2="18"/>'
            '<line x1="6" y1="6" x2="18" y2="18"/></svg>'
        )
        _can_items = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;padding:6px 0;'
            f'border-bottom:.5px solid #141e30;">{_chk}'
            f'<span style="font-size:12.5px;color:#8aaad0;">{it}</span></div>'
            for it in [
                "Portfolio weights",
                "Risk clusters",
                "Historical drawdowns",
                "EU / UCITS caveats",
            ]
        )
        _cant_items = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;padding:6px 0;'
            f'border-bottom:.5px solid #141e30;">{_xmk}'
            f'<span style="font-size:12.5px;color:#8aaad0;">{it}</span></div>'
            for it in [
                "Buy/sell recommendations",
                "Future return predictions",
            ]
        )
        st.markdown(f"""
<div class="ca-card" style="padding:14px 12px;display:flex;flex-direction:column;
                             min-height:480px;">
  <div style="font-size:13px;color:#8aaad0;font-weight:600;margin-bottom:10px;
              display:flex;align-items:center;gap:6px;">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8aaad0"
         stroke-width="2"><circle cx="12" cy="12" r="10"/>
         <path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
    What this advisor can explain
  </div>
  <div style="font-size:11px;color:#3a4a6a;margin-bottom:6px;
              text-transform:uppercase;letter-spacing:.04em;">Can explain</div>
  {_can_items}
  <div style="font-size:11px;color:#3a4a6a;margin-top:12px;margin-bottom:6px;
              text-transform:uppercase;letter-spacing:.04em;">Cannot do</div>
  {_cant_items}
  <div style="margin-top:auto;padding-top:12px;border-top:.5px solid #141e30;
              display:flex;align-items:flex-start;gap:6px;">
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#3a4a6a"
         stroke-width="2" style="flex-shrink:0;margin-top:1px;">
      <rect x="3" y="11" width="18" height="11" rx="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
    <span style="font-size:11px;color:#3a4a6a;line-height:1.4;">
      All responses are validated and grounded in approved data.
    </span>
  </div>
</div>
""", unsafe_allow_html=True)


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
    if profile_label == "aggressive":
        profile_label = "moderate"  # only moderate JSON available

    summary_file = _BACKTEST_DIR / f"backtest_summary_{profile_label}.json"

    if not summary_file.exists():
        st.info(
            "Backtest data not found. Run `scripts/run_backtest.py` to generate it. "
            "Walk-forward simulations will appear here automatically once the file is present."
        )
        return

    with open(summary_file) as fh:
        summary = json.load(fh)

    selected = st.selectbox(
        "Stress scenario",
        options=list(_SCENARIO_LABELS.keys()),
        format_func=lambda k: _SCENARIO_LABELS[k],
    )

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
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig = apply_plotly_dark_theme(fig)
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
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig_dd = apply_plotly_dark_theme(fig_dd)
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
