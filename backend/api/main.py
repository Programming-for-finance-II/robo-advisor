# backend/api/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from backend.ml.profiler.rule_based import profile_user, ProfilerOutput

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