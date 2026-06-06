# ADR-008: Per-Profile Guardrails for Risk-Appetite Differentiation

**Status:** Accepted
**Date:** 2026-06-06
**Author:** P2 (Quant/Optimizer)
**Supersedes:** ADR-001 § "Profile tilt (no γ in HRP)" and § "Post-optimisation guardrails"

---

## Context

Manual testing of the Streamlit dashboard revealed that the CONSERVATIVE,
MODERATE and AGGRESSIVE profiles produced **almost identical portfolios**. An
empirical reproduction on 482 trading days of real market data (yfinance, the
exact production code path) quantified the problem:

| Metric                  | CONSERVATIVE | MODERATE | AGGRESSIVE |
|-------------------------|:------------:|:--------:|:----------:|
| Equity (risk_assets)    | 10.2 %       | 10.4 %   | **10.0 %** |
| Expected volatility     | 3.65 %       | 3.67 %   | **3.63 %** |
| Cash (XEON.MI)          | 40.0 %       | 40.0 %   | 40.0 %     |

L1 weight distance between CONSERVATIVE and AGGRESSIVE was **0.037** on a 0–2
scale — i.e. effectively the same portfolio. Worse, the ordering was
**inverted**: AGGRESSIVE held *less* equity and *lower* volatility than
CONSERVATIVE. For a robo-advisor whose entire value proposition is mapping risk
appetite to an allocation, this is a fatal defect.

### Root causes

1. **The aggressive tilt pointed the wrong way.** ADR-001 tilted AGGRESSIVE
   toward **ERC (Equal Risk Contribution)** to "preserve philosophical
   consistency with HRP (no dependency on μ)." But ERC is a *risk-balancing*
   construction, not a risk-seeking one — it favours low-volatility assets to
   equalise risk contributions. Nothing in the pipeline ever asked for more
   equity. Empirically the ERC target held only ~2 pp more equity than the
   minimum-variance (CONSERVATIVE) target.

2. **The near-zero-vol cash ETF dominated the HRP base.** HRP's recursive
   bisection is inverse-variance, so XEON.MI (~3 % vol) received **59 % raw
   weight**, anchoring every profile to cash before any tilt was applied.

3. **A weak tilt and uniform box constraints erased what little remained.**
   `TILT_FACTOR = 0.3` diluted an already-tiny target difference, then the
   global guardrails (0.05–0.40 per asset, 0.10–0.60 per cluster) clipped every
   asset onto a shared boundary. With eight assets the 0.05 floors alone
   consume 40 % of the book.

The regression went undetected because the only differentiation test asserted
`max(|Δw|) > 1e-4` — a threshold so weak it passed on two identical boundary
portfolios.

---

## Decision

**Express risk appetite primarily through per-profile Strategic Asset
Allocation (SAA) bands, and secondarily through a μ-free directional tilt.**

This is the standard robo-advisor mechanism (Betterment, Wealthfront, and the
academic SAA literature): each risk profile is a band of cluster weights, and
the optimizer allocates *within* those bands.

### 1. Per-profile guardrails (the primary lever)

Each profile carries its own per-asset bounds and per-cluster `(min, max)`
bands (`PROFILE_CONSTRAINTS` in `hrp.py`):

| Cluster      | CONSERVATIVE | MODERATE    | AGGRESSIVE  |
|--------------|:------------:|:-----------:|:-----------:|
| risk_assets  | 0.05–0.25    | 0.20–0.45   | **0.45–0.75** |
| real_assets  | 0.05–0.20    | 0.05–0.25   | 0.05–0.25   |
| safe_haven   | 0.25–0.60    | 0.15–0.50   | 0.05–0.30   |
| cash         | 0.10–0.50    | 0.02–0.25   | 0.00–0.10   |

The equity **floor** for AGGRESSIVE and the cash **cap** are what guarantee
differentiation regardless of the (estimation-noisy) covariance structure.

### 2. μ-free directional tilt (secondary)

| Profile      | Tilt target                  | μ-free? |
|--------------|------------------------------|:-------:|
| CONSERVATIVE | minimum variance             | ✅ |
| MODERATE     | none (neutral HRP)           | ✅ |
| AGGRESSIVE   | volatility-proportional      | ✅ |

The AGGRESSIVE target weights each asset in proportion to its volatility — the
symmetric opposite of minimum variance — using only the covariance diagonal.
**Maximum-Sharpe was explicitly rejected** because it requires an estimate of
μ, which would contradict the central thesis of ADR-001 (HRP avoids the least
stable input in portfolio optimization). Keeping every target μ-free preserves
that thesis end-to-end.

`TILT_FACTOR` is raised to 0.5 (CONSERVATIVE) / 0.6 (AGGRESSIVE).

---

## Consequences

### Positive

Empirical result on the same 482-day real-data sample:

| Metric               | CONSERVATIVE | MODERATE | AGGRESSIVE |
|----------------------|:------------:|:--------:|:----------:|
| Equity (risk_assets) | 5.0 %        | 21.8 %   | **45.0 %** |
| Expected volatility  | 2.79 %       | 4.82 %   | **8.40 %** |
| Cash                 | 45.0 %       | 25.0 %   | 8.7 %      |

- L1 weight distance CONSERVATIVE↔AGGRESSIVE rose from **0.037 → 1.258**.
- Volatility is now **monotonic** in risk appetite (was inverted).
- The mechanism stays **μ-free**, consistent with ADR-001.
- Differentiation is **explainable**: each profile is a transparent SAA band,
  which the LLM narrator can describe in plain economic terms.

### Negative / Trade-offs

- The bands are **expert-set, not data-derived.** They encode a reasonable
  house view of risk budgeting rather than an output of the SCF model. This is
  documented in the Limitations section of the academic PDF.
- The iterative clip-and-renormalise projection is a heuristic, not a QP
  solution; `MAX_CONSTRAINT_ITER` was raised to 50 to ensure convergence under
  the tighter bands. Final weights are asserted to respect all bounds in tests.
- Because cluster floors bind, `solver_status` is typically `"clipped"` for
  CONSERVATIVE and AGGRESSIVE — expected and not an error condition.

---

## Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Keep ERC tilt, only widen bounds | Does not fix the root cause: ERC still never seeks risk; ordering could stay inverted |
| Max-Sharpe tilt for AGGRESSIVE | Reintroduces dependency on μ, contradicting ADR-001's core thesis |
| Single γ risk-aversion parameter | HRP has no μ and no natural γ; would require switching optimizer |
| Differentiate via tilt only (no bands) | Empirically too weak — the cash-dominated HRP base swamps any tilt |

---

## References

- López de Prado, M. (2016). *Building Diversified Portfolios that Outperform
  Out-of-Sample.* Journal of Portfolio Management.
- Ang, A. (2014). *Asset Management: A Systematic Approach to Factor Investing.*
  Oxford University Press — Ch. on Strategic Asset Allocation bands.
- ADR-001 — HRP over Markowitz (the no-μ thesis this ADR preserves).
- Design Document v3.1 — Section 2: Portfolio Optimization.
