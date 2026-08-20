from app.cache import CACHE_PREFIX, cache_key

BASE = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}


def test_key_is_prefixed_and_stable():
    assert cache_key(BASE).startswith(CACHE_PREFIX)
    assert cache_key(BASE) == cache_key(BASE)


def test_member_order_does_not_change_the_key():
    reordered = {"messages": BASE["messages"], "model": BASE["model"]}
    assert cache_key(BASE) == cache_key(reordered)


def test_different_temperature_is_a_different_entry():
    assert cache_key({**BASE, "temperature": 0}) != cache_key(
        {**BASE, "temperature": 0.9}
    )


def test_absent_temperature_differs_from_an_explicit_one():
    assert cache_key(BASE) != cache_key({**BASE, "temperature": 0})


def test_streaming_never_collides_with_a_buffered_request():
    # An SSE body is not interchangeable with a JSON one.
    assert cache_key(BASE) != cache_key({**BASE, "stream": True})


def test_different_model_or_messages_change_the_key():
    assert cache_key(BASE) != cache_key({**BASE, "model": "gpt-4o-mini"})
    assert cache_key(BASE) != cache_key(
        {**BASE, "messages": [{"role": "user", "content": "bye"}]}
    )


def test_seed_and_tools_are_part_of_the_key():
    assert cache_key(BASE) != cache_key({**BASE, "seed": 7})
    assert cache_key(BASE) != cache_key({**BASE, "tools": [{"type": "function"}]})


def test_non_semantic_fields_are_excluded():
    for field, value in (
        ("user", "alice"),
        ("metadata", {"tag": "x"}),
        ("store", True),
        ("stream_options", {"include_usage": True}),
    ):
        assert cache_key(BASE) == cache_key({**BASE, field: value}), field


def test_two_callers_sending_the_same_prompt_share_an_entry():
    assert cache_key({**BASE, "user": "alice"}) == cache_key({**BASE, "user": "bob"})


def test_unserialisable_value_does_not_raise():
    assert cache_key({**BASE, "extra": object()}).startswith(CACHE_PREFIX)
