# backend/api/main.py
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.data.loader import ValidatedDataLoader
from backend.data.snapshots import init_db, save_market_snapshot, save_recommendation
from backend.data.universe_config import get_cluster_map, get_primary_tickers
from backend.llm.narrator import NarratorClient, NarratorError
from backend.llm.validator import validate
from backend.ml.profiler.rule_based import ProfilerOutput, profile_user
from backend.optimizer.hrp import OptimizationResult, optimize
from backend.schemas.mock_data import get_mock_payload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Robo-Advisor API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# API Key auth
# ---------------------------------------------------------------------------

API_KEY_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """
    Validate the X-API-Key header on every protected endpoint.
    Key is read from the API_KEY environment variable.
    If API_KEY is not set, auth is disabled (development mode).
    """
    import os
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return "dev-mode"
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_RESPONSES = {"a", "b", "c", "d"}
QUESTION_KEYS = [f"Q{i}" for i in range(1, 11)]
VALID_PROFILE_LABELS = {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
START_DATE = "2023-01-01"
END_DATE = date.today().isoformat()
DB_PATH = "robo_advisor.db"

_PROFILE_LABEL_MAP: dict[str, str] = {
    "CONSERVATIVE": "conservative",
    "MODERATE": "balanced",
    "AGGRESSIVE": "aggressive",
}

# ---------------------------------------------------------------------------
# /profile — Pydantic models
# ---------------------------------------------------------------------------


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
def profile(
    request: Request, body: ProfileRequest, _: str = Depends(verify_api_key)
) -> ProfileResponse:
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


# ---------------------------------------------------------------------------
# /advice — LLM Narrator + Validator pipeline (W3)
# ---------------------------------------------------------------------------

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


@app.post("/advice", response_model=AdviceResponse)
@limiter.limit("10/minute")
def advice(
    request: Request, body: AdviceRequest, _: str = Depends(verify_api_key)
) -> AdviceResponse:
    """Generate LLM narrative advice for a saved portfolio recommendation."""
    try:
        conn = init_db(DB_PATH)
        row = conn.execute(
            "SELECT * FROM recommendations WHERE id = ?",
            (body.recommendation_id,),
        ).fetchone()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")

    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")

    profile_key = _PROFILE_LABEL_MAP.get(row["profile_label"], "balanced")
    payload = get_mock_payload(profile_key)

    from backend.llm.input_sanitiser import sanitise
    sanitiser_result = sanitise(body.user_message)
    if sanitiser_result.blocked:
        return AdviceResponse(
            safe_text=(
                "Your question could not be processed. "
                "Please rephrase it more concisely.\n\n"
                "This is an educational prototype. "
                "No formal financial advice is provided."
            ),
            passed=False,
            disclaimer_appended=False,
            validator_flags=["INJECTION_DETECTED"],
            injection_blocked=True,
            api_error=False,
        )

    try:
        narrator = NarratorClient()
    except NarratorError as e:
        raise HTTPException(status_code=503, detail=str(e))

    narrator_response = narrator.narrate(
        payload, sanitiser_result.sanitised_input
    )

    narrator_response = narrator.narrate(payload, body.user_message)

    eu_required = payload.regulatory_context.profiler_us_centric_caveat
    result = validate(
        narrator_response.raw_text,
        payload.llm_constraints.allowed_numbers,
        payload.llm_constraints.forbidden_phrases,
        eu_awareness_required=eu_required,
    )

    try:
        conn.execute(
            """
            UPDATE recommendations SET
                llm_model              = ?,
                system_prompt_hash     = ?,
                ground_truth_json_hash = ?,
                llm_response_raw       = ?,
                llm_response_validated = ?,
                validator_flags        = ?,
                retry_count            = ?,
                disclaimer_shown       = ?
            WHERE id = ?
            """,
            (
                narrator_response.model,
                narrator_response.system_prompt_hash,
                narrator_response.ground_truth_hash,
                narrator_response.raw_text,
                result.safe_text,
                json.dumps([f.value for f in result.flags]),
                0,
                int(not result.disclaimer_appended),
                row["id"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("DB audit update failed: %s", e)

    return AdviceResponse(
        safe_text=result.safe_text,
        passed=result.passed,
        disclaimer_appended=result.disclaimer_appended,
        validator_flags=[f.value for f in result.flags],
        injection_blocked=narrator_response.injection_blocked,
        api_error=narrator_response.api_error,
    )


# ---------------------------------------------------------------------------
# /backtest — Pydantic models
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    profile_label: str

    @field_validator("profile_label")
    @classmethod
    def validate_profile_label(cls, v: str) -> str:
        if v not in VALID_PROFILE_LABELS:
            raise ValueError(
                f"Invalid profile_label '{v}'; "
                f"expected one of {sorted(VALID_PROFILE_LABELS)}"
            )
        return v


class StrategyMetrics(BaseModel):
    cagr: float
    annualised_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    total_transaction_cost: float
    n_rebalances: int


class ScenarioResponse(BaseModel):
    scenario_key: str
    scenario_label: str
    test_start: str
    test_end: str
    strategies: dict[str, StrategyMetrics]


class BacktestResponse(BaseModel):
    profile_label: str
    scenarios: list[ScenarioResponse]


# ---------------------------------------------------------------------------
# /backtest endpoint
# ---------------------------------------------------------------------------

@app.post("/backtest", response_model=BacktestResponse)
@limiter.limit("5/minute")
def backtest(
    request: Request, body: BacktestRequest, _: str = Depends(verify_api_key)
) -> BacktestResponse:
    """
    Run HRP vs MV vs 1/N backtest on 3 historical stress scenarios.

    Scenarios: GFC 2008, COVID 2020, Rate Hike 2022.
    Returns metrics only (no equity curve) to keep response size manageable.
    """
    from backend.optimizer.backtest import run_all_scenarios

    tickers = get_primary_tickers()
    cluster_map = get_cluster_map()

    BACKTEST_START = "2006-01-01"

    try:
        loader = ValidatedDataLoader()
        prices, _ = loader.load(
            tickers=tickers,
            start=BACKTEST_START,
            end=END_DATE,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {e}")

    try:
        results = run_all_scenarios(prices, body.profile_label, cluster_map)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

    scenarios = []
    for key, result in results.items():
        strategies = {
            strat: StrategyMetrics(
                cagr=sr.cagr,
                annualised_volatility=sr.annualised_volatility,
                sharpe_ratio=sr.sharpe_ratio,
                max_drawdown=sr.max_drawdown,
                calmar_ratio=sr.calmar_ratio,
                total_transaction_cost=sr.total_transaction_cost,
                n_rebalances=sr.n_rebalances,
            )
            for strat, sr in result.strategies.items()
        }
        scenarios.append(ScenarioResponse(
            scenario_key=result.scenario_key,
            scenario_label=result.scenario_label,
            test_start=result.test_start,
            test_end=result.test_end,
            strategies=strategies,
        ))

    return BacktestResponse(
        profile_label=body.profile_label,
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# /compare — Pydantic models
# ---------------------------------------------------------------------------

class CompareRequest(BaseModel):
    profile_label: str

    @field_validator("profile_label")
    @classmethod
    def validate_profile_label(cls, v: str) -> str:
        if v not in VALID_PROFILE_LABELS:
            raise ValueError(
                f"Invalid profile_label '{v}'; "
                f"expected one of {sorted(VALID_PROFILE_LABELS)}"
            )
        return v


class CompareResponse(BaseModel):
    profile_label: str
    hrp: dict[str, float]
    mv: dict[str, float]
    equal_weight: dict[str, float]
    hrp_volatility: float
    mv_volatility: float
    equal_weight_volatility: float


# ---------------------------------------------------------------------------
# /compare endpoint
# ---------------------------------------------------------------------------

@app.post("/compare", response_model=CompareResponse)
@limiter.limit("10/minute")
def compare(
    request: Request, body: CompareRequest, _: str = Depends(verify_api_key)
) -> CompareResponse:
    """
    Compare HRP vs Markowitz vs 1/N portfolio weights for a given profile.

    Uses current market data (last 2 years). Returns weights and
    annualised volatility for each strategy.
    """
    from backend.optimizer.markowitz import optimize_markowitz

    tickers = get_primary_tickers()
    cluster_map = get_cluster_map()

    try:
        loader = ValidatedDataLoader()
        prices, _ = loader.load(
            tickers=tickers,
            start=START_DATE,
            end=END_DATE,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {e}")

    try:
        hrp_result = optimize(
            prices=prices,
            profile=body.profile_label,
            cluster_map=cluster_map,
        )
        mv_result = optimize_markowitz(prices)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {e}")

    n = len(tickers)
    equal_weights = {t: round(1.0 / n, 6) for t in tickers}

    daily_rets = prices.pct_change().dropna()
    eq_vol = float(
        (daily_rets @ list(equal_weights.values())).std() * (252 ** 0.5)
    )

    return CompareResponse(
        profile_label=body.profile_label,
        hrp=hrp_result["weights"],
        mv=mv_result["weights"],
        equal_weight=equal_weights,
        hrp_volatility=hrp_result["expected_volatility"],
        mv_volatility=mv_result["expected_volatility"],
        equal_weight_volatility=round(eq_vol, 6),
    )


# ---------------------------------------------------------------------------
# /optimize — Pydantic models
# ---------------------------------------------------------------------------

class OptimizeRequest(BaseModel):
    profile_label: str
    tickers: list[str] | None = None

    @field_validator("profile_label")
    @classmethod
    def validate_profile_label(cls, v: str) -> str:
        if v not in VALID_PROFILE_LABELS:
            raise ValueError(
                f"Invalid profile_label '{v}'; "
                f"expected one of {sorted(VALID_PROFILE_LABELS)}"
            )
        return v


class OptimizeResponse(BaseModel):
    algorithm: str
    weights: dict[str, float]
    expected_return: float | None
    expected_volatility: float
    sharpe_ratio: float | None
    risk_contributions: dict[str, float]
    optimizer_version: str
    solver_status: str
    ucits_tickers_used: list[str]
    fallback_tickers_applied: list[str]
    recommendation_id: str
    market_data_hash: str


# ---------------------------------------------------------------------------
# /optimize endpoint
# ---------------------------------------------------------------------------

@app.post("/optimize", response_model=OptimizeResponse)
@limiter.limit("10/minute")
def optimize_portfolio(
    request: Request, body: OptimizeRequest, _: str = Depends(verify_api_key)
) -> OptimizeResponse:
    """
    Run HRP portfolio optimization for a given risk profile.
    """
    tickers = body.tickers or get_primary_tickers()
    cluster_map = get_cluster_map()

    try:
        loader = ValidatedDataLoader()
        prices, report = loader.load(
            tickers=tickers,
            start=START_DATE,
            end=END_DATE,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {e}")

    try:
        result: OptimizationResult = optimize(
            prices=prices,
            profile=body.profile_label,
            cluster_map=cluster_map,
            ucits_tickers=report.ucits_tickers_used,
            fallback_tickers=list(report.fallback_tickers_applied.keys()),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimizer failed: {e}")

    try:
        conn = init_db(DB_PATH)
        save_market_snapshot(conn, prices, report)
        rec_id = str(uuid.uuid4())
        save_recommendation(conn, {
            "id": rec_id,
            "user_id": "anonymous",
            "data_fetch_timestamp": datetime.now(timezone.utc).isoformat(),
            "questionnaire_snapshot": "{}",
            "profile_label": body.profile_label,
            "profile_confidence": 1.0,
            "profile_model_version": "rule_based_v1",
            "tickers_used": tickers,
            "ucits_tickers_used": report.ucits_tickers_used,
            "fallback_tickers_applied": dict(report.fallback_tickers_applied),
            "data_window_start": report.date_range[0].isoformat(),
            "data_window_end": report.date_range[1].isoformat(),
            "market_data_hash": report.market_data_hash,
            "nan_count_pre_clean": 0,
            "nan_count_post_clean": 0,
            "optimizer_version": result["optimizer_version"],
            "weights_raw_hrp": result["weights"],
            "weights_final": result["weights"],
            "risk_metrics": {
                "expected_volatility": result["expected_volatility"],
                "risk_contributions": result["risk_contributions"],
            },
            "cluster_structure": {},
            "stress_scenarios": {},
            "llm_model": "none",
            "system_prompt_hash": "none",
            "ground_truth_json_hash": "none",
            "llm_response_raw": "none",
            "llm_response_validated": "none",
        })
        conn.close()
    except Exception as e:
        logger.warning("DB persist failed: %s", e)

    return OptimizeResponse(
        algorithm=result["algorithm"],
        weights=result["weights"],
        expected_return=result["expected_return"],
        expected_volatility=result["expected_volatility"],
        sharpe_ratio=result["sharpe_ratio"],
        risk_contributions=result["risk_contributions"],
        optimizer_version=result["optimizer_version"],
        solver_status=result["solver_status"],
        ucits_tickers_used=result["ucits_tickers_used"],
        fallback_tickers_applied=result["fallback_tickers_applied"],
        recommendation_id=rec_id,
        market_data_hash=report.market_data_hash,
    )