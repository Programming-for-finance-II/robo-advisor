# ADR-007 — Ledoit-Wolf Shrinkage as Mandatory Covariance Pre-Processing

**Status:** Accepted
**Date:** 2026-05-20
**Owner:** Emma Erba
**File:** `backend/optimizer/hrp.py`

---

## Context

Hierarchical Risk Parity (HRP) constructs a portfolio by clustering assets
according to a distance matrix derived from pairwise correlations:

```
D(i,j) = sqrt(0.5 · (1 − ρ_ij))
```

The quality of the clustering — and therefore the stability of the resulting
portfolio weights — depends directly on the quality of the correlation
estimate `ρ_ij`. If the covariance matrix `Σ` is noisy, the distance matrix
`D` is noisy, and the dendrogram structure changes erratically between
rebalancing dates, producing high portfolio turnover and unpredictable
weight allocations.

The standard estimator for `Σ` is the sample covariance matrix `S`:

```
S = (1 / (T-1)) · Xᵀ X,   X = matrix of demeaned returns
```

`S` is known to be a poor estimator when the number of assets `n` is not
negligible relative to the number of observations `T`. In our setting:

- `n = 8` assets
- `T ≈ 252` trading days (one year of daily returns)
- ratio `n/T ≈ 0.032`

While this ratio is modest, the Marčenko-Pastur law (1967) shows that even
at low `n/T`, the extreme eigenvalues of `S` are systematically biased
upward (largest eigenvalue) and downward (smallest eigenvalue). This
produces a condition number much higher than the true matrix, making `S`
ill-conditioned and causing instability in the distance metric `D`.

---

## Decision

We apply **Ledoit-Wolf Oracle Approximating Shrinkage** to the sample
covariance matrix before every HRP optimisation call. The shrinkage
estimator is:

```
Σ_LW = (1 − α) · S + α · μ_S · I
```

where:
- `S` is the sample covariance matrix
- `μ_S = (1/n) · tr(S)` is the average eigenvalue (trace / n)
- `I` is the identity matrix
- `α ∈ [0, 1]` is the shrinkage intensity, estimated analytically

The target `μ_S · I` is a scaled identity matrix, which embeds the
maximum-ignorance prior: all assets have equal variance and zero
pairwise correlation. The convex combination with `S` pulls the extreme
eigenvalues toward their true values, reducing estimation error.

### Why Ledoit-Wolf specifically

The Ledoit-Wolf (2004) estimator has three properties that make it
suitable for this context:

1. **Analytical shrinkage intensity.** `α` is estimated from a closed-form
   formula — no cross-validation, no hyperparameter tuning. This is
   important for a production system that must reestimate `Σ` at every
   monthly rebalancing date without manual intervention.

2. **Asymptotically optimal.** Under the Frobenius loss function, the
   Ledoit-Wolf estimator minimises the expected squared distance between
   `Σ_LW` and the true covariance matrix, over all linear combinations
   of `S` and `μ_S · I`.

3. **Sklearn implementation.** `sklearn.covariance.LedoitWolf` provides a
   well-tested, production-grade implementation with `assume_centered=False`,
   applied directly to the return matrix without requiring the caller to
   pre-demean the data.

### Why shrink before HRP, not after

The distance matrix `D` is computed from the correlation matrix `ρ`, which
is derived from `Σ`. If we apply HRP to the raw sample covariance `S`, the
noisy correlations propagate into `D`, producing an unstable dendrogram.

Shrinking `Σ` before computing `D` stabilises the correlation structure
that drives clustering. This directly reduces the variance of portfolio
weights across rebalancing dates, lowering turnover and transaction costs.
Applying shrinkage after HRP (e.g. to smooth weights) would not address
the root cause of instability.

### Implementation

```python
from sklearn.covariance import LedoitWolf

lw = LedoitWolf(assume_centered=False)
lw.fit(log_returns)          # log_returns: shape (T, n)
cov_lw = pd.DataFrame(
    lw.covariance_,
    index=tickers,
    columns=tickers,
)
```

`log_returns` is the matrix of daily log-returns computed from the
validated price series returned by `ValidatedDataLoader`. The resulting
`cov_lw` DataFrame is passed to both `hrp.py` (distance matrix) and
`regime_detector.py` (average pairwise correlation check).

---

## Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Sample covariance `S` (no shrinkage) | Ill-conditioned; produces unstable dendrogram and high turnover; formally penalised in project requirements |
| Oracle Approximating Shrinkage (OAS) | Also provided by sklearn; slightly better at very high `n/T`; at `n/T ≈ 0.03` the difference from LW is negligible — LW chosen for widespread citation and interpretability |
| Ledoit-Wolf (2004) analytical formula vs Wolf-Ledoit (2022) nonlinear | Nonlinear shrinkage is more accurate for large `n`; at `n=8` the added complexity is unwarranted |
| EWMA covariance (half-life 60 days) | More responsive to recent data; introduces an additional hyperparameter (half-life); deferred to future work (cited in P2 Nice-to-Have list) |
| Factor model (PCA-based) | Reduces dimensionality; interpretable factors; not justified for `n=8` assets where all factors are retained anyway |
| Constant Correlation Model | Assumes all pairwise correlations equal their cross-sectional average; too restrictive for a multi-asset universe with four structurally distinct clusters |

---

## Consequences

**Positive:**
- Stable distance matrix `D` across rebalancing dates → lower turnover
- Regime detector uses the same `Σ_LW` → single covariance computation per
  rebalancing cycle (no duplicate estimation)
- Analytically estimated `α` → no tuning required, fully automated
- Satisfies the mandatory project requirement: *"Ledoit-Wolf shrinkage
  on Σ is a P0 deliverable; absence results in grade penalty"*

**Negative / Limitations:**
- Shrinkage target `μ_S · I` assumes equal variances; assets with very
  different volatility regimes (e.g. XEON.MI cash vs VNQ REIT) may be
  over-shrunk. Mitigated by normalising returns before estimation.
- `α` is estimated from the same sample used to compute `S`; in very
  short windows (< 60 days) the estimate may itself be noisy. The backtest
  enforces a minimum lookback of 60 days before any rebalancing event.
- Ledoit-Wolf does not model time-varying correlations. EWMA shrinkage
  (future work) would address this limitation.

---

## References

- Ledoit, O., Wolf, M. (2004). *A Well-Conditioned Estimator for
  Large-Dimensional Covariance Matrices.* Journal of Multivariate Analysis,
  88(2), 365–411.
- Marčenko, V.A., Pastur, L.A. (1967). *Distribution of Eigenvalues for
  Some Sets of Random Matrices.* Mathematics of the USSR-Sbornik, 1(4),
  457–483.
- López de Prado, M. (2016). *Building Diversified Portfolios that
  Outperform Out-of-Sample.* Journal of Portfolio Management, 42(4), 59–69.
- Scikit-learn documentation: `sklearn.covariance.LedoitWolf`.
  https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html
