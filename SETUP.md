# TAP (Token Analytics Proxy) — Setup

TAP is a transparent proxy in front of an LLM provider (OpenAI by default). It forwards
requests upstream while adding API-key auth, response caching, per-key rate limiting,
request logging, cost accounting, and a metrics dashboard.

Every feature is behind a flag, and all four default to **off** — so the base
pass-through proxy runs the moment the stack is up, and each capability is opt-in.

---

## 1. Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2 (`docker compose`)
- [Node.js](https://nodejs.org/) 18+ and npm (only needed for the frontend dashboard)

---

## 2. Configure the environment

Copy the template and adjust if needed. **Never commit a real `.env`** — only
`.env.example` (placeholders) is tracked.

```bash
cp .env.example .env
```

Every variable is documented in `.env.example`.

Note: TAP does **not** hold an upstream API key. It uses **pass-through auth** — each
caller sends their own provider `Authorization` header and TAP relays it upstream
unchanged. Provider keys are never logged, cached, or persisted.

---

## 3. Run the stack

```bash
docker compose up --build
```

This starts three services:

- **api** — the FastAPI proxy on <http://localhost:8000>
- **postgres** — request-log storage
- **redis** — cache + rate-limit counters

The `api` service waits for Postgres and Redis to become healthy before starting.

Verify it is up:

- Health check: <http://localhost:8000/health> → `{"status": "ok"}`
- Interactive API docs: <http://localhost:8000/docs>

The Compose file is the **development** orchestration: it mounts `backend/app` and runs
uvicorn with `--reload`, so edits apply without a rebuild. The image built by
`backend/Dockerfile` (baked-in source, no reload) is the production artifact.

---

## 4. Send a request through the proxy

Point any OpenAI SDK (or curl) at TAP's `/v1` base URL. With `AUTH_ENABLED=false`
(the default) no TAP key is needed — just your own provider key.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",   # TAP proxy, not api.openai.com
    api_key="sk-...your-own-key...",        # relayed upstream unchanged
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello through TAP!"}],
)
print(resp.choices[0].message.content)
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-...your-own-key..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello through TAP!"}]
  }'
```

Streaming works the same way — add `"stream": true` and TAP relays the SSE chunks
incrementally, recording time-to-first-token.

---

## 5. Try it without a provider key

A fake OpenAI-compatible upstream ships under Compose's `dev` profile, so the whole
pipeline can be exercised with no API key and no provider spend:

```bash
docker compose --profile dev up --build
```

Then point TAP at it in `.env` and restart the api service:

```
UPSTREAM_BASE_URL=http://mock-upstream:9000
```

The mock returns realistic completions with token usage, supports streaming, and has
two testing hooks: a model prefixed `fail-` returns a 500, and one prefixed `slow-`
adds latency.

To populate the dashboard immediately, seed synthetic history:

```bash
docker compose exec api python -m dev.seed --hours 48 --requests 2400 --truncate
```

---

## 6. Enable the features

Flip the flag in `.env` and restart the api service (`docker compose up -d api`).

| Flag | Adds | Notes |
|---|---|---|
| `LOGGING_ENABLED` | one `request_logs` row per forwarded call | Prerequisite for every dashboard metric |
| `AUTH_ENABLED` | TAP-issued API keys, 401 on an unknown key | Issue a key first — see below |
| `CACHE_ENABLED` | Redis response cache with TTL | `CACHE_TTL_SECONDS` controls expiry |
| `RATE_LIMIT_ENABLED` | per-key request budgets, 429 when over | Budget comes from the key's `rate_limit` |

Related settings: `CACHE_TTL_SECONDS`, `DEFAULT_RATE_LIMIT`,
`RATE_LIMIT_WINDOW_SECONDS`, `UPSTREAM_TIMEOUT_SECONDS`, `CORS_ORIGINS`, `LOG_LEVEL`.

### Issuing API keys

With `AUTH_ENABLED=true`, callers must present a **TAP-issued** key (their provider key
still rides along to the upstream). Keys are created with the admin CLI:

```bash
docker compose exec api python -m app.cli create-project --name "My App"
docker compose exec api python -m app.cli issue-key --project-id 1 --name prod
```

The plaintext key is printed **once** — only its SHA-256 hash is stored, so it cannot
be recovered. If it is lost, revoke it and issue another:

```bash
docker compose exec api python -m app.cli list-projects
docker compose exec api python -m app.cli list-keys
docker compose exec api python -m app.cli revoke-key --id 1
```

Deactivating a project revokes every key it issued.

---

## 7. Run the frontend dashboard

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs on <http://localhost:5173> and shows request volume, cost by model,
latency percentiles, cache hit rate, and error rate, with a granularity selector
(minute → month). If your backend is not on the default `http://localhost:8000`, set
`VITE_API_BASE` before starting Vite:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

Charts read from `/metrics/*`, which requires `LOGGING_ENABLED=true` and at least one
proxied request (or seeded rows) to show anything.

---

## 8. Notes and current limitations

- `create_all` builds the tables on startup for dev convenience. Alembic is the
  intended production migration path and is not yet wired up.
- The `/metrics/*` endpoints are **unauthenticated**. That is fine on localhost, but
  they expose aggregated traffic data — put them behind auth or a private network
  before exposing TAP publicly.
- The ledger records *forwarded* traffic. Requests rejected at the auth or rate-limit
  gate short-circuit before logging, so a 429 storm does not appear in the error-rate
  metric — deliberate, since a row per rejected request turns a flood into unbounded
  database growth.
- The response cache is content-addressed and therefore **shared across projects**: an
  identical prompt from a different project is a hit. That is what makes it save money;
  namespace the key by project id in `cache_key` if you need tenant isolation.
- Never log, cache, or persist the `Authorization` header or any API key material.
