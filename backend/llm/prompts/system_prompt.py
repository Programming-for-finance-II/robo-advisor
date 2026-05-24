"""
backend/llm/prompts/system_prompt.py
=====================================
System prompt for the LLM Narrator agent.

WHAT THIS FILE DOES:
    Defines the rules of engagement for the Claude LLM used in the Chat
    Advisor page. Rather than forwarding the user's question to Claude
    directly, we inject a system prompt that constrains the model to:
        1. Act as a narrator (not a financial advisor)
        2. Reference only numbers from the Ground Truth JSON (no hallucination)
        3. Never use forbidden advisory language
        4. Respond in the same language the user writes in (adaptive)
        5. Always append the mandatory educational disclaimer

WHY THIS MATTERS:
    LLMs can hallucinate — confidently stating numbers or facts not in their
    input. In a financial context this is potentially illegal under MiFID II
    Article 25. By anchoring every response to a backend-computed JSON payload
    and validating output before display, we make hallucination structurally
    harder, not just prompt-dependent.

    This implements the "Narrator, not Calculator" pattern (design doc v3.1):
        Backend   = calculates and owns the ground truth numbers
        LLM       = narrates what those numbers mean in plain language
        Validator = verifies the LLM did not stray outside the numbers (W3)

CONSUMED BY:
    - backend/llm/narrator.py      injects runtime values and calls the API
    - backend/llm/validator.py     checks disclaimer presence by string match (W3)
    - tests/test_validator.py      verifies each rule is enforced (W3)

REFERENCES:
    - Design Document v3.1 — Section: LLM Safety & Ground Truth
    - MiFID II Directive 2014/65/EU, Article 25 — Suitability assessment
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# MANDATORY_DISCLAIMER
#
# Appended verbatim to the end of every LLM response.
#
# Defined as a module-level constant (not inside a function) so that:
#   - narrator.py injects the exact text into the system prompt template
#   - validator.py (W3) checks for the exact same string in the response
#
# If the two modules used different strings, a single character difference
# (e.g. a missing period) would make every response fail the disclaimer
# check. One constant, shared by both — no drift possible.
# ---------------------------------------------------------------------------

MANDATORY_DISCLAIMER: str = (
    "This is an educational prototype developed in an academic context "
    "(USI, Programming in Finance II 2026). No content constitutes financial "
    "advice under MiFID II or any other applicable regulatory framework. "
    "Market data may be inaccurate or delayed.*"
)

# ---------------------------------------------------------------------------
# MAX_RESPONSE_WORDS
#
# Soft word limit communicated to the LLM inside the prompt text.
# Claude will try to stay under this, but cannot be technically forced to.
# The hard token ceiling is enforced in the API call (narrator.py: max_tokens).
# ---------------------------------------------------------------------------

MAX_RESPONSE_WORDS: int = 250

# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_TEMPLATE
#
# Plain string template filled at request time via str.format().
# We use str.format() (not an f-string) because the template is defined at
# module import time, while the values to inject only exist at request time.
#
# Placeholders filled by build_system_prompt():
#   {ground_truth_json}     — GroundTruthPayload serialised as JSON
#   {forbidden_phrases}     — comma-separated list from llm_constraints
#   {mandatory_disclaimer}  — MANDATORY_DISCLAIMER constant above
#   {max_words}             — MAX_RESPONSE_WORDS constant above
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE: str = """\
You are the narrator of an AI-powered portfolio optimisation system.
Your role is EXCLUSIVELY to explain the results produced by the quantitative \
backend to the user.
You are NOT a financial advisor. You do NOT give operational instructions.

════════════════════════════════════════════════════════
ABSOLUTE RULES — violating any one causes the response to be discarded
════════════════════════════════════════════════════════

RULE 1 — NO INVENTED NUMBERS
Use ONLY numeric values that appear in the <CONTEXT> block below.
Do not round, estimate, or draw from general knowledge.
If a number is not in <CONTEXT>, do not mention it.

RULE 2 — NO PRESCRIPTIVE ADVICE
Never use the following words or phrases:
  {forbidden_phrases}
Always frame allocations descriptively:
  CORRECT:   "The current allocation reflects a preference for..."
  INCORRECT: "You should...", "I recommend...", "Consider moving..."

RULE 3 — NO REGULATORY COMPLIANCE CLAIMS
Never state that the portfolio "complies with MiFID II", is "suitable",
"safe", "optimal", or "compliant". This is an educational prototype.

RULE 4 — NO ABSOLUTES
Never use: guaranteed, certain, risk-free, infallible, optimal.
Backtest results are historical. Past performance does not predict the future.

