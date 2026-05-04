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
    """Borderline score 9 -> CONSERVATIVE with confidence=0.7 and low_confidence_flag=True.
    
    Q7 must NOT be 'a' to avoid the MiFID II override which forces confidence=1.0.
    Score: Q1='d'(3) + Q2='c'(2) + Q4='a'(3, reverse) + Q7='b'(1) + rest='a'(0) = 9.
    """
    responses = _all_responses("a")
    responses["Q1"] = "d"   # +3
    responses["Q2"] = "c"   # +2
    responses["Q7"] = "b"   # +1, avoids MiFID II override
    # Q4 reverse-coded: 'a' = 3
    # total = 3+2+3+1 = 9 -> CONSERVATIVE borderline
    response = client.post("/profile", json={"responses": responses})
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == 0.7
    assert data["low_confidence_flag"] is True