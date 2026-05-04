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

## Project Structure

```text
robo-advisor/
├── README.md                  ← you are here
├── AGENTS.md                  ← agentic workflow documentation
├── pyproject.toml             ← dependencies (uv)
├── .github/
│   └── workflows/
│       ├── ci.yml             ← lint + pytest on every push
│       └── agent_pr.yml       ← AI agent automated PR (criterion 5)
├── backend/
│   ├── api/                   ← FastAPI endpoints (/profile, /optimize, /advice)
│   ├── ml/
│   │   ├── profiler/          ← GBM classifier trained on Fed SCF 2022
│   │   └── regime_detector.py
│   ├── optimizer/             ← HRP + Ledoit-Wolf + Markowitz benchmark
│   ├── llm/                   ← Claude API narrator + 4-step validator
│   └── data/                  ← ValidatedDataLoader + UCITS fallback logic
├── frontend/
│   └── app.py                 ← Streamlit UI (questionnaire, dashboard, chat)
├── docs/
│   ├── user_guide.md          ← end-to-end user flow
│   └── adr/                   ← Architecture Decision Records
└── tests/                     ← pytest unit + integration
```
---

## Installation

### Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Clone and install

```bash
git clone https://github.com/Programming-for-finance-II/robo-advisor.git
cd robo-advisor
uv sync          # installs all dependencies from pyproject.toml
```

### Run locally

```bash
# Start the FastAPI backend
uv run uvicorn backend.api.main:app --reload --port 8000

# In a separate terminal, start the Streamlit frontend
uv run streamlit run frontend/app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

### Run with Docker

```bash
docker-compose up --build
```

---

## Usage

### Step-by-step user flow

1. **Questionnaire** — answer 7–10 risk profiling questions (Grable-Lytton scale)
2. **Profile Result** — view your investor profile (`CONSERVATIVE` / `MODERATE` / `AGGRESSIVE`) with model confidence score and top behavioural drivers (SHAP)
3. **Portfolio Dashboard** — explore your HRP-optimised portfolio with risk contribution breakdown, UCITS badges, and EU Investor Note
4. **Markowitz Tab** — compare HRP allocation against the Mean-Variance benchmark
5. **Chat Advisor** — ask natural-language questions about your portfolio; answers are validated by a 4-step LLM validator and always include an educational disclaimer

---

## API Documentation

The backend exposes three endpoints via FastAPI. Interactive docs available at `http://localhost:8000/docs`.

### `POST /profile`

Classifies investor risk profile from questionnaire answers.

```json
// Request
{
  "age": 35,
  "investment_horizon": "5-10 years",
  "loss_reaction": "Hold",
  "income_stability": "Stable",
  ...
}

// Response
{
  "profile_label": "MODERATE",
  "confidence": 0.82,
  "top_drivers": ["investment_horizon", "loss_reaction", "age"],
  "model_version": "rule_based_v1"
}
```

### `POST /optimize`

Returns HRP-optimised portfolio weights and risk metrics.

```json
// Request
{ "profile_label": "MODERATE", "tickers": ["IWDA.L", "IEMA.L", "AGGG.L"] }

// Response
{
  "weights": { "IWDA.L": 0.35, "IEMA.L": 0.15, "AGGG.L": 0.25 },
  "volatility": 0.084,
  "sharpe_ratio": 0.91,
  "regime": "NORMAL",
  "regulatory_context": { "ucits_tickers_used": ["IWDA.L", "AGGG.L"], ... }
}
```

### `POST /advice`

Generates a validated natural-language explanation of the portfolio.

```json
// Request
{ "user_message": "Why is my bond allocation so high?", "session_id": "abc123" }

// Response
{
  "response": "Given your moderate profile and 5–10 year horizon...",
  "validator_flags": [],
  "disclaimer_appended": true
}
```

---

## Technical Highlights

| Component | Technology | Notes |
|---|---|---|
| Risk Profiler ★ | scikit-learn GBM + SHAP | Trained on Fed SCF 2022 real data |
| LLM Narrator ★ | Claude API (Anthropic) | Narrator pattern — cannot invent numbers |
| LLM Validator | Custom 4-step pipeline | Number check, forbidden phrases, disclaimer, semantic |
| Portfolio Optimizer | PyPortfolioOpt HRP | Ledoit-Wolf shrinkage, guardrails 3–40% |
| Data Layer | yfinance + FRED | ValidatedDataLoader with UCITS fallback |
| Database | SQLite → PostgreSQL | Full audit trail (market hash, prompt hash) |
| Frontend | Streamlit | EU Investor Note, stress banner, UCITS badges |
| Backend API | FastAPI + slowapi | Rate limiting, API key auth |
| CI/CD | GitHub Actions | Lint + pytest + AI agent automated PR |

---

## 🇪EU Awareness

This prototype explicitly addresses the geographic tension between its US-trained
model and European retail investors:

- Portfolio universe includes **UCITS-eligible ETFs** (IWDA.L, AGGG.L, XEON.MI)
  with automatic fallback to US-listed equivalents if unavailable on yfinance
- The LLM narrator applies **Rule 9 (EU Awareness)**: all advice acknowledges
  the SCF/EU behavioural gap when addressing European investors
- A persistent **EU Investor Note** banner is shown on the Portfolio page
- **UCITS badges** are displayed in the portfolio weights table

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
- LLM Narrator architecture: Ground Truth JSON, 4-step Validator, EU Awareness
- Backtest results: 2008, 2020, 2022 stress scenarios
- Limitations and failure modes
- Lessons learned from the agentic development process

🔗 **GitHub:** [https://github.com/Programming-for-finance-II/robo-advisor](https://github.com/Programming-for-finance-II/robo-advisor)

