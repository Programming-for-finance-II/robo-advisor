import streamlit as st

# ── Theme tokens ──────────────────────────────────────────────────────────────
# Single source of truth for every colour used in inline-styled HTML. Both
# themes expose the same semantic keys so render helpers can stay theme-agnostic
# (`t = get_theme_tokens(); ... color:{t['text_primary']}`). Streamlit-native
# widgets are themed via the CSS blocks below; everything we build by hand in
# Python reads from these tokens instead of hardcoding hex values.

_DARK_TOKENS = {
    "bg_main": "#0b0f19",
    "bg_surface": "#111827",
    "bg_surface_alt": "#0d1220",
    "bg_card": "rgba(30,38,64,0.5)",
    "bg_card_solid": "#111827",
    "bg_nav": "#0d1220",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "border": "#1e2640",
    "border_soft": "#1a2236",
    "accent": "#7c5cfc",
    "accent_text": "#a78bfa",
    "accent_soft": "rgba(124,92,252,0.12)",
    "accent_border": "rgba(124,92,252,0.25)",
    "shadow": "0 2px 14px rgba(0,0,0,0.25)",
    "shadow_lg": "0 8px 28px rgba(0,0,0,0.35)",
    "button_bg": "transparent",
    "button_border": "#1e2640",
    "button_text": "#94a3b8",
    "button_bg_hover": "rgba(124,92,252,0.07)",
    "button_border_hover": "#7c5cfc",
    "input_bg": "#0d1220",
    "input_border": "#1e2640",
    "input_text": "#e2e8f0",
    "input_placeholder": "#64748b",
    "chart_font": "#94a3b8",
    "chart_grid": "#1e2640",
    "divider": "#1e2640",
    "question_block_bg": "transparent",
}

_LIGHT_TOKENS = {
    "bg_main": "#F6F7FB",
    "bg_surface": "#FFFFFF",
    "bg_surface_alt": "#F1F4FA",
    "bg_card": "#FFFFFF",
    "bg_card_solid": "#FFFFFF",
    "bg_nav": "rgba(255,255,255,0.88)",
    "text_primary": "#111827",
    "text_secondary": "#334155",
    "text_muted": "#64748B",
    "border": "#D8DEE9",
    "border_soft": "#E5E9F0",
    "accent": "#7C4DFF",
    "accent_text": "#6d4deb",
    "accent_soft": "#EEE8FF",
    "accent_border": "rgba(124,77,255,0.3)",
    "shadow": "0 4px 16px rgba(15,23,42,0.06)",
    "shadow_lg": "0 12px 32px rgba(15,23,42,0.10)",
    "button_bg": "#FFFFFF",
    "button_border": "#CBD5E1",
    "button_text": "#334155",
    "button_bg_hover": "#F8FAFC",
    "button_border_hover": "#94A3B8",
    "input_bg": "#FFFFFF",
    "input_border": "#CBD5E1",
    "input_text": "#111827",
    "input_placeholder": "#94A3B8",
    "chart_font": "#334155",
    "chart_grid": "#E2E8F0",
    "divider": "#E5EAF3",
    "question_block_bg": "#F8FAFC",
}


def get_theme_tokens() -> dict:
    """Return the active theme's semantic colour tokens.

    Reads ``st.session_state['theme']`` (``"dark"`` | ``"light"``), defaulting
    to dark. Use everywhere instead of hardcoding colours so the two themes stay
    in sync and a single edit re-skins the whole app.
    """
    return _LIGHT_TOKENS if st.session_state.get("theme") == "light" else _DARK_TOKENS


def is_light() -> bool:
    """True when the light theme is active."""
    return st.session_state.get("theme") == "light"


