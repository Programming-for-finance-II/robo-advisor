import streamlit as st

# ── Dark theme CSS ────────────────────────────────────────────────────────────

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Space+Grotesk:wght@500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Sidebar nav ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    display: flex !important;
    align-items: center !important;
    gap: 0.75rem !important;
    padding: 0.65rem 0.85rem !important;
    margin: 0.25rem 0 !important;
    border-radius: 10px !important;
    color: #94a3b8 !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(124,92,252,0.15) !important;
    color: #a78bfa !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label p {
    margin: 0 !important;
    line-height: 1.1 !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    white-space: nowrap !important;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; }

[data-testid="stSidebar"] {
    background: #0d1220 !important;
    border-right: 1px solid #1e2640 !important;
}

/* ── Metrics ──────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #111827 !important;
    border: 1px solid #1e2640 !important;
    border-radius: 10px !important;
    padding: 1rem 1.1rem !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.65rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #475569 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.6rem !important;
    font-weight: 600 !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #1e2640 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #475569 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #a78bfa !important;
    border-bottom: 2px solid #7c5cfc !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.stButton > button {
    background: transparent !important;
    border: 1px solid #1e2640 !important;
    color: #94a3b8 !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
}
.stButton > button[kind="primary"] {
    background: rgba(124,92,252,0.15) !important;
    border-color: #7c5cfc !important;
    color: #a78bfa !important;
}

hr { border-color: #1e2640 !important; }

/* ── Questionnaire section cards ──────────────────────────────────────────── */

/* Section container: clip the gradient header to rounded corners */
[data-testid="questionnaire_form"] [data-testid="stVerticalBlockBorderWrapper"] {
    overflow: hidden !important;
    padding: 0 !important;
    background: #0b1120 !important;
    border-color: #1e2640 !important;
}

/* Full-bleed gradient band at top of each section card */
.qs-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.1rem 1.25rem;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0d1220 100%);
    border-bottom: 1px solid #2d3748;
}

.qs-num {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.88rem;
    font-weight: 700;
    color: #a78bfa;
    background: rgba(124,92,252,0.18);
    border: 1px solid rgba(124,92,252,0.3);
    border-radius: 7px;
    min-width: 2.25rem;
    height: 2.25rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.qs-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #f1f5f9;
    line-height: 1.2;
}

.qs-sub {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.15rem;
}

/* Question body wrapper padding */
.qs-body {
    padding: 0.25rem 1.25rem 1rem 1.25rem;
}

/* Question badge + text row */
.qs-q-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin: 1.25rem 0 0.5rem 0;
}

.qs-q-badge {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    color: #a78bfa;
    background: rgba(124,92,252,0.12);
    border: 1px solid rgba(124,92,252,0.25);
    border-radius: 5px;
    padding: 0.12rem 0.45rem;
    flex-shrink: 0;
    letter-spacing: 0.04em;
}

.qs-q-text {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
    line-height: 1.35;
}

/* ── Radio options → 4-column card grid (questionnaire only) ─────────────── */

[data-testid="questionnaire_form"] div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: grid !important;
    grid-template-columns: repeat(4, 1fr) !important;
    gap: 0.5rem !important;
    margin-top: 0.25rem !important;
    margin-bottom: 0.5rem !important;
}

[data-testid="questionnaire_form"] div[data-testid="stRadio"] label {
    background: rgba(10, 15, 30, 0.65) !important;
    border: 1px solid #1e2640 !important;
    border-radius: 9px !important;
    padding: 0.8rem 0.95rem !important;
    cursor: pointer !important;
    min-height: 3.5rem !important;
    display: flex !important;
    align-items: flex-start !important;
    gap: 0.5rem !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
}

[data-testid="questionnaire_form"] div[data-testid="stRadio"] label:hover {
    border-color: rgba(124,92,252,0.45) !important;
    background: rgba(124,92,252,0.07) !important;
}

[data-testid="questionnaire_form"] div[data-testid="stRadio"] label:has(input:checked) {
    border-color: #7c5cfc !important;
    background: rgba(124,92,252,0.14) !important;
}

