# ADR-006 — Regime Detector: Dual-Signal Trigger and ERC Fallback

**Status:** Accepted  
**Date:** 2026-05-15  
**Owner:** Emma Erba 
**File:** `backend/optimizer/regime_detector.py`

---

## Context

The HRP optimizer relies on a Ledoit-Wolf shrinkage covariance matrix to
estimate asset correlations. During market stress episodes (e.g. COVID-19
March 2020, GFC 2008), pairwise correlations across equity, bond, and
alternative asset classes converge toward 1, collapsing the diversification
signal that HRP depends on. In this regime, the HRP allocation becomes
numerically unstable and economically misleading: the dendrogram clusters
cease to reflect genuine risk structure.

The system therefore requires a mechanism to:
1. detect when the correlation structure has broken down, and
2. substitute a minimum-assumption fallback allocation that remains
   defensible under crisis conditions.

---

## Decision

We implement a **dual-signal regime detector** (`detect_regime()`) that
classifies market conditions as `NORMAL` or `HIGH_STRESS` using two
independent triggers evaluated in OR logic:

### Signal 1 — Average Absolute Pairwise Correlation (Primary)

```
avg|ρ_LW| = mean of |ρ_ij| for all i ≠ j
            computed from the Ledoit-Wolf covariance matrix

Trigger: avg|ρ_LW| > STRESS_CORR_THRESHOLD = 0.75
```

**Rationale for 0.75:** Empirical literature on systemic risk
(Longin & Solnik, 2001; Ang & Bekaert, 2002) documents that cross-asset
correlations during equity drawdowns of ≥ 30% regularly exceed 0.70–0.80.
A threshold of 0.75 sits at the lower bound of this stress corridor,
triggering the fallback before correlation convergence is complete.
Crucially, this signal is computed from the same Ledoit-Wolf Σ already
present in the optimizer pipeline — no additional data source is required.

### Signal 2 — VIX Level (Secondary)

```
Trigger: VIX > STRESS_VIX_THRESHOLD = 30.0
```

**Rationale for 30.0:** VIX = 30 is a widely cited practitioner threshold
separating elevated uncertainty from systemic fear. Whaley (2009)
identifies 30 as the boundary above which VIX conveys genuine regime
information rather than normal volatility noise. CBOE's own classification
uses 20 (elevated) and 30 (extreme) as the two key cutoffs. The 30 level
also aligns with the historical VIX readings at the onset of the GFC
(Sep 2008), COVID (Mar 2020), and rate hike cycle (Nov 2022) — the three
backtest scenarios in this project.

**VIX is optional:** `vix_level=None` disables this signal, keeping the
detector functional when VIX data is unavailable (e.g. backtesting on
historical data without a VIX feed, or during yfinance outages).

### OR Combination Logic

```python
regime = "HIGH_STRESS" if (corr_triggered or vix_triggered) else "NORMAL"
```

The OR rule is intentionally conservative: a false positive (entering
fallback when not strictly necessary) is less costly than a false negative
(remaining in HRP during a genuine crisis). This asymmetry reflects the
asymmetric loss function of a risk-managed portfolio system.

---

## Fallback: ERC Cluster-Level Allocation

When `regime == HIGH_STRESS`, the optimizer substitutes the HRP weights
with an **Equal Risk Contribution (ERC) allocation at the cluster level**
(`get_erc_cluster_weights()`):

```
Step 1: Assign equal weight to each cluster  →  w_cluster = 1 / n_clusters
Step 2: Distribute equally within each cluster  →  w_asset = w_cluster / n_assets_in_cluster
Step 3: Clip to [ASSET_WEIGHT_MIN, ASSET_WEIGHT_MAX] = [0.05, 0.40]
Step 4: Renormalise to sum = 1.0
```

**Rationale:** ERC (Maillard, Roncalli & Teïletche, 2010) is the
minimum-assumption diversification strategy: it does not require an
estimate of expected returns, and its risk-balancing property is robust
when the covariance matrix is unreliable. By applying ERC at the cluster
level rather than the asset level, we preserve the four-cluster structure
defined in `universe_config.py` (Risk Assets, Real Assets, Safe Haven,
Cash), ensuring meaningful diversification even when all within-cluster
correlations are near 1.

The implementation delegates cluster membership to `universe_config.get_cluster_map()`,
maintaining the single-source-of-truth principle: cluster definitions live
in exactly one place.

---

## Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| VIX-only trigger | VIX is unavailable in some historical backtest windows; correlation signal is always computable from existing Σ_LW |
| Correlation-only trigger | VIX provides a forward-looking market sentiment signal that can precede correlation convergence by days; adding it reduces lag |
| Fixed threshold VIX = 20 | Too sensitive — fires during routine volatility episodes (e.g. earnings seasons), increasing unnecessary turnover |
| EWMA volatility trigger | Adds complexity with no clear advantage over correlation signal for this universe size (8 assets); deferred to future work |
| Full ERC (asset-level) with estimated Σ | Defeats the purpose: if Σ is unreliable, ERC using Σ inherits the same instability |
| Black-Litterman with stress views | Requires manual view specification per crisis; not automated; deferred to future work |

---

## Consequences

**Positive:**
- Automated protection against correlation convergence failures in HRP
- Two independent signals reduce both false negatives (missed crises) and false positives (unnecessary regime switches)
- ERC fallback is parameter-free given the existing cluster structure
- `RegimeResult` exposes `corr_triggered` and `vix_triggered` flags → audit trail and UI stress banner (P4 dependency)
- `vix_level=None` path keeps the detector functional in all backtest scenarios

**Negative / Limitations:**
- Threshold VIX = 30 was calibrated on US market conditions; may be less reliable for EU-specific stress episodes not correlated with US VIX
- No hysteresis: the detector can oscillate between regimes on consecutive days near the threshold (acknowledged as future work — rolling confirmation window)
- The 0.75 correlation threshold is not dynamically recalibrated; it is a fixed prior

---

## References

- Ang, A., Bekaert, G. (2002). *International Asset Allocation with Regime Shifts*. Review of Financial Studies, 15(4), 1137–1187.
- López de Prado, M. (2016). *Building Diversified Portfolios that Outperform Out of Sample*. Journal of Portfolio Management, 42(4), 59–69.
- Longin, F., Solnik, B. (2001). *Extreme Correlation of International Equity Markets*. Journal of Finance, 56(2), 649–676.
- Maillard, S., Roncalli, T., Teïletche, J. (2010). *The Properties of Equally Weighted Risk Contribution Portfolios*. Journal of Portfolio Management, 36(4), 60–70.
- Whaley, R.E. (2009). *Understanding the VIX*. Journal of Portfolio Management, 35(3), 98–105.
