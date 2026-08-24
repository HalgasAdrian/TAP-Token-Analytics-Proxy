# Setting up TAP

This walks you through getting TAP running on your machine, sending a request
through it, and seeing the dashboard. You don't need an OpenAI key. A fake
OpenAI is included.

If you just want to know what TAP is, read [README.md](README.md) first.

---

## 1. What you need installed

- [Docker](https://docs.docker.com/get-docker/), with Docker Compose v2 (check
  with `docker compose version`)
- [Node.js](https://nodejs.org/) 18 or newer, only for the dashboard

You don't need Python installed. The backend runs inside Docker.

---

## 2. Create your .env file

```bash
cp .env.example .env
```

The defaults work as-is, so you can move on. Every setting is explained by a
comment in the file.

Two things worth knowing:

- **`.env` is not committed, and shouldn't be.** Only `.env.example` is in git.
- **TAP does not store an OpenAI key.** Each caller sends their own OpenAI key
  in the `Authorization` header, and TAP passes it straight through. TAP never
  logs it, caches it, or saves it.

---

## 3. Start it

```bash
docker compose --profile dev up -d
```

That starts four containers:

| Container | What it is | Port |
| --- | --- | --- |
| `api` | TAP itself | 8000 |
| `postgres` | Stores the request rows | internal |
| `redis` | Cache and rate limit counters | internal |
| `mock-upstream` | The fake OpenAI | 9000 |

`api` waits for Postgres and Redis to be ready before it starts, then runs the
database migrations, then starts the server.

Check it worked:

```bash
docker compose ps                        # all four should say Up
curl localhost:8000/health               # {"status": "ok"}
curl localhost:8000/health/ready         # database and redis both "ok"
```

If something looks wrong, the logs are the place to look:

```bash
docker compose logs api -f
```

### Two things that confuse people

**`localhost:8000/` returns 404, and that's correct.** In development the
dashboard is served separately by Vite on port 5173 (step 6). Only the
production Docker image bundles the dashboard into the API.

**Editing Python files doesn't need a restart.** Compose mounts `backend/app`
into the container and runs the server with `--reload`. Editing `.env` *does*
need a restart: `docker compose up -d api`.

---

## 4. Send a request through it

`.env.example` ships with `AUTH_ENABLED=false`, so no TAP key is needed yet.

### With curl

```bash
curl localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello through TAP!"}]
  }'
```

You'll get back a fake completion from `mock-upstream`, in the same shape
OpenAI uses.

### With the OpenAI Python SDK

The only change is `base_url`. Everything else stays the same.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",   # TAP, not api.openai.com
    api_key="sk-anything-while-using-the-mock",
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello through TAP!"}],
)
print(resp.choices[0].message.content)
```

### Streaming

Add `"stream": true`. TAP passes the chunks through as they arrive and records
how long the first chunk took (`ttft_ms`).

```bash
curl -N localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"Hi"}]}'
```

One gotcha: if you pipe this into something that stops early, like `head`, the
row doesn't get saved. TAP writes the row when the stream finishes, and cutting
the connection means it never does. Let it run to `data: [DONE]`.

### See what got recorded

```bash
docker compose exec postgres psql -U tap -d tap \
  -c "select id, model, status_code, cache_hit, input_tokens, output_tokens, cost_usd, latency_ms, ttft_ms from request_logs order by id desc limit 5;"
```

### Try the cache

Send the exact same request twice. The response `id` will be identical the
second time, because the second answer came from Redis. In the table above the
second row will have `cache_hit = t` and a much smaller `latency_ms`.

### Try the rate limiter

The default budget is 60 requests per minute. Send 65 and watch the last few
come back as 429:

```bash
for i in $(seq 1 65); do
  curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"$i\"}]}"
