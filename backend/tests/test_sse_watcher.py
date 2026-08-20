"""The SSE watcher must reassemble events across arbitrary chunk boundaries.

Its hard case is a single event arriving split over two reads, which is normal
on a real connection and easy to get wrong.
"""

import json

from app.proxy import _MAX_SSE_RESIDUAL_BYTES, _SseUsageWatcher


def event(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


ROLE = {"choices": [{"delta": {"role": "assistant", "content": ""}}]}
TOKEN = {"choices": [{"delta": {"content": "Hello"}}]}
DONE = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
USAGE = {
    "model": "gpt-4o",
    "choices": [],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
}


def test_usage_envelope_is_captured_from_the_trailing_chunk():
    watcher = _SseUsageWatcher(0.0)
    for payload in (ROLE, TOKEN, DONE, USAGE):
        watcher.feed(event(payload))
    watcher.feed(b"data: [DONE]\n\n")

    assert watcher.usage_envelope is not None
    assert watcher.usage_envelope["usage"]["prompt_tokens"] == 11


def test_event_split_across_two_chunks_is_still_parsed():
    raw = event(USAGE)
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(raw[:20])
    assert watcher.usage_envelope is None
    watcher.feed(raw[20:])

    assert watcher.usage_envelope is not None


def test_event_split_byte_by_byte_is_still_parsed():
    watcher = _SseUsageWatcher(0.0)
    for byte in event(USAGE):
        watcher.feed(bytes([byte]))

    assert watcher.usage_envelope is not None


def test_several_events_in_one_chunk_are_all_consumed():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(event(ROLE) + event(TOKEN) + event(USAGE))

    assert watcher.usage_envelope is not None
    assert watcher.ttft_ms is not None


def test_ttft_is_set_by_the_first_content_token_not_the_role_chunk():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(event(ROLE))
    assert watcher.ttft_ms is None, "the empty role delta is not a token"

    watcher.feed(event(TOKEN))
    assert watcher.ttft_ms is not None


def test_ttft_records_only_the_first_token():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(event(TOKEN))
    first = watcher.ttft_ms
    watcher.feed(event({"choices": [{"delta": {"content": " world"}}]}))

    assert watcher.ttft_ms == first


def test_stream_with_no_usage_leaves_the_envelope_unset():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(event(ROLE) + event(TOKEN) + event(DONE))

    assert watcher.usage_envelope is None


def test_later_usage_chunk_supersedes_an_earlier_one():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(event(USAGE))
    watcher.feed(
        event(
            {"model": "gpt-4o", "usage": {"prompt_tokens": 99, "completion_tokens": 1}}
        )
    )

    assert watcher.usage_envelope["usage"]["prompt_tokens"] == 99


def test_malformed_and_non_data_lines_are_ignored():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(b": keep-alive comment\n\n")
    watcher.feed(b"event: ping\n\n")
    watcher.feed(b"data: {not json}\n\n")
    watcher.feed(b"data: [DONE]\n\n")
    watcher.feed(b"data: \n\n")
    watcher.feed(event(USAGE))

    assert watcher.usage_envelope is not None


def test_json_scalar_payload_is_ignored():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(b"data: 42\n\n")

    assert watcher.usage_envelope is None
    assert watcher.ttft_ms is None


def test_residual_buffer_is_bounded_when_no_delimiter_ever_arrives():
    watcher = _SseUsageWatcher(0.0)
    for _ in range(40):
        watcher.feed(b"x" * 8192)

    assert len(watcher._residual) <= _MAX_SSE_RESIDUAL_BYTES


def test_event_after_an_oversized_run_is_still_parsed():
    watcher = _SseUsageWatcher(0.0)
    watcher.feed(b"x" * (_MAX_SSE_RESIDUAL_BYTES * 2))
    watcher.feed(b"\n\n")
    watcher.feed(event(USAGE))

    assert watcher.usage_envelope is not None
