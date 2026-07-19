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


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    # ============================================================
    # ASSIGNMENT: A4 compute cost
    # ------------------------------------------------------------
    # Implement: look up per-token pricing for `model` in PRICING and return the total
    #            USD cost for the given input/output token counts.
    # Why:       turns raw token counts into the cost_usd stored per request and charted.
    # Done when: gpt-4o-mini with known token counts returns the expected USD value and
    #            an unknown model is handled without crashing.
    # Reference: https://platform.openai.com/docs/pricing
    #            https://docs.python.org/3/library/functions.html#float
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A4 compute cost")
