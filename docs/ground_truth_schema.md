# Ground Truth JSON Schema

**Version:** 3.1  
**Source of truth (code):** `backend/schemas/ground_truth.py`  
**Last updated:** 2026-05-04

This document defines every field of the Ground Truth JSON payload produced by the
numerical backend (P1 / P2 / P3) and consumed by the LLM Narrator, the LLM Validator,
and the Streamlit frontend.

> **Rule:** No component may invent or alter fields outside this schema.  
> **Principle:** The LLM is a narrator, not a calculator. Every number it mentions must
> appear verbatim in `llm_constraints.allowed_numbers`.

---

## Top-level structure

```
GroundTruthPayload
├── metadata
├── portfolio
│   ├── weights                  ← LLM uses this
│   └── risk_contributions       ← LLM uses this
├── profiler
│   ├── profile_label            ← LLM uses this
│   ├── profile_confidence       ← LLM uses this
│   └── top_drivers              ← LLM uses this
├── risk_metrics
├── cluster_structure
├── stress_scenarios
├── backtest_summary
├── llm_constraints
└── regulatory_context           ← EU Awareness Layer
```

---

## `metadata`

| Field | Type | Description |
|---|---|---|
| `recommendation_id` | `str` (UUID v4) | Unique ID for this recommendation run |
| `timestamp_utc` | `str` (ISO 8601) | Generation timestamp in UTC |
| `optimizer` | `"HRP" \| "MV"` | Algorithm used |
| `optimizer_version` | `str` | e.g. `"pypfopt==1.5.5"` |
| `market_data_hash` | `str` | SHA-256 of the price matrix CSV — audit trail key |
| `data_window` | `{start: str, end: str}` | Date range of market data used |

---

## `portfolio`

### `weights`

Ticker → portfolio weight mapping. Used directly by the LLM narrator and the
Streamlit weights table.

```json
"weights": {
  "SWRD.L": 0.22,
  "CSPX.L": 0.15,
  "AGGH.L": 0.18,
  "IGLT.L": 0.12,
  "SGLN.L": 0.11,
  "IWDP.L": 0.08,
  "BIL":    0.09,
  "TIPS":   0.05
}
```

**Invariant:** `sum(weights.values()) ∈ [0.999, 1.001]`

| Field | Type | Constraint |
|---|---|---|
| `weights` | `dict[str, float]` | Values sum to 1.0 ± 0.001 |
| `guardrail_applied` | `bool` | True if any weight was clipped |
| `clipped_assets` | `list[str]` | Tickers whose raw HRP weight was adjusted |
| `clip_note` | `str \| null` | Human-readable clip explanation |

### `risk_contributions`

Per-ticker **marginal risk contribution** to total portfolio volatility, expressed as
fractions summing to 1.0. Used by the LLM to explain which positions drive risk, and
rendered as a bar chart in the Streamlit dashboard.

```json
"risk_contributions": {
  "SWRD.L": 0.31,
  "CSPX.L": 0.22,
  "AGGH.L": 0.14,
  "IGLT.L": 0.10,
  "SGLN.L": 0.09,
  "IWDP.L": 0.08,
  "BIL":    0.03,
  "TIPS":   0.03
}
```

**Invariant:** `sum(risk_contributions.values()) ∈ [0.999, 1.001]`  
**Invariant:** same ticker keys as `weights`.

---

## `profiler`

Output of the risk profiling module (rule-based in Phase A, GBM + SHAP in Phase B).

### `profile_label`

```json
"profile_label": "MODERATE"
```

**Allowed values:** `"CONSERVATIVE"` | `"MODERATE"` | `"AGGRESSIVE"`  
(EN, UPPER — canonical across the entire codebase and DB schema.)

### `profile_confidence`

```json
"profile_confidence": 0.82
```

Float in `[0.0, 1.0]`. Derived from the distance of the raw score from the nearest
boundary in the Grable-Lytton scoring table. Values below `0.60` set
`low_confidence_flag = True` and are displayed with a warning badge in the UI.

### `top_drivers`

Top-3 questions by influence on the profile decision. In Phase A (rule-based): sorted
by absolute score deviation from neutral midpoint. In Phase B (GBM): sorted by SHAP
value magnitude.

