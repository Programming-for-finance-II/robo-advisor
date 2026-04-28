from __future__ import annotations

from typing import Literal, TypedDict


class OptimizationResult(TypedDict):
    algorithm: Literal["HRP", "MV", "ERC"]
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    risk_contributions: dict[str, float]
    optimizer_version: str
    solver_status: Literal["optimal", "infeasible", "fallback"]
    ucits_tickers_used: list[str]
    fallback_tickers_applied: list[str]
