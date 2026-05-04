"""
Integration tests for the FastAPI /profile endpoint.

Uses FastAPI's built-in TestClient (ASGI, no real HTTP server needed).
These tests verify that the endpoint correctly wires the HTTP layer to
rule_based.profile_user() — not the profiler logic itself (tested in
test_profiler.py by P3).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_responses(letter: str) -> dict[str, str]:
    """Return a complete 10-question response dict with all answers = letter."""
    return {f"Q{i}": letter for i in range(1, 11)}


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------

def test_profile_conservative():
    """All 'a' answers -> CONSERVATIVE (score=0, confidence=1.0)."""
    response = client.post("/profile", json={"responses": _all_responses("a")})
    assert response.status_code == 200
    data = response.json()
    assert data["profile_label"] == "CONSERVATIVE"
    assert data["confidence"] == 1.0
    assert data["low_confidence_flag"] is False
    assert len(data["top_drivers"]) == 3
    assert data["model_version"] == "rule_based_v1"


def test_profile_aggressive():
    """All 'd' answers -> AGGRESSIVE (score=30, confidence=1.0)."""
    response = client.post("/profile", json={"responses": _all_responses("d")})
    assert response.status_code == 200
    data = response.json()
    assert data["profile_label"] == "AGGRESSIVE"
    assert data["confidence"] == 1.0
    assert data["low_confidence_flag"] is False


def test_profile_q7_override():
    """Q7='a' forces CONSERVATIVE regardless of other answers (MiFID II hard rule)."""
    responses = _all_responses("d")  # would be AGGRESSIVE without override
    responses["Q7"] = "a"
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 200
    data = response.json()
    assert data["profile_label"] == "CONSERVATIVE"
    assert data["confidence"] == 1.0


def test_profile_response_schema():
    """Response contains all required fields with correct types."""
    response = client.post("/profile", json={"responses": _all_responses("b")})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["profile_label"], str)
    assert isinstance(data["confidence"], float)
    assert isinstance(data["low_confidence_flag"], bool)
    assert isinstance(data["top_drivers"], list)
    assert isinstance(data["model_version"], str)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

def test_profile_missing_question():
    """Missing a question key -> 422 Unprocessable Entity."""
    responses = _all_responses("a")
    del responses["Q5"]
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 422


def test_profile_invalid_response_letter():
    """Invalid response letter -> 422 Unprocessable Entity."""
    responses = _all_responses("a")
    responses["Q3"] = "z"
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 422


def test_profile_empty_responses():
    """Empty responses dict -> 422 Unprocessable Entity."""
    response = client.post("/profile", json={"responses": {}})
    assert response.status_code == 422

    def test_profile_moderate():
    """Mix of 'b' and 'c' answers -> MODERATE."""
    responses = {f"Q{i}": "b" for i in range(1, 6)}
    responses.update({f"Q{i}": "c" for i in range(6, 11)})
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 200
    data = response.json()
    assert data["profile_label"] == "MODERATE"


def test_profile_borderline_confidence():
    """Borderline score (8-9) -> confidence=0.7 and low_confidence_flag=True."""
    # Score 8: Q1-Q2 = 'c' (2+2=4), Q3-Q10 = 'a' (0x8=0), Q4 reverse 'a'=3
    # Easier: use map_score_to_label directly via a known boundary response set
    # All 'a' except Q1='c'(2) Q2='c'(2) Q4='a'=3(reverse) -> score = 2+2+3+0*7 = 7... 
    # Simplest guaranteed borderline: score 9
    # Q1='d'(3), Q2='c'(2), Q4='a'(3 reverse), rest='a'(0) -> 3+2+3=8... 
    # Use compute_score to find a clean borderline set:
    # Q1='d'(3), Q2='d'(3), Q4='a'(3), rest 'a'(0) -> 3+3+3=9 ✓ borderline
    responses = _all_responses("a")
    responses["Q1"] = "d"  # +3
    responses["Q2"] = "d"  # +3
    # Q4 is reverse-coded: 'a' = 3
    # total = 3+3+3 = 9 -> CONSERVATIVE borderline
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == 0.7
    assert data["low_confidence_flag"] is True