[data-testid="questionnaire_form"] div[data-testid="stRadio"] label p {
    font-size: 0.8rem !important;
    color: #94a3b8 !important;
    line-height: 1.45 !important;
    margin: 0 !important;
}

[data-testid="questionnaire_form"] div[data-testid="stRadio"] label:has(input:checked) p {
    color: #c4b5fd !important;
}

/* Submit button */
[data-testid="questionnaire_form"] [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    background: rgba(124,92,252,0.15) !important;
    border: 1px solid #7c5cfc !important;
    color: #c4b5fd !important;
    border-radius: 10px !important;
    padding: 0.875rem !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em !important;
    margin-top: 0.5rem !important;
    transition: background 0.15s ease !important;
}

[data-testid="questionnaire_form"] [data-testid="stFormSubmitButton"] button:hover {
    background: rgba(124,92,252,0.25) !important;
}
</style>
"""

DISCLAIMER_HTML = """
<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);
border-radius:8px;padding:8px 12px;margin-bottom:1rem;
font-size:0.72rem;color:#d97706;display:flex;align-items:flex-start;gap:8px;">
  <span style="flex-shrink:0;">⚠</span>
  Educational prototype — no content constitutes financial advice under MiFID II.
  Market data may be delayed or inaccurate.
</div>
"""

EU_NOTE_HTML = """
<div style="background:rgba(124,92,252,0.08);border:1px solid rgba(124,92,252,0.25);
border-radius:8px;padding:8px 12px;margin-bottom:1rem;
font-size:0.72rem;color:#a78bfa;display:flex;align-items:flex-start;gap:8px;">
  <span style="flex-shrink:0;">ℹ</span>
  EU investor note: model trained on US SCF 2022 data.
  Portfolio includes UCITS ETFs (CSPX.L, AGGH.MI, XEON.MI). EUR/USD exposure ~72%.
</div>
"""

STRESS_BANNER_HTML = """
<div style="background:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.3);
border-radius:8px;padding:8px 12px;margin-bottom:1rem;
font-size:0.72rem;color:#f87171;display:flex;align-items:center;gap:8px;">
  <span>🔴</span>
  <strong>HIGH STRESS REGIME</strong> — correlations unusually elevated.
  Conservative allocation applied automatically.
</div>
"""


def inject_css() -> None:
    """Inject dark premium theme CSS into the Streamlit app."""
    st.markdown(DARK_CSS, unsafe_allow_html=True)


def render_disclaimer() -> None:
    """Render the mandatory MiFID II educational disclaimer."""
    st.markdown(DISCLAIMER_HTML, unsafe_allow_html=True)


def render_eu_note() -> None:
    """Render the EU investor note (SCF US-centrism + UCITS + FX exposure)."""
    st.markdown(EU_NOTE_HTML, unsafe_allow_html=True)


def render_stress_banner() -> None:
    """Render stress regime banner. Call only when regime == 'HIGH_STRESS'."""
    st.markdown(STRESS_BANNER_HTML, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render a styled page header with Space Grotesk font."""
    sub_html = (
        f'<div style="font-size:0.72rem;color:#475569;margin-top:3px;'
        f'letter-spacing:0.04em;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="margin-bottom:1.25rem;">'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.1rem;'
        f'font-weight:600;color:#f1f5f9;">{title}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )

PLOTLY_DARK = {
    "template": "plotly_dark",
    "paper_bgcolor": "#111827",
    "plot_bgcolor": "#111827",
    "font": {"family": "DM Sans", "color": "#94a3b8", "size": 11},
    "colorway": ["#7c5cfc", "#0dcfb0", "#3b82f6", "#f59e0b", "#f87171"],
    "margin": {"l": 8, "r": 8, "t": 24, "b": 8},
}


def apply_plotly_dark_theme(fig):
    """Apply the custom dark finance theme to a Plotly figure."""
    fig.update_layout(**PLOTLY_DARK)
    fig.update_xaxes(gridcolor="#1e2640", linecolor="#1e2640")
    fig.update_yaxes(gridcolor="#1e2640", linecolor="#1e2640")
    return fig
