# backend/api/main.py
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.data.loader import ValidatedDataLoader
from backend.data.snapshots import init_db, save_market_snapshot, save_recommendation
from backend.data.universe_config import get_cluster_map, get_primary_tickers
from backend.llm.narrator import NarratorClient
from backend.llm.validator import validate
from backend.ml.profiler.rule_based import ProfilerOutput, profile_user
from backend.optimizer.hrp import OptimizationResult, optimize
from backend.schemas.ground_truth import (
    Cluster,
    GroundTruthPayload,
    LLMConstraints,
    RegulatoryContext,
    ScenarioResult,
    build_allowed_numbers,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Robo-Advisor API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# /profile — Pydantic models
# ---------------------------------------------------------------------------

VALID_RESPONSES = {"a", "b", "c", "d"}
QUESTION_KEYS = [f"Q{i}" for i in range(1, 11)]


class ProfileRequest(BaseModel):
    """Questionnaire responses for all 10 questions."""
    responses: dict[str, str]

    @field_validator("responses")
    @classmethod
    def validate_responses(cls, v: dict[str, str]) -> dict[str, str]:
        missing = set(QUESTION_KEYS) - set(v.keys())
        if missing:
            raise ValueError(f"Missing questions: {sorted(missing)}")
        extra = set(v.keys()) - set(QUESTION_KEYS)
        if extra:
            raise ValueError(f"Unexpected keys: {sorted(extra)}")
        for q, r in v.items():
            if r not in VALID_RESPONSES:
                raise ValueError(f"Invalid response '{r}' for {q}")
        return v


class TopDriverResponse(BaseModel):
    feature: str
    importance: float


class ProfileResponse(BaseModel):
    profile_label: str
    confidence: float
    low_confidence_flag: bool
    top_drivers: list[TopDriverResponse]
    model_version: str


# ---------------------------------------------------------------------------
# /profile endpoint
# ---------------------------------------------------------------------------

@app.post("/profile", response_model=ProfileResponse)
@limiter.limit("20/minute")
def profile(request: Request, body: ProfileRequest) -> ProfileResponse:
    """
    Classify a user's risk profile from their questionnaire responses.

    Returns CONSERVATIVE, MODERATE, or AGGRESSIVE with confidence score.
    Q7='a' (safety-net money) triggers a hard MiFID II override to CONSERVATIVE.
    """
    try:
        result: ProfilerOutput = profile_user(body.responses)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ProfileResponse(**result)



class AdviceRequest(BaseModel):
    recommendation_id: str
    user_message: str


class AdviceResponse(BaseModel):
    safe_text: str
    passed: bool
    disclaimer_appended: bool
    validator_flags: list[str]
    injection_blocked: bool
    api_error: bool


# ---------------------------------------------------------------------------
# /advice endpoint
# ---------------------------------------------------------------------------

@app.post("/advice", response_model=AdviceResponse)
@limiter.limit("10/minute")
def advice(request: Request, body: AdviceRequest) -> AdviceResponse:
    """
    Generate LLM narrative advice for a stored portfolio recommendation.

    Retrieves the OptimizationResult from DB by recommendation_id,
    builds the Ground Truth JSON payload, calls the Narrator (Claude API),
    runs the 5-step Validator, updates the DB audit trail, and returns
    the validated response.
    """
    # Step 1 — fetch recommendation from DB
    try:
        conn = init_db(DB_PATH)
        row = conn.execute(
            "SELECT * FROM recommendations WHERE id = ?",
            (body.recommendation_id,),
        ).fetchone()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"recommendation_id '{body.recommendation_id}' not found.",
        )

    # Step 2 — rebuild GroundTruthPayload from stored data
    weights: dict[str, float] = json.loads(row["weights_final"]) if row["weights_final"] else {}
    risk: dict = json.loads(row["risk_metrics"]) if row["risk_metrics"] else {}
    ucits: list[str] = json.loads(row["ucits_tickers_used"]) if row["ucits_tickers_used"] else []
    fallback: list[str] = list(
        json.loads(row["fallback_tickers_applied"]).keys()
    ) if row["fallback_tickers_applied"] else []

    # Stub cluster/stress/backtest — P2 will populate in W3
    stub_cluster = Cluster(
        members=[], total_weight=0.0,
        intra_cluster_correlation=None, cluster_volatility=0.0,
    )
    stub_scenario = ScenarioResult(portfolio_drawdown=0.0, benchmark_drawdown=0.0)

    payload_without_constraints = {
        "metadata": {
            "recommendation_id": row["id"],
            "timestamp_utc": row["created_at"],
            "optimizer": row["optimizer_algo"] or "HRP",
            "optimizer_version": row["optimizer_version"],
            "market_data_hash": row["market_data_hash"],
            "data_window": {
                "start": row["data_window_start"],
                "end": row["data_window_end"],
            },
            "user_profile": row["profile_label"].capitalize(),
            "profile_confidence": float(row["profile_confidence"]),
        },
        "profiler": {
            "profile_label": row["profile_label"].lower(),
            "confidence": float(row["profile_confidence"]),
            "model_version": row["profile_model_version"],
            "top_drivers": [{"feature": "score", "importance": 1.0}],
            "similar_profiles_note": f"Investor classified as {row['profile_label']}.",
            "low_confidence_flag": float(row["profile_confidence"]) < 0.65,
        },
        "portfolio": {
            "weights": weights,
            "guardrail_applied": bool(row["guardrails_applied"]),
            "ucits_tickers_used": ucits,
            "fallback_tickers_applied": fallback,
        },
        "risk_metrics": {
            "expected_annual_return": None,
            "annual_volatility": risk.get("expected_volatility", 0.1),
            "sharpe_ratio": None,
            "max_drawdown_historical": -0.1,
            "var_95_daily": -0.02,
            "cvar_95_daily": -0.03,
        },
        "cluster_structure": {
            "cluster_A_risk_assets": stub_cluster.model_dump(),
            "cluster_B_real_assets": stub_cluster.model_dump(),
            "cluster_C_safe_haven": stub_cluster.model_dump(),
            "cluster_D_cash": stub_cluster.model_dump(),
        },
        "stress_scenarios": {
            "covid_march_2020": stub_scenario.model_dump(),
            "ukraine_feb_2022": stub_scenario.model_dump(),
            "rates_hike_2022": stub_scenario.model_dump(),
        },
        "backtest_summary": {
            "period": f"{row['data_window_start'][:4]}–{row['data_window_end'][:4]}",
            "cagr": 0.07,
            "sharpe": 0.6,
            "max_drawdown": -0.15,
            "calmar_ratio": 0.47,
        },
        "regulatory_context": {
            "portfolio_usd_denominated_pct": 0.5,
            "portfolio_eur_denominated_pct": 0.3,
        },
    }

    allowed_numbers = build_allowed_numbers(payload_without_constraints)

    try:
        payload_without_constraints["regulatory_context"] = RegulatoryContext(
            portfolio_usd_denominated_pct=0.5,
            portfolio_eur_denominated_pct=0.3,
        )
        payload = GroundTruthPayload(
            **payload_without_constraints,
            llm_constraints=LLMConstraints(allowed_numbers=allowed_numbers),
        )