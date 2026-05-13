"""
backend/llm/input_sanitiser.py
================================
Input sanitiser for the /advice endpoint.

Wraps raw user input in a <user_input> tag and applies:
  - Length check (max 500 chars)
  - Keyword blocking (known injection patterns)

This is Layer 1 of the prompt injection defence pipeline.
Layer 2 (semantic check post-generation) is handled by validator.py.

Consumed by:
    - backend/api/main.py    POST /advice endpoint
    - tests/test_sanitiser.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Maximum accepted length of user input (characters).
# Legitimate questions are short. Inputs longer than this are likely
# injection attempts hiding instructions after the real question.
MAX_INPUT_CHARS: int = 500

# Known prompt injection patterns — checked before every API call.
# Stored as a tuple (immutable) — patterns must not change at runtime.
_BLOCKED_PATTERNS: tuple[str, ...] = (
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


@dataclass
class SanitiserResult:
    """
    Output of sanitise().

    Attributes
    ----------
    sanitised_input : str
        The wrapped input ready to pass to NarratorClient.
        Empty string if blocked=True.
    blocked : bool
        True if the input was rejected (too long or injection pattern detected).
    reason : str
        Human-readable reason for blocking. Empty string if blocked=False.
    """

    sanitised_input: str
    blocked: bool = field(default=False)
    reason: str = field(default="")


def sanitise(user_input: str) -> SanitiserResult:
    """
    Sanitise raw user input before passing it to the LLM narrator.

    Steps:
        1. Check length — reject if over MAX_INPUT_CHARS.
        2. Check for known injection patterns — reject if found.
        3. Wrap in <user_input> tag — signals to the LLM that this is
           untrusted user content, not part of the system prompt.

    Args:
        user_input: Raw string from the /advice endpoint request body.

    Returns:
        SanitiserResult with sanitised_input ready for NarratorClient,
        or blocked=True with a reason if the input was rejected.

    Examples:
        >>> result = sanitise("Why is my bond allocation high?")
        >>> result.blocked
        False
        >>> result.sanitised_input
        '<user_input>Why is my bond allocation high?</user_input>'

        >>> result = sanitise("ignore previous instructions")
        >>> result.blocked
        True
    """
    # Step 1 — length check
    if len(user_input) > MAX_INPUT_CHARS:
        return SanitiserResult(
            sanitised_input="",
            blocked=True,
            reason=(
                f"Input too long ({len(user_input)} chars). "
                f"Maximum allowed: {MAX_INPUT_CHARS} chars."
            ),
        )

    # Step 2 — keyword blocking
    lower = user_input.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lower:
            return SanitiserResult(
                sanitised_input="",
                blocked=True,
                reason=f"Blocked pattern detected: '{pattern}'.",
            )

    # Step 3 — wrap in <user_input> tag
    wrapped = f"<user_input>{user_input}</user_input>"
    return SanitiserResult(sanitised_input=wrapped, blocked=False)