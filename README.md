# AI-Powered Robo-Advisor Platform

> Educational robo-advisor prototype — USI Programming in Finance II (2026)

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/frontend-Streamlit-red)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-green)
[![CI](https://github.com/Programming-for-finance-II/robo-advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/Programming-for-finance-II/robo-advisor/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

An academic robo-advisor that classifies investor risk profiles with a
deterministic, MiFID II-aligned rule-based engine (Grable–Lytton, 1999),
complemented by a Gradient Boosting classifier trained and validated on real
household behaviour data (Fed SCF 2022, 94% cross-validated accuracy). It
optimises portfolios via Hierarchical Risk Parity (López de Prado, 2016), and
generates natural-language explanations through a constrained LLM narrator
(Claude API) that is mathematically prevented from inventing numbers.

**Course:** Programming in Finance II — Prof. P. Gruber — USI 2026

---

## Team

| Role | Name | Area |
|---|---|---|
| **P1** | Sabrina Virgillito | Backend / Data Engineering |
| **P2** | Emma Erba | Quant / Portfolio Optimization |
| **P3** | Matteo Buttiglieri | ML / Risk Profiling |
| **P4** | Elena Trombini | Frontend / LLM / Docs |

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
│   │   ├── profiler/          ← rule-based engine (live) + GBM trained on Fed SCF 2022
│   │   └── regime_detector.py
│   ├── optimizer/             ← HRP + Ledoit-Wolf + Markowitz benchmark
│   ├── llm/                   ← Claude API narrator + 5-step validator
│   ├── schemas/               ← Pydantic Ground Truth models + mock data
│   └── data/                  ← ValidatedDataLoader + UCITS fallback logic
├── frontend/
│   └── app.py                 ← Streamlit UI (questionnaire, dashboard, chat)
├── docs/
│   ├── user_guide.md          ← end-to-end user flow
│   ├── architecture.md        ← internal data flow and component boundaries
│   └── adr/                   ← Architecture Decision Records (ADR-001 to ADR-009)
└── tests/                     ← pytest unit + integration (≥80% coverage)
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

### Data Setup (SCF 2022 — required for ML pipeline)

The risk profiler is trained on the **Federal Reserve Survey of Consumer
Finances 2022** (public dataset, free download). The raw CSV is not stored
in this repository (~21 MB); follow these steps once after cloning:

**1. Download the SCF 2022 Summary Extract**

Go to the official Fed page:
```
https://www.federalreserve.gov/econres/scfindex.htm
```
Under the **2022** section, click  
**"Summary Extract Data (CSV)"** → download `SCFP2022s.zip`

Direct link (may change with future releases):
```
https://www.federalreserve.gov/econres/files/scfp2022s.zip
```

**2. Extract and place the file**

```bash
# from the repo root
mkdir -p data/scf
unzip ~/Downloads/SCFP2022s.zip -d /tmp/scf_extract
cp /tmp/scf_extract/SCFP2022.csv data/scf/scf2022.csv
```

Expected result:
```
data/scf/scf2022.csv   (~21 MB, 22 976 rows × 357 columns)
```

**3. Verify**

```bash
python - <<'EOF'
import pandas as pd
df = pd.read_csv("data/scf/scf2022.csv", nrows=5)
assert "Y1" in df.columns and "AGE" in df.columns, "Wrong file!"
print(f"OK — {len(pd.read_csv('data/scf/scf2022.csv'))} rows loaded")
EOF
```

**4. Run the ML pipeline** (optional — pre-built artifacts already in repo)

```bash
# Step 1 — cluster SCF households → data/scf/scf_labeled.parquet
python -m backend.ml.profiler.clustering

# Step 2 — train GBM → data/scf/gbm_model.pkl
python -m backend.ml.profiler.classifier
```

> **Note:** `data/scf/scf_labeled.parquet` (161 KB) and
> `data/scf/gbm_model.pkl` (950 KB) are already committed to this repo.
> Steps 1–2 above are only needed if you want to retrain from scratch.
> All tests run without the CSV (integration tests are auto-skipped when
> the file is absent).

---

### Environment Variables

The project needs two environment variables. Copy the example file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | Powers the LLM Narrator (`/advice` endpoint). Get one at [console.anthropic.com](https://console.anthropic.com/settings/keys). |
| `API_KEY` | No | Protects all API endpoints with an `X-API-Key` header. If left empty, auth is disabled (dev mode). Generate with `openssl rand -hex 32`. |

> **Never commit your `.env` file.** It is already listed in `.gitignore`.

---

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

The app has six pages, reachable from the top navigation bar:
**Questionnaire · Portfolio Dashboard · Compare Markowitz · Chat Advisor · Backtesting · Settings.**

1. **Questionnaire** — answer 10 risk profiling questions (Grable-Lytton scale, 1999).
   Q7 ("safety net money") triggers a MiFID II hard override to CONSERVATIVE
   regardless of other answers. On submission you immediately see your
   **investor profile** (`CONSERVATIVE` / `MODERATE` / `AGGRESSIVE`) with a model
   confidence score and the model's top behavioural drivers, shown as
   feature-importance scores.

2. **Portfolio Dashboard** — explore your HRP-optimised portfolio with:
   - Allocation donut chart with tickers and weights
   - Cluster grouping view (how your money is grouped) and HRP methodology cards
   - Key metrics cards (expected return, volatility, Sharpe, max drawdown)
   - Risk contribution breakdown (Plotly bar chart)
   - UCITS eligibility shown in the HRP-vs-Markowitz comparison table and the ETF Explorer 
   - EU Investor Note banner and Stress Regime banner (shown only when
     correlations spike above 0.75)
   - **ETF Explorer** — price chart, TER/AUM, ESG scores and analyst consensus
     for all 8 ETFs

3. **Compare Markowitz** — a deep-dive page comparing HRP against the
   Mean-Variance benchmark across three sections: a side-by-side metrics
   scorecard with a one-line data-driven verdict, a risk-contribution
   breakdown showing how each asset's share of total risk differs between
   the two methods, and an asset-correlation heatmap. A collapsible card
   explains the academic context of the comparison.

4. **Chat Advisor** — ask natural-language questions about your portfolio.
   Answers go through a 3-stage safety pipeline (input sanitiser → narrator →
   5-step validator) and always include an educational disclaimer.

5. **Backtesting** — replay each strategy on real historical prices across
   seven historical episodes (GFC 2008, Eurozone Debt Crisis 2011,
   Rate-Fear Selloff 2018, COVID-19 Crash 2020, Post-COVID Bull 2021,
   Ukraine Invasion Shock 2022, Rate Hike Cycle 2022), comparing HRP vs
   Mean-Variance (MV) vs equal-weight (1/N).

6. **Settings** — switch between **Dark and Light theme** (instant, no restart),
   and view the data source and about information.

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
  "expected_return": 0.061,
  "expected_volatility": 0.094,
  "sharpe_ratio": 0.65,
  "risk_contributions": { "CSPX.L": 0.31, "EFA": 0.22 },
  "optimizer_version": "hrp_v1",
  "solver_status": "optimal",
  "ucits_tickers_used": ["CSPX.L", "AGGH.MI", "XEON.MI"],
  "fallback_tickers_applied": [],
  "recommendation_id": "uuid-...",
  "market_data_hash": "sha256-..."
}
```

> Note: HRP does not rely on forward-return estimates to build the weights;
> `expected_return` and `sharpe_ratio` are reported ex-post from the loaded price
> history for comparability with the Mean-Variance benchmark. See ADR-001.

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
| Risk Profiler ★ | Rule-based engine + scikit-learn Gradient Boosting + SHAP | Grable–Lytton scoring (live); GBM trained & validated on Fed SCF 2022 |
| LLM Narrator ★ | Claude API (Anthropic) | Narrator pattern — cannot invent numbers |
| LLM Validator | Custom 5-step pipeline | Forbidden phrases, hallucinated numbers, disclaimer, injection detection, EU Awareness Rule 9 |
| Portfolio Optimizer | PyPortfolioOpt HRP | Ledoit-Wolf shrinkage, guardrails 5–40% per asset, 10–60% per cluster |
| Regime Detector | Correlation threshold + VIX | avg\|ρ\| > 0.75 → HIGH_STRESS flag + investor banner |
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
- UCITS eligibility is surfaced in the HRP-vs-Markowitz comparison table, the ETF Explorer, and a UCITS Coverage metric

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
(see the *Lessons Learned* section) includes a full retrospective on the agentic workflow.

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
Coverage target: ≥80% on backend modules.

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
- Backtest results: six historical episodes (GFC 2008, Eurozone 2011, Selloff 2018, COVID 2020, Bull 2021, Rate Hike 2022)
- Limitations and failure modes
- Lessons learned from the agentic development process

🔗 **GitHub:** [https://github.com/Programming-for-finance-II/robo-advisor](https://github.com/Programming-for-finance-II/robo-advisor)