# ── Dark theme CSS ────────────────────────────────────────────────────────────

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Space+Grotesk:wght@500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Typographic base ──────────────────────────────────────────────────────
   One coherent reading scale. Body copy sits at 0.95rem / line-height 1.6 so
   nothing on a content page is hard to read; micro-labels never go below
   0.72rem. Display headings use Space Grotesk, body uses DM Sans.            */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    color: #cbd5e1;
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
small, .stCaption {
    font-size: 0.84rem !important;
    line-height: 1.55 !important;
    color: #64748b !important;
}
/* Data tables: lift the default cell text to a readable size */
[data-testid="stDataFrame"] [role="gridcell"],
[data-testid="stDataFrame"] [data-testid="stTable"] td {
    font-size: 0.88rem !important;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    font-size: 0.78rem !important;
    letter-spacing: 0.04em !important;
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
    font-size: 0.72rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #64748b !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.7rem !important;
    font-weight: 600 !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #1e2640 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #64748b !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.05em !important;
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
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #3b82f6 !important;
    background: rgba(59,130,246,0.1) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
div[data-testid="stRadio"] label:has(input:checked) p {
    color: #93c5fd !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) div[data-testid="stRadio"] label:hover {
    border-left-color: rgba(245,158,11,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #f59e0b !important;
    background: rgba(245,158,11,0.1) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
div[data-testid="stRadio"] label:has(input:checked) p {
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
[data-testid="stVerticalBlockBorderWrapper"]
button[data-testid="stPills-pill"][aria-pressed="true"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button[data-selected="true"] {
    background: rgba(124,92,252,0.18) !important;
    border-color: #7c5cfc !important;
    color: #c4b5fd !important;
    font-weight: 500 !important;
    box-shadow: inset 0 0 0 1px rgba(124,92,252,0.35) !important;
}

/* Section-aware pill accent on selected */
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
[data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #3b82f6 !important;
    background: rgba(59,130,246,0.18) !important;
    color: #93c5fd !important;
    box-shadow: inset 0 0 0 1px rgba(59,130,246,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
[data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #f59e0b !important;
    background: rgba(245,158,11,0.18) !important;
    color: #fcd34d !important;
    box-shadow: inset 0 0 0 1px rgba(245,158,11,0.35) !important;
}
</style>
"""

LIGHT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=Space+Grotesk:wght@500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Main background override ──────────────────────────────────────────────── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main .block-container {
    background-color: #f8fafc !important;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    color: #334155;
}
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
small, .stCaption {
    font-size: 0.84rem !important;
    line-height: 1.55 !important;
    color: #94a3b8 !important;
}
[data-testid="stDataFrame"] [role="gridcell"],
[data-testid="stDataFrame"] [data-testid="stTable"] td {
    font-size: 0.88rem !important;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    font-size: 0.78rem !important;
    letter-spacing: 0.04em !important;
}

/* ── Sidebar nav ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    align-items: stretch !important;
    margin: 0.05rem 0 !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"] {
    padding: 0 !important;
    min-width: 0 !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
    > [data-testid="stColumn"] [data-testid="stMarkdownContainer"] {
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
}
.nav-svg-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.55rem 0 0.55rem 0.7rem;
    color: #94a3b8;
    opacity: 0.7;
}
.nav-svg-wrap.active {
    color: #7c5cfc;
    opacity: 1;
}

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
[data-testid="stSidebar"] .stButton > button p {
    text-align: left !important;
    margin: 0 !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(124,92,252,0.08) !important;
    color: #475569 !important;
    border: none !important;
}
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(124,92,252,0.1) !important;
    border: none !important;
    color: #6d4deb !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: rgba(124,92,252,0.16) !important;
    border: none !important;
}

#MainMenu, footer { visibility: hidden; }
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
    background: #f1f5f9 !important;
    border-right: 1px solid #e2e8f0 !important;
    min-width: 260px !important;
    width: 260px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
    margin-top: -1rem !important;
}

[data-testid="stSidebar"] button:not(:has(p)) {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 2rem !important;
    height: 2rem !important;
    background: transparent !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 50% !important;
    color: #94a3b8 !important;
    box-shadow: none !important;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
    cursor: pointer !important;
    position: relative !important;
}
[data-testid="stSidebar"] button:not(:has(p)):hover {
    background: rgba(124,92,252,0.08) !important;
    border-color: #7c5cfc !important;
    color: #6d4deb !important;
}
[data-testid="stSidebar"] button:not(:has(p))::after {
    content: "Chiudi menu";
    position: absolute;
    left: 2.4rem;
    top: 50%;
    transform: translateY(-50%);
    background: #ffffff;
    color: #475569;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 500;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
    border: 1px solid #e2e8f0;
    z-index: 9999;
}
[data-testid="stSidebar"] button:not(:has(p)):hover::after {
    opacity: 1;
}

/* ── Metrics ──────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #D8DEE9 !important;
    border-radius: 12px !important;
    padding: 1rem 1.1rem !important;
    box-shadow: 0 4px 16px rgba(15,23,42,0.05) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #94a3b8 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.7rem !important;
    font-weight: 600 !important;
    color: #1e293b !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #e2e8f0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #475569 !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #6d4deb !important;
}
.stTabs [aria-selected="true"] {
    color: #6d4deb !important;
    border-bottom: 2px solid #7c5cfc !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.stButton > button {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    color: #334155 !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04) !important;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease !important;
}
.stButton > button:hover {
    background: #F8FAFC !important;
    border-color: #94A3B8 !important;
    color: #1e293b !important;
}
.stButton > button[kind="primary"] {
    background: #EEE8FF !important;
    border-color: #7C4DFF !important;
    color: #5B34D6 !important;
}
.stButton > button[kind="primary"]:hover {
    background: #e3d9ff !important;
    border-color: #6d28d9 !important;
    color: #4c1d95 !important;
}

/* ── Segmented control (Backtesting scenario tabs) ───────────────────────── */
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"] {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    color: #334155 !important;
    font-weight: 600 !important;
}
[data-testid="stButtonGroup"] [data-testid="stBaseButton-segmented_control"]:hover {
    background: #F8FAFC !important;
    border-color: #94A3B8 !important;
    color: #1e293b !important;
}
[data-testid="stButtonGroup"]
[data-testid="stBaseButton-segmented_controlActive"] {
    background: #EEE8FF !important;
    border: 1px solid #7C4DFF !important;
    color: #5B34D6 !important;
    font-weight: 600 !important;
}

/* ── Text inputs / textareas (Chat composer, number/text fields) ─────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-baseweb="input"],
[data-baseweb="textarea"] {
    background: #FFFFFF !important;
    border-color: #CBD5E1 !important;
    color: #111827 !important;
}
[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stNumberInput"] div[data-baseweb="input"],
[data-testid="stTextArea"] div[data-baseweb="textarea"] {
    background: #FFFFFF !important;
    border-color: #CBD5E1 !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
    color: #94A3B8 !important;
}
[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
[data-testid="stTextArea"] div[data-baseweb="textarea"]:focus-within {
    border-color: #7C4DFF !important;
    box-shadow: 0 0 0 3px rgba(124,77,255,0.12) !important;
}

hr { border-color: #e2e8f0 !important; }

/* ── Questionnaire ──────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    overflow: hidden !important;
    border: 1px solid #D8DEE9 !important;
    border-radius: 20px !important;
    background: #ffffff !important;
    box-shadow: 0 10px 30px rgba(15,23,42,0.06) !important;
}
.qs-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.15rem 1.4rem;
    margin: -1rem -1rem 1rem -1rem;
    background: #EEF4FF;
    border-bottom: 1px solid #DCE6F5;
    border-radius: 20px 20px 0 0;
}
.qs-num {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.88rem;
    font-weight: 700;
    color: #7c5cfc;
    background: rgba(124,92,252,0.1);
    border: 1px solid rgba(124,92,252,0.25);
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
    font-size: 1.08rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
}
.qs-sub {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.2rem;
}
.qs-q-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 2.75rem 0 0.85rem 0;
    padding-top: 1.85rem;
    padding-left: 0.25rem;
    border-top: 1px solid #E8EDF5;
}
.qs-q-row:first-of-type {
    margin-top: 0.75rem;
    padding-top: 0;
    border-top: none;
}
/* Answer options sit directly under the question — no framed mini-cards.
   Separation between questions comes from spacing + the .qs-q-row divider. */
[data-testid="stForm"] [data-testid="stRadio"] {
    background: transparent !important;
    border: none !important;
    padding: 0 0 0.4rem 0 !important;
    margin-bottom: 0.6rem !important;
}
[data-testid="stForm"] [data-testid="stRadio"] [role="radiogroup"] {
    gap: 0.35rem !important;
}
.qs-q-badge {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    color: #7c5cfc;
    background: rgba(124,92,252,0.08);
    border: 1px solid rgba(124,92,252,0.2);
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
    color: #1e293b;
    line-height: 1.35;
}

[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] {
    padding-left: 3.25rem !important;
    margin-bottom: 0.25rem !important;
}
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
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] [data-baseweb="radio"] {
    display: none !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label {
    width: 100% !important;
    background: rgba(248,250,252,0.8) !important;
    border: 1px solid #e2e8f0 !important;
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
    background: rgba(124,92,252,0.04) !important;
    border-left-color: rgba(124,92,252,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #7c5cfc !important;
    background: rgba(124,92,252,0.06) !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label p {
    font-size: 0.9rem !important;
    color: #475569 !important;
    line-height: 1.5 !important;
    margin: 0 !important;
    text-align: left !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stRadio"] label:has(input:checked) p {
    color: #6d4deb !important;
    font-weight: 500 !important;
}

/* Section-aware accent — blue / purple / amber */
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) div[data-testid="stRadio"] label:hover {
    border-left-color: rgba(59,130,246,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #3b82f6 !important;
    background: rgba(59,130,246,0.06) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
div[data-testid="stRadio"] label:has(input:checked) p {
    color: #2563eb !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) div[data-testid="stRadio"] label:hover {
    border-left-color: rgba(245,158,11,0.35) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
div[data-testid="stRadio"] label:has(input:checked) {
    border-left-color: #f59e0b !important;
    background: rgba(245,158,11,0.06) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
div[data-testid="stRadio"] label:has(input:checked) p {
    color: #b45309 !important;
}

/* ── Section colour accents ──────────────────────────────────────────────── */
.qs-s1 {
    background: linear-gradient(135deg, #f8fafc 0%, #dbeafe 55%, #f1f5f9 100%) !important;
    border-bottom-color: #bfdbfe !important;
}
.qs-s1 .qs-num {
    color: #2563eb !important;
    background: rgba(59,130,246,0.1) !important;
    border-color: rgba(59,130,246,0.25) !important;
}
.qs-s3 {
    background: linear-gradient(135deg, #f8fafc 0%, #fef3c7 55%, #f1f5f9 100%) !important;
    border-bottom-color: #fde68a !important;
}
.qs-s3 .qs-num {
    color: #b45309 !important;
    background: rgba(245,158,11,0.1) !important;
    border-color: rgba(245,158,11,0.25) !important;
}

[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1) {
    border-left: 3px solid #3b82f6 !important;
    border-color: rgba(59,130,246,0.2) !important;
    background: rgba(239,246,255,0.6) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s2) {
    border-left: 3px solid #7c5cfc !important;
    border-color: rgba(124,92,252,0.2) !important;
    background: rgba(245,243,255,0.6) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3) {
    border-left: 3px solid #f59e0b !important;
    border-color: rgba(245,158,11,0.2) !important;
    background: rgba(255,251,235,0.6) !important;
}

/* Submit button */
[data-testid="stFormSubmitButton"] > button {
    width: 100% !important;
    background: rgba(124,92,252,0.1) !important;
    border: 1px solid #7c5cfc !important;
    color: #6d4deb !important;
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
    background: rgba(124,92,252,0.18) !important;
}

/* ── Info card ──────────────────────────────────────────────────────────── */
details.qs-info-card {
    background: #ffffff;
    border: 1px solid rgba(59,130,246,0.28);
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 1.25rem;
    box-shadow: 0 6px 20px rgba(15,23,42,0.06);
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
details.qs-info-card > summary::-webkit-details-marker { display: none; }
details.qs-info-card > summary::marker { display: none; }
.qs-info-icon { font-size: 1.1rem; flex-shrink: 0; }
.qs-info-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1rem;
    font-weight: 600;
    color: #2563eb;
    letter-spacing: 0.01em;
    flex: 1;
}
.qs-info-chevron {
    font-size: 1rem;
    color: #3b82f6;
    transition: transform 0.2s ease;
    flex-shrink: 0;
}
details.qs-info-card[open] .qs-info-chevron { transform: rotate(180deg); }
.qs-info-body {
    padding: 0.8rem 1.1rem 1rem 1.1rem;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.9rem;
    color: #475569;
    line-height: 1.65;
    border-top: 1px solid rgba(59,130,246,0.12);
}

/* ── Pills ──────────────────────────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] {
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 0.45rem !important;
    margin-top: 0.35rem !important;
    margin-bottom: 0.6rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button,
[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stPills-pill"] {
    background: rgba(248,250,252,0.9) !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 9px !important;
    color: #475569 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.87rem !important;
    padding: 0.7rem 1rem !important;
    line-height: 1.4 !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
    white-space: normal !important;
    text-align: left !important;
    height: auto !important;
    min-height: 3rem !important;
    width: calc(50% - 0.25rem) !important;
    box-sizing: border-box !important;
    flex-shrink: 0 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button:hover,
[data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stPills-pill"]:hover {
    border-color: rgba(124,92,252,0.4) !important;
    background: rgba(124,92,252,0.05) !important;
    color: #6d4deb !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stVerticalBlockBorderWrapper"]
button[data-testid="stPills-pill"][aria-pressed="true"],
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stPills"] button[data-selected="true"] {
    background: rgba(124,92,252,0.1) !important;
    border-color: #7c5cfc !important;
    color: #6d4deb !important;
    font-weight: 500 !important;
    box-shadow: inset 0 0 0 1px rgba(124,92,252,0.25) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s1)
[data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #3b82f6 !important;
    background: rgba(59,130,246,0.1) !important;
    color: #2563eb !important;
    box-shadow: inset 0 0 0 1px rgba(59,130,246,0.25) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.qs-s3)
[data-testid="stPills"] button[aria-pressed="true"] {
    border-color: #f59e0b !important;
    background: rgba(245,158,11,0.1) !important;
    color: #b45309 !important;
    box-shadow: inset 0 0 0 1px rgba(245,158,11,0.25) !important;
}

/* ── BaseWeb radio controls (Settings, range selectors) ─────────────────────
   These are the native radios outside the questionnaire (the questionnaire
   hides them and renders full-width option cards instead). On the dark base
   theme the unchecked inner dot stays near-black, which reads as an ugly black
   bullet on a light page — recolour the whole control to the light palette. */
[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
    background-color: #FFFFFF !important;
    border-color: #C7D2E0 !important;
    border-width: 2px !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child > div {
    background-color: transparent !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"]:hover > div:first-child {
    border-color: #7C4DFF !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked)
> div:first-child {
    background-color: #EEE8FF !important;
    border-color: #7C4DFF !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked)
> div:first-child > div {
    background-color: #7C4DFF !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"] > div:last-child {
    color: #334155 !important;
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

# Single discreet, app-wide footer line. Replaces the amber per-page banner:
# rendered once at the bottom of every page (see main()), so the mandatory
# MiFID II notice stays visible everywhere without shouting on each screen.
GLOBAL_FOOTER_HTML = """
<div style="margin-top:3.5rem;padding:1.1rem 0 0.4rem;
border-top:1px solid #1a2236;display:flex;align-items:center;
justify-content:center;gap:0.55rem;flex-wrap:wrap;text-align:center;">
  <span style="font-size:0.78rem;color:#475569;line-height:1.65;
  letter-spacing:0.01em;">
    <strong style="color:#64748b;font-weight:600;">Educational prototype</strong>
    &nbsp;·&nbsp; Not financial advice under MiFID&nbsp;II
    &nbsp;·&nbsp; Market data may be delayed or inaccurate
  </span>
</div>
"""

EU_NOTE_HTML = ""

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
    """Inject theme CSS (dark or light) based on session state."""
    css = LIGHT_CSS if st.session_state.get("theme", "dark") == "light" else DARK_CSS
    st.markdown(css, unsafe_allow_html=True)


def render_disclaimer() -> None:
    """Render the mandatory MiFID II educational disclaimer."""
    st.markdown(DISCLAIMER_HTML, unsafe_allow_html=True)


def render_global_footer() -> None:
    """Render the single app-wide MiFID II footer line (call once per page).

    Called once at the bottom of every page via main() so the MiFID II notice
    stays visible without being repeated on each individual screen.
    """
    t = get_theme_tokens()
    st.markdown(
        f'<div style="margin-top:3.5rem;padding:1.1rem 0 0.4rem;'
        f'border-top:1px solid {t["border_soft"]};display:flex;align-items:center;'
        f'justify-content:center;gap:0.55rem;flex-wrap:wrap;text-align:center;">'
        f'<span style="font-size:0.78rem;color:{t["text_muted"]};line-height:1.65;'
        f'letter-spacing:0.01em;">'
        f'<strong style="color:{t["text_secondary"]};font-weight:600;">'
        f'Educational prototype</strong>'
        f'&nbsp;·&nbsp; Not financial advice under MiFID&nbsp;II'
        f'&nbsp;·&nbsp; Market data may be delayed or inaccurate'
        f'</span></div>',
        unsafe_allow_html=True,
    )


def render_eu_note() -> None:
    """Render the EU investor note as a polished info card with expandable detail."""
    t = get_theme_tokens()
    st.markdown(
        f'<div style="background:{t["accent_soft"]};border:1px solid {t["accent_border"]};'
        f'border-left:3px solid {t["accent"]};border-radius:0 8px 8px 0;'
        f'padding:0.9rem 1.1rem 0.75rem;margin-bottom:0.5rem;">'
        f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.45rem;">'
        f'<span style="font-size:1rem;flex-shrink:0;">ℹ️</span>'
        f'<span style="font-family:\'Space Grotesk\',sans-serif;font-size:0.85rem;'
        f'font-weight:600;color:{t["accent_text"]};">EU Investor Note</span>'
        f'</div>'
        f'<div style="font-size:0.8rem;color:{t["text_secondary"]};line-height:1.6;">'
        f'The risk-profile model is trained on US Federal Reserve SCF data (2022). '
        f'Results may not fully reflect the behaviour of European retail investors. '
        f'The portfolio includes UCITS-eligible ETFs (CSPX.L, AGGH.MI, XEON.MI) '
        f'with EUR/USD exposure ~72%.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Learn more — EU data limitations"):
        st.markdown(
            "**Why does this matter?**  \n"
            "The SCF samples US households, whose savings behaviour, risk tolerance, "
            "and asset mix differ meaningfully from European retail investors "
            "surveyed by the ECB HFCS.\n\n"
            "**What it means in practice:**  \n"
            "Profile boundaries (Conservative / Moderate / Aggressive) are calibrated "
            "on US income and wealth distributions. A European investor near the "
            "Conservative–Moderate boundary may be mis-classified by ±1 band.\n\n"
            "**Academic reference:**  \n"
            "Grable & Lytton (1999) — *Financial risk tolerance revisited*; "
            "ECB Household Finance and Consumption Survey, Wave 4 (2021).\n\n"
            "*EU Awareness Rule 9 · Design v3.1*"
        )


def render_stress_banner() -> None:
    """Render stress regime banner. Call only when regime == 'HIGH_STRESS'."""
    st.markdown(STRESS_BANNER_HTML, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Render a styled page header with Space Grotesk font and optional icon."""
    t = get_theme_tokens()
    sub_html = (
        f'<div style="font-size:0.95rem;color:{t["text_secondary"]};margin-top:7px;'
        f'letter-spacing:0.01em;font-weight:400;">{subtitle}</div>'
        if subtitle else ""
    )
    icon_html = (
        f'<div style="'
        f'width:2.8rem;height:2.8rem;'
        f'background:{t["accent_soft"]};'
        f'border:1px solid {t["accent_border"]};'
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
        f'font-weight:700;color:{t["text_primary"]};letter-spacing:-0.02em;line-height:1.15;">'
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

PLOTLY_LIGHT = {
    "template": "plotly_white",
    "paper_bgcolor": "#ffffff",
    "plot_bgcolor": "#ffffff",
    "font": {"family": "DM Sans", "color": "#334155", "size": 11},
    "colorway": ["#7c5cfc", "#0dcfb0", "#3b82f6", "#f59e0b", "#f87171"],
    "margin": {"l": 8, "r": 8, "t": 24, "b": 8},
}


def apply_plotly_dark_theme(fig):
    """Apply the custom dark finance theme to a Plotly figure."""
    fig.update_layout(**PLOTLY_DARK)
    fig.update_xaxes(gridcolor="#1e2640", linecolor="#1e2640")
    fig.update_yaxes(gridcolor="#1e2640", linecolor="#1e2640")
    return fig


def apply_plotly_theme(fig):
    """Apply dark or light theme to a Plotly figure based on session state.

    Beyond background and gridlines, this also forces a dark, readable colour on
    every text element (title, axis titles, tick labels, legend, annotations,
    hover labels) so nothing renders washed-out on the light surface.
    """
    if st.session_state.get("theme", "dark") == "light":
        fig.update_layout(**PLOTLY_LIGHT)
        fig.update_layout(
            legend_font_color="#334155",
            hoverlabel=dict(
                bgcolor="#ffffff",
                bordercolor="#cbd5e1",
                font=dict(color="#111827", family="DM Sans"),
            ),
        )
        # Only recolour the title when one actually exists — passing a title
        # font without text makes Plotly render the literal string "undefined".
        if fig.layout.title is not None and fig.layout.title.text:
            fig.update_layout(title_font_color="#111827")
        # Colour every axis element explicitly. Unlike the main layout title,
        # setting an axis title font colour does NOT invent an "undefined" label,
        # so it is safe and guarantees readable axis titles + tick labels.
        fig.update_xaxes(
            gridcolor="#e2e8f0", linecolor="#cbd5e1",
            color="#334155", tickfont_color="#334155",
            title_font_color="#334155", zerolinecolor="#e2e8f0",
        )
        fig.update_yaxes(
            gridcolor="#e2e8f0", linecolor="#cbd5e1",
            color="#334155", tickfont_color="#334155",
            title_font_color="#334155", zerolinecolor="#e2e8f0",
        )
        # Annotations carry their own font colour; relax any near-white values.
        for ann in fig.layout.annotations:
            if ann.font is not None and ann.font.color in (
                None, "#94a3b8", "#cbd5e1", "#e2e8f0", "#f1f5f9", "white", "#ffffff",
            ):
                ann.font.color = "#334155"
        # Polar charts (radar) keep their own axis styling
        if fig.layout.polar is not None:
            fig.update_polars(
                radialaxis=dict(gridcolor="#e2e8f0", color="#334155"),
                angularaxis=dict(gridcolor="#e2e8f0", color="#334155"),
            )
    else:
        fig.update_layout(**PLOTLY_DARK)
        fig.update_xaxes(gridcolor="#1e2640", linecolor="#1e2640")
        fig.update_yaxes(gridcolor="#1e2640", linecolor="#1e2640")
    return fig
