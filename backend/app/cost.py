"""Cost computation for proxied requests.

PRICING UNIT: all prices below are **USD per 1,000,000 tokens**, split into
`"input"` (prompt) and `"output"` (completion) rates.

Pricing changes over time — keep in sync with
https://platform.openai.com/docs/pricing

`compute_cost` is the A4 assignment stub.
"""

from __future__ import annotations

# Prices are USD per 1,000,000 tokens. Placeholder values — see keep-current
# note above; the exact numbers are not the assignment, the arithmetic is (A4).
PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


TOKENS_PER_PRICE_UNIT = 1_000_000


def lookup_pricing(model: str) -> dict[str, float] | None:
    """Return the input/output rates for `model`, or None if it is unpriced.

    Providers return dated model ids (`gpt-4o-mini-2024-07-18`) that will never
    match a PRICING key exactly, so an exact miss falls back to the longest
    PRICING key that prefixes the model. Longest-match matters: `gpt-4o-mini-…`
    must resolve to `gpt-4o-mini`, not to `gpt-4o`.
    """
    if not model:
        return None
    if model in PRICING:
        return PRICING[model]

    prefixes = [key for key in PRICING if model.startswith(key)]
    if not prefixes:
        return None
    return PRICING[max(prefixes, key=len)]


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost of a call, or 0.0 when the model has no known price.

    An unpriced model is not an error — TAP proxies arbitrary OpenAI-compatible
    upstreams, so it records the call at zero cost rather than dropping it.
    """
    pricing = lookup_pricing(model)
    if pricing is None:
        return 0.0

    billed_input = max(0, input_tokens) * pricing["input"]
    billed_output = max(0, output_tokens) * pricing["output"]
    return (billed_input + billed_output) / TOKENS_PER_PRICE_UNIT
