# backend/api/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from backend.ml.profiler.rule_based import ProfilerOutput, profile_user

from datetime import date, datetime, timezone
import uuid

from backend.data.loader import ValidatedDataLoader
from backend.data.universe_config import get_cluster_map, get_primary_tickers
from backend.data.snapshots import init_db, save_market_snapshot, save_recommendation
from backend.optimizer.hrp import OptimizationResult, optimize

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
# ---------------------------------------------------------------------------
# /advice, /compare, /backtest — stubs
# ---------------------------------------------------------------------------

@app.post("/advice")
@limiter.limit("10/minute")
def advice(request: Request) -> None:
    """Generate LLM narrative advice for a portfolio. Stub — W3."""
    raise HTTPException(
        status_code=503,
        detail="LLM advisor not yet available — P4 implementation in W3.",
    )


@app.post("/compare")
@limiter.limit("10/minute")
def compare(request: Request) -> None:
    """Compare HRP vs Markowitz portfolio. Stub — W3."""
    raise HTTPException(
        status_code=503,
        detail="MV comparison not yet available — P2 implementation in W2-W3.",
    )


@app.post("/backtest")
@limiter.limit("10/minute")
def backtest(request: Request) -> None:
    """Run historical backtest on 3 stress scenarios. Stub — W3."""
    raise HTTPException(
        status_code=503,
        detail="Backtest not yet available — P2 implementation in W3.",
    )
   
# ---------------------------------------------------------------------------
# /optimize — Pydantic models
# ---------------------------------------------------------------------------
# Design note: /optimize wires ValidatedDataLoader (P1) + optimize() (P2).
# ASSET_MIN diverges between hrp.py (0.03) and universe_config.py (0.05) —
# flagged to P2 via GitHub issue, to be aligned in W3. Not a blocker.
# expected_return and sharpe_ratio are returned as float by hrp.optimize()
# despite being null in ground_truth.py — flagged to P2, to fix in W3.
# ---------------------------------------------------------------------------

VALID_PROFILE_LABELS = {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
START_DATE = "2023-01-01"
END_DATE = date.today().isoformat()
DB_PATH = "robo_advisor.db"


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
def optimize_portfolio(request: Request, body: OptimizeRequest) -> OptimizeResponse:
    """
    Run HRP portfolio optimization for a given risk profile.

    Accepts profile_label (CONSERVATIVE / MODERATE / AGGRESSIVE) and optional
    tickers override. Calls P2's optimize(), persists result in DB audit trail,
    returns OptimizationResult as JSON.

    DB audit trail: every call writes a row to recommendations and a snapshot
    to market_data_snapshots via snapshots.py.
    """
    # Step 1 — resolve tickers
    tickers = body.tickers or get_primary_tickers()
    cluster_map = get_cluster_map()

    # Step 2 — load and validate market data
    try:
        loader = ValidatedDataLoader()
        prices, report = loader.load(
            tickers=tickers,
            start=START_DATE,
            end=END_DATE,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {e}")

    # Step 3 — run HRP optimizer
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

    # Step 4 — persist to DB audit trail
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
        # DB failure does not block the response — log and continue
        import logging
        logging.getLogger(__name__).warning("DB persist failed: %s", e)

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
