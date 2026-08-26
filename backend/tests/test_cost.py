import pytest

from app import cost
from app.cost import PRICING, compute_cost, lookup_pricing


def test_known_model_is_priced_per_million_tokens():
    # 1000 * 0.15/1e6 + 500 * 0.60/1e6
    assert compute_cost("gpt-4o-mini", 1000, 500) == pytest.approx(0.00045)


def test_one_million_tokens_costs_the_listed_rate():
    for model, rates in PRICING.items():
        assert compute_cost(model, 1_000_000, 0) == pytest.approx(rates["input"])
        assert compute_cost(model, 0, 1_000_000) == pytest.approx(rates["output"])


def test_zero_tokens_cost_nothing():
    assert compute_cost("gpt-5.6-sol", 0, 0) == 0.0


def test_negative_token_counts_do_not_produce_a_credit():
    assert compute_cost("gpt-5", -1000, -1000) == 0.0


# --- resolving model ids ----------------------------------------------------


def test_dated_release_resolves_to_its_base_model():
    assert lookup_pricing("gpt-4o-mini-2024-07-18") is PRICING["gpt-4o-mini"]
    assert lookup_pricing("gpt-5.6-sol-2026-07-01") is PRICING["gpt-5.6-sol"]
    assert lookup_pricing("o4-mini-2025-04-16") is PRICING["o4-mini"]


def test_longest_prefix_wins_so_mini_does_not_resolve_to_its_parent():
    # "gpt-4o-mini-..." is prefixed by both "gpt-4o" and "gpt-4o-mini".
    assert lookup_pricing("gpt-4o-mini-2024-07-18") is not PRICING["gpt-4o"]
    assert lookup_pricing("gpt-5.4-mini-2026-01-01") is PRICING["gpt-5.4-mini"]
    assert lookup_pricing("gpt-5-nano-2025-08-07") is PRICING["gpt-5-nano"]


def test_a_version_family_never_inherits_from_a_shorter_one():
    """`gpt-5` is a string prefix of `gpt-5.6-sol` but not its base model."""
    for model in ("gpt-5.6-sol", "gpt-5.5", "gpt-5.4", "gpt-5.2", "gpt-5.1"):
        assert lookup_pricing(model) is PRICING[model], model
        assert lookup_pricing(model) is not PRICING["gpt-5"], model


def test_an_unreleased_version_is_unpriced_rather_than_mispriced():
    # A future family must not silently bill at an older family's rate.
    for model in ("gpt-5.9-nova", "gpt-5.7", "gpt-4.2-mini"):
        assert lookup_pricing(model) is None, model
        assert compute_cost(model, 1_000_000, 1_000_000) == 0.0, model


def test_gpt_4_does_not_swallow_the_4o_or_4_1_families():
    assert lookup_pricing("gpt-4o") is PRICING["gpt-4o"]
    assert lookup_pricing("gpt-4.1-nano") is PRICING["gpt-4.1-nano"]
    assert lookup_pricing("gpt-4o-2024-08-06") is PRICING["gpt-4o"]


def test_the_expensive_gpt_4o_snapshot_keeps_its_own_price():
    assert compute_cost("gpt-4o-2024-05-13", 1_000_000, 0) == pytest.approx(5.00)
    assert compute_cost("gpt-4o", 1_000_000, 0) == pytest.approx(2.50)


def test_floating_aliases_are_priced():
    for alias in ("gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"):
        assert lookup_pricing(alias) is not None, alias


def test_reasoning_models_are_priced():
    for model in ("o1", "o1-pro", "o3", "o3-pro", "o3-mini", "o4-mini"):
        assert lookup_pricing(model) is not None, model


# --- unpriced models --------------------------------------------------------


def test_unpriced_model_costs_nothing_rather_than_raising():
    assert compute_cost("llama-3-70b", 5000, 5000) == 0.0
    assert lookup_pricing("llama-3-70b") is None


def test_empty_model_is_unpriced():
    assert compute_cost("", 100, 100) == 0.0
    assert lookup_pricing("") is None


