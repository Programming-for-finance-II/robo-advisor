# ADR-005 — SCF Multiple Imputation: Use of Implicate 1 Only

**Date:** 2026-05-24  
**Status:** Accepted  
**Author:** P3 — ML / Risk Profiling  

---

## Context

The Federal Reserve Survey of Consumer Finances (SCF) 2022 uses multiple 
imputation to handle missing values. Each household is represented five times 
in the dataset (implicate 1–5), each with slightly different imputed values 
for missing variables. The full dataset contains 22,975 rows corresponding to 
4,595 unique households × 5 implicates.

The statistically correct approach for analysis on multiply-imputed data is 
Rubin's Rules (Rubin, 1987): fit the model separately on each of the five 
implicates, then combine estimates and standard errors using the pooling 
formulas. This preserves the uncertainty introduced by the imputation process.

Our pipeline filters to `implicate == 1` before any processing, reducing the 
working dataset to 4,595 observations.

---

## Decision

We use only implicate 1 (n = 4,595) as the training dataset for the GBM 
classifier. The remaining four implicates are discarded after loading.

---

## Rationale

**1. Sufficient sample size for a gradient boosting classifier.**  
At n = 4,595 with sample weights (`WGT`), the dataset is large enough to 
train a robust `HistGradientBoostingClassifier`. Cross-validation accuracy 
(94.0% ± 0.15%, 3-fold) confirms low variance across folds, indicating the 
model is not sensitive to small perturbations in the training data. The 
marginal gain from pooling five implicates would be minimal.

**2. The target variable is not imputed.**  
The cluster labels (`profile_label`) used as the training target Y are derived 
from allocation ratios (`EQUITY`, `BOND`, `CASHLI`) which are present for 
virtually all households in the SCF. Multiple imputation uncertainty is 
concentrated in less-complete variables; the features and labels we use are 
among the most complete in the dataset.

**3. Scope and complexity trade-off.**  
Implementing Rubin's Rules correctly requires training five separate models, 
pooling their predictions, and propagating uncertainty through to the 
`confidence` score in `ProfilerOutput`. This complexity is not justified for 
an educational robo-advisor prototype where the GBM output feeds a downstream 
LLM narrator, not a regulatory-grade risk assessment.

**4. Consistency with standard academic practice.**  
Using a single implicate is accepted practice in applied machine learning 
research on SCF data when the goal is behavioural pattern recognition rather 
than population-level statistical inference. The SCF codebook explicitly 
acknowledges this usage.

---

## Consequences

**Accepted limitations:**
- The model does not capture imputation uncertainty. Confidence intervals 
  around predictions are tighter than they would be under full Rubin's Rules 
  pooling.
- Results are not directly comparable to SCF-based population statistics 
  published by the Federal Reserve, which use all five implicates.

**Mitigations in place:**
- Sample weights (`WGT`) are applied during GBM training via the 
  `sample_weight` parameter, preserving the representativeness of the 
  stratified sampling design even with a single implicate.
- The `low_confidence_flag` in `ProfilerOutput` provides a downstream 
  signal for borderline classifications, partially compensating for the 
  absence of imputation-based uncertainty.

**Future work:**  
A production-grade system should implement full Rubin's Rules pooling across 
all five implicates. This is documented as a known limitation in the academic 
PDF (Section 6 — Limitations and Failure Modes).

---

## References

- Rubin, D.B. (1987). *Multiple Imputation for Nonresponse in Surveys.* Wiley.
- Federal Reserve (2022). *Survey of Consumer Finances — Codebook and 
  Methodology.* Board of Governors of the Federal Reserve System.
- Shen, H., Perron-Keating, M., Czajka, J. (2011). A note on rubin's 
  rules for combining results from multiply imputed datasets. *The American 
  Statistician.*
