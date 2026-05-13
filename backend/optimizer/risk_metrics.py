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

    Uses the formula from Maillard et al. (2010) to decompose total portfolio
    risk into contributions from each asset, normalized to sum to 1.0:
        RC_i = w_i * (Σw)_i / (wᵀΣw)
    
    where w is the weight vector, Σ is the covariance matrix, and (Σw)_i is
    the marginal contribution to portfolio variance from asset i.

    Args:
        weights: Dictionary mapping ticker symbols to portfolio weights.
                 Weights must sum to 1.0.
        cov: Ledoit-Wolf shrinkage covariance matrix with tickers as both
             index and columns. Must be positive definite.

    Returns:
        Dictionary mapping ticker symbols to their normalized risk contributions.
        Values are rounded to 6 decimal places and sum to 1.0.

    Raises:
        AssertionError: If fewer than 2 assets provided, weights don't sum to 1.0,
                       or portfolio variance is not positive.
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
    Compute annualized portfolio volatility.

    Calculates the annualized standard deviation of portfolio returns using:
        σ_p = sqrt(wᵀΣw * 252)
    
    where w is the weight vector, Σ is the daily covariance matrix, and 252
    is the typical number of trading days per year.

    Args:
        weights: Dictionary mapping ticker symbols to portfolio weights.
        cov: Daily covariance matrix (Ledoit-Wolf shrinkage estimator).
             Must have tickers as both index and columns.

    Returns:
        Annualized portfolio volatility as a positive float, rounded to
        6 decimal places. Typical values range from 0.05 to 0.40 (5%-40%).

    Note:
        Assumes the covariance matrix is in daily units, as returned by
        CovarianceShrinkage when fitted on daily price series.
    """
    tickers = list(cov.columns)
    w = np.array([weights[t] for t in tickers])
    daily_var = float(w @ cov.values @ w)
    return round(float(np.sqrt(daily_var * TRADING_DAYS_PER_YEAR)), 6)


def compute_max_drawdown(returns: pd.Series) -> float:
    """
    Compute historical maximum drawdown from a return series.

    Maximum drawdown measures the largest peak-to-trough decline in cumulative
    returns over the historical period. It represents the worst possible loss
    an investor would have experienced by buying at the peak and selling at
    the trough.

    Args:
        returns: Series of daily portfolio returns (arithmetic or log returns).
                 Index should be datetime, values should be fractional returns.

    Returns: