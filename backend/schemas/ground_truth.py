"""
Ground Truth JSON Schema — AI-Powered Robo-Advisor Platform
Design Document v3.1 — USI Programming in Finance II (2026)

Philosophy: separation of concerns.
    - The backend CALCULATES and owns the ground truth.
    - The LLM NARRATES from the data provided, never inventing numbers.
    - The backend VALIDATES every LLM response before it reaches the user.

This schema implements the "Narrator, not Calculator" pattern: every numeric
value the LLM is allowed to cite must originate from the backend-generated
Ground Truth Payload and be validated before reaching the user.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class Metadata(BaseModel):
    recommendation_id: str = Field(..., description="UUID v4")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC")
    optimizer: Literal["HRP", "MV", "ERC"] = "HRP"
    optimizer_version: str = Field(..., description="e.g. 'pypfopt==1.5.5'")
    market_data_hash: str = Field(..., description="SHA-256 hash of the price CSV")
    data_window: dict[str, str] = Field(
        ..., description="{'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}"
    )
    user_profile: Literal["Conservative", "Balanced", "Aggressive"]
    profile_confidence: float = Field(..., ge=0.0, le=1.0)


class TopDriver(BaseModel):
    feature: str
    importance: float = Field(..., ge=0.0, le=1.0)


class Profiler(BaseModel):
    profile_label: Literal["conservative", "balanced", "aggressive"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: Literal["rule_based_v1", "gbm_scf_v1"] = "rule_based_v1"
    top_drivers: list[TopDriver] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="SHAP-derived top features driving the profile classification",
    )
    similar_profiles_note: str = Field(
        ...,
        description=(
            "Descriptive note about similar investors, passed to the LLM narrator"
        ),
    )
    low_confidence_flag: bool = Field(
        default=False,
        description="True if confidence < 0.65; triggers the UI clarification flow",
    )


class Portfolio(BaseModel):
    weights: dict[str, float] = Field(
        ..., description="Ticker-to-allocation mapping. Weights must sum to 1.0"
    )
    guardrail_applied: bool
    clipped_assets: list[str] = Field(
        default_factory=list,
        description="Tickers whose raw HRP weights were clipped to guardrail bounds",
    )
    clip_note: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of the clipping decisions",
    )
    # Design v3.1: UCITS-aware auditability — required by test_ucits_fallback.py
    ucits_tickers_used: list[str] = Field(
        default_factory=list,
        description="UCITS-eligible tickers effectively used in the final portfolio",
    )
    fallback_tickers_applied: list[str] = Field(
        default_factory=list,
        description="Fallback substitutions applied, e.g. ['CSPX.L->SPY']",
    )

    @model_validator(mode="after")
    def validate_weights(self) -> "Portfolio":
        if not self.weights:
            raise ValueError("Portfolio weights cannot be empty")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("Portfolio weights must be non-negative")
        total = sum(self.weights.values())
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"Portfolio weights sum to {total:.4f}, expected 1.0")
        return self


class RiskMetrics(BaseModel):
    # HRP does not require expected returns as an optimization input.
    # These fields are optional because they are descriptive historical metrics,
    # not forward-looking forecasts.
    expected_annual_return: Optional[float] = Field(
        default=None,
        description=(
        "Annualised historical mean log return. Populated with historical "
        "average when available; null if data is insufficient. "
        "Not a forward-looking forecast."
        ),
    )
    annual_volatility: float = Field(..., gt=0.0)
    sharpe_ratio: Optional[float] = Field(
        default=None,
        description=(
        "Historical Sharpe ratio (rf ≈ 0). Populated when expected_annual_return "
        "is available; null otherwise."
        ),
    )
    max_drawdown_historical: float = Field(
        ..., le=0.0, description="Historical maximum drawdown, expressed as a negative float"
    )
    var_95_daily: float = Field(
        ..., le=0.0, description="One-day 95% VaR, expressed as a negative float"
    )
    cvar_95_daily: float = Field(
        ..., le=0.0, description="One-day 95% CVaR, expressed as a negative float"
    )


class Cluster(BaseModel):
    members: list[str]
    total_weight: float = Field(..., ge=0.0, le=1.0)
    intra_cluster_correlation: Optional[float] = Field(
        default=None, ge=-1.0, le=1.0
    )
    cluster_volatility: float = Field(..., ge=0.0)


class ClusterStructure(BaseModel):
    cluster_A_risk_assets: Cluster
    cluster_B_real_assets: Cluster
    cluster_C_safe_haven: Cluster
    cluster_D_cash: Cluster


class ScenarioResult(BaseModel):
    portfolio_drawdown: float = Field(..., le=0.0)
    benchmark_drawdown: float = Field(..., le=0.0)


class StressScenarios(BaseModel):
    covid_march_2020: ScenarioResult
    ukraine_feb_2022: ScenarioResult
    rates_hike_2022: ScenarioResult


class BacktestSummary(BaseModel):
    period: str = Field(..., description="e.g. '2019-2026'")
    cagr: float
    sharpe: float
    max_drawdown: float = Field(..., le=0.0)
    calmar_ratio: float


class LLMConstraints(BaseModel):
    allowed_numbers: list[float] = Field(
        ...,
        description=(
            "List of numeric values from the ground truth payload that the "
            "LLM narrator is allowed to cite. Auto-populated by build_allowed_numbers()."
        ),
    )
    forbidden_phrases: list[str] = Field(
        default=[
            "sell",
            "buy",
            "guaranteed",
            "safe",
            "MiFID compliant",
            "you should",
            "I recommend",
            "invest",
            "liquidate",
            "move your money",
        ],
        description=(
            "Phrases that the LLM narrator must not use because they sound "
            "prescriptive, advisory, or legally overconfident."
        ),
    )
    disclaimer_required: bool = True


class RegulatoryContext(BaseModel):
    """
    EU Awareness Layer — design v3.1.

    Passed to the LLM narrator to enable Rule 9 of the system prompt.
    Allows the LLM to describe geographic and regulatory limitations
    without making legal compliance claims.
    """

    profiler_us_centric_caveat: bool = Field(
        default=True,
        description="True signals the LLM narrator to apply the EU Awareness rule",
    )
    profiler_data_source: str = Field(
        default="Federal Reserve Survey of Consumer Finances 2022 (United States)"
    )
    profiler_training_geography: str = Field(
        default="United States",
        description="Geographic area represented by the profiler training dataset",
    )
    hfcs_note: str = Field(
        default=(
            "The ECB Household Finance and Consumption Survey (HFCS) would be a "
            "more geographically appropriate dataset for European investors. "
            "It is identified as a priority for future development."
        )
    )
    currency_risk_note: str = Field(
        default=(
            "A significant portion of the portfolio is denominated in USD. "
            "EUR-based investors are exposed to EUR/USD currency risk."
        )
    )
    portfolio_usd_denominated_pct: float = Field(
        ..., ge=0.0, le=1.0,
        description="Fraction of portfolio weight denominated in USD",
    )
    portfolio_eur_denominated_pct: float = Field(
        ..., ge=0.0, le=1.0,
        description="Fraction of portfolio weight denominated in EUR",
    )
    etf_ucits_eligible: list[str] = Field(
        default_factory=lambda: ["CSPX.L", "AGGH.MI", "XEON.MI"],
        description="UCITS-eligible tickers in the current investment universe",
    )
    etf_non_ucits: list[str] = Field(
        default_factory=lambda: ["EFA", "TLT", "GLD", "VNQ", "TIP"],
        description="Non-UCITS tickers in the current investment universe",
    )
    mifid_disclaimer: str = Field(
        default=(
            "This is an educational prototype. No formal MiFID II suitability "
            "assessment has been performed."
        )
    )

    @model_validator(mode="after")
    def currency_exposure_valid(self) -> "RegulatoryContext":
        # NOTE: CSPX.L is listed in GBP (London Stock Exchange), so USD + EUR
        # will not sum to exactly 1.0. We only check they do not exceed 1.0.
        total = self.portfolio_usd_denominated_pct + self.portfolio_eur_denominated_pct
        if total > 1.001:
            raise ValueError(
                f"USD ({self.portfolio_usd_denominated_pct:.2%}) + "
                f"EUR ({self.portfolio_eur_denominated_pct:.2%}) = {total:.4f} "
                "exceeds 1.0. Check GBP exposure from CSPX.L."
            )
        return self


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------

class GroundTruthPayload(BaseModel):
    """
    Complete Ground Truth JSON passed to the LLM narrator.

    Usage:
        payload = build_ground_truth_payload(...)
        json_str = payload.model_dump_json(indent=2)
        # Inject json_str into the system prompt CONTEXT block.
    """

    metadata: Metadata
    profiler: Profiler
    portfolio: Portfolio
    risk_metrics: RiskMetrics
    cluster_structure: ClusterStructure
    stress_scenarios: StressScenarios
    backtest_summary: BacktestSummary
    llm_constraints: LLMConstraints
    regulatory_context: RegulatoryContext


# ---------------------------------------------------------------------------
# Helper: extract all numeric values from a payload -> allowed_numbers
# ---------------------------------------------------------------------------

_STRING_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _extract_floats(obj: object) -> list[float]:
    """
    Recursively extract every float and int from a nested object.

    Booleans are excluded because they are subclasses of int in Python.
    Values are rounded to 6 decimals to make validator comparisons stable.

    Numbers embedded in string fields (e.g. the "40–55%" range inside a
    profiler note) are also harvested: they are part of the ground truth shown
    to the narrator, so citing them is not hallucination. Each string number is
    whitelisted in both its raw and percent (value / 100) form so the validator
    matches regardless of whether the narrator renders it as "40" or "40%".
    """
    result: list[float] = []

    if isinstance(obj, bool):
        return result
    if isinstance(obj, float):
        result.append(round(obj, 6))
    elif isinstance(obj, int):
        result.append(float(obj))
    elif isinstance(obj, str):
        for token in _STRING_NUMBER_RE.findall(obj):
            try:
                val = float(token.replace(",", "."))
            except ValueError:
                continue
            result.append(round(val, 6))
            result.append(round(val / 100.0, 6))
    elif isinstance(obj, dict):
        for value in obj.values():
            result.extend(_extract_floats(value))
    elif isinstance(obj, list):
        for item in obj:
            result.extend(_extract_floats(item))
    elif isinstance(obj, BaseModel):
        result.extend(_extract_floats(obj.model_dump()))

    return result


def build_allowed_numbers(payload_without_constraints: dict) -> list[float]:
    """
    Build the exhaustive list of numeric values the LLM narrator is allowed to cite.

    Called automatically by mock_data.py and by the live backend before
    finalising a GroundTruthPayload. No manual maintenance required.

    Args:
        payload_without_constraints: model_dump() of the payload minus
                                     the llm_constraints block.

    Returns:
        Deduplicated list of floats in order of first appearance.
    """
    nums = _extract_floats(payload_without_constraints)

    seen: set[float] = set()
    unique: list[float] = []
    for num in nums:
        if num not in seen:
            seen.add(num)
            unique.append(num)

    return unique