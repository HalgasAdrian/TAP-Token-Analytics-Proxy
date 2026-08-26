import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import (
    TAP_KEY_HEADER,
    generate_api_key,
    hash_api_key,
    require_auth,
    resolve_auth,
)


def make_request(headers: dict) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in headers.items()
            ],
        }
    )


def test_generated_keys_are_unique_and_long():
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100
    assert all(len(key) >= 40 for key in keys)


def test_hash_is_deterministic_and_hides_the_key():
    key = generate_api_key()
    assert hash_api_key(key) == hash_api_key(key)
    assert key not in hash_api_key(key)
    assert len(hash_api_key(key)) == 64


async def test_valid_key_resolves_to_its_project_and_key(session, issue_key):
    plaintext, project = await issue_key()

    context = await resolve_auth(plaintext, session)

    assert context is not None
    assert context.project.id == project.id
    assert context.api_key.rate_limit == 60


async def test_unknown_key_does_not_resolve(session, issue_key):
    await issue_key()
    assert await resolve_auth("not-a-real-key", session) is None


async def test_revoked_key_does_not_resolve(session, issue_key):
    plaintext, _ = await issue_key(key_active=False)
    assert await resolve_auth(plaintext, session) is None


async def test_deactivating_a_project_revokes_its_keys(session, issue_key):
    plaintext, _ = await issue_key(project_active=False)
    assert await resolve_auth(plaintext, session) is None


async def test_missing_tap_key_header_is_401(session):
    with pytest.raises(HTTPException) as raised:
        await require_auth(make_request({}), session)
    assert raised.value.status_code == 401


async def test_an_empty_tap_key_header_is_401(session):
    with pytest.raises(HTTPException) as raised:
        await require_auth(make_request({TAP_KEY_HEADER: ""}), session)
    assert raised.value.status_code == 401


async def test_a_tap_key_in_authorization_is_not_accepted(session, issue_key):
    """Authorization belongs to the upstream provider, not to TAP."""
    plaintext, _ = await issue_key()

    with pytest.raises(HTTPException) as raised:
        await require_auth(
            make_request({"Authorization": f"Bearer {plaintext}"}), session
        )

    assert raised.value.status_code == 401


async def test_unknown_key_is_401(session):
    with pytest.raises(HTTPException) as raised:
        await require_auth(make_request({TAP_KEY_HEADER: "nope"}), session)
    assert raised.value.status_code == 401


async def test_error_details_never_echo_the_credential(session):
    with pytest.raises(HTTPException) as raised:
        await require_auth(
            make_request({TAP_KEY_HEADER: "super-secret-value"}), session
        )
    assert "super-secret-value" not in str(raised.value.detail)


async def test_a_valid_tap_key_authenticates(session, issue_key):
    plaintext, project = await issue_key()

    context = await require_auth(make_request({TAP_KEY_HEADER: plaintext}), session)

    assert context.project.id == project.id
