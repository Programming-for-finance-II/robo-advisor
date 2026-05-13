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

    where RC_i is the risk contribution of asset i, w_i is its weight,
    Σ is the covariance matrix, and (Σw)_i is the marginal contribution
    to portfolio variance.

    Args:
        weights: Dictionary mapping ticker to portfolio weight. Weights must
                 sum to 1.0. At least 2 assets required.
        cov: Ledoit-Wolf covariance matrix as a pandas DataFrame with tickers
             as both index and columns. Must be positive definite.

    Returns:
        Dictionary mapping each ticker to its risk contribution (float).
        Values sum to 1.0 and are rounded to 6 decimal places.

    Raises:
        AssertionError: If fewer than 2 assets provided, weights don't sum to 1.0,
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
    Compute annualized portfolio volatility.

    Formula: σ_p = sqrt(wᵀΣw * 252)

    This function assumes the covariance matrix is in daily units (as returned
    by CovarianceShrinkage from daily price series). The result is annualized
    by multiplying by the square root of trading days per year (252).

    Args:
        weights: Dictionary mapping ticker to portfolio weight. Each ticker
                 must be present in the covariance matrix columns.
        cov: Daily covariance matrix (Ledoit-Wolf shrinkage estimator) as a
             pandas DataFrame with tickers as both index and columns.

    Returns:
        Annualized portfolio volatility as a positive float, rounded to 6
        decimal places.
    """
    tickers = list(cov.columns)
    w = np.array([weights[t] for t in tickers])
    daily_var = float(w @ cov.values @ w)
    return round(float(np.sqrt(daily_var * TRADING_DAYS_PER_YEAR)), 6)


def compute_max_drawdown(returns: pd.Series) -> float:
    """
    Compute historical maximum drawdown from a return series.

    Maximum drawdown is the largest peak-to-trough decline in cumulative returns.
    This metric measures the largest loss an investor would have experienced from
    a local peak to the subsequent trough.

    Args:
        returns: Daily portfolio returns as a pandas Series. Can be arithmetic
                 or log returns. Must not be empty.

    Returns:
        Maximum drawdown as a negative float (e.g., -0.312 represents -31.2%),
        rounded to 6 decimal places.

    Raises:
        AssertionError: If returns series is empty