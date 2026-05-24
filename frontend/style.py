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

#MainMenu, footer { visibility: hidden; }
/* Hide header branding/toolbar but NOT the sidebar toggle button */
header { visibility: hidden; }
header button,
header [role="button"] {
    visibility: visible !important;
    display: flex !important;
    opacity: 1 !important;
    pointer-events: auto !important;
}
.block-container { padding-top: 1.5rem !important; }

section[data-testid="stSidebar"],
[data-testid="stSidebar"] {
    background: #0d1220 !important;
    border-right: 1px solid #1e2640 !important;
    min-width: 260px !important;
    width: 260px !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
    margin-top: -1rem !important;
}

/* Collapse button — styled to match dark theme, visible as a close hint */
[data-testid="stSidebar"] button:not(:has(p)) {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 2rem !important;
    height: 2rem !important;
    background: transparent !important;
    border: 1px solid #1e2640 !important;
    border-radius: 50% !important;
    color: #64748b !important;
    box-shadow: none !important;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
    cursor: pointer !important;
    position: relative !important;
}

[data-testid="stSidebar"] button:not(:has(p)):hover {
    background: rgba(124,92,252,0.15) !important;
    border-color: #7c5cfc !important;
    color: #a78bfa !important;
}

[data-testid="stSidebar"] button:not(:has(p))::after {
    content: "Chiudi menu";
    position: absolute;
    left: 2.4rem;
    top: 50%;
    transform: translateY(-50%);
    background: #1e2640;
    color: #94a3b8;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 500;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
    border: 1px solid #2d3748;
    z-index: 9999;
}

[data-testid="stSidebar"] button:not(:has(p)):hover::after {
    opacity: 1;
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

/* Question badge + text row
   padding-left: 0.25rem aligns Q-badge with the 01 section badge
   (header has 1.25rem padding; container content defaults to 1rem) */
.qs-q-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 2rem 0 0.5rem 0;
    padding-top: 1rem;
    padding-left: 0.25rem;
    border-top: 1px solid #1a2236;
}

/* No top border on the very first question in each section */
.qs-q-row:first-of-type {
    margin-top: 0.75rem;
    padding-top: 0;
    border-top: none;
}

/* Q badge — same square shape as the section number badge (.qs-num) */
.qs-q-badge {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    color: #a78bfa;
    background: rgba(124,92,252,0.12);
    border: 1px solid rgba(124,92,252,0.25);
    border-radius: 7px;
    min-width: 2.25rem;
    width: 2.25rem;
    height: 2.25rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    letter-spacing: 0.02em;
}

.qs-q-text {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
    line-height: 1.35;
}

/* ── Question options: full-width vertical selector list ─────────────────── */
/* Indented to align with question text (badge width 2.25rem + gap 0.75rem).   */
/* Selected = coloured left accent bar matching section colour.                 */

/* Indent radio widget: 0.25rem (q-row offset) + 2.25rem (badge) + 0.75rem (gap) */
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] {
    padding-left: 3.25rem !important;
    margin-bottom: 0.25rem !important;
}

/* Hide native radio input appearance */
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] input[type="radio"] {
    -webkit-appearance: none !important;
    appearance: none !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    position: absolute !important;
    opacity: 0 !important;
}

/* Also target BaseWeb radio indicator if present */
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] [data-baseweb="radio"] {
    display: none !important;
}

