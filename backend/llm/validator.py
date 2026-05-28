"""
backend/llm/validator.py
========================
LLM Validator Agent — 5-step post-generation safety filter.

Pipeline:
    Step 1 — Forbidden phrases check
    Step 2 — Allowed numbers check  (hallucination detection)
    Step 3 — Disclaimer presence check
    Step 4 — Prompt injection defence (semantic, post-generation)
    Step 5 — EU awareness check for US-trained profiler

Consumed by:
    - backend/api/main.py    POST /advice endpoint (W3)
    - tests/test_validator.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from backend.llm.prompts.system_prompt import MANDATORY_DISCLAIMER

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUMBER_TOLERANCE: float = 0.02          # 2% relative tolerance
SAFE_FALLBACK_MESSAGE: str = (
    "I cannot provide a detailed response at this time. "
    "Please consult a qualified financial advisor for personalised advice.\n\n"
    + MANDATORY_DISCLAIMER
)

# Rule 9 (EU Awareness) note. When the profiler is US-centric and the narrator
# omits the required US/EU caveat, the validator appends this note instead of
# discarding an otherwise-valid answer (corrective, not blocking). The text
# itself satisfies _check_eu_awareness_missing (Group A + Group B keywords).
EU_AWARENESS_NOTE: str = (
    "Note: the risk profile was determined using a model trained on US household "
    "data (Federal Reserve Survey of Consumer Finances 2022). European investors "
    "may exhibit systematically different risk preferences."
)

_INJECTION_PATTERNS_SEMANTIC: tuple[str, ...] = (
    "ignore previous",
    "ignore above",
    "disregard",
    "new instruction",
    "forget your rules",
    "act as",
    "jailbreak",
    "pretend you are",
    "you are now",
    "override",
    "system:",
    "assistant:",
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class ValidationFlag(str, Enum):
    FORBIDDEN_PHRASE    = "FORBIDDEN_PHRASE"
    HALLUCINATED_NUMBER = "HALLUCINATED_NUMBER"
    MISSING_DISCLAIMER  = "MISSING_DISCLAIMER"
    INJECTION_DETECTED  = "INJECTION_DETECTED"
    EU_AWARENESS_MISSING = "EU_AWARENESS_MISSING"


@dataclass
class ValidationResult:
    """
    Output of the 5-step validator.

    Attributes
    ----------
    passed : bool
        True if the response passed all checks and is safe to display.
    flags : list[ValidationFlag]
        All checks that failed.
    safe_text : str
        The text to display to the user.
        - If passed=True:  the original (possibly disclaimer-appended) text.
        - If passed=False: SAFE_FALLBACK_MESSAGE.
    disclaimer_appended : bool
        True if the disclaimer was missing and was auto-appended (Step 3).
    eu_note_appended : bool
        True if the EU awareness note was missing and was auto-appended (Step 5).
    """
    passed: bool
    flags: list[ValidationFlag] = field(default_factory=list)
    safe_text: str = ""
    disclaimer_appended: bool = False
    eu_note_appended: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(
    response_text: str,
    allowed_numbers: list[float],
    forbidden_phrases: list[str],
    eu_awareness_required: bool = False,
) -> ValidationResult:
    """
    Run the 5-step validator on a raw LLM response.

    Steps are run in order. Steps 1, 2 and 4 are blocking (return fallback).
    Steps 3 and 5 are corrective (auto-append the disclaimer / EU note, do not
    block).

    Args:
        response_text:    Raw text from NarratorClient.narrate().
        allowed_numbers:  From GroundTruthPayload.llm_constraints.allowed_numbers.
        forbidden_phrases: From GroundTruthPayload.llm_constraints.forbidden_phrases.
        eu_awareness_required: Whether Rule 9 EU awareness check is required.

    Returns:
        ValidationResult with passed flag, list of triggered flags, and safe text.
    """
    flags: list[ValidationFlag] = []

    # Step 1 — Forbidden phrases
    if _check_forbidden_phrases(response_text, forbidden_phrases):
        flags.append(ValidationFlag.FORBIDDEN_PHRASE)
        return ValidationResult(passed=False, flags=flags, safe_text=SAFE_FALLBACK_MESSAGE)

    # Step 2 — Hallucinated numbers
    if _check_hallucinated_numbers(response_text, allowed_numbers):
        flags.append(ValidationFlag.HALLUCINATED_NUMBER)
        return ValidationResult(passed=False, flags=flags, safe_text=SAFE_FALLBACK_MESSAGE)

    # Step 3 — Disclaimer presence (corrective, not blocking)
    text, appended = _ensure_disclaimer(response_text)
    if appended:
        flags.append(ValidationFlag.MISSING_DISCLAIMER)

    # Step 4 — Post-generation injection detection
    if _check_injection_semantic(response_text):
        flags.append(ValidationFlag.INJECTION_DETECTED)
        return ValidationResult(passed=False, flags=flags, safe_text=SAFE_FALLBACK_MESSAGE)

    # Step 5 — EU Awareness Rule 9 (corrective, not blocking)
    # Required when profiler was trained on US data (SCF 2022).
    # If the narrator omits the US/EU caveat we append the standard note rather
    # than discarding an otherwise-valid answer — the note is inserted just
    # before the mandatory disclaimer so it reads naturally.
    eu_note_appended = False
    if eu_awareness_required and _check_eu_awareness_missing(text):
        flags.append(ValidationFlag.EU_AWARENESS_MISSING)
        if MANDATORY_DISCLAIMER in text:
            text = text.replace(
                MANDATORY_DISCLAIMER,
                EU_AWARENESS_NOTE + "\n\n" + MANDATORY_DISCLAIMER,
                1,
            )
        else:
            text = text + "\n\n" + EU_AWARENESS_NOTE
        eu_note_appended = True

    return ValidationResult(
        passed=True,
        flags=flags,
        safe_text=text,
        disclaimer_appended=appended,
        eu_note_appended=eu_note_appended,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _check_forbidden_phrases(text: str, forbidden_phrases: list[str]) -> bool:
    """Return True (= fail) if any forbidden phrase is found (case-insensitive).

    Single-word phrases use word-boundary matching to avoid false positives on
    substrings (e.g. "invest" must not match "investitore" in Italian responses).
    Multi-word phrases use plain substring matching.
    """
    lower = text.lower()
    for phrase in forbidden_phrases:
        p = phrase.lower()
        if " " in p:
            if p in lower:
                return True
        else:
            if re.search(rf"\b{re.escape(p)}\b", lower):
                return True
    return False


def _extract_numbers(text: str) -> list[float]:
    """
    Extract all numeric values from text.
    Handles: 12, 12.5, 12,5, 12%, -0.08, 0.35

    Percentages are normalised:
        35% -> 0.35

    This avoids treating both 35 and 0.35 as separate numbers.
    """
    pattern = r"-?\d+(?:[.,]\d+)?(?:\s*%)?"
    results = []

    for match in re.findall(pattern, text):
        cleaned = match.replace(",", ".").replace("%", "").strip()
        try:
            val = float(cleaned)

            # Percentages in the LLM text must match decimal values
            # in the Ground Truth JSON. Example: "35%" -> 0.35.
            if "%" in match:
                results.append(val / 100.0)
            else:
                results.append(val)

        except ValueError:
            continue

    return results


def _is_number_allowed(n: float, allowed: list[float]) -> bool:
    """Return True if n is within NUMBER_TOLERANCE of any allowed number."""
    for gt in allowed:
        if abs(gt) < 1e-9:
            if abs(n) < 1e-9:
                return True
        else:
            if abs(n - gt) / abs(gt) <= NUMBER_TOLERANCE:
                return True
    return False


def _check_hallucinated_numbers(text: str, allowed_numbers: list[float]) -> bool:
    """
    Return True (= fail) if any number in the response cannot be matched
    to an allowed number within tolerance.

    The mandatory disclaimer is removed before checking numbers because it
    contains fixed academic/legal text such as "2026", which is not part of
    the financial Ground Truth JSON.

    Small integers like "3 assets", "2 clusters", "1 year" are ignored as
    narrative context.

    Decimal values like 0.35, 0.091 or 0.72 are always checked because they
    are likely to be financial figures from the Ground Truth JSON.
    """
    # Remove the mandatory disclaimer before number validation.
    # Otherwise fixed text such as "USI 2026" may be incorrectly flagged.
    text_to_check = text.replace(MANDATORY_DISCLAIMER, "")

    numbers = _extract_numbers(text_to_check)

    for n in numbers:
        # Ignore small integers used as narrative context.
        # Example: "3 clusters" should not trigger hallucination detection.
        # Decimals such as 0.35 or 0.091 must still be checked.
        if float(n).is_integer() and abs(n) <= 10:
            continue

        # Ignore year-like integers (1900–2100).
        # Years appear in narrative text: "SCF 2022", "MiFID II 2014", etc.
        # They are not financial values from the Ground Truth JSON.
        if float(n).is_integer() and 1900 <= n <= 2100:
            continue

        if not _is_number_allowed(n, allowed_numbers):
            return True

    return False


def _ensure_disclaimer(text: str) -> tuple[str, bool]:
    """
    Check for MANDATORY_DISCLAIMER. If missing, append it.
    Returns (text, was_appended).
    """
    if MANDATORY_DISCLAIMER in text:
        return text, False
    return text + "\n\n" + MANDATORY_DISCLAIMER, True


def _check_injection_semantic(text: str) -> bool:
    """
    Post-generation check: did the LLM echo injection instructions back?
    Looks for known injection patterns in the generated output.
    """
    lower = text.lower()
    return any(pattern in lower for pattern in _INJECTION_PATTERNS_SEMANTIC)


# Keywords the narrator must use to satisfy Rule 9.
# At least ONE keyword from EACH group must appear in the response.
# Group A: identifies the data source (US-centric)
# Group B: identifies the target audience (European investor)

_EU_AWARENESS_KEYWORDS_A: tuple[str, ...] = (
    "scf",
    "survey of consumer finances",
    "federal reserve",
    "us household",
    "united states",
    "us-based",
    "us data",
    "u.s.",
)

_EU_AWARENESS_KEYWORDS_B: tuple[str, ...] = (
    "european",
    "eu investor",
    "europe",
    "hfcs",
)


def _check_eu_awareness_missing(text: str) -> bool:
    """
    Return True (= fail) if the response does not satisfy Rule 9.

    Rule 9 requires that when profiler_us_centric_caveat=True, the LLM
    acknowledges that the risk profiler was trained on US data and that
    European investors may have different risk preferences.

    Both conditions must be present:
        - A reference to the US data source (SCF / Federal Reserve / US household)
        - A reference to European investors or the geographic gap

    Returns True if either group is entirely absent (= rule violated).
    """
    lower = text.lower()
    has_us_reference = any(kw in lower for kw in _EU_AWARENESS_KEYWORDS_A)
    has_eu_reference = any(kw in lower for kw in _EU_AWARENESS_KEYWORDS_B)
    return not (has_us_reference and has_eu_reference)