RULE 5 — EXPECTED RETURN: HISTORICAL CONTEXT ONLY
If expected_annual_return or sharpe_ratio are present in <CONTEXT>, 
they represent historical averages, NOT forward-looking forecasts.
Always frame them as: "historically, over the backtest period..."
Never extrapolate or imply future performance.
If these fields are null, do not mention them.

RULE 6 — OUT OF CONTEXT: FIXED RESPONSE
If the user asks about anything not covered by the <CONTEXT> block, respond
with exactly:
  "I do not have sufficient data to answer this question accurately."
Do not speculate or draw on general knowledge.

RULE 7 — CLUSTERS: ECONOMIC LANGUAGE, NOT MATHEMATICAL
Describe portfolio clusters in economic terms, not correlation coefficients.
  CORRECT:   "Equity assets tend to move together during periods of market \
optimism."
  INCORRECT: "The intra-cluster correlation is 0.74."

RULE 8 — PROFILE DRIVERS
If <CONTEXT> includes top_drivers from the risk profiler, use them to explain
WHY the user received their particular risk profile classification.
Do not invent additional drivers.

RULE 9 — EU AWARENESS (REQUIRED when profiler_us_centric_caveat is true)
If regulatory_context.profiler_us_centric_caveat is true in <CONTEXT>,
explicitly include the following note in your response.
Write this note ALWAYS IN ENGLISH, even if the rest of the response is in
another language:
  "The risk profile was determined using a model trained on US household data
  (Federal Reserve Survey of Consumer Finances 2022). European investors may
  exhibit systematically different risk preferences."
Paraphrasing is allowed as long as the meaning is equivalent and the English
keywords (Federal Reserve, Survey of Consumer Finances, European) are preserved.

════════════════════════════════════════════════════════
OUTPUT FORMAT
════════════════════════════════════════════════════════

- Language: always respond in English, regardless of the language the user writes in.
- Length: maximum {max_words} words.
- Tone: clear, academic, non-commercial.
- Always close with the following disclaimer, word for word:

{mandatory_disclaimer}

════════════════════════════════════════════════════════
CONTEXT (source of truth — use only this data)
════════════════════════════════════════════════════════

<CONTEXT>
{ground_truth_json}
</CONTEXT>
"""


def build_system_prompt(
    ground_truth_json: str,
    forbidden_phrases: list[str],
) -> str:
    """
    Assemble the final system prompt by injecting runtime values into the template.

    WHAT THIS FUNCTION DOES:
        Fills the {placeholder} markers in SYSTEM_PROMPT_TEMPLATE with the
        two values only available at request time:
            1. ground_truth_json — portfolio data for this specific user
            2. forbidden_phrases — banned words from the payload constraints

    HOW IT IS USED:
        Called once per user request inside narrator.py:
            system_prompt = build_system_prompt(
                payload.model_dump_json(indent=2),
                payload.llm_constraints.forbidden_phrases,
            )
            # Then passed as the system= argument to the Claude API call.

    AUDIT TRAIL:
        narrator.py hashes the return value with SHA-256 and stores it in
        the DB recommendations table (system_prompt_hash field). This lets
        us prove which exact prompt version generated any historical response.

    Args:
        ground_truth_json:  JSON string from GroundTruthPayload.model_dump_json().
                            Becomes the entire <CONTEXT> block in the prompt.
        forbidden_phrases:  List of banned strings from
                            payload.llm_constraints.forbidden_phrases.
                            Example: ["sell", "buy", "guaranteed", "safe", ...]

    Returns:
        Fully assembled system prompt string ready for the Claude API
        system= parameter.

    Example:
        >>> from backend.schemas.mock_data import get_mock_payload
        >>> payload = get_mock_payload("balanced")
        >>> prompt = build_system_prompt(
        ...     ground_truth_json=payload.model_dump_json(),
        ...     forbidden_phrases=payload.llm_constraints.forbidden_phrases,
        ... )
        >>> "RULE 9" in prompt
        True
        >>> "sell" in prompt    # forbidden phrases were injected
        True
    """
    # Convert the forbidden phrases list into a quoted comma-separated string.
    # Input:  ["sell", "buy", "guaranteed"]
    # Output: '"sell", "buy", "guaranteed"'
    # This string is inserted verbatim into Rule 2 of the system prompt.
    phrases_str = ", ".join(f'"{p}"' for p in forbidden_phrases)

    # str.format() substitutes every {key} marker in the template string.
    # A missing key in kwargs raises KeyError immediately — good for catching
    # template/argument mismatches during development and testing.
    return SYSTEM_PROMPT_TEMPLATE.format(
        ground_truth_json=ground_truth_json,
        forbidden_phrases=phrases_str,
        mandatory_disclaimer=MANDATORY_DISCLAIMER,
        max_words=MAX_RESPONSE_WORDS,
    )
