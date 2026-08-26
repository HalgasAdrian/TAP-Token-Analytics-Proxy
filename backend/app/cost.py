"""Per-model cost computation.

Prices are USD per 1,000,000 tokens. Keep in sync with
https://developers.openai.com/api/docs/pricing

Each entry carries `input` and `output` rates, plus `cached` where the provider
publishes a discounted rate for repeated prompt prefixes. A missing `cached`
rate means no discount exists, so those tokens bill at the full input rate.

Note this is the provider's prompt cache, which discounts the input tokens of a
call that still happens. It is unrelated to TAP's own response cache, which
avoids the call entirely.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PRICING: dict[str, dict[str, float]] = {
    # GPT-5.6
    "gpt-5.6-sol": {"input": 4.00, "cached": 0.40, "output": 20.00},
    "gpt-5.6-terra": {"input": 2.00, "cached": 0.20, "output": 12.00},
    "gpt-5.6-luna": {"input": 0.20, "cached": 0.02, "output": 1.20},
    # GPT-5.5
    "gpt-5.5": {"input": 5.00, "cached": 0.50, "output": 30.00},
    "gpt-5.5-pro": {"input": 30.00, "output": 180.00},
    # GPT-5.4
    "gpt-5.4": {"input": 2.50, "cached": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "cached": 0.075, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "cached": 0.02, "output": 1.25},
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00},
    # GPT-5.2
    "gpt-5.2": {"input": 1.75, "cached": 0.175, "output": 14.00},
    "gpt-5.2-pro": {"input": 21.00, "output": 168.00},
    # GPT-5.1
    "gpt-5.1": {"input": 1.25, "cached": 0.125, "output": 10.00},
    # GPT-5
    "gpt-5": {"input": 1.25, "cached": 0.125, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached": 0.005, "output": 0.40},
    "gpt-5-pro": {"input": 15.00, "output": 120.00},
    # GPT-4.1
    "gpt-4.1": {"input": 2.00, "cached": 0.50, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "cached": 0.10, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "cached": 0.025, "output": 0.40},
    # GPT-4o. The 2024-05-13 snapshot is priced above the current alias, so it
    # needs its own entry rather than inheriting.
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
    # o-series reasoning models. Reasoning tokens are already counted in
    # completion_tokens, so they bill at the output rate with no special case.
    "o1": {"input": 15.00, "cached": 7.50, "output": 60.00},
    "o1-pro": {"input": 150.00, "output": 600.00},
    "o3": {"input": 2.00, "cached": 0.50, "output": 8.00},
    "o3-pro": {"input": 20.00, "output": 80.00},
    "o3-mini": {"input": 1.10, "cached": 0.55, "output": 4.40},
    "o4-mini": {"input": 1.10, "cached": 0.275, "output": 4.40},
    # Legacy. `gpt-4-turbo` and `gpt-4` are the floating aliases; without them
    # a caller using the alias rather than a dated id would price at zero.
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-2024-04-09": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-0613": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-1106": {"input": 1.00, "output": 2.00},
    "gpt-3.5-turbo-instruct": {"input": 1.50, "output": 2.00},
    "davinci-002": {"input": 2.00, "output": 2.00},
    "babbage-002": {"input": 0.40, "output": 0.40},
}

TOKENS_PER_PRICE_UNIT = 1_000_000

# Models seen without a price, so the warning fires once each rather than per
# request. Capped because the model name comes from the caller.
_UNPRICED_SEEN: set[str] = set()
_UNPRICED_SEEN_LIMIT = 256


def _warn_unpriced(model: str) -> None:
    if model in _UNPRICED_SEEN:
        return
    if len(_UNPRICED_SEEN) < _UNPRICED_SEEN_LIMIT:
        _UNPRICED_SEEN.add(model)
    logger.warning("no pricing for model %r; recording its cost as 0", model)


def lookup_pricing(model: str) -> dict[str, float] | None:
    """Return rates for `model`, resolving dated releases to their base model."""
    if not model:
        return None
    if model in PRICING:
        return PRICING[model]

    # A dated release is "<base>-<date>", so a prefix only counts when it ends on
    # a hyphen. Matching bare prefixes instead would let "gpt-5" claim
    # "gpt-5.6-sol" and bill a new family at an older family's rate — silently
    # wrong numbers, which are worse than none. Longest match still wins, so
    # "gpt-4o-mini-2024-07-18" resolves to "gpt-4o-mini" and not "gpt-4o".
    candidates = [key for key in PRICING if model.startswith(f"{key}-")]
    if not candidates:
        _warn_unpriced(model)
        return None
    return PRICING[max(candidates, key=len)]


def cached_input_rate(pricing: dict[str, float]) -> float:
    """The discounted prompt-cache rate, or the full rate where none exists."""
    return pricing.get("cached", pricing["input"])


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    """Return the USD cost of a call, or 0.0 for an unpriced model.

    `cached_input_tokens` is the subset of `input_tokens` the provider served
    from its prompt cache — it is counted inside the input total, not alongside
    it, so it is billed at the discounted rate and deducted from the remainder.
    """
    pricing = lookup_pricing(model)
    if pricing is None:
        return 0.0

    input_tokens = max(0, input_tokens)
    # Clamp rather than trust: a provider reporting more cached than total
    # tokens must not produce a negative bill.
    cached = min(max(0, cached_input_tokens), input_tokens)

    billed = (
        (input_tokens - cached) * pricing["input"]
        + cached * cached_input_rate(pricing)
        + max(0, output_tokens) * pricing["output"]
    )
    return billed / TOKENS_PER_PRICE_UNIT


def cache_savings(model: str, cached_input_tokens: int) -> float:
    """USD avoided on `cached_input_tokens` versus paying full input rate."""
    pricing = lookup_pricing(model)
    if pricing is None:
        return 0.0

    discount = pricing["input"] - cached_input_rate(pricing)
    return max(0, cached_input_tokens) * discount / TOKENS_PER_PRICE_UNIT