```json
"top_drivers": [
  {"question_id": "Q3", "label": "Investment horizon",          "contribution": 0.34},
  {"question_id": "Q7", "label": "Emergency fund",              "contribution": 0.28},
  {"question_id": "Q9", "label": "Past behaviour in downturns", "contribution": 0.21}
]
```

| Sub-field | Type | Description |
|---|---|---|
| `question_id` | `str` | Matches `questionnaire_schema.md` IDs (Q1–Q10) |
| `label` | `str` | Human-readable question topic |
| `contribution` | `float` | Relative contribution to profile decision, in `[0.0, 1.0]` |

**Invariant:** `len(top_drivers) == 3`

---

## `risk_metrics`

| Field | Type | Description |
|---|---|---|
| `expected_annual_return` | `float \| null` | **Always `null` for HRP.** HRP does not require or reliably produce point estimates of expected return. |
| `annual_volatility` | `float` | Annualised portfolio volatility (e.g. `0.094` = 9.4 %) |
| `sharpe_ratio` | `float \| null` | **Always `null` for HRP** — undefined without expected return |
| `max_drawdown_historical` | `float` | Worst peak-to-trough drawdown in the data window (negative) |
| `var_95_daily` | `float` | 1-day 95% Value at Risk (negative) |
| `cvar_95_daily` | `float` | 1-day 95% Conditional VaR / Expected Shortfall (negative) |

---

## `cluster_structure`

Four clusters from Ward hierarchical linkage on the correlation matrix. Each object:

| Field | Type | Description |
|---|---|---|
| `members` | `list[str]` | Tickers in this cluster |
| `total_weight` | `float` | Sum of weights of members |
| `intra_cluster_correlation` | `float \| null` | Avg pairwise correlation (null for single-member clusters) |
| `cluster_volatility` | `float` | Annualised volatility of the cluster sub-portfolio |

| Cluster key | Role |
|---|---|
| `cluster_A_risk_assets` | Equity risk |
| `cluster_B_real_assets` | Inflation hedge / real assets |
| `cluster_C_safe_haven` | Duration / safe haven |
| `cluster_D_cash` | Liquidity buffer |

---

## `stress_scenarios`

| Key | Event |
|---|---|
| `covid_march_2020` | COVID-19 crash, Feb–Mar 2020 |
| `ukraine_feb_2022` | Russia–Ukraine invasion, Feb 2022 |
| `rates_hike_2022` | Fed aggressive rate hikes, full year 2022 |

Each: `{ portfolio_drawdown: float, benchmark_drawdown: float }` (both negative).

---

## `backtest_summary`

| Field | Type | Description |
|---|---|---|
| `period` | `str` | e.g. `"2019-2026"` |
| `cagr` | `float` | Compound Annual Growth Rate |
| `sharpe` | `float` | Realised Sharpe ratio over the backtest window |
| `max_drawdown` | `float` | Maximum drawdown (negative) |
| `calmar_ratio` | `float` | `CAGR / abs(max_drawdown)` |

---

## `llm_constraints`

The interface contract between the backend and the LLM Narrator.

| Field | Type | Description |
|---|---|---|
| `allowed_numbers` | `list[float]` | Auto-populated by `build_allowed_numbers()`. Every number the LLM may mention must be in this list. |
| `forbidden_phrases` | `list[str]` | Trigger Validator Step 3 → response discarded |
| `disclaimer_required` | `bool` | Always `true`. Validator Step 4 checks presence. |

**Canonical forbidden phrases:**
```
vendi, compra, investi, liquida, sposta,
garantito, sicuro, senza rischio, certo,
MiFID compliant, dovresti, ti consiglio di
```

**Mandatory disclaimer (appended by Validator if absent):**
```
Questo è un prototipo educativo e non costituisce consulenza finanziaria.
```

---

## `regulatory_context`

EU Awareness Layer introduced in Design v3.1. Consumed by the LLM system prompt
(Rule 9) and the Streamlit EU Investor Note banner.

