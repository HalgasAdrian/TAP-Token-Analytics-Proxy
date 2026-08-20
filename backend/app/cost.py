"""Per-model cost computation.

Prices are USD per 1,000,000 tokens, split into input (prompt) and output
(completion) rates. Keep in sync with https://platform.openai.com/docs/pricing
"""

from __future__ import annotations

PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

TOKENS_PER_PRICE_UNIT = 1_000_000


def lookup_pricing(model: str) -> dict[str, float] | None:
    """Return rates for `model`, resolving dated ids to their base model."""
    if not model:
        return None
    if model in PRICING:
        return PRICING[model]

    # Longest match, so gpt-4o-mini-2024-07-18 resolves to gpt-4o-mini.
    prefixes = [key for key in PRICING if model.startswith(key)]
    if not prefixes:
        return None
    return PRICING[max(prefixes, key=len)]


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost of a call, or 0.0 for an unpriced model."""
    pricing = lookup_pricing(model)
    if pricing is None:
        return 0.0

    billed = (
        max(0, input_tokens) * pricing["input"]
        + max(0, output_tokens) * pricing["output"]
    )
    return billed / TOKENS_PER_PRICE_UNIT
