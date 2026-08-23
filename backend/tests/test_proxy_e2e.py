"""End-to-end tests through the proxy against the mock provider.

The mock stamps every completion with a fresh id, so an id repeating across two
responses proves the second was served from cache rather than forwarded.
"""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import RequestLog

PAYLOAD = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "hello through TAP"}],
}
AUTH = {"Authorization": "Bearer sk-caller-provider-key"}


async def ledger(session) -> list[RequestLog]:
    result = await session.execute(select(RequestLog).order_by(RequestLog.id))
    return list(result.scalars().all())


async def row_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(RequestLog))


# --- pass-through -----------------------------------------------------------


async def test_request_is_forwarded_and_the_body_relayed(client):
    response = await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-4o-mini"
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["prompt_tokens"] > 0


async def test_nothing_is_recorded_while_logging_is_off(client, session):
    await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    assert await row_count(session) == 0


async def test_a_get_passes_through(client):
    response = await client.get("/v1/models", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["object"] == "list"


# --- logging ----------------------------------------------------------------


async def test_a_forwarded_call_is_recorded_with_tokens_and_cost(client, session):
    settings.logging_enabled = True

    await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    row = (await ledger(session))[0]
    assert row.status_code == 200
    assert row.endpoint == "/v1/chat/completions"
    assert row.provider == "openai"
    assert row.model == "gpt-4o-mini"
    assert row.input_tokens > 0
    assert row.output_tokens > 0
    assert row.cost_usd == pytest.approx(
        row.input_tokens * 0.15 / 1e6 + row.output_tokens * 0.60 / 1e6
    )
    assert row.latency_ms > 0
    assert row.cache_hit is False
    assert row.ttft_ms is None


async def test_the_caller_credential_is_never_persisted(client, session):
    settings.logging_enabled = True

    await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    row = (await ledger(session))[0]
    stored = f"{row.request_body} {row.response_body} {row.error}"
    assert "sk-caller-provider-key" not in stored
    assert "uthorization" not in stored


async def test_an_upstream_failure_is_recorded_without_usage(client, session):
    settings.logging_enabled = True

    response = await client.post(
        "/v1/chat/completions",
        json={**PAYLOAD, "model": "fail-gpt-4o"},
        headers=AUTH,
    )

    assert response.status_code == 500
    row = (await ledger(session))[0]
    assert row.status_code == 500
    assert row.input_tokens is None
    assert row.cost_usd is None


# --- auth -------------------------------------------------------------------


async def test_auth_rejects_a_request_with_no_key(client, session):
    settings.auth_enabled = True

    response = await client.post("/v1/chat/completions", json=PAYLOAD)

    assert response.status_code == 401


async def test_auth_rejects_an_unknown_key(client):
    settings.auth_enabled = True

    response = await client.post(
        "/v1/chat/completions", json=PAYLOAD, headers={"Authorization": "Bearer nope"}
    )

    assert response.status_code == 401


async def test_a_valid_key_is_admitted_and_attributed(client, session, issue_key):
    settings.auth_enabled = True
    settings.logging_enabled = True
    plaintext, project = await issue_key()

    response = await client.post(
        "/v1/chat/completions",
        json=PAYLOAD,
        headers={"Authorization": f"Bearer {plaintext}"},
    )

    assert response.status_code == 200
    assert (await ledger(session))[0].project_id == project.id


# --- rate limiting ----------------------------------------------------------


async def test_the_budget_is_enforced_per_key(client, session, issue_key):
    settings.auth_enabled = True
    settings.rate_limit_enabled = True
    first, _ = await issue_key(rate_limit=2)
    second, _ = await issue_key(rate_limit=2)

    codes = [
        (
            await client.post(
                "/v1/chat/completions",
                json=PAYLOAD,
                headers={"Authorization": f"Bearer {first}"},
            )
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]

    # A second key has its own budget.
    other = await client.post(
        "/v1/chat/completions",
        json=PAYLOAD,
        headers={"Authorization": f"Bearer {second}"},
    )
    assert other.status_code == 200


async def test_a_rejected_request_is_not_forwarded_or_recorded(
    client, session, issue_key
):
    settings.auth_enabled = True
    settings.rate_limit_enabled = True
    settings.logging_enabled = True
    plaintext, _ = await issue_key(rate_limit=1)
    headers = {"Authorization": f"Bearer {plaintext}"}

    await client.post("/v1/chat/completions", json=PAYLOAD, headers=headers)
    rejected = await client.post("/v1/chat/completions", json=PAYLOAD, headers=headers)

    assert rejected.status_code == 429
    # The ledger records forwarded traffic only.
    assert await row_count(session) == 1


# --- caching ----------------------------------------------------------------


async def test_an_identical_request_is_served_from_cache(client):
    settings.cache_enabled = True

    first = await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)
    second = await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    assert first.json()["id"] == second.json()["id"]


async def test_a_cache_hit_is_flagged_and_faster(client, session, monkeypatch):
    # The suite strips the mock's latency, which leaves a hit and a miss both
    # sub-millisecond and their ordering down to scheduling noise. Forwarding
    # has to cost something measurable for the comparison to mean anything.
    monkeypatch.setattr("dev.mock_upstream.MOCK_BASE_MS", 50.0)
    settings.cache_enabled = True
    settings.logging_enabled = True

    await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)
    await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)

    miss, hit = await ledger(session)
    assert (miss.cache_hit, hit.cache_hit) == (False, True)
    assert hit.latency_ms < miss.latency_ms
    # A hit still carries usage and cost, taken from the cached body.
    assert hit.input_tokens == miss.input_tokens
    assert hit.cost_usd == pytest.approx(miss.cost_usd)