| Field | Type | Description |
|---|---|---|
| `profiler_us_centric_caveat` | `bool` | `true` = profiler trained on Fed SCF 2022 (US survey). **Triggers Rule 9** in the LLM system prompt. |
| `mifid_disclaimer` | `str` | MiFID II disclaimer text. Surfaced above every financial output in the UI. |
| `currency_risk_note` | `str` | Note about currency risk for EU investors holding USD-denominated or GBP-listed ETFs. |
| `etf_ucits_eligible` | `bool` | `true` if all tickers in `weights` are UCITS-compliant. `false` triggers a warning badge in the UI. |
| `hfcs_note` | `str \| null` | Note about HFCS as a European alternative to SCF for profiler training. `null` if not applicable. |
| `ucits_tickers_used` | `list[str]` | UCITS tickers present in this run |
| `non_ucits_tickers` | `list[str]` | Non-UCITS (US fallback) tickers present in this run |
| `currency_exposure` | `dict[str, float]` | `{"USD": float, "EUR": float, "GBP": float}`. Sum ≤ 1.0. |
| `stress_regime` | `"NORMAL" \| "HIGH_STRESS"` | `HIGH_STRESS` → Streamlit shows red stress banner |
| `eu_investor_note` | `str` | Full text for the EU Investor Note banner on the Portfolio page |

### Canonical static values

```json
"mifid_disclaimer": "This tool is an educational prototype. It does not constitute
  investment advice under MiFID II Article 25 or any other applicable regulation.
  Past performance is not indicative of future results.",

"currency_risk_note": "Some ETFs in this portfolio are denominated in USD or listed
  in GBP. EU investors are exposed to USD/EUR and GBP/EUR exchange rate risk in
  addition to market risk.",

"hfcs_note": "The risk profiler was trained on the Federal Reserve Survey of Consumer
  Finances (SCF 2022), a US-based dataset. European household financial behaviour may
  differ systematically. The ECB Household Finance and Consumption Survey (HFCS) would
  be a more representative training source for EU investors."
```

### Rule 9 — LLM system prompt behaviour

When `profiler_us_centric_caveat = true`, the narrator must include:

> "Il profilo di rischio è stato determinato con un modello addestrato su dati
> statunitensi (Fed SCF 2022). Gli investitori europei potrebbero presentare
> preferenze di rischio sistematicamente diverse."

---

## Validation invariants

Enforced by `backend/schemas/ground_truth.py` via Pydantic `model_validator`:

1. `sum(portfolio.weights.values()) ∈ [0.999, 1.001]`
2. `sum(portfolio.risk_contributions.values()) ∈ [0.999, 1.001]`
3. Same ticker keys in `weights` and `risk_contributions`
4. All tickers in `weights` appear in at least one cluster
5. `len(profiler.top_drivers) == 3`
6. `len(llm_constraints.allowed_numbers) ≥ len(portfolio.weights)`
7. `sum(regulatory_context.currency_exposure.values()) ≤ 1.0`
8. `risk_metrics.var_95_daily < 0` and `risk_metrics.cvar_95_daily < 0`

---

## Component usage summary

| Component | Fields consumed |
|---|---|
| **LLM Narrator** (`backend/llm/narrator.py`) | Full payload as `CONTEXT` block. `llm_constraints` for guardrails. `regulatory_context` for Rule 9. |
| **LLM Validator** (`backend/llm/validator.py`) | `llm_constraints.allowed_numbers`, `forbidden_phrases`, `disclaimer_required` |
| **Streamlit — Profile page** | `profiler.profile_label`, `profile_confidence`, `top_drivers` |
| **Streamlit — Portfolio page** | `portfolio.weights`, `risk_contributions`, `risk_metrics`, `cluster_structure`, `stress_scenarios`, `regulatory_context.*` |
| **Streamlit — Chat Advisor** | Passes full payload to narrator; displays validated response + disclaimer |
| **Mock factory** (`backend/schemas/mock_data.py`) | `get_mock_payload(profile)` → valid `GroundTruthPayload` for Phase A |

---

## Related documents

- `backend/schemas/ground_truth.py` — Pydantic model (code source of truth)
- `backend/schemas/mock_data.py` — Phase A mock factory
- `docs/adr/ADR-001-hrp-over-markowitz.md` — HRP design rationale
- `docs/adr/ADR-004-llm-narrator-validator.md` — Narrator + Validator design (W3)
- `docs/architecture.md` — Full system data flow
- `docs/questionnaire_schema.md` — Question IDs referenced in `top_drivers`