def test_an_unpriced_model_is_reported_once(caplog, monkeypatch):
    monkeypatch.setattr(cost, "_UNPRICED_SEEN", set())

    with caplog.at_level("WARNING", logger="app.cost"):
        for _ in range(5):
            lookup_pricing("mystery-model-9000")

    warnings = [r for r in caplog.records if "mystery-model-9000" in r.getMessage()]
    assert len(warnings) == 1


def test_the_unpriced_cache_cannot_grow_without_bound(monkeypatch):
    """The model name comes from the caller, so it must not be a memory leak."""
    monkeypatch.setattr(cost, "_UNPRICED_SEEN", set())

    for index in range(cost._UNPRICED_SEEN_LIMIT + 50):
        lookup_pricing(f"unknown-model-{index}")

    assert len(cost._UNPRICED_SEEN) <= cost._UNPRICED_SEEN_LIMIT


# --- guarding the table itself ----------------------------------------------


def test_every_entry_is_complete_and_positive():
    for model, rates in PRICING.items():
        # `cached` is optional; the provider does not publish one for every model.
        assert set(rates) <= {"input", "cached", "output"}, model
        assert {"input", "output"} <= set(rates), model
        assert rates["input"] > 0, model
        assert rates["output"] > 0, model


def test_output_is_never_cheaper_than_input():
    """Catches a transcription error that swapped the two columns."""
    for model, rates in PRICING.items():
        assert rates["output"] >= rates["input"], model


# --- prompt-cache discount --------------------------------------------------


def test_cached_tokens_bill_at_the_discounted_rate():
    # gpt-5.6-sol: 1M input at $4.00, cached at $0.40.
    full = compute_cost("gpt-5.6-sol", 1_000_000, 0)
    half_cached = compute_cost("gpt-5.6-sol", 1_000_000, 0, 500_000)

    # 500k at $4/M + 500k at $0.40/M = $2.00 + $0.20
    assert full == pytest.approx(4.00)
    assert half_cached == pytest.approx(2.20)


def test_cached_tokens_are_a_subset_not_an_addition():
    """A fully cached prompt costs the cached rate, not input + cached."""
    assert compute_cost("gpt-5.6-sol", 1_000_000, 0, 1_000_000) == pytest.approx(0.40)


def test_zero_cached_tokens_matches_the_undiscounted_call():
    assert compute_cost("gpt-4o", 1000, 500, 0) == compute_cost("gpt-4o", 1000, 500)


def test_a_model_without_a_cached_rate_gets_no_discount():
    # gpt-5-pro publishes no cached rate, so cached tokens bill in full.
    assert "cached" not in PRICING["gpt-5-pro"]
    assert compute_cost("gpt-5-pro", 1_000_000, 0, 1_000_000) == pytest.approx(15.00)


def test_more_cached_than_total_cannot_produce_a_negative_bill():
    cost_value = compute_cost("gpt-5.6-sol", 1000, 0, 999_999)

    assert cost_value >= 0
    # Clamped to the input total, so it prices as fully cached.
    assert cost_value == pytest.approx(1000 * 0.40 / 1_000_000)


def test_negative_cached_tokens_are_ignored():
    assert compute_cost("gpt-4o", 1000, 0, -500) == compute_cost("gpt-4o", 1000, 0)


def test_cached_rate_is_never_more_than_the_input_rate():
    for model, rates in PRICING.items():
        if "cached" in rates:
            assert rates["cached"] <= rates["input"], model
            assert rates["cached"] > 0, model


def test_savings_are_the_difference_against_the_full_rate():
    # gpt-5.6-sol: $4.00 - $0.40 = $3.60 per 1M cached tokens.
    assert cost.cache_savings("gpt-5.6-sol", 1_000_000) == pytest.approx(3.60)
    assert cost.cache_savings("gpt-5.6-sol", 0) == 0.0


def test_savings_are_zero_where_no_discount_exists():
    assert cost.cache_savings("gpt-5-pro", 1_000_000) == 0.0
    assert cost.cache_savings("unknown-model", 1_000_000) == 0.0


def test_savings_reconcile_with_the_charged_cost():
    """Discounted cost plus savings equals what the call would have cost."""
    charged = compute_cost("gpt-4.1", 100_000, 0, 40_000)
    saved = cost.cache_savings("gpt-4.1", 40_000)

    assert charged + saved == pytest.approx(compute_cost("gpt-4.1", 100_000, 0))
