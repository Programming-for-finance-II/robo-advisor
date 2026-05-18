# AI-Powered Robo-Advisor Platform

> Educational robo-advisor prototype — USI Programming in Finance II (2026)

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/frontend-Streamlit-red)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-green)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

An academic robo-advisor that classifies investor risk profiles using a
machine learning model trained on real household behaviour data (Fed SCF 2022),
optimises portfolios via Hierarchical Risk Parity (López de Prado, 2016),
and generates natural-language explanations through a constrained LLM narrator
(Claude API) that is mathematically prevented from inventing numbers.

**Team:** P1 Backend/Data · P2 Quant/Optimizer · P3 ML/Profiling · P4 Frontend/LLM/Docs  
**Course:** Programming in Finance II — Prof. P. Gruber — USI 2026

---

## Live Demo

🌐 **[https://robo-advisor-usi.streamlit.app/](https://robo-advisor-usi.streamlit.app/)**

---

## Project Structure

```text
robo-advisor/
├── README.md                  ← you are here
├── AGENTS.md                  ← agentic workflow documentation
├── pyproject.toml             ← dependencies (uv)
├── docker-compose.yml         ← local dev environment
├── Dockerfile                 ← container image
├── .github/
│   └── workflows/
│       ├── ci.yml             ← lint + pytest on every push
│       └── agent_pr.yml       ← AI agent automated PR (criterion 5)
├── backend/
│   ├── api/                   ← FastAPI endpoints (/profile, /optimize, /advice, /backtest, /compare)
│   ├── ml/
│   │   ├── profiler/          ← GBM classifier trained on Fed SCF 2022
│   │   └── regime_detector.py
│   ├── optimizer/             ← HRP + Ledoit-Wolf + Markowitz benchmark
│   ├── llm/                   ← Claude API narrator + 5-step validator
│   └── data/                  ← ValidatedDataLoader + UCITS fallback logic
├── frontend/
│   └── app.py                 ← Streamlit UI (questionnaire, dashboard, chat)
├── docs/
│   ├── user_guide.md          ← end-to-end user flow
│   └── adr/                   ← Architecture Decision Records
└── tests/                     ← pytest unit + integration (≥75% coverage)
```

---

## Installation

### Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

### Clone and install

```bash
git clone https://github.com/Programming-for-finance-II/robo-advisor.git
cd robo-advisor
uv sync
```

### Environment variables

Create a `.env` file in the root (never commit this file):

```bash
ANTHROPIC_API_KEY=sk-ant-...
API_KEY=your-api-key
```

### Run locally

```bash
uv run streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501).

### Run with Docker

```bash
docker-compose up --build
```

SQLite data persists in a Docker volume between restarts.

---

## User Guide

### Step-by-step flow

1. **Questionnaire** — answer 10 risk profiling questions (Grable-Lytton scale, 1999).
   Q7 ("safety net money") triggers a MiFID II hard override to CONSERVATIVE
   regardless of other answers.

2. **Profile Result** — view your investor profile (`CONSERVATIVE` / `MODERATE` /
   `AGGRESSIVE`) with model confidence score and top behavioural drivers
   (SHAP values in Phase B, importance scores in Phase A).

3. **Portfolio Dashboard** — explore your HRP-optimised portfolio with:
   - Risk contribution breakdown
   - UCITS badges 🇪🇺 in the weights table
   - EU Investor Note banner
   - Stress Regime banner (visible only when correlations spike)

4. **Markowitz Tab** — compare HRP allocation against the Mean-Variance benchmark.

5. **Chat Advisor** — ask natural-language questions about your portfolio.
   Answers go through a 3-stage safety pipeline (input sanitiser, narrator,
   5-step validator) and always include an educational disclaimer.

See [`docs/user_guide.md`](docs/user_guide.md) for the complete user guide.

---

## API Documentation

Interactive docs available at `http://localhost:8000/docs` when running locally.

All endpoints require the header `X-API-Key: your-api-key`.

### `POST /profile`

Classifies investor risk profile from questionnaire answers.

```json
// Request
{
  "responses": {
    "Q1": "a", "Q2": "b", "Q3": "c", "Q4": "a",
    "Q5": "b", "Q6": "c", "Q7": "b", "Q8": "c",
    "Q9": "d", "Q10": "b"
  }
}

// Response
{
  "profile_label": "MODERATE",
  "confidence": 0.82,
  "low_confidence_flag": false,
  "top_drivers": [
    {"feature": "Q7", "importance": 0.67},
    {"feature": "Q9", "importance": 0.33}
  ],
  "model_version": "rule_based_v1"
}
```

### `POST /optimize`

Returns HRP-optimised portfolio weights and risk metrics.

```json
// Request
{ "profile_label": "MODERATE" }

// Response
{
  "algorithm": "HRP",
  "weights": { "CSPX.L": 0.18, "EFA": 0.12, "AGGH.MI": 0.25 },
  "expected_volatility": 0.084,
  "sharpe_ratio": null,
  "risk_contributions": { "CSPX.L": 0.22, "EFA": 0.18 },
  "ucits_tickers_used": ["CSPX.L", "AGGH.MI", "XEON.MI"],
  "fallback_tickers_applied": [],
  "recommendation_id": "uuid-...",
  "market_data_hash": "sha256-..."
}
```

### `POST /advice`

Generates a validated LLM explanation of the portfolio.

```json
// Request
{
  "recommendation_id": "uuid-...",
  "user_message": "Why is my bond allocation so high?"
}

// Response
{
  "safe_text": "Given your moderate profile...",
  "passed": true,
  "disclaimer_appended": true,
  "validator_flags": [],
  "injection_blocked": false,
  "api_error": false
}
```

### `POST /backtest`

Runs HRP vs MV vs 1/N backtest on 3 historical stress scenarios
(GFC 2008, COVID 2020, Rate Hike 2022).

```json
// Request
{ "profile_label": "MODERATE" }

// Response
{
  "profile_label": "MODERATE",
  "scenarios": [
    {
      "scenario_key": "gfc_2008",
      "scenario_label": "Global Financial Crisis (2008)",
      "test_start": "2008-01-02",
      "test_end": "2009-06-30",
      "strategies": {
        "HRP": { "cagr": -0.12, "max_drawdown": -0.38, "sharpe_ratio": -0.45 },
        "MV":  { "cagr": -0.18, "max_drawdown": -0.45, "sharpe_ratio": -0.52 },
        "1/N": { "cagr": -0.15, "max_drawdown": -0.41, "sharpe_ratio": -0.48 }
      }
    }
  ]
}
```

### `POST /compare`

Compares HRP vs Markowitz vs equal-weight portfolios.

```json
// Request
{ "profile_label": "MODERATE" }

// Response
{
  "profile_label": "MODERATE",
  "hrp": { "CSPX.L": 0.18, "EFA": 0.12 },
  "mv":  { "CSPX.L": 0.25, "EFA": 0.08 },
  "equal_weight": { "CSPX.L": 0.125, "EFA": 0.125 },
  "hrp_volatility": 0.084,
  "mv_volatility": 0.091,
  "equal_weight_volatility": 0.096
}
```

---

## Technical Highlights

| Component | Technology | Notes |
|---|---|---|
| Risk Profiler ★ | scikit-learn GBM + SHAP | Trained on Fed SCF 2022 real data |
| LLM Narrator ★ | Claude API (Anthropic) | Narrator pattern — cannot invent numbers |
| LLM Validator | Custom 5-step pipeline | Forbidden phrases, hallucinated numbers, disclaimer, injection detection, EU Awareness Rule 9 |
| Portfolio Optimizer | PyPortfolioOpt HRP | Ledoit-Wolf shrinkage, guardrails 5–40% |
| Data Layer | yfinance | ValidatedDataLoader with UCITS fallback + SHA-256 audit hash |
| Database | SQLite | Full audit trail (market hash, prompt hash, validator flags) |
| Frontend | Streamlit | EU Investor Note, stress banner, UCITS badges |
| Backend API | FastAPI + slowapi | Rate limiting, API key auth |
| CI/CD | GitHub Actions | Lint + pytest + coverage + AI agent automated PR |
| Deployment | Streamlit Community Cloud | Live at robo-advisor-usi.streamlit.app |

---

## EU Awareness

This prototype explicitly addresses the geographic tension between its US-trained
model and European retail investors:

- Portfolio universe includes **UCITS-eligible ETFs** (CSPX.L, AGGH.MI, XEON.MI)
  with automatic fallback to US-listed equivalents if unavailable on yfinance
- The LLM narrator applies **Rule 9 (EU Awareness)**: all advice acknowledges
  the SCF/EU behavioural gap when addressing European investors
- A persistent **EU Investor Note** banner is shown on the Portfolio page
- **UCITS badges** 🇪🇺 are displayed in the portfolio weights table

---

## Testing

```bash
# Run full test suite
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=backend --cov-report=term-missing
```

CI runs lint (ruff) + pytest + coverage on every push.
Coverage target: ≥75% on backend modules.

---

## Disclaimer

This is an **educational prototype** developed in an academic context at USI
(Università della Svizzera italiana). No content constitutes financial advice
under MiFID II or any other regulatory framework. Market data may be inaccurate
or delayed. The risk profiling model is trained on US household data (Fed SCF 2022)
and may not reflect European investor behaviour.

---

## Academic Documentation

Full project documentation (LaTeX PDF, 5–8 pages) submitted on iCorsi includes:
- Mathematical derivation of HRP (López de Prado, 2016)
- ML pipeline: SCF preprocessing, clustering, GBM + SHAP
- LLM Narrator architecture: Ground Truth JSON, 5-step Validator, EU Awareness
- Backtest results: 2008, 2020, 2022 stress scenarios
- Limitations and failure modes
- Lessons learned from the agentic development process

🔗 **GitHub:** [https://github.com/Programming-for-finance-II/robo-advisor](https://github.com/Programming-for-finance-II/robo-advisor)
