"""
Rule-based risk tolerance profiler — Phase A.

This module implements the Grable & Lytton (1999) Risk Tolerance Scale on the
10-question questionnaire defined in `docs/questionnaire_schema.md` (v1.0). It is
the always-available baseline of the ML Risk Profiler subsystem: when the GBM
trained on Fed SCF 2022 (Phase B) is unavailable, falling back to this module
keeps the `/profile` endpoint live with deterministic, explainable output.

The output schema (`ProfilerOutput`) is intentionally identical to the schema
returned by the Phase B GBM, so downstream consumers (P1's `/profile` endpoint,
P4's LLM Ground Truth JSON, the DB audit trail) need no code changes when the
backend is swapped.

References
----------
Grable, J. E., & Lytton, R. H. (1999). Financial risk tolerance revisited: The
    development of a risk assessment instrument. Financial Services Review,
    8(3), 163-181.
MiFID II Directive 2014/65/EU, Article 25 — Suitability assessment.
Federal Reserve Board (2022). Survey of Consumer Finances.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# =============================================================================
# Type definitions
# =============================================================================

ProfileLabel = Literal["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]
ResponseLetter = Literal["a", "b", "c", "d"]


class TopDriver(TypedDict):
    """Single feature attribution exposed to the LLM narrator for explainability."""

    feature: str
    importance: float


class ProfilerOutput(TypedDict):
    """Stable output schema shared by Phase A (rule-based) and Phase B (GBM).

    Consumed by:
    - P1's `/profile` endpoint (HTTP response body).
    - P4's LLM Ground Truth JSON (drives narrator explanations).
    - The `recommendations` audit-trail table (`profile_label`,
      `profile_confidence`, `profile_model_version`).
    """

    profile_label: ProfileLabel
    confidence: float
    low_confidence_flag: bool
    top_drivers: list[TopDriver]
    model_version: str


# =============================================================================
# Constants — derived verbatim from docs/questionnaire_schema.md (v1.0).
# Do not edit here without updating the schema document and the ADR.
# =============================================================================

MODEL_VERSION: str = "rule_based_v1"

N_QUESTIONS: int = 10
SCORE_MIN: int = 0
SCORE_MAX: int = 30  # 10 questions x max 3 points per question

# Score-to-label boundaries (inclusive upper bounds), per schema §Scoring.
# 0-7    -> CONSERVATIVE high confidence
# 8-9    -> CONSERVATIVE borderline
# 10-11  -> MODERATE     borderline
# 12-17  -> MODERATE     high confidence
# 18-19  -> MODERATE     borderline
# 20-21  -> AGGRESSIVE   borderline
# 22-30  -> AGGRESSIVE   high confidence
CONSERVATIVE_HIGH_MAX: int = 7
CONSERVATIVE_BORDERLINE_MAX: int = 9
MODERATE_BORDERLINE_LOW_MAX: int = 11
MODERATE_HIGH_MAX: int = 17
MODERATE_BORDERLINE_HIGH_MAX: int = 19
AGGRESSIVE_BORDERLINE_MAX: int = 21

CONFIDENCE_HIGH: float = 1.0
CONFIDENCE_BORDERLINE: float = 0.7

# Q7 override: if the user declares the money is a safety net (option "a"),
# MiFID II suitability requirements cap the profile at CONSERVATIVE regardless
# of the questionnaire total. The override is a hard rule, not a probability.
Q7_OVERRIDE_QUESTION: str = "Q7"
Q7_OVERRIDE_RESPONSE: ResponseLetter = "a"

# Question identifiers (insertion-ordered).
QUESTION_KEYS: tuple[str, ...] = (
    "Q1", "Q2", "Q3", "Q4", "Q5",
    "Q6", "Q7", "Q8", "Q9", "Q10",
)

VALID_RESPONSES: frozenset[str] = frozenset({"a", "b", "c", "d"})

# Score map per question. Q4 is reverse-coded (more dependents -> lower risk
# capacity), all other questions are forward-coded (a=0, b=1, c=2, d=3).
SCORE_MAP: dict[str, dict[str, int]] = {
    "Q1":  {"a": 0, "b": 1, "c": 2, "d": 3},  # age
    "Q2":  {"a": 0, "b": 1, "c": 2, "d": 3},  # income comfort
    "Q3":  {"a": 0, "b": 1, "c": 2, "d": 3},  # liquid runway months
    "Q4":  {"a": 3, "b": 2, "c": 1, "d": 0},  # dependents (REVERSE-CODED)
    "Q5":  {"a": 0, "b": 1, "c": 2, "d": 3},  # investment experience
    "Q6":  {"a": 0, "b": 1, "c": 2, "d": 3},  # theoretical knowledge
    "Q7":  {"a": 0, "b": 1, "c": 2, "d": 3},  # purpose / horizon
    "Q8":  {"a": 0, "b": 1, "c": 2, "d": 3},  # immediate drawdown reaction
    "Q9":  {"a": 0, "b": 1, "c": 2, "d": 3},  # temporal loss composure
    "Q10": {"a": 0, "b": 1, "c": 2, "d": 3},  # self-assessed risk appetite
}

# Domain-friendly feature names, exposed in `top_drivers` so the LLM narrator
# can verbalise drivers in plain language without referring to "Q1, Q2, ...".
QUESTION_TOPICS: dict[str, str] = {
    "Q1":  "age",
    "Q2":  "income_comfort",
    "Q3":  "liquid_runway_months",
    "Q4":  "financial_dependents",
    "Q5":  "investment_experience",
    "Q6":  "financial_knowledge",
    "Q7":  "investment_horizon",
    "Q8":  "drawdown_reaction",
    "Q9":  "temporal_loss_composure",
    "Q10": "self_assessed_risk_appetite",
}

# Heuristic constants for `top_drivers` in Phase A. Rationale documented in
# `_compute_top_drivers`. Replaced by SHAP TreeExplainer values in Phase B.
NEUTRAL_RESPONSE_MIDPOINT: float = 1.5  # midpoint of the [0, 3] response scale
MAX_POSSIBLE_DEVIATION_FROM_NEUTRAL: float = 1.5  # |0 - 1.5| = |3 - 1.5| = 1.5
N_TOP_DRIVERS: int = 3


# =============================================================================
# Public API
# =============================================================================

def profile_user(responses: dict[str, str]) -> ProfilerOutput:
    """Classify a user from their 10-question questionnaire responses.

    Parameters
    ----------
    responses : dict[str, str]
        Mapping ``{"Q1": "a"|"b"|"c"|"d", ..., "Q10": ...}``. All ten keys
        must be present and each value must be one of ``"a"``, ``"b"``,
        ``"c"``, ``"d"``.

    Returns
    -------
    ProfilerOutput
        Profile label, confidence, low-confidence flag, top drivers, and
        model version. Schema is shared with the Phase B GBM profiler.

    Raises
    ------
    ValueError
        If `responses` is missing keys, contains unexpected keys, or
        contains invalid response letters.

    Notes
    -----
    The Q7 override (option "a" -> safety net) is applied *after* score
    computation. When triggered on a non-CONSERVATIVE preliminary label, the
    final label is forced to CONSERVATIVE with `confidence=1.0` because the
    override is a deterministic suitability constraint, not a statistical
    estimate.
    """
    _validate_responses(responses)

    score = _compute_score_unchecked(responses)
    label, confidence = map_score_to_label(score)

    if _is_q7_override_triggered(responses):
        label = "CONSERVATIVE"
        confidence = CONFIDENCE_HIGH

    low_confidence_flag = confidence < CONFIDENCE_HIGH
    top_drivers = _compute_top_drivers(responses, label)

    return ProfilerOutput(
        profile_label=label,
        confidence=confidence,
        low_confidence_flag=low_confidence_flag,
        top_drivers=top_drivers,
        model_version=MODEL_VERSION,
    )


def compute_score(responses: dict[str, str]) -> int:
    """Sum question scores into the total questionnaire score.

    Parameters
    ----------
    responses : dict[str, str]
        Questionnaire responses. Validated before scoring.

    Returns
    -------
    int
        Total score in ``[SCORE_MIN, SCORE_MAX] = [0, 30]``.

    Raises
    ------
    ValueError
        On any malformed input (delegated to `_validate_responses`).
    """
    _validate_responses(responses)
    return _compute_score_unchecked(responses)


def _compute_score_unchecked(responses: dict[str, str]) -> int:
    """Sum question scores assuming `responses` is already validated.

    Internal use only. Public callers must go through `compute_score`. This
    split avoids redundant validation when `profile_user` calls scoring after
    already validating its input ("validate at the boundary").
    """
    total = sum(SCORE_MAP[q][responses[q]] for q in QUESTION_KEYS)
    assert SCORE_MIN <= total <= SCORE_MAX, (
        f"Score {total} fell outside [{SCORE_MIN}, {SCORE_MAX}]; "
        f"this indicates a corrupted SCORE_MAP."
    )
    return total


def map_score_to_label(score: int) -> tuple[ProfileLabel, float]:
    """Map a raw questionnaire score to (label, confidence).

    Implements the boundary table from `docs/questionnaire_schema.md` §Scoring.
    Borderline zones around the inter-class boundaries (8-9 / 10-11 / 18-19 /
    20-21) yield ``confidence = 0.7``; all other scores yield ``confidence = 1.0``.

    Parameters
    ----------
    score : int
        Raw questionnaire score in ``[0, 30]``.

    Returns
    -------
    tuple[ProfileLabel, float]
        ``(label, confidence)``.

    Raises
    ------
    ValueError
        If `score` is outside the valid range.
    """
    if not (SCORE_MIN <= score <= SCORE_MAX):
        raise ValueError(
            f"Score {score} out of range [{SCORE_MIN}, {SCORE_MAX}]"
        )

    if score <= CONSERVATIVE_HIGH_MAX:
        return "CONSERVATIVE", CONFIDENCE_HIGH
    if score <= CONSERVATIVE_BORDERLINE_MAX:
        return "CONSERVATIVE", CONFIDENCE_BORDERLINE
    if score <= MODERATE_BORDERLINE_LOW_MAX:
        return "MODERATE", CONFIDENCE_BORDERLINE
    if score <= MODERATE_HIGH_MAX:
        return "MODERATE", CONFIDENCE_HIGH
    if score <= MODERATE_BORDERLINE_HIGH_MAX:
        return "MODERATE", CONFIDENCE_BORDERLINE
    if score <= AGGRESSIVE_BORDERLINE_MAX:
        return "AGGRESSIVE", CONFIDENCE_BORDERLINE
    return "AGGRESSIVE", CONFIDENCE_HIGH


# =============================================================================
# Internal helpers
# =============================================================================

def _validate_responses(responses: dict[str, str]) -> None:
    """Defensively validate the structure and content of `responses`.

    Raises
    ------
    ValueError
        On any malformed input.
    """
    if not isinstance(responses, dict):
        raise ValueError(
            f"`responses` must be a dict, got {type(responses).__name__}"
        )

    expected = set(QUESTION_KEYS)
    received = set(responses.keys())

    missing = expected - received
    if missing:
        raise ValueError(f"Missing responses for: {sorted(missing)}")

    extra = received - expected
    if extra:
        raise ValueError(f"Unexpected response keys: {sorted(extra)}")

    for q in QUESTION_KEYS:
        r = responses[q]
        if r not in VALID_RESPONSES:
            raise ValueError(
                f"Invalid response '{r}' for {q}; "
                f"expected one of {sorted(VALID_RESPONSES)}"
            )


def _is_q7_override_triggered(responses: dict[str, str]) -> bool:
    """Return True iff the Q7 safety-net override applies."""
    return responses[Q7_OVERRIDE_QUESTION] == Q7_OVERRIDE_RESPONSE


def _compute_top_drivers(
    responses: dict[str, str],
    label: ProfileLabel,
) -> list[TopDriver]:
    """Return the top-3 questions that drove the classification.

    Phase A heuristic (deterministic):
    - CONSERVATIVE -> the three lowest-scoring responses
    - AGGRESSIVE   -> the three highest-scoring responses
    - MODERATE     -> the three responses with the largest absolute deviation
                      from the neutral midpoint (i.e. the most informative
                      contributors regardless of direction)

    `importance` is the absolute deviation of the question score from the
    neutral midpoint, normalised to the **maximum possible** deviation on the
    [0, 3] scale (= 1.5), so values lie in ``[0, 1]``. Normalising against the
    *observed* maximum (instead of the constant 1.5) would inflate importance
    on responses that are uniformly tepid: e.g. ten "b" answers (score 1, dev
    0.5) would all yield importance 1.0 — falsely signalling strong drivers
    when in fact no answer was decisive. The constant denominator avoids this:
    uniform "b" answers correctly produce importance 0.33, signalling that
    the classification rests on weak evidence.

    In Phase B (W3), this function is replaced by a SHAP TreeExplainer call
    against the trained GBM. The output schema (list of `TopDriver`) is
    unchanged so downstream code requires no modification.
    """
    per_q_score: dict[str, int] = {
        q: SCORE_MAP[q][responses[q]] for q in QUESTION_KEYS
    }

    if label == "AGGRESSIVE":
        ranked = sorted(per_q_score.items(), key=lambda kv: -kv[1])
    elif label == "CONSERVATIVE":
        ranked = sorted(per_q_score.items(), key=lambda kv: kv[1])
    else:  # MODERATE
        ranked = sorted(
            per_q_score.items(),
            key=lambda kv: -abs(kv[1] - NEUTRAL_RESPONSE_MIDPOINT),
        )

    top_keys = [q for q, _ in ranked[:N_TOP_DRIVERS]]

    return [
        TopDriver(
            feature=QUESTION_TOPICS[q],
            importance=round(
                abs(per_q_score[q] - NEUTRAL_RESPONSE_MIDPOINT)
                / MAX_POSSIBLE_DEVIATION_FROM_NEUTRAL,
                4,
            ),
        )
        for q in top_keys
    ]
