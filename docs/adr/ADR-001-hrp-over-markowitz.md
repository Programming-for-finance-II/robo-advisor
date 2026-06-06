# ADR-001: HRP over Markowitz as Default Portfolio Optimizer

**Status:** Accepted  
**Date:** 2026-04-27  
**Author:** P2 (Quant/Optimizer) — reviewed by P4  
**Supersedes:** Design v1.0 (Markowitz-based)

---

## Context

The initial design used Mean-Variance Optimization (Markowitz, 1952) as the
portfolio construction engine. A design review identified three structural
weaknesses that motivated a pivot:

1. **Markowitz is an error maximizer.** The optimizer requires inverting the
   covariance matrix Σ. Matrix inversion amplifies estimation errors on
   off-diagonal elements exponentially. With 8 assets and ~1,260 daily
   observations, these errors are not negligible and systematically produce
   unstable, concentrated portfolios.

2. **Dependency on expected returns μ.** Markowitz requires an estimate of
   forward-looking returns. μ is the least stable input in portfolio
   optimization — small changes in μ produce large swings in weights. For an
   educational prototype using historical data, this dependency introduces
   misleading precision.

3. **Corner solutions.** Unconstrained Markowitz frequently allocates 100% to
   one or two assets, which is pedagogically counterproductive for a tool
   designed to demonstrate diversification.

---

## Decision

**Use Hierarchical Risk Parity (HRP, López de Prado 2016) as the default
optimizer. Retain Markowitz as a benchmark tab for educational comparison.**

HRP resolves all three issues structurally:

- It never inverts Σ → numerically stable by construction
- It requires no estimate of μ → eliminates the most unstable input
- It produces diversified portfolios by design → no corner solutions

### Algorithm (three phases)

```
Phase 1 — Tree Clustering
  Distance matrix:  D(i,j) = sqrt(0.5 · (1 − ρ_LW(i,j)))
  Hierarchical linkage: Ward (minimises intra-cluster variance)
  Output: dendrogram

Phase 2 — Quasi-Diagonalisation
  Reorder Σ according to dendrogram leaf order
  Correlated assets become adjacent → quasi-diagonal blocks

Phase 3 — Recursive Bisection
  Split dendrogram into two sub-clusters
  Assign weights inversely proportional to cluster variance
  Recurse to individual assets
```

### Ledoit-Wolf shrinkage (mandatory pre-processing)

Before HRP, the empirical covariance matrix Σ is shrunk using the
Ledoit-Wolf Oracle Approximation:

```
Σ_LW = (1 − α) · Σ_empirical + α · Σ_target
```

where `Σ_target` is the scaled identity matrix and `α` is estimated
analytically. This stabilises the distance matrix D that drives clustering,
reducing portfolio turnover between rebalancing dates.

**Why shrink before HRP and not after?** The distance matrix D depends on ρ,
which depends on Σ. A noisy Σ produces a noisy D, which causes unstable
clustering. Shrinking Σ first means the dendrogram structure is stable across
rebalancing dates — directly reducing turnover.

### Linkage method: Ward (default)

| Method   | Pros                          | Cons                    | Use |
|----------|-------------------------------|-------------------------|-----|
| Single   | Fast                          | Chaining effect         | No  |
| Complete | Compact clusters              | Sensitive to outliers   | No  |
| Average  | Robust                        | Less interpretable      | Alt |
| **Ward** | **Minimises intra-cluster variance** | **Slightly slower** | **Default** |

### Profile tilt (no γ in HRP)

> **⚠️ Superseded by [ADR-008](ADR-008-profile-differentiation.md).** The ERC
> aggressive tilt and uniform guardrails described below were found to produce
> nearly identical portfolios across all three profiles (L1 distance 0.037,
> with volatility *inverted*). ADR-008 replaces this with per-profile SAA bands
> and a μ-free risk-seeking tilt. The no-μ principle is preserved. This section
> is retained for historical context.

Since HRP has no explicit risk-aversion parameter γ, a profile-dependent
tilt is applied post-optimisation:

| Profile      | Formula                      | Rationale |
|--------------|------------------------------|-----------|
| Conservative | `0.7·w_HRP + 0.3·w_MinVar`  | MinVar reduces absolute variance |
| Balanced     | `w_HRP`                      | HRP already balances risk contributions |
| Aggressive   | `0.7·w_HRP + 0.3·w_ERC`     | ERC distributes risk equally without μ |

Note: the aggressive tilt uses ERC (Equal Risk Contribution), not Max Sharpe,
to preserve philosophical consistency with HRP (no dependency on μ).

### Post-optimisation guardrails

HRP raw weights can be extreme in low-correlation regimes. Two guardrail
levels are applied after optimisation:

```
Asset level:   0.03 ≤ w_i ≤ 0.40
Cluster level: 0.10 ≤ w_cluster ≤ 0.60
```

After clipping: renormalise so weights sum to 1.0. Log clipped assets in
`portfolio.clipped_assets` for audit trail and LLM narrator transparency.

---

## Consequences

### Positive

- **Robustness:** HRP is structurally more stable than Markowitz for small
  sample sizes. Out-of-sample performance is superior to both Markowitz and
  1/N (López de Prado, 2016; Raffinot, 2017).
- **Educational value:** showing HRP vs Markowitz side-by-side in the
  Portfolio Dashboard makes the diversification benefit visible and concrete.
- **No μ required:** `expected_annual_return` and `sharpe_ratio` are
  deliberately `null` in the Ground Truth JSON — HRP does not produce
  reliable point estimates of forward returns. This is honest and
  academically defensible.
- **Audit trail:** `market_data_hash` + `optimizer_version` in the DB
  guarantee bit-for-bit reproducibility of every recommendation.

### Negative / Trade-offs

- **Narrative opacity:** the recursive bisection step is harder to explain
  to a non-technical user than "allocate more to assets with higher
  expected Sharpe." Mitigated by: (a) the LLM narrator explaining cluster
  structure in economic terms, (b) the HRP vs Markowitz comparison tab.
- **No expected return:** the absence of μ means we cannot show a
  risk/return frontier. This is a deliberate design choice, not a
  limitation to hide. It is documented in the Limitations section of the
  academic PDF.

---

## Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Markowitz with shrinkage | Still requires μ; corner solutions persist with tight constraints |
| Equal Weight (1/N) | No risk awareness; not defensible as "advanced" for grading |
| Black-Litterman | Requires prior views on μ — introduces subjectivity without SCF support |
| Risk Parity (ERC only) | Less flexible than HRP; ignores correlation structure |

---

## References

- López de Prado, M. (2016). *Building Diversified Portfolios that Outperform
  Out-of-Sample.* Journal of Portfolio Management.
- Raffinot, T. (2017). *Hierarchical Clustering-Based Asset Allocation.*
  Journal of Portfolio Management.
- Ledoit, O., Wolf, M. (2004). *A well-conditioned estimator for
  large-dimensional covariance matrices.* Journal of Multivariate Analysis.
- Design Document v3.1 — Section 2: Portfolio Optimization.