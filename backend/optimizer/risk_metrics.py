from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR: int = 252

CONFIDENCE_LEVEL: float = 0.95

def compute_risk_contributions(
    weights: dict[str, float],
    cov: pd.DataFrame,
) -> dict[str, float]:
    """
    Compute per-asset marginal risk contributions (sum to 1.0).

    Formula (Maillard et al., 2010):
        RC_i = w_i * (Σw)_i / (wᵀΣw)

    Args:
        weights: Dict mapping ticker to portfolio weight, must sum to 1.0.
        cov: Ledoit-Wolf covariance matrix with tickers as columns/index.

    Returns:
        Dict mapping ticker to risk contribution, values sum to 1.0.

    Raises:
        AssertionError: If fewer than 2 assets, weights don't sum to 1.0,
                       or portfolio variance is non-positive.
    """
    assert len(weights) >= 2, "need at least 2 assets"
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "weights must sum to 1.0"

    tickers = list(cov.columns)
    w = np.array([weights[t] for t in tickers])

    portfolio_var = float(w @ cov.values @ w)
    assert portfolio_var > 0, "portfolio variance must be positive"

    marginal = cov.values @ w          # (Σw)_i
    rc = w * marginal / portfolio_var  # normalised contributions

    return {t: round(float(v), 6) for t, v in zip(tickers, rc)}


def compute_annual_volatility(
    weights: dict[str, float],
    cov: pd.DataFrame,
) -> float:
    """
    Compute annualised portfolio volatility.

    Formula: σ_p = sqrt(wᵀΣw * 252)

    Assumes cov is in daily units (as returned by CovarianceShrinkage 
    from daily price series). Annualization uses 252 trading days per year.

    Args:
        weights: Dict mapping ticker to portfolio weight.
        cov: Daily covariance matrix (Ledoit-Wolf).

    Returns:
        Annualised portfolio volatility as a positive float, rounded to 6 decimals.
    """
    tickers = list(cov.columns)
    w = np.array([weights[t] for t in tickers])
    daily_var = float(w @ cov.values @ w)
    return round(float(np.sqrt(daily_var * TRADING_DAYS_PER_YEAR)), 6)


def compute_max_drawdown(returns: pd.Series) -> float:
    """
    Compute historical maximum drawdown from a return series.

    The maximum drawdown is the largest peak-to-trough decline in cumulative
    returns over the entire history.

    Args:
        returns: Daily portfolio returns (arithmetic or log).

    Returns:
        Maximum drawdown as a negative float (e.g. -0.312 = -31.2%), 
        rounded to 6 decimals.

    Raises:
        AssertionError: If returns series is empty.
    """
    assert not returns.empty, "returns series cannot be empty"

    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    drawdowns = (cum - rolling_max) / rolling_max
    return round(float(drawdowns.min()), 6)


def compute_var_cvar(
    returns: pd.Series,
    confidence: float = CONFIDENCE_LEVEL,
) -> tuple[float, float]:
    """
    Compute historical 1-day VaR and CVaR at the given confidence level.

    Value at Risk (VaR) is the percentile of the return distribution at the
    (1 - confidence) level. Conditional VaR (CVaR