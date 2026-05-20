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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from backend.llm.narrator import NarratorClient, NarratorError
from backend.llm.validator import validate
from backend.schemas.mock_data import get_mock_payload

# ---------------------------------------------------------------------------
# Page config -- must be the first Streamlit call in the file
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Robo-Advisor -- USI 2026",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# MiFID II disclaimer shown above every financial output
DISCLAIMER = (
    "**Educational prototype** developed in an academic context. "
    "No content constitutes financial advice under MiFID II or any other "
    "regulatory framework. Market data may be inaccurate or delayed."
)

# Maps the uppercase profile label from the backend to the lowercase key
# used by get_mock_payload()
_LABEL_TO_MOCK: dict[str, str] = {
    "CONSERVATIVE": "conservative",
    "MODERATE": "balanced",
    "AGGRESSIVE": "aggressive",
}

# UCITS-eligible tickers in the universe -- used to display the EU badge
_UCITS_TICKERS: frozenset[str] = frozenset({"CSPX.L", "AGGH.MI", "XEON.MI"})

# Start date for the live market data download
_DATA_START: str = "2023-01-01"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def show_disclaimer() -> None:
    # Show the mandatory MiFID II disclaimer at the top of every page
    st.warning(DISCLAIMER)


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

PAGES = ["Questionnaire", "Portfolio Dashboard", "Chat Advisor"]


def main() -> None:
    # Sidebar with page selector
    st.sidebar.title("Robo-Advisor")
    st.sidebar.caption("USI -- Programming in Finance II -- 2026")
    page = st.sidebar.radio("Navigation", PAGES)

    if page == PAGES[0]:
        render_questionnaire()
    elif page == PAGES[1]:
        render_portfolio()
    elif page == PAGES[2]:
        render_chat()


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
    st.title("Investor Profile Questionnaire")
    show_disclaimer()
    st.markdown("---")
    st.markdown(
        "Answer all 10 questions honestly. "
        "Your responses determine your investor risk profile."
    )

    answers: dict[str, int] = {}
    current_section = ""

    with st.form("questionnaire_form"):
        for q in _QUESTIONS:
            # Print a section header when the section changes
            if q["section"] != current_section:
                current_section = q["section"]
                st.subheader(current_section)

            selected = st.radio(
                label=f"**{q['id']}. {q['text']}**",
                options=q["options"],
                index=None,  # no pre-selected default -- user must choose
                key=f"q_{q['id']}",
            )
            answers[q["id"]] = q["options"].index(selected) if selected else None

        submitted = st.form_submit_button("Calculate my profile")

    if submitted:
        # Make sure all questions are answered before computing
        if any(v is None for v in answers.values()):
            st.error("Please answer all questions before submitting.")
            return

        result = _compute_profile(answers)
        st.session_state["profile"] = result
        st.session_state["questionnaire_answers"] = answers

        # Clear any cached portfolio so the Dashboard reloads for the new profile
        st.session_state.pop("portfolio_data", None)

        st.success("Profile calculated. Navigate to Portfolio Dashboard.")
        st.metric("Your risk profile", result["profile_label"])
        st.metric("Confidence", f"{result['confidence']:.0%}")

        if result["low_confidence_flag"]:
            st.warning("Borderline score -- consider reviewing your answers.")

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
    st.title("Portfolio Dashboard")
    show_disclaimer()
    st.markdown("---")

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

    # Toggle between mock data (Phase A) and live optimizer (Phase B)
    use_live = st.toggle(
        "Load live market data",
        value=False,
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
    st.markdown("**Portfolio Weights**")

    # Build the weights table
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
    # plot_risk_contributions is defined in backend/optimizer/charts.py
    try:
        from backend.optimizer.charts import plot_risk_contributions
        fig = plot_risk_contributions(
            risk_contributions,
            profile_label=st.session_state.get("profile", {}).get("profile_label", ""),
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.caption(f"Chart unavailable: {exc}")

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
    Chat Advisor: user types a question, the LLM narrator answers,
    the validator checks the response, result is shown to the user.

    3-stage pipeline:
        Stage 1 -- build Ground Truth JSON from mock payload
        Stage 2 -- call NarratorClient (Claude API)
        Stage 3 -- run 5-step validator before showing anything
    """
    st.title("Chat Advisor")
    show_disclaimer()
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

                # Show any validator flags that were triggered
                # Remove this block before the final demo
                if result.flags:
                    st.caption(f"Validator flags: {[f.value for f in result.flags]}")

            except NarratorError:
                # NarratorClient raised at construction -- API key is missing
                st.error(
                    "ANTHROPIC_API_KEY is not configured. "
                    "Add it to .streamlit/secrets.toml or set it as an environment variable."
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
main()
