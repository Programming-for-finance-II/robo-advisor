"""
Mock Ground Truth Payloads — Phase A (Frontend without live backend)
AI-Powered Robo-Advisor Platform — USI Programming in Finance II (2026)

Provides realistic mock data for all three risk profiles so the Streamlit
frontend is always demonstrable, independent of P1/P2/P3 backend readiness.

Design constraint (def_2 v3.1):
    "Phase A (frontend mock + rule-based integration) = MVP sempre funzionante
     — prerequisito assoluto."

Usage:
    from backend.schemas.mock_data import get_mock_payload
    payload = get_mock_payload("balanced")
    json_str = payload.model_dump_json(indent=2)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from backend.schemas.ground_truth import (
    BacktestSummary,
    Cluster,
    ClusterStructure,
    GroundTruthPayload,
    LLMConstraints,
    Metadata,
    Portfolio,
    Profiler,
    RegulatoryContext,
    RiskMetrics,
    ScenarioResult,
    StressScenarios,
    TopDriver,
    build_allowed_numbers,
)

ProfileLabel = Literal["conservative", "balanced", "aggressive"]

# ---------------------------------------------------------------------------
# ETF Universe (UCITS-aware, v3.1)
#
# UCITS tickers:  CSPX.L (GBP-listed, USD underlying)
#                 AGGH.MI (EUR-hedged aggregate bonds)
#                 XEON.MI (EUR overnight cash, ESTER)
# Non-UCITS:      EFA, TLT, GLD, VNQ, TIP  (all USD-denominated)
#
# Currency exposure for EUR investors:
#   USD: CSPX.L (underlying), EFA, TLT, GLD, VNQ, TIP
#   EUR: AGGH.MI, XEON.MI
#   GBP: CSPX.L listing currency — residual, not modelled separately
# ---------------------------------------------------------------------------

_UCITS_TICKERS: set[str] = {"CSPX.L", "AGGH.MI", "XEON.MI"}
_EUR_TICKERS: set[str] = {"AGGH.MI", "XEON.MI"}

_WEIGHTS: dict[ProfileLabel, dict[str, float]] = {
    "conservative": {
        "CSPX.L":  0.10,   # UCITS — US equity (GBP-listed, USD underlying)
        "EFA":     0.07,   # International developed equity
        "AGGH.MI": 0.25,   # UCITS — Global aggregate bonds, EUR-hedged
        "TLT":     0.18,   # US long-duration treasuries
        "GLD":     0.12,   # Gold
        "VNQ":     0.03,   # US REITs (floored by guardrail from raw HRP weight)
        "XEON.MI": 0.15,   # UCITS — EUR overnight cash (ESTER)
        "TIP":     0.10,   # US inflation-linked bonds
    },
    "balanced": {
        "CSPX.L":  0.22,   # UCITS
        "EFA":     0.15,
        "AGGH.MI": 0.18,   # UCITS
        "TLT":     0.12,
        "GLD":     0.11,
        "VNQ":     0.08,
        "XEON.MI": 0.09,   # UCITS
        "TIP":     0.05,
    },
    "aggressive": {
        "CSPX.L":  0.35,   # UCITS
        "EFA":     0.28,
        "AGGH.MI": 0.08,   # UCITS
        "TLT":     0.05,
        "GLD":     0.09,
        "VNQ":     0.10,
        "XEON.MI": 0.03,   # UCITS — minimum cash position
        "TIP":     0.02,
    },
}

_CLIPPED: dict[ProfileLabel, list[str]] = {
    "conservative": ["VNQ"],   # raw HRP weight was below the 0.03 floor
    "balanced":     ["VNQ"],
    "aggressive":   [],
}


def _eur_pct(weights: dict[str, float]) -> float:
    """EUR-denominated exposure = AGGH.MI + XEON.MI."""
    return round(sum(w for t, w in weights.items() if t in _EUR_TICKERS), 4)


def _usd_pct(weights: dict[str, float]) -> float:
    """
    USD-denominated exposure.
    CSPX.L is GBP-listed but USD-underlying — counted as USD for
    EUR investor currency risk purposes (Phase A simplification).
    """
    return round(sum(w for t, w in weights.items() if t not in _EUR_TICKERS), 4)


# ---------------------------------------------------------------------------
# Builder functions — one per sub-model
# ---------------------------------------------------------------------------

def _make_metadata(profile: ProfileLabel) -> Metadata:
    label_cap: Literal["Conservative", "Balanced", "Aggressive"] = (
        profile.capitalize()  # type: ignore[assignment]
    )
    confidences: dict[ProfileLabel, float] = {
        "conservative": 0.88,
        "balanced":     0.81,
        "aggressive":   0.76,
    }
    return Metadata(
        recommendation_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        optimizer="HRP",
        optimizer_version="pypfopt==1.5.5",
        market_data_hash="sha256:mock_phase_a_no_real_hash",
        data_window={"start": "2021-05-01", "end": "2026-04-29"},
        user_profile=label_cap,
        profile_confidence=confidences[profile],
    )


def _make_profiler(profile: ProfileLabel) -> Profiler:
    data: dict[ProfileLabel, dict] = {
        "conservative": {
            "confidence": 0.88,
            "top_drivers": [
                TopDriver(feature="investment_horizon", importance=0.41),
                TopDriver(feature="risk_attitude",      importance=0.32),
                TopDriver(feature="age",                importance=0.17),
            ],
            "note": (
                "Investors with similar characteristics typically hold "
                "60–75% of their portfolio in bonds and cash equivalents."
            ),
        },
        "balanced": {
            "confidence": 0.81,
            "top_drivers": [
                TopDriver(feature="investment_horizon", importance=0.34),
                TopDriver(feature="net_worth",          importance=0.28),
                TopDriver(feature="risk_attitude",      importance=0.21),
            ],
            "note": (
                "Investors with similar characteristics typically allocate "
                "40–55% of their portfolio to growth assets."
            ),
        },
        "aggressive": {
            "confidence": 0.76,
            "top_drivers": [
                TopDriver(feature="investment_horizon",  importance=0.38),
                TopDriver(feature="annual_income",       importance=0.29),
                TopDriver(feature="financial_experience", importance=0.22),
            ],
            "note": (
                "Investors with similar characteristics typically hold "
                "more than 60% of their portfolio in global equities."
            ),
        },
    }
    d = data[profile]
    return Profiler(
        profile_label=profile,
        confidence=d["confidence"],
        model_version="rule_based_v1",   # Phase A: rule-based fallback
        top_drivers=d["top_drivers"],
        similar_profiles_note=d["note"],
        low_confidence_flag=d["confidence"] < 0.65,
    )


def _make_portfolio(profile: ProfileLabel) -> Portfolio:
    weights = _WEIGHTS[profile]
    clipped = _CLIPPED[profile]
    ucits_used = [t for t in weights if t in _UCITS_TICKERS]
    return Portfolio(
        weights=weights,
        guardrail_applied=len(clipped) > 0,
        clipped_assets=clipped,
        clip_note=(
            f"{', '.join(clipped)}: raw HRP weight was below the 0.03 floor; clipped up."
            if clipped else None
        ),
        ucits_tickers_used=ucits_used,
        fallback_tickers_applied=[],   # no fallback needed in mock data
    )


def _make_risk_metrics(profile: ProfileLabel) -> RiskMetrics:
    metrics: dict[ProfileLabel, dict] = {
        "conservative": {
            "annual_volatility":      0.062,
            "max_drawdown_historical": -0.112,
            "var_95_daily":           -0.0058,
            "cvar_95_daily":          -0.0089,
        },
        "balanced": {
            "annual_volatility":      0.094,
            "max_drawdown_historical": -0.187,
            "var_95_daily":           -0.0089,
            "cvar_95_daily":          -0.0134,
        },
        "aggressive": {
            "annual_volatility":      0.148,
            "max_drawdown_historical": -0.312,
            "var_95_daily":           -0.0141,
            "cvar_95_daily":          -0.0213,
        },
    }
    m = metrics[profile]
    return RiskMetrics(
        expected_annual_return=None,   # intentionally null — HRP design
        annual_volatility=m["annual_volatility"],
        sharpe_ratio=None,             # intentionally null — no expected return
        max_drawdown_historical=m["max_drawdown_historical"],
        var_95_daily=m["var_95_daily"],
        cvar_95_daily=m["cvar_95_daily"],
    )


def _make_cluster_structure(profile: ProfileLabel) -> ClusterStructure:
    w = _WEIGHTS[profile]
    risk_w  = round(w["CSPX.L"] + w["EFA"], 4)
    real_w  = round(w["GLD"] + w["VNQ"], 4)
    safe_w  = round(w["AGGH.MI"] + w["TLT"] + w["TIP"], 4)
    cash_w  = round(w["XEON.MI"], 4)
    return ClusterStructure(
        cluster_A_risk_assets=Cluster(
            members=["CSPX.L", "EFA"],
            total_weight=risk_w,
            intra_cluster_correlation=0.74,
            cluster_volatility=0.162,
        ),
        cluster_B_real_assets=Cluster(
            members=["GLD", "VNQ"],
            total_weight=real_w,
            intra_cluster_correlation=0.21,
            cluster_volatility=0.138,
        ),
        cluster_C_safe_haven=Cluster(
            members=["AGGH.MI", "TLT", "TIP"],
            total_weight=safe_w,
            intra_cluster_correlation=0.68,
            cluster_volatility=0.071,
        ),
        cluster_D_cash=Cluster(
            members=["XEON.MI"],
            total_weight=cash_w,
            intra_cluster_correlation=None,
            cluster_volatility=0.003,
        ),
    )


_STRESS: dict[ProfileLabel, StressScenarios] = {
    "conservative": StressScenarios(
        covid_march_2020=ScenarioResult(portfolio_drawdown=-0.078,  benchmark_drawdown=-0.338),
        ukraine_feb_2022=ScenarioResult(portfolio_drawdown=-0.042,  benchmark_drawdown=-0.127),
        rates_hike_2022=ScenarioResult(portfolio_drawdown=-0.061,  benchmark_drawdown=-0.183),
    ),
    "balanced": StressScenarios(
        covid_march_2020=ScenarioResult(portfolio_drawdown=-0.142,  benchmark_drawdown=-0.338),
        ukraine_feb_2022=ScenarioResult(portfolio_drawdown=-0.071,  benchmark_drawdown=-0.127),
        rates_hike_2022=ScenarioResult(portfolio_drawdown=-0.089,  benchmark_drawdown=-0.183),
    ),
    "aggressive": StressScenarios(
        covid_march_2020=ScenarioResult(portfolio_drawdown=-0.241,  benchmark_drawdown=-0.338),
        ukraine_feb_2022=ScenarioResult(portfolio_drawdown=-0.108,  benchmark_drawdown=-0.127),
        rates_hike_2022=ScenarioResult(portfolio_drawdown=-0.139,  benchmark_drawdown=-0.183),
    ),
}

_BACKTEST: dict[ProfileLabel, BacktestSummary] = {
    "conservative": BacktestSummary(period="2019-2026", cagr=0.042, sharpe=0.61, max_drawdown=-0.114, calmar_ratio=0.37),
    "balanced":     BacktestSummary(period="2019-2026", cagr=0.068, sharpe=0.71, max_drawdown=-0.194, calmar_ratio=0.35),
    "aggressive":   BacktestSummary(period="2019-2026", cagr=0.091, sharpe=0.62, max_drawdown=-0.318, calmar_ratio=0.29),
}


def _make_regulatory_context(profile: ProfileLabel) -> RegulatoryContext:
    weights = _WEIGHTS[profile]
    usd = _usd_pct(weights)
    eur = _eur_pct(weights)
    return RegulatoryContext(
        profiler_us_centric_caveat=True,
        profiler_data_source="Federal Reserve Survey of Consumer Finances 2022 (United States)",
        profiler_training_geography="United States",
        hfcs_note=(
            "The ECB Household Finance and Consumption Survey (HFCS) would be a "
            "more geographically appropriate dataset for European investors. "
            "It is identified as a priority for future development."
        ),
        currency_risk_note=(
            f"Approximately {int(usd * 100)}% of the portfolio is denominated in USD. "
            "EUR-based investors are exposed to EUR/USD currency risk."
        ),
        portfolio_usd_denominated_pct=usd,
        portfolio_eur_denominated_pct=eur,
        etf_ucits_eligible=["CSPX.L", "AGGH.MI", "XEON.MI"],
        etf_non_ucits=["EFA", "TLT", "GLD", "VNQ", "TIP"],
        mifid_disclaimer=(
            "This is an educational prototype. No formal MiFID II suitability "
            "assessment has been performed."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_mock_payload(profile: ProfileLabel) -> GroundTruthPayload:
    """
    Return a fully-validated GroundTruthPayload for the given risk profile.

    The llm_constraints.allowed_numbers list is auto-populated from all
    numeric values in the payload — no manual maintenance required.

    Args:
        profile: One of "conservative", "balanced", "aggressive"

    Returns:
        GroundTruthPayload ready for model_dump_json() and LLM injection

    Example:
        >>> payload = get_mock_payload("balanced")
        >>> payload.profiler.profile_label
        'balanced'
        >>> sum(payload.portfolio.weights.values())
        1.0
    """
    if profile not in ("conservative", "balanced", "aggressive"):
        raise ValueError(
            f"Unknown profile: {profile!r}. "
            "Expected one of: conservative, balanced, aggressive"
        )

    metadata          = _make_metadata(profile)
    profiler          = _make_profiler(profile)
    portfolio         = _make_portfolio(profile)
    risk_metrics      = _make_risk_metrics(profile)
    cluster_structure = _make_cluster_structure(profile)
    stress            = _STRESS[profile]
    backtest          = _BACKTEST[profile]
    regulatory        = _make_regulatory_context(profile)

    # Build allowed_numbers from all numeric fields before adding constraints.
    partial: dict = {
        "metadata":          metadata.model_dump(),
        "profiler":          profiler.model_dump(),
        "portfolio":         portfolio.model_dump(),
        "risk_metrics":      risk_metrics.model_dump(),
        "cluster_structure": cluster_structure.model_dump(),
        "stress_scenarios":  stress.model_dump(),
        "backtest_summary":  backtest.model_dump(),
        "regulatory_context": regulatory.model_dump(),
    }
    allowed = build_allowed_numbers(partial)

    constraints = LLMConstraints(
        allowed_numbers=allowed,
        forbidden_phrases=[
            "sell", "buy", "guaranteed", "safe",
            "MiFID compliant", "you should", "I recommend",
            "invest", "liquidate", "move your money",
        ],
        disclaimer_required=True,
    )

    return GroundTruthPayload(
        metadata=metadata,
        profiler=profiler,
        portfolio=portfolio,
        risk_metrics=risk_metrics,
        cluster_structure=cluster_structure,
        stress_scenarios=stress,
        backtest_summary=backtest,
        llm_constraints=constraints,
        regulatory_context=regulatory,
    )


def get_all_mock_payloads() -> dict[ProfileLabel, GroundTruthPayload]:
    """Return mock payloads for all three profiles. Useful for testing."""
    return {p: get_mock_payload(p) for p in ("conservative", "balanced", "aggressive")}