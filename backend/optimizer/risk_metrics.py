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
        weights: Dict {ticker: weight}, must sum to 1.0.
        cov:     Ledoit-Wolf covariance matrix

    Returns:
        Dict {ticker: risk_contribution}, values sum to 1.0.
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

    Note: assumes cov is in daily units (as returned by
    CovarianceShrinkage from daily price series).

    Args:
        weights: Dict {ticker: weight}.
        cov:     Daily covariance matrix (Ledoit-Wolf).

    Returns:
        Annualised volatility as a positive float.
    """
    tickers = list(cov.columns)
    w = np.array([weights[t] for t in tickers])
    daily_var = float(w @ cov.values @ w)
    return round(float(np.sqrt(daily_var * TRADING_DAYS_PER_YEAR)), 6)


def compute_max_drawdown(returns: pd.Series) -> float:
    """
    Compute historical maximum drawdown from a return series.

    Args:
        returns: Daily portfolio returns (arithmetic or log).

    Returns:
        Maximum drawdown as a negative float (e.g. -0.312 = -31.2%).
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

    Args:
        returns:    Daily portfolio returns.
        confidence: Confidence level (default 0.95).

    Returns:
        (var, cvar) — both negative floats.
        var  = 5th percentile of the return distribution.
        cvar = mean of returns below the VaR threshold (Expected Shortfall).
    """
    assert len(returns) >= 30, (
        f"too few observations ({len(returns)}) for reliable VaR/CVaR"
    )
    assert 0 < confidence < 1, "confidence must be in (0, 1)"

    var = float(np.percentile(returns, (1 - confidence) * 100))
    tail_returns = returns[returns <= var]
    cvar = float(tail_returns.mean()) if len(tail_returns) > 0 else var

    return round(var, 6), round(cvar, 6)


def compute_portfolio_returns(
    prices: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    """
    Compute daily portfolio log-returns from price series and weights.

    Used internally to compute drawdown, VaR, CVaR.

    Args:
        prices:  Adjusted close prices (rows=dates, cols=tickers).
        weights: Dict {ticker: weight}.

    Returns:
        pd.Series of daily portfolio log-returns.
    """
    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers])
    log_returns = np.log(prices[tickers] / prices[tickers].shift(1)).dropna()
    portfolio_returns = log_returns.values @ w
    return pd.Series(portfolio_returns, index=log_returns.index)


def compute_all(
    weights: dict[str, float],
    cov: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, object]:
        
    """
    Compute all risk metrics in one call.

    Returns a dict matching the RiskMetrics sub-model in ground_truth.py:
        annual_volatility         float
        max_drawdown_historical   float (negative)
        var_95_daily              float (negative)
        cvar_95_daily             float (negative)
        risk_contributions        dict[str, float]
        expected_annual_return    None  (HRP design — no reliable mu estimate)
        sharpe_ratio              None  (HRP design — no mu, no Sharpe)

    Args:
        weights: Final portfolio weights from hrp.optimize().
        cov:     Ledoit-Wolf covariance matrix from compute_covariance().
        prices:  Cleaned price DataFrame from ValidatedDataLoader.
    """
    assert len(weights) >= 2, "need at least 2 assets"
    assert not prices.empty, "prices DataFrame is empty"
    port_returns = compute_portfolio_returns(prices, weights)
    var, cvar = compute_var_cvar(port_returns)

    return {
        "expected_annual_return": None,       # intentionally null — HRP design
        "annual_volatility": compute_annual_volatility(weights, cov),
        "sharpe_ratio": None,                 # intentionally null — no mu
        "max_drawdown_historical": compute_max_drawdown(port_returns),
        "var_95_daily": var,
        "cvar_95_daily": cvar,
        "risk_contributions": compute_risk_contributions(weights, cov),
    }
