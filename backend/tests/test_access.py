import base64

from app.config import settings

TOKEN = "metrics-token-abc123"
PASSWORD = "dashboard-secret"


def basic(password: str, username: str = "admin") -> dict:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


async def test_metrics_are_open_when_no_credential_is_configured(client):
    assert (await client.get("/metrics/volume")).status_code == 200


async def test_a_configured_token_is_required(client):
    settings.metrics_token = TOKEN

    assert (await client.get("/metrics/volume")).status_code == 401


async def test_the_correct_bearer_token_is_accepted(client):
    settings.metrics_token = TOKEN

    response = await client.get(
        "/metrics/volume", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200


async def test_a_wrong_bearer_token_is_rejected(client):
    settings.metrics_token = TOKEN

    response = await client.get(
        "/metrics/volume", headers={"Authorization": "Bearer wrong"}
    )

    assert response.status_code == 401


async def test_basic_credentials_are_accepted(client):
    settings.dashboard_password = PASSWORD

    response = await client.get("/metrics/volume", headers=basic(PASSWORD))

    assert response.status_code == 200


async def test_the_username_is_not_checked(client):
    settings.dashboard_password = PASSWORD

    response = await client.get(
        "/metrics/volume", headers=basic(PASSWORD, username="anyone")
    )

    assert response.status_code == 200


async def test_a_wrong_basic_password_is_rejected(client):
    settings.dashboard_password = PASSWORD

    response = await client.get("/metrics/volume", headers=basic("nope"))

    assert response.status_code == 401


async def test_either_credential_suffices_when_both_are_set(client):
    settings.metrics_token = TOKEN
    settings.dashboard_password = PASSWORD

    by_token = await client.get(
        "/metrics/volume", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    by_basic = await client.get("/metrics/volume", headers=basic(PASSWORD))

    assert (by_token.status_code, by_basic.status_code) == (200, 200)


async def test_a_rejection_prompts_the_browser_for_basic_credentials(client):
    settings.dashboard_password = PASSWORD

    response = await client.get("/metrics/volume")

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")


async def test_malformed_basic_headers_do_not_raise(client):
    settings.dashboard_password = PASSWORD

    for header in ("Basic ", "Basic !!!not-base64!!!", "Basic " + "eHg=", "Bearer"):
        response = await client.get(
            "/metrics/volume", headers={"Authorization": header}
        )
        assert response.status_code == 401, header


async def test_every_metrics_route_is_gated(client):
    settings.metrics_token = TOKEN

    for path in ("volume", "cost-by-model", "latency", "cache", "errors"):
        response = await client.get(f"/metrics/{path}")
        assert response.status_code == 401, path


async def test_the_proxy_is_unaffected_by_metrics_credentials(client):
    settings.metrics_token = TOKEN

    response = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer sk-caller-provider-key"},
    )

    assert response.status_code == 200


async def test_health_is_never_gated(client):
    settings.metrics_token = TOKEN
    settings.dashboard_password = PASSWORD

    assert (await client.get("/health")).status_code == 200
