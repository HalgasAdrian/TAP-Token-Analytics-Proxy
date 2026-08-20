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

## 8. Tests

```bash
docker compose exec api pytest
docker compose exec api ruff check .
```

The suite runs against a real Postgres and Redis — the metrics queries depend on
`date_trunc`, `percentile_cont`, and JSONB — using a dedicated `tap_test` database and
Redis index 1, so a run cannot touch development data. It creates that database itself
on first use.

Three tiers: pure unit tests for cost, usage extraction, cache keys, and the SSE
watcher; integration tests for auth, the limiter, the cache, and the five aggregations;
and end-to-end tests that drive the whole proxy with the mock provider mounted as an
ASGI app, so no socket or provider is involved.

CI runs the same suite plus `ruff`, the frontend typecheck and build, and both Docker
image builds on every push and pull request.

---

## 9. Deploying

The production image serves the API **and** the built dashboard from one origin, so
there is one thing to deploy, no CORS, and no API URL baked into the bundle.

Managed Postgres and Redis are used rather than self-hosted containers, so the app
owns no volume and holds no state — it can scale to zero without losing anything.

### Schema changes

Alembic owns the schema. `create_all` is gone: it never alters an existing table and
races when several instances start at once.

```bash
docker compose exec api alembic upgrade head        # applied automatically on boot
docker compose exec api alembic revision --autogenerate -m "describe the change"
```

A test asserts the models and migrations have not drifted, so forgetting to generate a
revision fails CI rather than production.

### Provisioning

1. **Postgres** — create a project on [Neon](https://neon.com). Take the connection
   string and convert the scheme to `postgresql+asyncpg://`, keeping `?ssl=require`.
2. **Redis** — create a database on [Upstash](https://upstash.com). Use its `rediss://`
   URL. Only the cache and rate-limit counters live here, so losing it is survivable.
3. **Fly** — `fly launch --no-deploy` (the committed `fly.toml` already has the
   config), then set the secrets:

```bash
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://...neon.tech/tap?ssl=require" \
  REDIS_URL="rediss://...upstash.io:6379" \
  DASHBOARD_PASSWORD="$(openssl rand -base64 24)" \
  METRICS_TOKEN="$(openssl rand -hex 32)"
fly deploy
```

`release_command` runs `alembic upgrade head` once per deploy, before the new machines
take traffic.

### Access

The dashboard and `/metrics` are gated by `app/access.py`. `DASHBOARD_PASSWORD` works
over HTTP Basic, which is what lets a browser authenticate without a secret inside the
bundle; `METRICS_TOKEN` is a bearer token for scripts. `/v1/*` is unaffected — it has
its own API-key auth — and `/health` stays public for the platform probe.

With neither set, the dashboard and metrics are open and startup logs a warning.

### Cost

Roughly **$3–15/month**: one `shared-cpu-1x` 512MB machine at $3.32, Neon and Upstash
on their free or usage-based tiers. `auto_stop_machines = "suspend"` with
`min_machines_running = 0` idles compute toward zero, at the cost of a cold start on
the first request after a quiet spell. Avoid Fly's own Managed Postgres — its cheapest
plan is $38/month.

Watch the ledger: it is the only thing that grows. `MAX_BODY_BYTES` caps stored bodies
and `LOG_RETENTION_DAYS` bounds history, enforced by a weekly `prune.yml` workflow or
manually:

```bash
docker compose exec api python -m app.cli prune-logs --dry-run
```

---

## 10. Notes and current limitations

- The ledger records *forwarded* traffic. Requests rejected at the auth or rate-limit
  gate short-circuit before logging, so a 429 storm does not appear in the error-rate
  metric — deliberate, since a row per rejected request turns a flood into unbounded
  database growth.
- The response cache is content-addressed and therefore **shared across projects**: an
  identical prompt from a different project is a hit. That is what makes it save money;
  namespace the key by project id in `cache_key` if you need tenant isolation.
- The rate limiter **fails open**: if Redis is unreachable, requests are allowed and a
  warning is logged. Availability is preferred over enforcement; return `False` in
  `check_rate_limit` to invert that.
- A single Fly machine with `min_machines_running = 0` means no redundancy and a cold
  start after idle. Raise it to 2 for real availability, roughly doubling compute cost.
- Never log, cache, or persist the `Authorization` header or any API key material.
