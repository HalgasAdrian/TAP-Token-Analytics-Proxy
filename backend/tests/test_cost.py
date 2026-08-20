import pytest

from app.cost import PRICING, compute_cost, lookup_pricing


def test_known_model_is_priced_per_million_tokens():
    # 1000 * 0.15/1e6 + 500 * 0.60/1e6
    assert compute_cost("gpt-4o-mini", 1000, 500) == pytest.approx(0.00045)


def test_one_million_input_tokens_costs_the_listed_input_rate():
    for model, rates in PRICING.items():
        assert compute_cost(model, 1_000_000, 0) == pytest.approx(rates["input"])
        assert compute_cost(model, 0, 1_000_000) == pytest.approx(rates["output"])


def test_dated_model_id_resolves_to_its_base_model():
    assert compute_cost("gpt-4o-mini-2024-07-18", 1_000_000, 0) == pytest.approx(0.15)


def test_longest_prefix_wins_so_mini_does_not_resolve_to_gpt_4o():
    # "gpt-4o-mini-..." is prefixed by both "gpt-4o" and "gpt-4o-mini".
    assert lookup_pricing("gpt-4o-mini-2024-07-18") is PRICING["gpt-4o-mini"]


def test_unpriced_model_costs_nothing_rather_than_raising():
    assert compute_cost("llama-3-70b", 5000, 5000) == 0.0
    assert lookup_pricing("llama-3-70b") is None


def test_empty_model_is_unpriced():
    assert compute_cost("", 100, 100) == 0.0
    assert lookup_pricing("") is None


def test_zero_tokens_cost_nothing():
    assert compute_cost("gpt-4o", 0, 0) == 0.0


def test_negative_token_counts_do_not_produce_a_credit():
    assert compute_cost("gpt-4o", -1000, -1000) == 0.0
