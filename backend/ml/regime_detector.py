"""
regime_detector.py
------------------
Market stress regime detection — Phase B stub.

Current status: always returns "normal" regime.
Future work: implement VIX-threshold detection (VIX > 25 → stress),
and optionally a Hidden Markov Model on rolling volatility.

References:
    - CBOE VIX White Paper (2019).
    - Hamilton, J.D. (1989). A New Approach to the Economic Analysis of
      Nonstationary Time Series and the Business Cycle. Econometrica.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class RegimeOutput(TypedDict):
    """Output schema for the regime detector.

    Attributes
    ----------
    stress_regime : bool
        True if the market is currently in a stress regime.
    regime_label : str
        Human-readable regime label: "normal" or "stress".
    vix_proxy : float or None
        Estimated VIX-proxy value used for the decision.
        None when not yet implemented.
    """

    stress_regime: bool
    regime_label: Literal["normal", "stress"]
    vix_proxy: float | None


def detect_regime(market_data: dict | None = None) -> RegimeOutput:
    """Detect market stress regime.

    Phase B stub: always returns normal regime.
    Future work: implement VIX threshold detection (VIX > 25 → stress).

    Parameters
    ----------
    market_data : dict or None
        Optional dict with market indicators. Currently unused.

    Returns
    -------
    RegimeOutput
        Regime classification with stress flag.
    """
    return RegimeOutput(stress_regime=False, regime_label="normal", vix_proxy=None)
