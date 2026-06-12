"""
backend/llm/narrator.py
========================
LLM Narrator Agent — Claude API client (Phase A scaffold, Week 2).

WHAT THIS FILE DOES:
    This is the engine behind the Chat Advisor page. When a user types a
    question such as "Why is my bond allocation so high?", this module:

        1. Checks the question for prompt injection attacks (pre-call defence)
        2. Serialises the Ground Truth JSON payload into a string
        3. Builds the system prompt by injecting the GT JSON as context
        4. Calls the Claude API with the system prompt + user question
        5. Returns the raw LLM response for the Validator to check (W3)

    This module does NOT validate the response — that is the Validator's job (W3).
    This module does NOT write to the database — that happens in the API layer (W3).

THE 3-STAGE LLM SAFETY PIPELINE (where this module fits):

    Stage 1 — P1/P2/P3 backend  →  produces GroundTruthPayload (JSON)
    Stage 2 — THIS FILE          →  assembles prompt + calls Claude API
    Stage 3 — validator.py (W3)  →  4-step post-generation filter

    The user sees ONLY the output of Stage 3. If the Validator rejects the
    response, a safe static fallback message is shown instead.

WHY STATELESS DESIGN:
    Each call to narrate() is completely independent — no conversation history
    is kept between turns. The full Ground Truth JSON is re-injected on every
    call. This ensures the LLM is always anchored to the current backend data
    and cannot drift away from the ground truth numbers across multiple turns.

W2 SCOPE (what is implemented here — scaffold):
    - NarratorClient class with the complete public interface
    - System prompt assembly via build_system_prompt()
    - Raw Claude API call with correct parameters
    - Returns NarratorResponse (raw text, not yet validated)
    - Structured error handling with NarratorError

W3 SCOPE (not in this file — added next week):
    - Integration with the 4-step Validator (validator.py)
    - Retry logic when the Validator rejects a response
    - DB audit trail persistence (snapshots.save_recommendation)
    - Wiring into the FastAPI POST /advice endpoint

CONSUMED BY:
    - backend/api/main.py          POST /advice endpoint (W3)
    - frontend/app.py              Chat Advisor page (W3 wiring)
    - tests/test_narrator.py       unit tests (W3)

REFERENCES:
    - Design Document v3.1 — Section: LLM Safety & Ground Truth
    - AGENTS.md — Agent 3: LLM Narrator Agent
    - docs/adr/ADR-004-llm-narrator-validator.md
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Generator, Optional

# anthropic is the official Python SDK for the Claude API.
# Listed in pyproject.toml as: anthropic>=0.28.0
# The Anthropic() client reads ANTHROPIC_API_KEY from the environment
# automatically unless we pass api_key= explicitly.
import anthropic

from backend.llm.prompts.system_prompt import MANDATORY_DISCLAIMER, build_system_prompt
from backend.schemas.ground_truth import GroundTruthPayload

# Standard Python logger. Log level is set by the application entry point.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONSTANTS
#
# Named constants instead of magic numbers scattered through the code.
# If a value needs changing, it changes in exactly one place.
# ---------------------------------------------------------------------------

# Claude model version — pinned for reproducibility.
# The audit trail records which model generated each response.
# Update only via an explicit team decision documented in ADR-004.
NARRATOR_MODEL: str = "claude-sonnet-4-6"

# Hard token ceiling enforced by the Claude API itself.
# Rough calculation: 250 words * ~1.3 tokens/word ≈ 325 tokens + buffer = 512.
NARRATOR_MAX_TOKENS: int = 512

# Temperature 0.0 = fully deterministic output.
# Same prompt + same Ground Truth JSON = same response every time.
# Required for reproducibility and to prevent creative paraphrasing of numbers.
NARRATOR_TEMPERATURE: float = 0.0

# Maximum accepted length of user input (characters).
# Legitimate questions are short. Inputs longer than this are likely
# injection attempts hiding instructions after the real question.
MAX_USER_INPUT_CHARS: int = 800

# Returned when the injection pre-check blocks a request.
# Appends the disclaimer because the Validator (W3) will check for it
# even on fallback responses.
INJECTION_FALLBACK: str = (
    "Your question could not be processed. "
    "Please rephrase it more concisely.\n\n"
    + MANDATORY_DISCLAIMER
)

# Returned when the Claude API call raises an unexpected exception.
# The user sees this instead of a Python traceback.
API_ERROR_FALLBACK: str = (
    "A response could not be generated at this time. "
    "Please try again in a moment.\n\n"
    + MANDATORY_DISCLAIMER
)

# Known prompt injection patterns checked before every API call (Layer 1).
# Layer 2 (semantic injection detection) is handled by the Validator in W3.
# Stored as a tuple (immutable) — injection patterns must not change at runtime.
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous",
    "ignore above",
    "disregard",
    "new instruction",
    "system:",
    "assistant:",
    "<system>",
    "</system>",
    "forget your rules",
    "act as",
    "jailbreak",
    "pretend you are",
    "you are now",
    "override",
)


# ---------------------------------------------------------------------------
# DATA CLASSES
#
# @dataclass auto-generates __init__, __repr__, and __eq__ from the annotated
# fields. Cleaner than a plain dict (typed, named, IDE-completable) and
# lighter than a full class with manually written __init__.
# ---------------------------------------------------------------------------

@dataclass
class NarratorResponse:
    """
    Container for the output of a single narrator call.

    Attributes
    ----------
    raw_text : str
        Raw LLM response text, NOT yet validated.
        Pass to the Validator (W3) before displaying to the user.
        On soft failure, contains INJECTION_FALLBACK or API_ERROR_FALLBACK.

    system_prompt_hash : str
        SHA-256 of the assembled system prompt.
        Stored in the DB audit trail to prove which prompt was used.

    ground_truth_hash : str
        SHA-256 of the Ground Truth JSON string.
        Cross-references market_data_hash in the recommendations table.

    model : str
        Claude model identifier used for this call.

    injection_blocked : bool
        True if _is_injection_attempt() blocked the request.
        raw_text contains INJECTION_FALLBACK when this is True.

    api_error : bool
        True if the Claude API call raised an exception.
        raw_text contains API_ERROR_FALLBACK when this is True.
    """

    raw_text: str
    system_prompt_hash: str
    ground_truth_hash: str
    model: str = field(default=NARRATOR_MODEL)
    injection_blocked: bool = field(default=False)
    api_error: bool = field(default=False)


@dataclass
class NarratorError(Exception):
    """
    Raised when NarratorClient is misconfigured (e.g. missing API key).

    NOT raised for soft runtime failures:
        - Injection blocked  →  NarratorResponse(injection_blocked=True)
        - API call failed    →  NarratorResponse(api_error=True)

    NarratorError is only for hard configuration problems that prevent the
    client from functioning at all. It surfaces immediately at startup or
    in tests, not silently at request time.
    """

    message: str
    # default_factory=dict creates a fresh dict per instance.
    # Without it, all instances would share the same dict object — a classic
    # mutable default argument bug in Python.
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"NarratorError: {self.message} | details={self.details}"


# ---------------------------------------------------------------------------
# NarratorClient
# ---------------------------------------------------------------------------

class NarratorClient:
    """
    Calls the Claude API to generate a constrained narrative from a
    Ground Truth JSON payload and a user question.

    DESIGN DECISIONS:
        Stateless:
            Each narrate() call is fully independent. No conversation history
            is maintained. The full Ground Truth JSON is re-injected on every
            call to ensure the LLM always references the current data.

        Never raises on soft failures:
            Injection attempts and API errors return a NarratorResponse with
            a safe fallback text and the relevant flag set to True.
            Only hard misconfiguration (missing API key) raises NarratorError.
            The Chat Advisor page therefore always shows something to the user.

    Parameters
    ----------
    api_key : str, optional
        Anthropic API key. Falls back to ANTHROPIC_API_KEY environment variable.
        Raises NarratorError at construction time if neither is provided.
    model : str
        Claude model identifier. Default: NARRATOR_MODEL.
    max_tokens : int
        Hard token ceiling for narrator output. Default: NARRATOR_MAX_TOKENS.
    temperature : float
        Sampling temperature. Must be 0.0 for deterministic output.

    Raises
    ------
    NarratorError
        If no API key is available at construction time.

    Example
    -------
    >>> from backend.schemas.mock_data import get_mock_payload
    >>> client = NarratorClient()            # reads ANTHROPIC_API_KEY from env
    >>> payload = get_mock_payload("balanced")
    >>> response = client.narrate(payload, "Why is my bond allocation high?")
    >>> response.injection_blocked           # False for normal input
    False
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = NARRATOR_MODEL,
        max_tokens: int = NARRATOR_MAX_TOKENS,
        temperature: float = NARRATOR_TEMPERATURE,
    ) -> None:
        # Prefer explicit argument, fall back to environment variable, then "".
        # os.environ.get() returns None if the variable is absent; we use ""
        # as the default so the truthiness check below works cleanly.
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

        if not resolved_key:
            raise NarratorError(
                message="ANTHROPIC_API_KEY is not set.",
                details={
                    "hint": (
                        "Set the ANTHROPIC_API_KEY environment variable, "
                        "or pass api_key= explicitly to NarratorClient()."
                    )
                },
            )

        # Leading underscore signals "private by convention" — callers should
        # use narrate(), not access self._client directly.
        self._client = anthropic.Anthropic(api_key=resolved_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def narrate(
        self,
        payload: GroundTruthPayload,
        user_message: str,
    ) -> NarratorResponse:
        """
        Generate a constrained natural-language narrative.

        STEP-BY-STEP EXECUTION:

            Step 1 — Injection defence (pre-call)
                Rejects suspiciously long or pattern-matching inputs.
                Returns INJECTION_FALLBACK immediately if triggered.

            Step 2 — Serialise Ground Truth JSON
                payload.model_dump_json(indent=2) converts the Pydantic model
                to a pretty-printed JSON string. This becomes the <CONTEXT>
                block the LLM reads.

            Step 3 — Assemble system prompt
                build_system_prompt() fills all {placeholders} in the template
                with this user's data (Ground Truth JSON + forbidden phrases).

            Step 4 — Compute audit hashes
                SHA-256 of the system prompt and the GT JSON are stored in
                NarratorResponse for later persistence in the DB audit trail.

            Step 5 — Call the Claude API
                Sends the system prompt + user question to Claude.
                Returns a Message object; we extract .content[0].text.

            Step 6 — Return NarratorResponse
                Raw response, not yet validated. The caller (W3 API endpoint)
                passes this to the Validator before showing it to the user.

        Args:
            payload:      Validated GroundTruthPayload. Use get_mock_payload()
                          in Phase A; live backend output in Phase B.
            user_message: Raw question from the Chat Advisor text input.

        Returns:
            NarratorResponse. Never raises — all failures return a response
            with the appropriate flag set and a safe fallback text.
        """
        # ── Step 1: Pre-call injection defence ──────────────────────────
        if self._is_injection_attempt(user_message):
            logger.warning(
                "Prompt injection attempt blocked. Input length=%d chars.",
                len(user_message),
            )
            gt_hash = self._hash(payload.model_dump_json())
            return NarratorResponse(
                raw_text=INJECTION_FALLBACK,
                system_prompt_hash="blocked",
                ground_truth_hash=gt_hash,
                model=self._model,
                injection_blocked=True,
            )

        # ── Step 2: Serialise Ground Truth JSON ─────────────────────────
        # model_dump_json() converts the Pydantic model to a JSON string.
        # indent=2 produces human-readable output — easier to debug and audit.
        ground_truth_json: str = payload.model_dump_json(indent=2)
        forbidden_phrases: list[str] = payload.llm_constraints.forbidden_phrases

        # ── Step 3: Assemble system prompt ──────────────────────────────
        system_prompt: str = build_system_prompt(ground_truth_json, forbidden_phrases)

        # ── Step 4: Compute audit hashes ────────────────────────────────
        # Stored in NarratorResponse → persisted in DB by the W3 API layer.
        system_prompt_hash: str = self._hash(system_prompt)
        ground_truth_hash: str = self._hash(ground_truth_json)

        # ── Step 5: Call the Claude API ─────────────────────────────────
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,    # hard stop enforced by the API
                temperature=self._temperature,  # 0.0 = deterministic output
                system=system_prompt,           # rules + <CONTEXT> block
                messages=[
                    # No conversation history — stateless by design.
                    {"role": "user", "content": user_message},
                ],
            )
            # content[0] is a TextBlock for text-only requests.
            raw_text: str = message.content[0].text

            logger.info(
                "Narrator API call successful — model=%s output_tokens=%d",
                self._model,
                message.usage.output_tokens,
            )

        except anthropic.AuthenticationError as exc:
            # Invalid or expired API key — hard configuration error.
            # Raise so it surfaces immediately in tests and at startup.
            logger.error("Anthropic authentication error: %s", exc)
            raise NarratorError(
                message="Invalid Anthropic API key.",
                details={"original_error": str(exc)},
            ) from exc

        except Exception as exc:  # noqa: BLE001
            # Any other API failure (rate limit, timeout, server error).
            # Return a safe fallback rather than crashing the Chat Advisor page.
            # BLE001 (broad exception catch) is intentional here — the comment
            # above explains why. noqa silences the ruff lint warning.
            logger.error("Anthropic API call failed: %s", exc)
            return NarratorResponse(
                raw_text=API_ERROR_FALLBACK,
                system_prompt_hash=system_prompt_hash,
                ground_truth_hash=ground_truth_hash,
                model=self._model,
                api_error=True,
            )

        # ── Step 6: Return raw response ─────────────────────────────────
        return NarratorResponse(
            raw_text=raw_text,
            system_prompt_hash=system_prompt_hash,
            ground_truth_hash=ground_truth_hash,
            model=self._model,
        )

    def narrate_stream(
        self,
        payload: GroundTruthPayload,
        user_message: str,
    ) -> Generator[str, None, None]:
        """
        Yield text chunks from the Claude API streaming response.

        Same injection defence and prompt assembly as narrate(), but yields
        tokens as they arrive instead of waiting for the full response.
        The caller is responsible for collecting chunks and running validation
        on the complete text after the stream ends.

        Args:
            payload:      Validated GroundTruthPayload.
            user_message: Raw question from the Chat Advisor text input.

        Yields:
            str: Individual text chunks from the streaming response.
                 On injection block, yields the full INJECTION_FALLBACK string
                 as a single chunk. On API error, yields API_ERROR_FALLBACK.
        """
        # ── Injection defence ────────────────────────────────────────────
        if self._is_injection_attempt(user_message):
            logger.warning(
                "Prompt injection attempt blocked. Input length=%d chars.",
                len(user_message),
            )
            yield INJECTION_FALLBACK
            return

        # ── Prompt assembly ──────────────────────────────────────────────
        ground_truth_json: str = payload.model_dump_json(indent=2)
        forbidden_phrases: list[str] = payload.llm_constraints.forbidden_phrases
        system_prompt: str = build_system_prompt(ground_truth_json, forbidden_phrases)

        # ── Streaming API call ───────────────────────────────────────────
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except anthropic.AuthenticationError as exc:
            logger.error("Anthropic authentication error: %s", exc)
            raise NarratorError(
                message="Invalid Anthropic API key.",
                details={"original_error": str(exc)},
            ) from exc

        except Exception as exc:  # noqa: BLE001
            logger.error("Anthropic streaming API call failed: %s", exc)
            yield API_ERROR_FALLBACK

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _is_injection_attempt(user_input: str) -> bool:
        """
        Layer 1 prompt injection defence — fast pre-call heuristic.

        Checks two things:
            1. Input length — anything over MAX_USER_INPUT_CHARS is rejected.
               Real questions are short; injected payloads tend to be long.

            2. Pattern matching — scans lowercase input for known injection
               keywords (e.g. "ignore previous instructions", "act as", etc.).

        Layer 2 (semantic injection, e.g. obfuscated instructions) is handled
        by the Validator in W3.

        Args:
            user_input: Raw string from the Chat Advisor text input widget.

        Returns:
            True if the input should be blocked. False if safe to proceed.
        """
        if len(user_input) > MAX_USER_INPUT_CHARS:
            return True
        lower: str = user_input.lower()
        # any() short-circuits on the first match — efficient for clean inputs.
        return any(pattern in lower for pattern in _INJECTION_PATTERNS)

    @staticmethod
    def _hash(text: str) -> str:
        """
        Return the SHA-256 hex digest of a UTF-8 string.

        Used to create compact fingerprints of the system prompt and Ground
        Truth JSON for the DB audit trail. SHA-256 is:
            - Deterministic: same input always produces the same hash
            - One-way: the original text cannot be recovered from the hash
            - Collision-resistant: different inputs produce different hashes

        Args:
            text: Any Python string.

        Returns:
            64-character lowercase hexadecimal string.

        Example:
            >>> NarratorClient._hash("hello")
            '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
        """
        return hashlib.sha256(text.encode()).hexdigest()
