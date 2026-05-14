# User Guide — AI-Powered Robo-Advisor Platform

**Version:** 1.0  
**Course:** Programming in Finance II — USI, Prof. P. Gruber (2026)  
**Repository:** https://github.com/Programming-for-finance-II/robo-advisor

---

> ⚠️ **Educational Disclaimer**  
> This is an educational prototype developed in an academic context (USI, Programming in Finance II 2026).  
> No content constitutes financial advice under MiFID II or any other applicable regulatory framework.  
> Market data may be inaccurate or delayed. The risk profiling model is trained on US household data  
> (Fed SCF 2022) and may not reflect European investor behaviour.

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Step 1 — Risk Profiling Questionnaire](#step-1--risk-profiling-questionnaire)
4. [Step 2 — Profile Result](#step-2--profile-result)
5. [Step 3 — Portfolio Dashboard](#step-3--portfolio-dashboard)
6. [Step 4 — Chat Advisor](#step-4--chat-advisor)
7. [EU Investor Awareness](#eu-investor-awareness)
8. [Known Limitations](#known-limitations)
9. [API Reference (for developers)](#api-reference-for-developers)

---

## Overview

The AI-Powered Robo-Advisor Platform is an educational prototype that demonstrates a full end-to-end
investment workflow:

```
Questionnaire → Risk Profile → Portfolio Optimisation → Natural-Language Explanation
```

The platform combines four technical components:

| Component | Technology | Role |
|---|---|---|
| Risk Profiler | Rule-based (Phase A) / GBM on Fed SCF 2022 (Phase B) | Classifies investor risk tolerance |
| Portfolio Optimizer | Hierarchical Risk Parity (HRP) + Ledoit-Wolf shrinkage | Builds diversified UCITS-aware portfolio |
| LLM Narrator | Claude API (Anthropic) | Explains results in natural language |
| LLM Validator | 5-step post-generation filter | Ensures narrator does not hallucinate or give advice |

---

## Getting Started

### Local installation

```bash
git clone https://github.com/Programming-for-finance-II/robo-advisor.git
cd robo-advisor
uv sync
```

### Run the app

```bash
# Terminal 1 — FastAPI backend
uv run uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — Streamlit frontend
uv run streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (for Chat Advisor) | Anthropic API key for the LLM narrator |
| `API_KEY` | No | FastAPI authentication key (disabled in dev mode if unset) |

Set via `.streamlit/secrets.toml` for local development:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Or as environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Step 1 — Risk Profiling Questionnaire

**Navigation:** sidebar → *Questionnaire*

### What it does

The questionnaire implements the Grable & Lytton (1999) Risk Tolerance Scale, adapted
for MiFID II suitability requirements. It consists of 10 questions grouped in three sections:

| Section | Questions | What it measures |
|---|---|---|
| Who You Are Financially | Q1–Q4 | Age, income, liquidity, financial dependents |
| How You Invest | Q5–Q7 | Investment experience, financial knowledge, investment horizon |
| How You React | Q8–Q10 | Drawdown reaction, loss composure, self-assessed risk appetite |

### How to use it

1. Answer all 10 questions using the radio buttons.
2. No answer is pre-selected — every question requires an explicit choice.
3. Click **Calculate my profile** to submit.

### Scoring

Each answer carries a score from 0 to 3. The total score (range 0–30) maps to a risk profile:

| Score | Profile | Confidence |
|---|---|---|
| 0–7 | CONSERVATIVE | High (1.0) |
| 8–9 | CONSERVATIVE | Borderline (0.7) |
| 10–11 | MODERATE | Borderline (0.7) |
| 12–17 | MODERATE | High (1.0) |
| 18–19 | MODERATE | Borderline (0.7) |
| 20–21 | AGGRESSIVE | Borderline (0.7) |
| 22–30 | AGGRESSIVE | High (1.0) |

### MiFID II override (Q7)

**Q7 — Investment horizon** carries a hard override rule: if you select *"Safety net — I may need
this money at any time"*, your profile is automatically set to **CONSERVATIVE** regardless of
your total score. This reflects the MiFID II suitability requirement that capital earmarked for
short-term liquidity must not be exposed to portfolio volatility.

When this override fires, the app displays a blue info box explaining why.

---

## Step 2 — Profile Result

**Shown immediately after submitting the questionnaire.**

After submission, the questionnaire page displays a preview with:

- **Your risk profile** — CONSERVATIVE, MODERATE, or AGGRESSIVE
- **Confidence** — percentage certainty of the classification
- A **warning badge** if your score falls in a borderline zone (confidence = 0.7),
  suggesting you review your answers

The full result is stored in `st.session_state["profile"]` and consumed by the Portfolio
Dashboard and Chat Advisor pages.

### Top drivers

The result also includes the three questions that most influenced your classification
(called *top drivers*). In Phase A (rule-based), these are the questions whose answers
deviated most from the neutral midpoint. In Phase B (GBM + SHAP), they are replaced by
SHAP TreeExplainer values from the trained gradient boosting model.

---

## Step 3 — Portfolio Dashboard

**Navigation:** sidebar → *Portfolio Dashboard*

### What it shows

The dashboard displays the portfolio recommended for your risk profile. It reads your
profile from session state (or falls back to MODERATE if you navigate here directly without
completing the questionnaire first).

The page is divided into two tabs:

#### HRP Portfolio tab

Shows the Hierarchical Risk Parity portfolio:

- **Portfolio weights** — allocation per ETF ticker
- **Active profile and confidence** — your investor classification
- *(Phase B)* Risk contribution bar chart, dendrogram, and full metrics table

#### Markowitz Benchmark tab

Shows the Mean-Variance (Markowitz) benchmark for educational comparison.
This tab makes the diversification benefit of HRP visible: HRP does not
require an estimate of expected returns and avoids the corner solutions
typical of unconstrained Markowitz.

### EU Investor Note

A persistent info banner at the bottom of the page reads:

> *EU Investor Note — The risk profile model is trained on US Federal Reserve SCF data (2022).
> Results may not fully reflect the behaviour of European retail investors. (EU Awareness Rule 9)*

This note is always shown and cannot be dismissed. It is part of the EU Awareness Layer
(design v3.1) and is required by the LLM system prompt Rule 9.

### MiFID II disclaimer

A yellow warning banner is shown above all financial outputs on every page:

> *Educational prototype developed in an academic context. No content constitutes financial
> advice under MiFID II or any other regulatory framework. Market data may be inaccurate
> or delayed.*

---

## Step 4 — Chat Advisor

**Navigation:** sidebar → *Chat Advisor*

### What it does

The Chat Advisor allows you to ask natural-language questions about your portfolio.
Responses are generated by a constrained LLM (Claude API) and validated by a
5-step safety pipeline before being shown to you.

### How to use it

1. Navigate to *Chat Advisor* in the sidebar.
2. The active profile is shown in a blue info box.
3. Type your question in the text field, e.g.:
   - *"Why is my bond allocation so high?"*
   - *"What does the safe haven cluster mean?"*
   - *"How did this portfolio perform in 2020?"*
4. Click **Ask**.

### What the LLM can and cannot do

| ✅ Can do | ❌ Cannot do |
|---|---|
| Explain portfolio weights and their rationale | Give investment advice ("you should buy/sell") |
| Describe risk metrics in plain language | Invent numbers not present in the portfolio data |
| Explain what the risk profile classification means | Make forward-looking return forecasts |
| Acknowledge limitations and geographic data gaps | Claim MiFID II compliance or portfolio optimality |
| Respond in the same language you write in | Answer questions outside the portfolio context |

### 5-step validation pipeline

Every LLM response passes through the Validator before reaching you:

| Step | Check | Behaviour on failure |
|---|---|---|
| 1 | Forbidden phrases (e.g. "you should", "guaranteed") | Blocked → safe fallback shown |
| 2 | Hallucinated numbers (not in portfolio data) | Blocked → safe fallback shown |
| 3 | Disclaimer presence | Auto-appended if missing — response still shown |
| 4 | Post-generation prompt injection | Blocked → safe fallback shown |
| 5 | EU Awareness Rule 9 (US data gap acknowledgement) | Blocked → safe fallback shown |

If the response is blocked, you will see:

> *"I cannot provide a detailed response at this time. Please consult a qualified financial
> advisor for personalised advice."*

### Prompt injection protection

The Chat Advisor includes two layers of protection against prompt injection attacks:

- **Layer 1 (pre-call):** input is checked for length (max 500 characters) and known
  injection patterns (*"ignore previous instructions"*, *"act as"*, *"jailbreak"*, etc.)
  before the API call is made.
- **Layer 2 (post-generation):** the Validator scans the LLM output for echoed injection
  instructions before the response reaches the UI.

If your question is blocked by Layer 1, you will see a warning asking you to rephrase.

### API key not configured

If `ANTHROPIC_API_KEY` is not set, the Chat Advisor displays:

> *"ANTHROPIC_API_KEY is not configured. Add it to `.streamlit/secrets.toml`..."*

The Questionnaire and Portfolio Dashboard pages remain fully functional without an API key
(Phase A mock data is always available).

---

## EU Investor Awareness

This platform explicitly addresses the geographic gap between its US-trained model and
European retail investors. Key disclosures:

### Risk profiler data source

The risk profiler is trained on the **Federal Reserve Survey of Consumer Finances (SCF) 2022**,
a US household survey. European investors may exhibit systematically different risk preferences,
savings rates, and financial literacy patterns.

The ECB Household Finance and Consumption Survey (HFCS) would be a more geographically
appropriate training source for EU investors. It is identified as a priority for future work.

### Portfolio universe

The ETF universe (v3.1) includes UCITS-eligible instruments where available:

| Ticker | Asset Class | UCITS | Currency |
|---|---|---|---|
| CSPX.L | Equity USA | ✅ | GBP-listed, USD underlying |
| AGGH.MI | Bond Aggregate (EUR-hedged) | ✅ | EUR |
| XEON.MI | Cash / Overnight (€STR) | ✅ | EUR |
| EFA | Equity International | ❌ | USD |
| TLT | US Treasury Long Duration | ❌ | USD |
| GLD | Gold | ❌ | USD |
| VNQ | Real Estate (REIT) | ❌ | USD |
| TIP | US TIPS (Inflation-Linked) | ❌ | USD |

Non-UCITS tickers are used because no UCITS equivalent with comparable yfinance
data quality was available at prototype scope. EUR-based investors are exposed to
EUR/USD currency risk for the USD-denominated positions.

### LLM EU Awareness (Rule 9)

The LLM narrator is required to include an explicit acknowledgement of the US/EU
data gap whenever `profiler_us_centric_caveat = true` in the Ground Truth JSON.
The Validator blocks any response that does not satisfy this rule.

---

## Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Risk profiler trained on US data (SCF 2022) | European risk preferences may not be well represented | EU Awareness banner + LLM Rule 9 disclosure |
| yfinance as sole data source | Subject to retroactive adjustments and occasional gaps | SHA-256 audit trail of every price snapshot; UCITS fallback logic |
| HRP does not produce expected return estimates | No forward-looking Sharpe ratio available | `expected_annual_return = null` by design; documented in ADR-001 |
| SCF uses implicate=1 only (not all 5 imputations) | Slight underestimate of standard errors in profiler | Documented as simplification in ADR-002 |
| SQLite resets on redeploy (Streamlit Cloud) | Audit trail not persistent across deploys | Full local reproducibility via `docker-compose`; PostgreSQL path documented |
| Streamlit Cloud cold starts | First request after inactivity may take 10–30s | Known and accepted for prototype scope |
| "safe" substring false positives in validator | *"safe haven"* cluster label may trigger forbidden phrase check | Documented in ADR-004 and accepted for prototype scope |

---

## API Reference (for developers)

The backend exposes three endpoints via FastAPI.
Interactive documentation available at `http://localhost:8000/docs`.

### `POST /profile`

Classifies investor risk profile from questionnaire responses.

**Rate limit:** 20 requests/minute

```json
// Request
{
  "responses": {
    "Q1": "b", "Q2": "c", "Q3": "b", "Q4": "a",
    "Q5": "c", "Q6": "b", "Q7": "c", "Q8": "b",
    "Q9": "c", "Q10": "b"
  }
}

// Response
{
  "profile_label": "MODERATE",
  "confidence": 0.82,
  "low_confidence_flag": false,
  "top_drivers": [
    {"feature": "investment_horizon", "importance": 0.41},
    {"feature": "risk_attitude", "importance": 0.32},
    {"feature": "age", "importance": 0.17}
  ],
  "model_version": "rule_based_v1"
}
```

### `POST /optimize`

Returns HRP-optimised portfolio weights and risk metrics.

**Rate limit:** 10 requests/minute

```json
// Request
{
  "profile_label": "MODERATE",
  "tickers": ["CSPX.L", "EFA", "AGGH.MI", "TLT", "GLD", "VNQ", "TIP", "XEON.MI"]
}

// Response
{
  "algorithm": "HRP",
  "weights": {"CSPX.L": 0.22, "EFA": 0.15, "AGGH.MI": 0.18, ...},
  "expected_volatility": 0.094,
  "expected_return": null,
  "sharpe_ratio": null,
  "risk_contributions": {"CSPX.L": 0.31, ...},
  "recommendation_id": "uuid-v4",
  "market_data_hash": "sha256:...",
  "ucits_tickers_used": ["CSPX.L", "AGGH.MI", "XEON.MI"],
  "fallback_tickers_applied": [],
  "optimizer_version": "2.0.0",
  "solver_status": "optimal"
}
```

### `POST /advice`

Generates a validated natural-language explanation of a saved portfolio recommendation.

**Rate limit:** 10 requests/minute  
**Requires:** `ANTHROPIC_API_KEY` set in environment

```json
// Request
{
  "recommendation_id": "uuid-from-optimize-response",
  "user_message": "Why is my bond allocation so high?"
}

// Response
{
  "safe_text": "Given your MODERATE profile...\n\n[disclaimer]",
  "passed": true,
  "disclaimer_appended": false,
  "validator_flags": [],
  "injection_blocked": false,
  "api_error": false
}
```

---

## References

- Grable, J. E., & Lytton, R. H. (1999). *Financial risk tolerance revisited.* Financial Services Review, 8(3), 163–181.
- López de Prado, M. (2016). *Building Diversified Portfolios that Outperform Out-of-Sample.* Journal of Portfolio Management.
- Ledoit, O., Wolf, M. (2004). *A well-conditioned estimator for large-dimensional covariance matrices.* Journal of Multivariate Analysis.
- Federal Reserve Board (2022). *Survey of Consumer Finances.* Washington, D.C.
- MiFID II Directive 2014/65/EU, Article 25 — Suitability assessment.

---

*This user guide covers prototype v3.1. For architecture decisions and design rationale, see `docs/architecture.md` and the ADR directory (`docs/adr/`).*
