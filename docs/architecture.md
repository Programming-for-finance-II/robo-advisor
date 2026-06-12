# Architecture — Internal Design Notes

> For installation, usage, endpoint examples, and project structure, see `README.md`.  
> This document focuses only on internal data flows, component boundaries, and architecture decisions.

---

## 1. Core Architecture Principle

The backend owns all financial calculations.

The LLM is never allowed to compute portfolio weights, risk metrics, returns, or regulatory conclusions. Its role is limited to explaining backend-generated outputs in natural language.

This separation is the main safety principle of the platform:

```text
Backend   = calculator and source of truth
LLM       = constrained narrator
Validator = safety gate
Frontend  = presentation layer
```

---

## 2. End-to-End Data Flow

```text
Questionnaire answers
        │
        ▼
POST /profile
        │
        ├──► Rule-based profiler fallback
        └──► GBM Classifier trained on SCF 2022
                 └──► SHAP top_drivers
        │
        ▼
profile_label + confidence
        │
        ▼
POST /optimize
        │
        ├──► ValidatedDataLoader
        │        ├── market data download
        │        ├── UCITS-first tickers
        │        ├── US fallback if needed
        │        └── market_data_hash
        │
        ├──► Ledoit-Wolf covariance shrinkage
        ├──► HRP optimizer
        ├──► profile-specific tilt
        ├──► asset and cluster guardrails
        └──► regime detector
                 └── if avg pairwise correlation > 0.75 or VIX > 30:
                         flag HIGH_STRESS → show warning banner
                         (ERC fallback available, not auto-applied)
        │
        ▼
Ground Truth JSON
        │
        ▼
POST /advice
        │
        ▼
LLM Narrator
        │
        ├── narrator, not calculator
        ├── allowed_numbers from Ground Truth JSON
        └── regulatory_context for EU Awareness
        │
        ▼
5-step Validator
        │
        ├── forbidden phrases check
        ├── number hallucination check
        ├── disclaimer check
        ├── prompt injection detection
        └── EU Awareness (Rule 9) consistency
        │
        ▼
Validated response
        │
        ▼
Streamlit UI
```

---

## 3. Component Boundaries

The architecture follows strict module boundaries:

| Component | Owns | Must not do |
|---|---|---|
| Frontend | UI, charts, user interaction | Compute financial results |
| Backend API | Request routing, orchestration | Invent business logic outside modules |
| Profiler | Risk profile classification | Optimize portfolios |
| Optimizer | Portfolio weights and risk metrics | Generate natural-language advice |
| LLM Narrator | Explanation of existing results | Create new numbers or recommendations |
| Validator | Safety checks before display | Modify portfolio calculations |
| Database | Audit trail and reproducibility | Replace source calculations |

These boundaries are important for maintainability, testing, and LLM safety.

---

## 4. Ground Truth JSON Principle

Before every LLM call, the backend creates a Ground Truth JSON.

This object contains the only information that the LLM is allowed to discuss:

- investor profile;
- confidence score;
- portfolio weights;
- risk metrics;
- cluster structure;
- stress scenarios;
- UCITS and currency-risk context;
- allowed numerical values;
- forbidden phrases;
- required disclaimer.

The LLM may only narrate numbers that appear in `allowed_numbers`.

The validator rejects responses that contain numerical claims outside the Ground Truth JSON.

This makes hallucination structurally constrained rather than only prompt-dependent.

---

## 5. LLM Safety Pipeline

```text
User question
     │
     ▼
Sanitization
     │
     ▼
Ground Truth JSON injection
     │
     ▼
Claude narrator response
     │
     ▼
Validator
     │
     ├── forbidden financial advice language
     ├── invented number detection
     ├── missing disclaimer detection
     └── EU Awareness consistency
     │
     ▼
Safe response or fallback message
```

The LLM layer is therefore not trusted by default. Every response must pass validation before reaching the frontend.

---

## 6. Failure Modes and Fallbacks

| Failure mode | Handling |
|---|---|
| UCITS ticker unavailable | Use US-listed fallback and log it |
| Too many missing market values | Raise data quality error or use last valid snapshot |
| High correlation regime | Flag HIGH_STRESS and show an investor warning banner (ERC fallback available, not auto-applied) |
| Low profiler confidence | Use rule-based fallback or clarification questions |
| LLM invents numbers | Block response and retry or fallback |
| LLM uses forbidden advice language | Block response |
| Disclaimer missing | Append or reject depending on validator result |

---

## 7. Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](adr/ADR-001-hrp-over-markowitz.md) | HRP over Markowitz as default optimizer | Accepted |
| [ADR-002](adr/ADR-002-scf-preprocessing.md) | SCF preprocessing choices | Accepted |
| [ADR-003](adr/ADR-003-cloud-deploy.md) | Cloud deployment strategy (Streamlit Cloud vs Railway) | Accepted |
| [ADR-004](adr/ADR-004-llm-narrator-validator.md) | LLM as narrator only — Ground Truth JSON + Validator | Accepted |
| [ADR-005](adr/ADR-005-db-schema.md) | Database schema and audit trail design | Accepted |
| [ADR-006](adr/ADR-006-regime-detector.md) | Regime detector — dual-signal trigger and ERC fallback | Accepted |
| [ADR-007](adr/ADR-007-ledoit-wolf-shrinkage.md) | Ledoit-Wolf shrinkage as mandatory covariance pre-processing | Accepted |
| [ADR-008](adr/ADR-008-profile-differentiation.md) | Per-profile guardrails for risk-appetite differentiation | Accepted |
| [ADR-009](adr/ADR-009-scf-implicate-choice.md) | SCF multiple imputation — use of implicate 1 only | Accepted |

---

## 8. Notes for AI Agents

AI agents should respect the component boundaries above.

Examples:

- a documentation agent may update README, architecture notes, or ADRs;
- a test-generation agent may add tests without changing business logic;
- a code-review agent may suggest improvements but should not silently alter financial assumptions;
- an LLM-safety agent should focus on prompts, validator checks, and forbidden phrases.

Any change to portfolio logic, profiling logic, or LLM safety rules should be documented through an ADR.