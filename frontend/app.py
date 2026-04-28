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
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Global disclaimer (mandatory above every financial output — MiFID II)
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "⚠️ **Educational prototype** developed in an academic context. "
    "No content constitutes financial advice under MiFID II or any other "
    "regulatory framework. Market data may be inaccurate or delayed."
)

def show_disclaimer() -> None:
    """Render the mandatory MiFID II educational disclaimer."""
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
PAGES = ["📋 Questionnaire", "📊 Portfolio Dashboard", "💬 Chat Advisor"]

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
# Page 1 — Questionnaire
# ---------------------------------------------------------------------------
def render_questionnaire() -> None:
    """Risk profiling questionnaire (7-10 questions → POST to /profile)."""
    st.title("📋 Investor Profile Questionnaire")
    show_disclaimer()
    st.markdown("---")
    st.info("🔜 Questionnaire UI — coming in Week 2")

    # Mock structure (will be replaced in W2)
    with st.form("questionnaire_form"):
        st.slider("Age", min_value=18, max_value=80, value=35)
        st.selectbox(
            "Investment horizon",
            ["< 2 years", "2–5 years", "5–10 years", "> 10 years"],
        )
        st.selectbox(
            "Reaction to a -20% portfolio drop",
            ["Sell everything", "Sell part", "Hold", "Buy more"],
        )
        submitted = st.form_submit_button("Submit (mock)")
        if submitted:
            st.success("✅ Mock profile saved. Dashboard will use mock data.")
            st.session_state["profile_label"] = "MODERATE"
            st.session_state["confidence"] = 0.72

# ---------------------------------------------------------------------------
# Page 2 — Portfolio Dashboard
# ---------------------------------------------------------------------------
def render_portfolio() -> None:
    """Portfolio dashboard: HRP weights, risk metrics, EU Investor Note."""
    st.title("📊 Portfolio Dashboard")
    show_disclaimer()
    st.markdown("---")
    st.info("🔜 Full dashboard — coming in Week 2. Showing mock data.")

    profile = st.session_state.get("profile_label", "MODERATE")
    st.metric("Investor Profile", profile)

    # Tab structure (HRP vs Markowitz — fully wired in W4)
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
        st.write("Coming in Week 2 when P2 optimizer is ready.")

    # EU Investor Note placeholder
    st.markdown("---")
    st.info(
        "🇪🇺 **EU Investor Note** — The risk profile model is trained on "
        "US Federal Reserve SCF data (2022). Results may not fully reflect "
        "the behaviour of European retail investors. (Rule 9 — EU Awareness)"
    )

# ---------------------------------------------------------------------------
# Page 3 — Chat Advisor
# ---------------------------------------------------------------------------
def render_chat() -> None:
    """Chat Advisor placeholder — LLM Narrator wired in Week 3."""
    st.title("💬 Chat Advisor")
    show_disclaimer()
    st.markdown("---")
    st.info("🔜 LLM Narrator (Claude API) — coming in Week 3.")

    st.text_input("Ask about your portfolio...", disabled=True,
                  placeholder="Available in Week 3")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()