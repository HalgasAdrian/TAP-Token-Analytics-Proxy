# TAP (Token Analytics Proxy) — Setup

TAP is a transparent proxy in front of an LLM provider (OpenAI by default). It forwards
requests upstream and — once the optional features are turned on — adds auth, caching,
rate limiting, request logging, and a metrics dashboard.

The base proxy works immediately, before any assignment (A1..A10) is implemented, because
all four feature flags default to **off**.

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

Every variable is documented in `.env.example`. The four feature flags
(`AUTH_ENABLED`, `CACHE_ENABLED`, `RATE_LIMIT_ENABLED`, `LOGGING_ENABLED`) default to
`false`, which keeps the base proxy running before any A-assignment is done.

Note: TAP does **not** hold an upstream API key. It uses **pass-through auth** — each caller
sends their own `Authorization` header and TAP relays it upstream unchanged. Keys are never
logged, cached, or persisted.

---

## 3. Run the backend

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

---

## 4. Send a request through the proxy (pass-through)

Point any OpenAI SDK (or curl) at TAP's `/v1` base URL and use **your own** OpenAI key.
This works right away — no assignment needs to be implemented first.

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

TAP forwards the call to `UPSTREAM_BASE_URL` (default `https://api.openai.com`) and returns
the upstream response verbatim.

---

## 5. Run the frontend dashboard

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs on <http://localhost:5173>. If your backend is not on the default
`http://localhost:8000`, set `VITE_API_BASE` before starting Vite:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

Out of the box the dashboard shows the live **Volume** chart plus four
"Not yet implemented — A10" placeholder cards. The placeholders fill in as you complete the
frontend assignments.

---

## 6. Assignment build order (A1..A10)

The base proxy runs with every feature flag off. Implement the assignments in roughly this
order, flipping the matching flag to `true` in `.env` to exercise each one:

| # | File | Flag to enable | What it adds |
|---|---|---|---|
| **A1** | `backend/app/auth.py` | `AUTH_ENABLED=true` | API-key generation/hashing + project resolution (401 on bad key) |
| **A2** | `backend/app/logging_sink.py` | `LOGGING_ENABLED=true` | Persist one `request_logs` row per proxied call |
| **A3** | `backend/app/providers.py` | — | Extract OpenAI token usage from responses |
| **A4** | `backend/app/cost.py` | — | Turn token counts into `cost_usd` |
| **A5** | `backend/app/cache.py` | `CACHE_ENABLED=true` | Redis response cache with TTL |
| **A6** | `backend/app/rate_limit.py` | `RATE_LIMIT_ENABLED=true` | Per-project rate limiting (429 when over) |
| **A7** | `backend/app/metrics.py` | — | Aggregate `request_logs` for the `/metrics/*` endpoints |
| **A8** | `backend/app/proxy.py` | — | Streaming (SSE) passthrough with TTFT |
| **A9** | `frontend/src/hooks/*` | — | TanStack Query hooks for each metric |
| **A10** | `frontend/src/components/*` | — | Recharts chart components (replace placeholders) |

A2, A3, A4, and A7 form the logging → metrics pipeline: enable `LOGGING_ENABLED`, implement
A2/A3/A4 so rows are written with token counts and cost, then A7 + A9 + A10 to surface them
on the dashboard.

Reminder: never log, cache, or persist the `Authorization` header or any API key material.

---

## 7. Notes

- The root `.gitignore` already exists (it ignores `.env`); do not modify it.
- `create_all` builds the tables on startup for dev convenience. Alembic is the intended
  production migration path.
