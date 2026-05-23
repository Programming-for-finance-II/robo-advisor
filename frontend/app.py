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

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
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

    # Info card — Grable-Lytton explanation (only this one, no icon on page title)
    st.markdown(
        """
        <div style="
            background: rgba(30,38,64,0.5);
            border: 1px solid #1e2640;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            margin-bottom: 1.25rem;
            display: flex;
            gap: 0.875rem;
            align-items: flex-start;
        ">
            <div style="
                width:2rem;height:2rem;flex-shrink:0;
                background:rgba(59,130,246,0.12);
                border:1px solid rgba(59,130,246,0.25);
                border-radius:7px;
                display:inline-flex;align-items:center;
                justify-content:center;font-size:0.95rem;
            ">🎓</div>
            <div>
                <div style="
                    font-family:'Space Grotesk',sans-serif;
                    font-size:0.9rem;font-weight:600;
                    color:#e2e8f0;margin-bottom:0.25rem;
                ">What is the Grable-Lytton Scale?</div>
                <div style="font-size:0.79rem;color:#64748b;line-height:1.55;">
                    An academic risk-tolerance questionnaire used to estimate how much financial
                    risk an investor is willing and able to take. In this prototype, it provides
                    the rule-based baseline for the investor profile.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="font-size:0.85rem;color:#64748b;margin:0 0 1.5rem 0;">'
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
        },
        {
            "number": "02",
            "title": "Investment Behaviour",
            "subtitle": "How you think about time horizon, return and uncertainty.",
            "key": "How You Invest",
        },
        {
            "number": "03",
            "title": "Reaction to Risk",
            "subtitle": "How you would react under market stress.",
            "key": "How You React",
        },
    ]

    with st.form("questionnaire_form"):
        for section in sections:
            # Each section is its own independent card — siblings, not nested
            with st.container(border=True):
                st.markdown(
                    f"""
                    <div class="qs-header">
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
                            <span class="qs-q-badge">{q["id"]}</span>
                            <span class="qs-q-text">{q["text"]}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    selected = st.radio(
                        label="",
                        options=q["options"],
                        index=None,
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

        st.success("Profile calculated. Navigate to Portfolio Dashboard.")
        col_a, col_b = st.columns(2)
        col_a.metric("Your risk profile", result["profile_label"])
        col_b.metric("Confidence", f"{result['confidence']:.0%}")

        if result["low_confidence_flag"]:
            st.warning("Borderline score — consider reviewing your answers.")

        if result["q7_override_applied"]:
            st.info(
                "Q7 override applied: capital earmarked as a safety net "
                "forces profile to CONSERVATIVE (MiFID II suitability rule)."
            )


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
    page_header("Portfolio Dashboard", "HRP optimization · Balanced profile")
    render_disclaimer()
    render_eu_note()

    # Read the profile that was set by the Questionnaire page
    profile_data = st.session_state.get("profile", {})
    profile_label = profile_data.get("profile_label", "MODERATE")
    confidence = profile_data.get("confidence", None)
    profile_key = _LABEL_TO_MOCK.get(profile_label, "balanced")

    # Show current profile at the top
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Investor Profile", profile_label)
    with col2:
        if confidence is not None:
            st.metric("Confidence", f"{confidence:.0%}")

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


def _render_hrp_tab(portfolio: dict) -> None:
    """
    HRP tab: key metrics, weights table with UCITS column, risk chart.
    """
    st.subheader("Hierarchical Risk Parity -- Portfolio Allocation")

    weights: dict[str, float] = portfolio["weights"]
    risk_contributions: dict[str, float] = portfolio["risk_contributions"]
    ucits_used: list[str] = portfolio.get("ucits_tickers_used", [])
    vol: float = portfolio.get("expected_volatility", 0.0)
    exp_ret = portfolio.get("expected_return")
    sharpe = portfolio.get("sharpe_ratio")
    max_dd = portfolio.get("max_drawdown")

    # Key metrics row
    m_cols = st.columns(4)
    m_cols[0].metric("Annual Volatility", f"{vol:.1%}")
    if exp_ret is not None:
        m_cols[1].metric("Exp. Return (hist.)", f"{exp_ret:.1%}")
    if sharpe is not None:
        m_cols[2].metric("Sharpe Ratio", f"{sharpe:.2f}")
    if max_dd is not None:
        m_cols[3].metric("Max Drawdown (hist.)", f"{max_dd:.1%}")

    st.markdown("---")

    # Donut chart + weights table side by side
    col_donut, col_table = st.columns([1, 1.1])

    with col_donut:
        try:
            from backend.optimizer.charts import plot_weights_donut
            fig_donut = plot_weights_donut(weights)
            fig_donut = apply_plotly_dark_theme(fig_donut)
            st.plotly_chart(fig_donut, use_container_width=True)
        except Exception as exc:
            st.caption(f"Chart unavailable: {exc}")

    with col_table:
        st.markdown("**Portfolio Weights**")
        # UCITS-eligible tickers show "EU" in the UCITS column, others show "-"
        ucits_set = set(ucits_used) | _UCITS_TICKERS
        rows = []
        for ticker, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            rows.append({
                "Ticker": ticker,
                "Weight": f"{w:.1%}",
                "UCITS": "EU" if ticker in ucits_set else "-",
                "Risk Contrib.": f"{risk_contributions.get(ticker, 0.0):.1%}",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)

    # Risk contribution bar chart
    try:
        from backend.optimizer.charts import plot_risk_contributions
        fig = plot_risk_contributions(
            risk_contributions,
            profile_label=st.session_state.get("profile", {}).get("profile_label", ""),
        )
        fig = apply_plotly_dark_theme(fig)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.caption(f"Chart unavailable: {exc}")

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
        st.plotly_chart(fig_dend, use_container_width=True)

    except Exception as exc:
        st.caption(f"Dendrogram unavailable: {exc}")


def _render_mv_tab(portfolio: dict, profile_key: str) -> None:
    """
    Markowitz tab: placeholder for HRP vs MV comparison,
    stress scenario table, backtest summary.
    """
    st.subheader("Markowitz Mean-Variance -- Benchmark Comparison")

    # Full side-by-side comparison will be available when P2 finishes /compare
    st.info(
        "Side-by-side HRP vs MV weight comparison will be available "
        "when /compare endpoint is live (P2 W4)."
    )

    # Load stress scenarios -- from live result if available, otherwise from mock
    stress = portfolio.get("stress_scenarios")
    if stress is None:
        try:
            payload = get_mock_payload(profile_key)
            stress = payload.stress_scenarios
        except Exception:
            stress = None

    if stress is not None:
        st.markdown("**Historical Stress Scenarios -- HRP drawdown vs benchmark**")
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
            "Phase B will use real backtested values from P2."
        )

    # Backtest summary row
    backtest = portfolio.get("backtest")
    if backtest is None:
        try:
            payload = get_mock_payload(profile_key)
            backtest = payload.backtest_summary
        except Exception:
            backtest = None

    if backtest is not None:
        st.markdown("**Backtest Summary (mock -- Phase A)**")
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
    Chat Advisor: user types a question, the LLM narrator answers,
    the validator checks the response, result is shown to the user.

    3-stage pipeline:
        Stage 1 -- build Ground Truth JSON from mock payload
        Stage 2 -- call NarratorClient (Claude API)
        Stage 3 -- run 5-step validator before showing anything
    """
    page_header("Chat Advisor", "LLM Narrator · Validated responses")
    render_disclaimer()
    st.markdown("---")

    # Read profile from session_state; default to MODERATE if questionnaire not done
    profile_data = st.session_state.get("profile", {})
    raw_label = profile_data.get("profile_label", "MODERATE")
    profile_key = _LABEL_TO_MOCK.get(raw_label, "balanced")

    st.info(f"Active profile: **{raw_label}**")

    # Show the recommendation_id that links this chat to the portfolio loaded
    # in the Dashboard -- used for the DB audit trail in Phase B
    rec_id = st.session_state.get("recommendation_id", "")
    if rec_id and not rec_id.startswith("mock-"):
        st.caption(f"Linked to portfolio recommendation {rec_id[:12]}...")

    # Load API key from Streamlit secrets or environment variable
    if "ANTHROPIC_API_KEY" not in os.environ:
        try:
            os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            pass

    user_message = st.text_input(
        "Ask about your portfolio...",
        placeholder="E.g. Why is my bond allocation high?",
    )

    if st.button("Ask") and user_message:
        with st.spinner("Generating response..."):
            try:
                # Stage 1: build the Ground Truth JSON for this profile
                # This is the only data the LLM is allowed to reference
                payload = get_mock_payload(profile_key)

                # Stage 2: call the LLM narrator
                # narrator.py assembles the system prompt, injects the GT JSON,
                # and calls the Claude API
                narrator = NarratorClient()
                narrator_response = narrator.narrate(payload, user_message)

                # Stage 3: run the 5-step validator before showing anything
                result = validate(
                    response_text=narrator_response.raw_text,
                    allowed_numbers=payload.llm_constraints.allowed_numbers,
                    forbidden_phrases=payload.llm_constraints.forbidden_phrases,
                    eu_awareness_required=(
                        payload.regulatory_context.profiler_us_centric_caveat
                    ),
                )

                # Display based on what happened at each stage
                if narrator_response.injection_blocked:
                    # The input was flagged as a prompt injection attempt
                    st.warning(
                        "Your question could not be processed. "
                        "Please rephrase it more concisely."
                    )
                elif narrator_response.api_error:
                    # The Claude API call failed (timeout, rate limit, etc.)
                    st.error("Could not reach the AI service. Please try again.")
                elif not result.passed:
                    # The validator blocked the response -- show safe fallback
                    st.warning(result.safe_text)
                else:
                    # Clean response -- show the validated narrative
                    st.markdown(result.safe_text)
           
            except NarratorError:
                # NarratorClient raised at construction -- API key is missing
                st.error(
                    "ANTHROPIC_API_KEY is not configured. "
                    "Add it to .streamlit/secrets.toml or set it as an environment variable."
                )


# ---------------------------------------------------------------------------
# Page 4 -- Backtesting (placeholder)
# ---------------------------------------------------------------------------

def render_backtesting() -> None:
    page_header("Backtesting", "Historical performance simulation", icon="📈")
    render_disclaimer()
    st.info(
        "Backtesting module coming in Phase B. "
        "It will run walk-forward simulations on the HRP portfolio "
        "using historical price data from yfinance."
    )


# ---------------------------------------------------------------------------
# Page 5 -- Compare MV (placeholder)
# ---------------------------------------------------------------------------

def render_compare() -> None:
    page_header("Compare (MV)", "HRP vs Markowitz mean-variance", icon="⚖")
    render_disclaimer()
    st.info(
        "Side-by-side comparison of HRP and Mean-Variance portfolios "
        "coming in Phase B (P2 W4 /compare endpoint)."
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
