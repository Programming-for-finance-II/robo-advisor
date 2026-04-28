from __future__ import annotations
from typing import TypedDict, Literal


class OptimizationResult(TypedDict):
    algorithm: Literal["HRP", "MV", "ERC"]
    weights: dict[str, float]              # ticker -> weight, sum = 1.0
    expected_return: float                 # annualized
    expected_volatility: float             # annualized
    sharpe_ratio: float                    # configurable risk-free rate
    risk_contributions: dict[str, float]   # for XAI and LLM narrator, sum = 1.0
    optimizer_version: str                 # e.g. "pypfopt-1.5.5-HRP"
    solver_status: Literal["optimal", "infeasible", "fallback"]
    ucits_tickers_used: list[str]          # UCITS tickers actually used
    fallback_tickers_applied: list[str]    # e.g. ["CSPX.L→IVV"]
