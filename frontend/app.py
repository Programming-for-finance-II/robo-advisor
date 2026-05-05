"""
frontend/app.py — Streamlit UI scaffold
AI-Powered Robo-Advisor Platform
Programming in Finance II (2026) — USI
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Robo-Advisor — USI 2026",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global disclaimer (mandatory above every financial output — MiFID II)
# ---------------------------------------------------------------------------
DISCLAIMER = (
    " **Educational prototype** developed in an academic context. "
    "No content constitutes financial advice under MiFID II or any other "
    "regulatory framework. Market data may be inaccurate or delayed."
)

def show_disclaimer() -> None:
    """Render the mandatory MiFID II educational disclaimer."""
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
PAGES = ["Questionnaire", "Portfolio Dashboard", "Chat Advisor"]

def main() -> None:
    """Main entry point — renders sidebar navigation and active page."""
    st.sidebar.title("Robo-Advisor")
    st.sidebar.caption("USI · Programming in Finance II · 2026")
    page = st.sidebar.radio("Navigation", PAGES)

    if page == PAGES[0]:
        render_questionnaire()
    elif page == PAGES[1]:
        render_portfolio()
    elif page == PAGES[2]:
        render_chat()

# ---------------------------------------------------------------------------
# Questionnaire data — Grable & Lytton (1999) adapted
# ---------------------------------------------------------------------------
# Each question maps to one of three sections of the risk profiling framework.
# Every option carries a score (0–3); the total score (0–30) determines the
# investor profile label.  Q7 carries a hard override: selecting option 0
# ("safety net") forces profile CONSERVATIVE regardless of the total score,
# in line with MiFID II suitability assessment requirements.

_QUESTIONS: list[dict] = [
    # --- Section 1: Who You Are Financially ---
    # Demographic and financial capacity questions.
    # Younger investors with higher income and net worth can typically
    # afford more risk, hence higher scores map to more aggressive profiles.
    {
        "id": "Q1",
        "section": "Who You Are Financially",
        "text": "What is your current age?",
        "options": ["Over 65", "56-65", "36-55", "18-35"],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q2",
        "section": "Who You Are Financially",
        "text": "What is your approximate annual household income?",
        "options": [
            "Under 25,000 EUR",
            "25,000-50,000 EUR",
            "50,000-100,000 EUR",
            "Over 100,000 EUR",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q3",
        "section": "Who You Are Financially",
        "text": "What is your approximate net worth (assets minus debts)?",
        "options": [
            "Under 10,000 EUR",
            "10,000-50,000 EUR",
            "50,000-150,000 EUR",
            "Over 150,000 EUR",
        ],
        "scores": [0, 1, 2, 3],
    },
    # --- Section 2: How You Invest ---
    # Investment behaviour and financial literacy questions.
    # Longer horizons and greater experience support higher risk tolerance.
    {
        "id": "Q4",
        "section": "How You Invest",
        "text": "What is your investment time horizon?",
        "options": [
            "Less than 2 years",
            "2-5 years",
            "5-10 years",
            "More than 10 years",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q5",
        "section": "How You Invest",
        "text": "How would you describe your investment experience?",
        "options": [
            "None - I have never invested",
            "Limited - a few investments",
            "Moderate - I invest regularly",
            "Extensive - I actively manage a portfolio",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q6",
        "section": "How You Invest",
        "text": "How familiar are you with financial products (ETFs, bonds, equities)?",
        "options": [
            "Not at all",
            "Slightly familiar",
            "Moderately familiar",
            "Very familiar",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q7",
        "section": "How You Invest",
        "text": "When you invest, what is most important to you?",
        "options": [
            "Protecting my capital above all - safety net",
            "Mostly preserving capital with some growth",
            "Balancing growth and security",
            "Maximising long-term growth, even with higher risk",
        ],
        "scores": [0, 1, 2, 3],
        # Hard override: option index 0 forces profile_label = CONSERVATIVE.
        # This implements the MiFID II suitability hard constraint: a client
        # who explicitly prioritises capital protection must not be classified
        # as Moderate or Aggressive regardless of other answers.
        "override": True,
    },
    # --- Section 3: How You React ---
    # Behavioural questions placed last to reduce social desirability bias
    # (Grable & Lytton, 1999).  Q9 uses first-person framing intentionally.
    {
        "id": "Q8",
        "section": "How You React",
        "text": "If your portfolio dropped 20% in one month, what would you do?",
        "options": [
            "Sell everything immediately",
            "Sell part of it to reduce risk",
            "Hold and wait for recovery",
            "Buy more - it is a buying opportunity",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q9",
        "section": "How You React",
        "text": "Thinking about your own investing behaviour: which best describes you?",
        "options": [
            "I avoid any investment that could lose value",
            "I accept small losses for modest gains",
            "I accept moderate losses for good long-term gains",
            "I accept large short-term losses for potentially high returns",
        ],
        "scores": [0, 1, 2, 3],
    },
    {
        "id": "Q10",
        "section": "How You React",
        "text": "How many dependants rely on your income?",
        "options": ["3 or more", "2", "1", "None"],
        "scores": [0, 1, 2, 3],
    },
]

# Scoring thresholds (Grable & Lytton adapted, range 0-30)
_SCORE_CONSERVATIVE_MAX: int = 9
_SCORE_MODERATE_MAX: int = 19

# Borderline scores produce low confidence: the profile assignment is less
# certain and the UI warns the user to review their answers.
_CONFIDENCE_BORDERLINE_SCORES: set[int] = {8, 9, 10, 11, 18, 19, 20, 21}


def _compute_profile(answers: dict[str, int]) -> dict:
    """Compute the investor risk profile from questionnaire answers.

    Implements Phase A rule-based scoring (Grable & Lytton, 1999).
    The output schema is identical to the Phase B GBM classifier output
    so downstream modules (narrator, validator, dashboard) require no
    changes when Phase B is integrated.

    Parameters
    ----------
    answers : dict[str, int]
        Mapping of question ID to selected option index (0-based).

    Returns
    -------
    dict
        profile_label        : "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE"
        score                : int, total Grable-Lytton score (0-30)
        confidence           : float, certainty of the classification (0-1)
        low_confidence_flag  : bool, True if score is in a borderline zone
        top_drivers          : list of top 3 questions by answer weight
        q7_override_applied  : bool, True if the MiFID II hard rule fired
    """
    # Apply Q7 override before computing the total score.
    q7_override: bool = answers.get("Q7", -1) == 0

    score: int = sum(
        q["scores"][answers[q["id"]]]
        for q in _QUESTIONS
        if q["id"] in answers
    )

    if q7_override:
        profile_label = "CONSERVATIVE"
        confidence: float = 1.0          # hard rule, no uncertainty
    elif score <= _SCORE_CONSERVATIVE_MAX:
        profile_label = "CONSERVATIVE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.85
    elif score <= _SCORE_MODERATE_MAX:
        profile_label = "MODERATE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.82
    else:
        profile_label = "AGGRESSIVE"
        confidence = 0.55 if score in _CONFIDENCE_BORDERLINE_SCORES else 0.88

    low_confidence_flag: bool = confidence < 0.65

    # Top drivers: questions ranked by the fraction of their maximum
    # possible score that the user actually selected (0.0 to 1.0).
    # In Phase B this will be replaced by SHAP values from the GBM model.
    scored_questions = sorted(
        [
            {"feature": q["id"], "importance": answers[q["id"]] / 3.0}
            for q in _QUESTIONS
            if q["id"] in answers
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )
    top_drivers = scored_questions[:3]

    return {
        "profile_label": profile_label,
        "score": score,
        "confidence": confidence,
        "low_confidence_flag": low_confidence_flag,
        "top_drivers": top_drivers,
        "q7_override_applied": q7_override,
    }


# ---------------------------------------------------------------------------
# Page 1 — Questionnaire
# ---------------------------------------------------------------------------
def render_questionnaire() -> None:
    """Render the investor risk profiling questionnaire.

    Presents 10 questions grouped by section.  On submission, calls
    _compute_profile() and stores the result in st.session_state["profile"]
    for consumption by render_portfolio() and render_chat().
    """
    st.title("Investor Profile Questionnaire")
    show_disclaimer()
    st.markdown("---")
    st.markdown(
        "Answer all 10 questions honestly. Your responses determine your "
        "investor risk profile. There are no right or wrong answers."
    )

    answers: dict[str, int] = {}
    current_section = ""

    with st.form("questionnaire_form"):
        for q in _QUESTIONS:
            # Print section header when the section changes
            if q["section"] != current_section:
                current_section = q["section"]
                st.subheader(current_section)

            selected = st.radio(
                label=f"**{q['id']}. {q['text']}**",
                options=q["options"],
                index=None,     # no pre-selected default: user must choose
                key=f"q_{q['id']}",
            )
            answers[q["id"]] = q["options"].index(selected) if selected else None

        submitted = st.form_submit_button("Calculate my profile")

    if submitted:
        if any(v is None for v in answers.values()):
            st.error("Please answer all questions before submitting.")
            return

        result = _compute_profile(answers)
        st.session_state["profile"] = result
        st.session_state["questionnaire_answers"] = answers

        st.success(
            "Profile calculated. Navigate to Portfolio Dashboard to see "
            "your personalised allocation."
        )

        # Inline preview of the result
        st.metric("Your risk profile", result["profile_label"])
        st.metric("Confidence", f"{result['confidence']:.0%}")

        if result["low_confidence_flag"]:
            st.warning(
                "Your score is in a borderline zone. "
                "Consider reviewing your answers for a more reliable result."
            )
        if result["q7_override_applied"]:
            st.info(
                "Your answer to Q7 has set your profile to CONSERVATIVE "
                "regardless of other answers (capital protection priority, "
                "MiFID II suitability rule)."
            )

# ---------------------------------------------------------------------------
# Page 2 — Portfolio Dashboard
# ---------------------------------------------------------------------------
def render_portfolio() -> None:
    """Portfolio dashboard: HRP weights, risk metrics, EU Investor Note.

    Reads the profile computed by render_questionnaire() from session_state.
    Falls back to MODERATE mock data if the user navigates here directly
    without completing the questionnaire (Phase A always-works guarantee).
    """
    st.title("Portfolio Dashboard")
    show_disclaimer()
    st.markdown("---")

    # Read profile from session_state; fall back to mock if not yet computed
    profile_data = st.session_state.get("profile", {})
    profile = profile_data.get("profile_label", "MODERATE")
    confidence = profile_data.get("confidence", None)

    st.metric("Investor Profile", profile)
    if confidence is not None:
        st.metric("Confidence", f"{confidence:.0%}")

    st.markdown("---")

    # Tab structure: HRP as default, Markowitz as comparison benchmark
    tab_hrp, tab_mv = st.tabs(["HRP Portfolio", "Markowitz Benchmark"])

    with tab_hrp:
        st.caption("Hierarchical Risk Parity — mock weights")
        mock_weights = {
            "IWDA.L (World Equity)": 0.35,
            "IEMA.L (EM Equity)": 0.15,
            "AGGG.L (Global Bond)": 0.25,
            "IGLO.L (Gov Bond)": 0.15,
            "SGLD.L (Gold)": 0.10,
        }
        for ticker, w in mock_weights.items():
            st.write(f"**{ticker}** — {w:.0%}")

    with tab_mv:
        st.caption("Markowitz Mean-Variance — benchmark (mock)")
        st.write("Markowitz comparison will be available when the optimizer module is integrated.")

    # EU Investor Note — mandatory under EU Awareness Rule 9
    st.markdown("---")
    st.info(
        "EU Investor Note — The risk profile model is trained on "
        "US Federal Reserve SCF data (2022). Results may not fully reflect "
        "the behaviour of European retail investors. (EU Awareness Rule 9)"
    )

# ---------------------------------------------------------------------------
# Page 3 — Chat Advisor
# ---------------------------------------------------------------------------
def render_chat() -> None:
    """Chat Advisor placeholder — LLM Narrator wired in Week 3."""
    st.title("Chat Advisor")
    show_disclaimer()
    st.markdown("---")
    st.info("LLM Narrator (Claude API) — coming in Week 3.")

    st.text_input("Ask about your portfolio...", disabled=True,
                  placeholder="Available in Week 3")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()