done | sort | uniq -c
```

---

## 5. The fake OpenAI

`mock-upstream` answers like OpenAI does, with realistic token counts, but it
never contacts anyone and costs nothing. It has three hooks for testing:

| What you send | What happens |
| --- | --- |
| a model starting with `fail-` | returns a 500 |
| a model starting with `slow-` | adds about a second of delay |
| `"stream": true` | sends SSE chunks, ending with a usage chunk |

So `"model": "fail-gpt-4o"` is how you check that errors get recorded properly.

To point TAP at the real OpenAI instead, change one line in `.env` and restart:

```
UPSTREAM_BASE_URL=https://api.openai.com
```

```bash
docker compose up -d api
```

Then callers need to send a real OpenAI key in the `Authorization` header.

---

## 6. Run the dashboard

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. There are five charts: request volume, cost by
model, latency percentiles, cache hit rate, and error rate. The dropdown at the
top right changes the time bucket, from minute up to month.

Vite forwards `/v1` and `/metrics` to port 8000 for you, so there's no CORS
setup and no API URL to configure.

### Filling the charts with data

An empty database means empty charts. Two ways to fix that.

Send a bunch of real requests through the loop in step 4, or generate fake
history instantly:

```bash
docker compose exec api python -m dev.seed --hours 48 --requests 2400 --truncate
```

That writes 2,400 rows spread over the last 48 hours, with a believable mix of
models, cache hits, and errors. `--truncate` clears `request_logs` first, so
don't use it if you want to keep what's there.

---

## 7. API keys

Setting `AUTH_ENABLED=true` in `.env` (then `docker compose up -d api`) means
callers must send a TAP-issued key. This is how you attribute calls to a
project and give different callers different rate limits.

Create a project and issue a key:

```bash
docker compose exec api python -m app.cli create-project --name "My App"
docker compose exec api python -m app.cli issue-key --project-id 1 --name prod
```

The key is printed once. Only its hash is stored, so it cannot be looked up
later. Copy it somewhere safe. If you lose it, revoke it and issue another.

Then use it:

```bash
curl localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <the-key-you-just-got>" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hi"}]}'
```

Other commands:

```bash
docker compose exec api python -m app.cli list-projects
docker compose exec api python -m app.cli list-keys
docker compose exec api python -m app.cli revoke-key --id 1
docker compose exec api python -m app.cli issue-key --project-id 1 --name ci --rate-limit 10
```

Marking a project inactive revokes every key belonging to it.

### One thing to be aware of

With `AUTH_ENABLED=true`, the `Authorization` header is read as your *TAP* key,
and it's also the header that gets forwarded to OpenAI. Against the fake
provider that's fine, because it ignores credentials. Against the real OpenAI
the forwarded TAP key would be rejected. So right now, pick one: auth on with
the mock, or auth off against real OpenAI. Giving the two keys separate headers
is the fix, and it hasn't been done yet.

---

## 8. Running the tests

```bash
docker compose exec api pytest
docker compose exec api ruff check .
docker compose exec api ruff format --check .
```

139 tests, about 4 seconds.

For the dashboard:

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Together those are exactly what CI runs, minus the Docker image builds.

### How the tests are set up

They run against a real Postgres and a real Redis, not fakes. The metrics
queries use `date_trunc`, `percentile_cont`, and JSONB, and no stand-in gets
those right.

To avoid wiping your development data, the tests use a separate database called
`tap_test` and Redis database 1 instead of 0. `conftest.py` refuses to start if
the database name doesn't end in `_test`, or if Redis is pointed at database 0.
It creates `tap_test` itself the first time you run it.

The tests come in three groups:

| Group | What it means | Examples |
| --- | --- | --- |
| Unit | Plain functions, no database | cost maths, cache keys, parsing token counts out of a stream |
| Integration | Real Postgres and Redis | key lookup, rate limit counters, the five metrics queries |
| End to end | A whole request through the real proxy | `test_proxy_e2e.py` |

The end-to-end tests are the ones to read first if you want to understand what
TAP promises. They mount the fake OpenAI directly into the test, so there's no
network involved at all.

Useful while working:

```bash
docker compose exec api pytest tests/test_proxy_e2e.py   # one file
docker compose exec api pytest -k cache                  # anything with "cache" in the name
docker compose exec api pytest -x                        # stop at the first failure
docker compose exec api pytest -v                        # print every test name
```

---

## 9. Changing the database schema

Alembic handles this. Don't use `create_all`: it won't alter a table that
already exists, and two containers starting at once will trip over each other.

```bash
# after editing app/models.py
docker compose exec api alembic revision --autogenerate -m "add a column"
docker compose exec api alembic upgrade head
```

Compose runs `alembic upgrade head` on startup, so a fresh checkout is
migrated automatically.

There's a test that compares `models.py` against the migrations and fails if
they've drifted apart. So if you forget to generate a migration, CI catches it
instead of production.

---

## 10. Deleting old rows

`request_logs` is the only thing here that grows forever, and the stored request
and response bodies are most of its size. Two settings keep it in check:

- `MAX_BODY_BYTES` (default 16 KB) replaces any body bigger than that with a
  small marker recording its real size. The row survives, so the charts still
  work.
- `LOG_RETENTION_DAYS` (default 30) is how old a row has to be before
  `prune-logs` will delete it.

```bash
docker compose exec api python -m app.cli prune-logs --dry-run   # count only
docker compose exec api python -m app.cli prune-logs             # actually delete
```

In production a GitHub Actions workflow (`.github/workflows/prune.yml`) runs
this once a week.

---

## 11. Deploying

The production Docker image serves the API *and* the built dashboard from the
same origin. One thing to deploy, no CORS, and no API URL compiled into the
JavaScript.

Postgres and Redis are hosted services rather than containers, so the app holds
no data of its own and can be shut down without losing anything.

### Setting it up

1. **Postgres.** Create a project on [Neon](https://neon.com). Take the
   connection string and change the beginning to `postgresql+asyncpg://`,
   keeping `?ssl=require` on the end.
2. **Redis.** Create a database on [Upstash](https://upstash.com) and use its
   `rediss://` URL. Only the cache and rate limit counters live here, so losing
   it isn't a disaster.
3. **Fly.** Run `fly launch --no-deploy` (the committed `fly.toml` already has
   the settings), then set the secrets and deploy:

```bash
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://...neon.tech/tap?ssl=require" \
  REDIS_URL="rediss://...upstash.io:6379" \
  DASHBOARD_PASSWORD="$(openssl rand -base64 24)" \
  METRICS_TOKEN="$(openssl rand -hex 32)"

fly deploy
```

`fly.toml` runs `alembic upgrade head` once per deploy, before the new machines
start taking traffic.

### Who can see the dashboard

`/metrics` and the dashboard are protected by `app/access.py`. There are two
ways in:

- `DASHBOARD_PASSWORD` over HTTP Basic. This is for browsers. The browser shows
  a login box and then remembers it, which means no password has to be built
  into the JavaScript.
- `METRICS_TOKEN` as a bearer token. This is for scripts.

`/v1/*` isn't affected, since it has its own API key check. `/health` stays open
so Fly can check the machine is alive.

If you set neither, the dashboard and metrics are open to anyone who can reach
the server, and a warning is logged at startup.

### What it costs

Roughly $3 to $15 a month. One `shared-cpu-1x` 512MB machine is $3.32, and Neon
and Upstash have free tiers that a small setup fits inside.

`fly.toml` sets `min_machines_running = 0`, so the machine suspends when nobody
is using it. That's most of the saving. The trade-off is that the first request
after a quiet spell waits for the machine to wake up.

Avoid Fly's own Managed Postgres for this. Its cheapest plan is $38 a month,
which is more than everything else combined.
