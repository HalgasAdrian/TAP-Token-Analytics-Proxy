from app.providers import DEFAULT_PROVIDER, OpenAIAdapter, get_adapter


def test_chat_completions_usage_is_extracted():
    usage = OpenAIAdapter().extract_usage(
        {
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 120, "completion_tokens": 34},
        }
    )
    assert (usage.model, usage.input_tokens, usage.output_tokens) == (
        "gpt-4o-mini",
        120,
        34,
    )


def test_responses_api_spelling_is_accepted():
    usage = OpenAIAdapter().extract_usage(
        {"model": "gpt-4o", "usage": {"input_tokens": 7, "output_tokens": 9}}
    )
    assert (usage.input_tokens, usage.output_tokens) == (7, 9)


def test_body_without_usage_yields_zeros():
    usage = OpenAIAdapter().extract_usage({"model": "gpt-4o"})
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("gpt-4o", 0, 0)


def test_error_body_yields_zeros_and_no_model():
    usage = OpenAIAdapter().extract_usage({"error": {"message": "bad key"}})
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("", 0, 0)


def test_null_token_counts_are_treated_as_zero():
    usage = OpenAIAdapter().extract_usage(
        {
            "model": "gpt-4o",
            "usage": {"prompt_tokens": None, "completion_tokens": None},
        }
    )
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


def test_non_numeric_and_negative_counts_are_coerced():
    usage = OpenAIAdapter().extract_usage(
        {"model": "gpt-4o", "usage": {"prompt_tokens": "many", "completion_tokens": -5}}
    )
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


def test_non_dict_usage_does_not_raise():
    usage = OpenAIAdapter().extract_usage({"model": "gpt-4o", "usage": "none"})
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


def test_non_dict_body_does_not_raise():
    usage = OpenAIAdapter().extract_usage([])  # type: ignore[arg-type]
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("", 0, 0)


def test_non_string_model_is_normalised():
    usage = OpenAIAdapter().extract_usage(
        {"model": 42, "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    )
    assert usage.model == ""


def test_upstream_url_is_built_under_v1(monkeypatch):
    from app import providers

    monkeypatch.setattr(providers.settings, "upstream_base_url", "https://example.test")
    assert (
        OpenAIAdapter().build_upstream_url("chat/completions")
        == "https://example.test/v1/chat/completions"
    )


def test_unknown_provider_falls_back_to_the_default():
    assert get_adapter("anthropic") is get_adapter(DEFAULT_PROVIDER)


def test_prompt_cache_hits_are_extracted():
    usage = OpenAIAdapter().extract_usage(
        {
            "model": "gpt-5.6-sol",
            "usage": {
                "prompt_tokens": 2000,
                "completion_tokens": 100,
                "prompt_tokens_details": {"cached_tokens": 1024},
            },
        }
    )
    assert usage.input_tokens == 2000
    assert usage.cached_input_tokens == 1024


def test_the_responses_api_details_block_is_accepted():
    usage = OpenAIAdapter().extract_usage(
        {
            "model": "gpt-5",
            "usage": {
                "input_tokens": 500,
                "output_tokens": 20,
                "input_tokens_details": {"cached_tokens": 128},
            },
        }
    )
    assert usage.cached_input_tokens == 128


def test_no_details_block_means_no_cache_hits():
    usage = OpenAIAdapter().extract_usage(
        {"model": "gpt-4o", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    )
    assert usage.cached_input_tokens == 0


def test_a_malformed_details_block_is_ignored():
    for details in ("nope", 7, [], {"cached_tokens": None}, {}):
        usage = OpenAIAdapter().extract_usage(
            {
                "model": "gpt-4o",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "prompt_tokens_details": details,
                },
            }
        )
        assert usage.cached_input_tokens == 0, details
