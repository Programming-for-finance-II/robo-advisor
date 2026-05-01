# ADR-002 — SCF Preprocessing Choices

**Date:** 29 April 2026
**Author:** P3 — ML / Risk Profiling
**Status:** Accepted
**Branch:** feature/p3-scf-pipeline

---

## Context

The ML Risk Profiler component requires a real-world dataset to train the classifier. We selected the **Survey of Consumer Finances (SCF)** published by the Federal Reserve as our primary source. The SCF is a triennial survey on U.S. household finances — income, net worth, debt, and portfolio allocation behaviour — freely published by the Fed and widely used in academic literature (Grable & Lytton, 1999; Guiso et al., 2018).

This ADR documents three preprocessing decisions made before implementation, so that they are traceable and defensible in the academic PDF.

---

## Decision 1 — Dataset version: SCF 2022

**Problem:** the SCF is published every three years. Available versions include 2019, 2022, and earlier.

**Choice:** we use **SCF 2022** (Summary Extract Public Data, CSV, published October 2023).

**Rationale:** household financial behaviour changes over time — saving habits, risk propensity, portfolio composition. SCF 2022 is the most recent version available and reflects post-pandemic behaviour and the 2022 interest rate environment. Using the 2019 edition would introduce an unnecessary temporal lag when more recent data exists and is freely accessible.

**Acknowledged limitation:** SCF 2022 does not capture household behaviour after the Fed rate hikes of 2023–2025. Risk attitude in a high-rate regime may differ systematically from what was observed in 2022. This is identified as a limitation in the academic PDF.

---

## Decision 2 — Implicate: implicate = 1

**Problem:** the SCF uses **multiple imputation** to handle missing data. Respondents do not always fill in every field (income, net worth, etc.) and the Fed estimates missing values five times using different statistical techniques. The CSV file therefore contains 22,975 rows = 4,595 families × 5 implicates. The column `Y1` identifies the implicate (its last digit is 1, 2, 3, 4, or 5).

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| Use all 5 implicates (Rubin's Rules) | Statistically correct, reduces estimation error | 5× training runs, complex aggregation logic, out of scope |
| Use implicate = 1 only | Simple, ~4,595 observations sufficient for the model | Slight loss of statistical precision |

**Choice:** we use **implicate = 1** — the first imputation, ~4,595 rows.

**Rationale:** for an academic project of this scope, the complexity of handling 5 implicates with Rubin's Rules is not justified by the marginal gain in precision. 4,595 observations are sufficient to train a GBM robustly. The choice is consistent with standard academic practice for exploratory analyses on SCF data (cf. Fed SCF documentation).

**Acknowledged limitation:** using a single implicate introduces a slight underestimate of standard errors. Documented as a simplification in the academic PDF.

---

## Decision 3 — Feature selection

**Problem:** the SCF Summary Extract contains 357 columns. We need to select variables relevant to the profiler that correspond to information collectable via the user questionnaire.

**Selection criterion:** every SCF feature must have a direct counterpart in the user questionnaire (`docs/questionnaire_schema.md`). This ensures that at inference time the model receives inputs consistent with what it was trained on.

**Selected features:**

| SCF Column | Type | Questionnaire mapping |
|---|---|---|
| `AGE` | Demographic | Q1 — age |
| `INCOME` | Financial | Q2 — annual income |
| `NETWORTH` | Financial | Q3 — net worth |
| `WSAVED` | Behavioural | Q4 — saving propensity |
| `YESFINRISK` | Attitudinal | Q5 — willing to take financial risk (1=yes) |
| `NOFINRISK` | Attitudinal | Q5 — unwilling to take any risk (1=yes) |
| `KIDS` | Demographic | Q6 — number of children / dependants |
| `EDUC` | Demographic | Q7 — education level (proxy for financial experience) |

**Note:** the variable `RISKSCALE` (1–4 risk attitude scale) does not exist in the SCF 2022 Summary Extract. Risk attitude is instead encoded via the binary variables `YESFINRISK` and `NOFINRISK`, verified directly on file `SCFP2022.csv`.

**Allocation columns** (used to build labels via clustering, not as features):

| SCF Column | Content |
|---|---|
| `EQUITY` | Total value held in equity (stocks + equity mutual funds) |
| `BOND` | Total value held in bonds |
| `CASHLI` | Value held in cash and liquid assets |
| `STOCKS` | Direct stock holdings (subset of EQUITY) |

---

## Decision 4 — Sample weights: WGT mandatory

**Problem:** the SCF uses a stratified sampling design that deliberately over-samples high-net-worth households. These are rare in reality but control a disproportionate share of national wealth — the Fed over-samples them to produce accurate aggregate estimates. The `WGT` value of each row indicates how many real U.S. families that row represents (e.g. WGT = 3027.96 → that family represents ~3,028 real families).

**Consequence if ignored:** the ML model learns primarily from the behaviour of wealthy households, producing a profiler biased towards high-net-worth users. Most real users of the robo-advisor do not belong to this segment.

**Choice:** `WGT` is passed as `sample_weight` to the `.fit()` method of the GBM classifier and to K-Means / GMM for clustering.

**Rationale:** this is a necessary statistical correction for population representativeness. Ignoring it would produce a model that is not academically defensible. The Fed itself explicitly recommends using weights in any analysis on SCF data.

---

## Consequences and system impact

- `scf_pipeline.py` encodes these choices in the constants `SCF_IMPLICATE`, `SCF_FEATURE_COLUMNS`, `SCF_ALLOCATION_COLUMNS`, `SCF_WEIGHT_COLUMN`
- `clustering.py` (W2) receives `alloc` and `weights` from `build_pipeline()` and uses `WGT` in the fit
- `classifier.py` (W3) receives `X` and `weights` and passes `sample_weight=weights` to the GBM
- The limitations documented here (US-centrism, implicate=1, 2022 lag) feed into the "Limitations and Failure Modes" section of the LaTeX PDF

---

## References

- Federal Reserve (2022). *Survey of Consumer Finances — Codebook and Methodology.*
- Grable, J.E., Lytton, R.H. (1999). *Financial risk tolerance revisited.* Financial Services Review.
- Guiso, L., Sapienza, P., Zingales, L. (2018). *Time Varying Risk Aversion.* Journal of Financial Economics.