async def test_a_different_payload_is_a_separate_entry(client):
    settings.cache_enabled = True

    first = await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)
    second = await client.post(
        "/v1/chat/completions",
        json={**PAYLOAD, "messages": [{"role": "user", "content": "different"}]},
        headers=AUTH,
    )

    assert first.json()["id"] != second.json()["id"]


async def test_an_upstream_failure_is_not_cached(client, session):
    settings.cache_enabled = True
    settings.logging_enabled = True
    payload = {**PAYLOAD, "model": "fail-gpt-4o"}

    first = await client.post("/v1/chat/completions", json=payload, headers=AUTH)
    second = await client.post("/v1/chat/completions", json=payload, headers=AUTH)

    assert first.status_code == second.status_code == 500
    # Both were forwarded: a 500 must never be stored and replayed.
    assert [row.cache_hit for row in await ledger(session)] == [False, False]


# --- streaming --------------------------------------------------------------


async def test_a_streamed_response_is_relayed_as_sse(client):
    response = await client.post(
        "/v1/chat/completions", json={**PAYLOAD, "stream": True}, headers=AUTH
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.text.startswith("data: ")
    assert response.text.rstrip().endswith("data: [DONE]")


async def test_streaming_records_ttft_and_usage(client, session):
    settings.logging_enabled = True

    await client.post(
        "/v1/chat/completions", json={**PAYLOAD, "stream": True}, headers=AUTH
    )

    row = (await ledger(session))[0]
    assert row.ttft_ms is not None
    # Time to the first token necessarily precedes the end of the stream.
    assert 0 < row.ttft_ms < row.latency_ms
    assert row.input_tokens > 0
    assert row.output_tokens > 0
    assert row.cost_usd > 0


async def test_a_streamed_request_bypasses_the_cache(client):
    settings.cache_enabled = True
    payload = {**PAYLOAD, "stream": True}

    first = await client.post("/v1/chat/completions", json=payload, headers=AUTH)
    second = await client.post("/v1/chat/completions", json=payload, headers=AUTH)

    assert first.text != second.text, "each stream must be fetched fresh"