/* Each option: full-width row with transparent left border (fills on select) */
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label {
    width: 100% !important;
    background: rgba(10, 15, 30, 0.45) !important;
    border: 1px solid #1e2640 !important;
    border-left: 3px solid transparent !important;
    border-radius: 0 8px 8px 0 !important;
    padding: 0.72rem 1.1rem !important;
    cursor: pointer !important;
    min-height: 2.75rem !important;
    display: flex !important;
    align-items: center !important;
    gap: 0 !important;
    margin-bottom: 0.3rem !important;
    transition: border-left-color 0.15s ease, background 0.15s ease !important;
    box-sizing: border-box !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:hover {
    background: rgba(124,92,252,0.06) !important;
    border-left-color: rgba(124,92,252,0.35) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #7c5cfc !important;
    background: rgba(124,92,252,0.1) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label p {
    font-size: 0.9rem !important;
    color: #94a3b8 !important;
    line-height: 1.5 !important;
    margin: 0 !important;
    text-align: left !important;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) p {
    color: #c4b5fd !important;
    font-weight: 500 !important;
}

/* Section-aware accent bar on selected — blue / purple / amber */
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) div[data-testid="stRadio"] label:hover {
    border-left-color: rgba(59,130,246,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #3b82f6 !important;
    background: rgba(59,130,246,0.1) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) div[data-testid="stRadio"] label:has(input:checked) p {
    color: #93c5fd !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) div[data-testid="stRadio"] label:hover {
    border-left-color: rgba(245,158,11,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #f59e0b !important;
    background: rgba(245,158,11,0.1) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) div[data-testid="stRadio"] label:has(input:checked) p {
    color: #fcd34d !important;
}

/* ── Section colour accents ──────────────────────────────────────────────── */
/* Header gradient + badge colours driven by modifier class on .qs-header.     */
/* Card left-border accent driven by :has() on the wrapper — most visible cue. */

/* 01 — Financial Situation: blue */
.qs-s1 {
    background: linear-gradient(135deg, #0f172a 0%, #0e2040 55%, #0d1220 100%) !important;
    border-bottom-color: #1b3560 !important;
}
.qs-s1 .qs-num {
    color: #60a5fa !important;
    background: rgba(59,130,246,0.18) !important;
    border-color: rgba(59,130,246,0.3) !important;
}

/* 02 — Investment Behaviour: default purple (no override on gradient/badge) */

/* 03 — Reaction to Risk: amber */
.qs-s3 {
    background: linear-gradient(135deg, #0f172a 0%, #1a1200 55%, #0d1220 100%) !important;
    border-bottom-color: #3d2d05 !important;
}
.qs-s3 .qs-num {
    color: #fbbf24 !important;
    background: rgba(245,158,11,0.18) !important;
    border-color: rgba(245,158,11,0.3) !important;
}

/* Card-level accent — left border + subtle background tint per section */
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) {
    border-left: 3px solid #3b82f6 !important;
    border-color: rgba(59,130,246,0.28) !important;
    background: rgba(15, 38, 80, 0.22) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s2) {
    border-left: 3px solid #7c5cfc !important;
    border-color: rgba(124,92,252,0.28) !important;
    background: rgba(30, 18, 70, 0.22) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) {
    border-left: 3px solid #f59e0b !important;
    border-color: rgba(245,158,11,0.28) !important;
    background: rgba(50, 28, 0, 0.22) !important;
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

/* ── Custom <details> info card (.qs-info-card) ──────────────────────────── */
/* Native HTML5 <details> gives full style control, no Streamlit wrapper.      */

details.qs-info-card {
    background: rgba(59,130,246,0.06);
    border: 1px solid rgba(59,130,246,0.22);
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 1.25rem;
}

details.qs-info-card > summary {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.85rem 1.1rem;
    cursor: pointer;
    list-style: none;
    user-select: none;
}

/* Hide default triangle marker in all browsers */
details.qs-info-card > summary::-webkit-details-marker { display: none; }
details.qs-info-card > summary::marker { display: none; }

.qs-info-icon {
    font-size: 1.1rem;
    flex-shrink: 0;
}

.qs-info-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1rem;
    font-weight: 600;
    color: #93c5fd;
    letter-spacing: 0.01em;
    flex: 1;
}

.qs-info-chevron {
    font-size: 1rem;
    color: #60a5fa;
    transition: transform 0.2s ease;
    flex-shrink: 0;
}

details.qs-info-card[open] .qs-info-chevron {
    transform: rotate(180deg);
}

.qs-info-body {
    padding: 0.8rem 1.1rem 1rem 1.1rem;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.9rem;
    color: #94a3b8;
    line-height: 1.65;
    border-top: 1px solid rgba(59,130,246,0.15);
}

/* ── Pills (st.pills) question options ───────────────────────────────────── */
/* st.pills wraps options as clickable pills — no radio dot, modern look.      */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 0.45rem !important;
    margin-top: 0.35rem !important;
    margin-bottom: 0.6rem !important;
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button,
[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stPills-pill"] {
    background: rgba(10,15,30,0.7) !important;
    border: 1px solid #1e2640 !important;
    border-radius: 9px !important;
    color: #94a3b8 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.87rem !important;
    padding: 0.7rem 1rem !important;
    line-height: 1.4 !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
    white-space: normal !important;
    text-align: left !important;
    height: auto !important;
    min-height: 3rem !important;
    /* Force 2-column grid: each pill takes exactly half the row */
    width: calc(50% - 0.25rem) !important;
    box-sizing: border-box !important;
    flex-shrink: 0 !important;
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button:hover,
[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stPills-pill"]:hover {
    border-color: rgba(124,92,252,0.5) !important;
    background: rgba(124,92,252,0.09) !important;
    color: #c4b5fd !important;
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stPills-pill"][aria-pressed="true"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button[data-selected="true"] {
    background: rgba(124,92,252,0.18) !important;
    border-color: #7c5cfc !important;
    color: #c4b5fd !important;
    font-weight: 500 !important;
    box-shadow: inset 0 0 0 1px rgba(124,92,252,0.35) !important;
}

/* Section-aware pill accent on selected */
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) [data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #3b82f6 !important;
    background: rgba(59,130,246,0.18) !important;
    color: #93c5fd !important;
    box-shadow: inset 0 0 0 1px rgba(59,130,246,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) [data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #f59e0b !important;
    background: rgba(245,158,11,0.18) !important;
    color: #fcd34d !important;
    box-shadow: inset 0 0 0 1px rgba(245,158,11,0.35) !important;
}
</style>
"""

DISCLAIMER_HTML = """
<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);
border-radius:8px;padding:11px 16px;margin-bottom:1rem;
font-size:0.9rem;color:#d97706;display:flex;align-items:flex-start;gap:10px;">
  <span style="flex-shrink:0;font-size:1rem;">⚠</span>
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
        f'<div style="font-size:0.88rem;color:#64748b;margin-top:6px;'
        f'letter-spacing:0.02em;font-weight:400;">{subtitle}</div>'
        if subtitle else ""
    )
    icon_html = (
        f'<div style="'
        f'width:2.8rem;height:2.8rem;'
        f'background:rgba(124,92,252,0.12);'
        f'border:1px solid rgba(124,92,252,0.25);'
        f'border-radius:10px;'
        f'display:inline-flex;align-items:center;justify-content:center;'
        f'font-size:1.2rem;flex-shrink:0;">{icon}</div>'
        if icon else ""
    )
    layout = "display:flex;align-items:center;gap:1rem;" if icon else ""
    st.markdown(
        f'<div style="{layout}margin-bottom:1.5rem;">'
        f'{icon_html}'
        f'<div>'
        f'<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2.0rem;'
        f'font-weight:700;color:#f1f5f9;letter-spacing:-0.02em;line-height:1.15;">'
        f'{title}</div>{sub_html}'
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
