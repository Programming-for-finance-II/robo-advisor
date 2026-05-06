from __future__ import annotations

from typing import Literal, TypedDict

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, expected_returns
from pypfopt import CovarianceShrinkage

from backend.optimizer.hrp import OptimizationResult, OPTIMIZER_VERSION
from backend.optimizer.risk_metrics import compute_risk_contributions
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Asset-level weight bounds — same guardrails as HRP for fair comparison
MV_ASSET_MIN: float = 0.03
MV_ASSET_MAX: float = 0.40

# Risk-free rate for Sharpe computation (annualised, approximate EUR rate 2024)
RISK_FREE_RATE: float = 0.03

# Return estimation method — historical mean log returns, annualised
RETURNS_FREQUENCY: int = 252


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def optimize_markowitz(
    prices: pd.DataFrame,
    ucits_tickers: list[str] | None = None,
    fallback_tickers: list[str] | None = None,
) -> OptimizationResult:
    """
    Run Max Sharpe Mean-Variance optimisation as the HRP benchmark.

    Uses Ledoit-Wolf shrinkage on the covariance matrix (same as HRP)
    to ensure a fair comparison: the only difference is the optimisation
    algorithm, not the input data quality.

    Expected returns are estimated via historical mean log returns.
    This is the standard academic approach and is explicitly documented
    as a limitation in the PDF (mu instability — Michaud 1989).

    Args:
        prices:          Cleaned adjusted close prices from ValidatedDataLoader.
        ucits_tickers:   UCITS tickers in use (for audit trail).
        fallback_tickers: Fallback tickers applied (for audit trail).

    Returns:
        OptimizationResult with algorithm="MV".
        Note: expected_return and sharpe_ratio are populated here
        (unlike HRP where they are null), because MV explicitly uses mu.
    """
    assert not prices.empty, "prices DataFrame is empty"
    assert prices.shape[1] >= 2, "need at least 2 assets"

    # ── Step 1: Estimate inputs ──────────────────────────────────────────
    # Ledoit-Wolf shrinkage
    cov: pd.DataFrame = CovarianceShrinkage(prices).ledoit_wolf()

    # Historical mean log returns, annualised
    # Acknowledged limitation: mu is highly unstable out-of-sample
    mu: pd.Series = expected_returns.mean_historical_return(
        prices,
        returns_data=False,
        frequency=RETURNS_FREQUENCY,
        log_returns=True,
    )

    # ── Step 2: Max Sharpe optimisation ──────────────────────────────────
    ef = EfficientFrontier(
        mu,
        cov,
        weight_bounds=(MV_ASSET_MIN, MV_ASSET_MAX),
    )

    try:
        ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
        solver_status: Literal["optimal", "clipped", "fallback_erc"] = "optimal"
    except Exception:
        # Fallback: if Max Sharpe fails (e.g. no feasible solution),
        # use Min Volatility — always feasible with box constraints
        ef = EfficientFrontier(
            mu,
            cov,
            weight_bounds=(MV_ASSET_MIN, MV_ASSET_MAX),
        )
        ef.min_volatility()
        solver_status = "clipped"

    weights_raw = ef.clean_weights()
    # clean_weights() may produce small negatives due to solver precision
    # Clip and renormalise to ensure valid weights
    w_series = pd.Series(weights_raw).clip(lower=0.0)
    w_series = w_series / w_series.sum()
    final_weights: dict[str, float] = {
        t: round(float(v), 6) for t, v in w_series.items()
    }

    # ── Step 3: Performance metrics ──────────────────────────────────────
    tickers = list(cov.columns)
    w_vec = np.array([final_weights[t] for t in tickers])

    # Annualised volatility
    daily_var = float(w_vec @ cov.values @ w_vec)
    ann_vol = float(np.sqrt(daily_var * RETURNS_FREQUENCY))

    # Expected return and Sharpe (populated for MV — unlike HRP)
    exp_ret = float(mu.values @ w_vec)
    sharpe = (exp_ret - RISK_FREE_RATE) / ann_vol if ann_vol > 0 else 0.0

    # Risk contributions
    risk_contributions = compute_risk_contributions(final_weights, cov)

    return OptimizationResult(
        algorithm="MV",
        weights=final_weights,
        expected_return=round(exp_ret, 6),
        expected_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 6),
        risk_contributions=risk_contributions,
        optimizer_version=OPTIMIZER_VERSION,
        solver_status=solver_status,
        ucits_tickers_used=ucits_tickers or [],
        fallback_tickers_applied=fallback_tickers or [],
    )


# ---------------------------------------------------------------------------
# Comparison helper — used by the Dashboard tab
# ---------------------------------------------------------------------------

def compare_hrp_vs_mv(
    hrp_result: OptimizationResult,
    mv_result: OptimizationResult,
) -> dict:
    """
    Build a side-by-side comparison dict for the Streamlit comparison tab.

    Returns a structured dict consumed by P4's frontend to render the
    HRP vs MV comparison table and weight divergence chart.

    Args:
        hrp_result: OptimizationResult from hrp.optimize().
        mv_result:  OptimizationResult from markowitz.optimize_markowitz().

    Returns:
        Dict with keys: tickers, hrp_weights, mv_weights,
        hrp_volatility, mv_volatility, hrp_sharpe, mv_sharpe,
        weight_diff (absolute difference per ticker).
    """
    assert hrp_result["algorithm"] == "HRP", "first arg must be HRP result"
    assert mv_result["algorithm"] == "MV",   "second arg must be MV result"

    tickers = sorted(hrp_result["weights"].keys())

    hrp_w = [hrp_result["weights"].get(t, 0.0) for t in tickers]
    mv_w  = [mv_result["weights"].get(t, 0.0)  for t in tickers]
    diff  = [round(abs(h - m), 4) for h, m in zip(hrp_w, mv_w)]

    return {
        "tickers":        tickers,
        "hrp_weights":    hrp_w,
        "mv_weights":     mv_w,
        "weight_diff":    diff,
        "hrp_volatility": hrp_result["expected_volatility"],
        "mv_volatility":  mv_result["expected_volatility"],
        "hrp_sharpe":     hrp_result["sharpe_ratio"],
        "mv_sharpe":      mv_result["sharpe_ratio"],
        "hrp_solver":     hrp_result["solver_status"],
        "mv_solver":      mv_result["solver_status"],
    }
