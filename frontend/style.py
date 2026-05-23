import streamlit as st

# ── Dark theme CSS ────────────────────────────────────────────────────────────

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Space+Grotesk:wght@500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Sidebar nav: icon + button rows ──────────────────────────────────────── */

/* Row container: no gap, vertically centered */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    align-items: stretch !important;
    margin: 0.05rem 0 !important;
}

/* Each column: flex so children can vertically center */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"] {
    padding: 0 !important;
    min-width: 0 !important;
    display: flex !important;
    align-items: center !important;
}

/* stMarkdownContainer inside icon column must also center */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"] [data-testid="stMarkdownContainer"] {
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
}

/* SVG icon wrapper */
.nav-svg-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.55rem 0 0.55rem 0.7rem;
    color: #64748b;
    opacity: 0.7;
}

.nav-svg-wrap.active {
    color: #a78bfa;
    opacity: 1;
}

/* Nav buttons: no border, left-aligned text */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    color: #64748b !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 0.55rem 0.6rem 0.55rem 0.4rem !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em !important;
    box-shadow: none !important;
    width: 100% !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}

/* Force the inner <p> left-aligned */
[data-testid="stSidebar"] .stButton > button p {
    text-align: left !important;
    margin: 0 !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(124,92,252,0.07) !important;
    color: #94a3b8 !important;
    border: none !important;
}

[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(124,92,252,0.15) !important;
    border: none !important;
    color: #a78bfa !important;
    font-weight: 600 !important;
}

[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: rgba(124,92,252,0.22) !important;
    border: none !important;
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

/* ── Questionnaire layout ──────────────────────────────────────────────────── */

/* Hide the form's own outer border — only the 3 section cards should be visible */
[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

/* Section cards: clip the gradient header at rounded corners */
[data-testid="stVerticalBlockBorderWrapper"] {
    overflow: hidden !important;
    border-color: #1e2640 !important;
}

/* Gradient header band — full-bleed inside each section card */
.qs-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem;
    margin: -1rem -1rem 0.75rem -1rem;
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0d1220 100%);
    border-bottom: 1px solid #2d3748;
    border-radius: 10px 10px 0 0;
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

/* ── Radio options → 4-column card grid ───────────────────────────────────── */
/* Scoped to section cards (stVerticalBlockBorderWrapper) so it doesn't leak   */

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: grid !important;
    grid-template-columns: repeat(4, 1fr) !important;
    gap: 0.5rem !important;
    margin-top: 0.25rem !important;
    margin-bottom: 0.5rem !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label {
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

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:hover {
    border-color: rgba(124,92,252,0.45) !important;
    background: rgba(124,92,252,0.07) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) {
    border-color: #7c5cfc !important;
    background: rgba(124,92,252,0.14) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label p {
    font-size: 0.8rem !important;
    color: #94a3b8 !important;
    line-height: 1.45 !important;
    margin: 0 !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) p {
    color: #c4b5fd !important;
}

/* Submit button */
[data-testid="stFormSubmitButton"] > button {
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

[data-testid="stFormSubmitButton"] > button:hover {
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


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Render a styled page header with Space Grotesk font and optional icon."""
    sub_html = (
        f'<div style="font-size:0.72rem;color:#475569;margin-top:4px;'
        f'letter-spacing:0.04em;">{subtitle}</div>'
        if subtitle else ""
    )
    icon_html = (
        f'<div style="'
        f'width:2.4rem;height:2.4rem;'
        f'background:rgba(124,92,252,0.12);'
        f'border:1px solid rgba(124,92,252,0.25);'
        f'border-radius:9px;'
        f'display:inline-flex;align-items:center;justify-content:center;'
        f'font-size:1.05rem;flex-shrink:0;">{icon}</div>'
        if icon else ""
    )
    layout = "display:flex;align-items:center;gap:0.875rem;" if icon else ""
    st.markdown(
        f'<div style="{layout}margin-bottom:1.25rem;">'
        f'{icon_html}'
        f'<div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.45rem;'
        f'font-weight:600;color:#f1f5f9;">{title}</div>{sub_html}'
        f'</div></div>',
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
