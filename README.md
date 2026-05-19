# AI-Powered Robo-Advisor Platform

> Educational robo-advisor prototype — USI Programming in Finance II (2026)

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/frontend-Streamlit-red)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-green)
[![CI](https://github.com/Programming-for-finance-II/robo-advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/Programming-for-finance-II/robo-advisor/actions/workflows/ci.yml)
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

> The app may take 10–30 seconds to wake up after a period of inactivity (Streamlit Cloud cold start).

---

## Project Structure

```text
robo-advisor/
├── README.md                  ← you are here
├── AGENTS.md                  ← agentic workflow + AI tools documentation
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
│   ├── architecture.md        ← internal data flow and component boundaries
│   └── adr/                   ← Architecture Decision Records (ADR-001 to ADR-006)
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

Or configure via `.streamlit/secrets.toml` for local Streamlit:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

### Run locally

```bash
# Terminal 1 — FastAPI backend
uv run uvicorn backend.api.main:app --reload --port 8000

# Terminal 2 — Streamlit frontend
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
   - Risk contribution breakdown (Plotly bar chart)
   - UCITS badges 🇪🇺 in the weights table
   - EU Investor Note banner
   - Stress Regime banner (visible only when correlations spike above 0.75)

4. **Markowitz Tab** — compare HRP allocation against the Mean-Variance benchmark.
   Includes efficient frontier chart and weight divergence table.

5. **Chat Advisor** — ask natural-language questions about your portfolio.
   Answers go through a 3-stage safety pipeline (input sanitiser → narrator →
   5-step validator) and always include an educational disclaimer.

See [`docs/user_guide.md`](docs/user_guide.md) for the complete user guide with
API examples and known limitations.

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
    {"feature": "investment_horizon", "importance": 0.41},
    {"feature": "risk_attitude",      "importance": 0.32},
    {"feature": "age",                "importance": 0.17}
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
  "weights": { "CSPX.L": 0.22, "EFA": 0.15, "AGGH.MI": 0.18 },
  "expected_volatility": 0.094,
  "sharpe_ratio": null,
  "risk_contributions": { "CSPX.L": 0.31, "EFA": 0.22 },
  "ucits_tickers_used": ["CSPX.L", "AGGH.MI", "XEON.MI"],
  "fallback_tickers_applied": [],
  "recommendation_id": "uuid-...",
  "market_data_hash": "sha256-..."
}
```

> Note: `expected_return` and `sharpe_ratio` are `null` by design for HRP — the algorithm
> does not require or produce reliable point estimates of forward returns. See ADR-001.

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
  "safe_text": "Given your moderate profile, the allocation reflects...\n\n[disclaimer]",
  "passed": true,
  "disclaimer_appended": false,
  "validator_flags": [],
  "injection_blocked": false,
  "api_error": false
}
```

---

## Technical Highlights

| Component | Technology | Notes |
|---|---|---|
| Risk Profiler ★ | scikit-learn GBM + SHAP | Trained on Fed SCF 2022 real data |
| LLM Narrator ★ | Claude API (Anthropic) | Narrator pattern — cannot invent numbers |
| LLM Validator | Custom 5-step pipeline | Forbidden phrases, hallucinated numbers, disclaimer, injection detection, EU Awareness Rule 9 |
| Portfolio Optimizer | PyPortfolioOpt HRP | Ledoit-Wolf shrinkage, guardrails 5–40% per asset, 10–60% per cluster |
| Regime Detector | Correlation threshold + VIX | avg\|ρ\| > 0.75 → HIGH_STRESS → ERC fallback |
| Data Layer | yfinance | ValidatedDataLoader with UCITS fallback + SHA-256 audit hash |
| Database | SQLite | Full audit trail (market hash, prompt hash, validator flags) |
| Frontend | Streamlit | EU Investor Note, stress banner, UCITS badges, HRP vs MV tabs |
| Backend API | FastAPI + slowapi | Rate limiting, API key auth |
| CI/CD | GitHub Actions | Lint + pytest + coverage + AI agent automated PR |
| Deployment | Streamlit Community Cloud | Live at [robo-advisor-usi.streamlit.app](https://robo-advisor-usi.streamlit.app) |

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

## AI Tools & Development Process

This project was developed as an explicitly **agentic project**, as required by the
course specification. AI tools were used throughout the development process and their
use is fully declared here and in [`AGENTS.md`](AGENTS.md).

| Tool | How we used it |
|---|---|
| **ChatGPT** | Initial brainstorming and explanation of financial concepts (HRP, MiFID II, SCF survey methodology) |
| **GitHub Copilot / Gemini** | Code comparison and alternative implementation suggestions during development |
| **Claude (Anthropic)** | Primary coding assistant and technical advisor across all weeks; also powers the Chat Advisor at runtime via the Claude API |

### AI Agent PR (GitHub Actions + Claude API)

The `agent_pr.yml` workflow demonstrates a full agentic loop: GitHub Actions triggers
→ Claude API generates docstrings for `backend/optimizer/` → changes committed to a
new branch → PR opened automatically. The PR URL is documented in `AGENTS.md` as
evidence for the course's AI agent criterion.

All AI-assisted contributions are visible in the commit history. The academic PDF
(Section 7: Lessons Learned) includes a full retrospective on the agentic workflow.

---

## Testing

```bash
# Run full test suite
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=backend --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_validator.py -v
```

CI runs `ruff` lint + `pytest` + coverage on every push and PR.
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
- Backtest results: GFC 2008, COVID 2020, rate hike 2022
- Limitations and failure modes
- Lessons learned from the agentic development process

🔗 **GitHub:** [https://github.com/Programming-for-finance-II/robo-advisor](https://github.com/Programming-for-finance-II/robo-advisor)
