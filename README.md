# TAP — Token Analytics Proxy

[![CI](https://github.com/HalgasAdrian/TAP-Token-Analytics-Proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/HalgasAdrian/TAP-Token-Analytics-Proxy/actions/workflows/ci.yml)

A proxy that sits between your app and OpenAI and keeps a record of every call.

## What problem this solves

Normally your app calls OpenAI directly. That works, but you can't see much. How
much did last month cost? Which model is the expensive one? How slow are the
calls? How often do they fail? None of that is visible from inside your app
unless you write the tracking code yourself, in every app that makes a call.

TAP moves that work to one place. You point your app at TAP instead of OpenAI.
TAP forwards the request, sends the answer back, and saves a row in a database
describing what happened: which model, how many tokens, what it cost, how long
it took, whether it worked.

Because all the traffic now goes through one place, TAP can do a few more useful
things at the same time:

- **Caching.** If the exact same request comes in twice, the second one is
  answered from Redis instead of OpenAI. You don't pay twice for the same
  answer.
- **Rate limiting.** Each API key gets a budget of requests per minute. Over
  budget gets a 429.
- **API keys.** You can issue your own keys so you know which app or team made
  which calls.
- **A dashboard.** Charts for volume, cost per model, speed, cache hits, and
  errors.

## How a request travels through TAP

![How a request flows through TAP](architecture.svg)

1. **Check the API key.** If auth is on, look up the caller's TAP key in the
   database. Unknown key gets a 401 and nothing else happens.
2. **Check the rate limit.** Count this request against the key's budget in
   Redis. Over budget gets a 429.
3. **Check the cache.** Turn the request body into a hash, and look for that
   hash in Redis. If it's there, send back the stored answer and skip OpenAI
   entirely.
4. **Forward it.** Send the request to OpenAI and wait for the answer.
5. **Send the answer back.** Either all at once, or streamed chunk by chunk if
   the caller asked for streaming.
6. **Save a row.** Work out the token counts and cost, then write it all to
   Postgres. This happens *after* the caller already has their answer, so
   saving the record never slows down the response.

The order matters. The cheap checks come first, so a request that's going to be
rejected gets rejected before TAP does any real work.

## What's in the box

| Part | What it is |
| --- | --- |
| `backend/app/proxy.py` | The proxy itself. Handles `/v1/*`. |
| `backend/app/metrics.py` | Five endpoints under `/metrics/*` that the dashboard reads. |
| `backend/app/auth.py` | Issuing and checking TAP API keys. |
| `backend/app/cache.py` | Reading and writing the Redis cache. |
| `backend/app/rate_limit.py` | Counting requests per key in Redis. |
| `backend/app/cost.py` | Turning token counts into dollars. |
| `backend/app/cli.py` | Admin commands: create a project, issue a key, delete old rows. |
| `backend/dev/mock_upstream.py` | A fake OpenAI you can develop against, so you don't need a real key. |
| `frontend/` | The React dashboard. |

## Tech used

| Layer | Technology |
| --- | --- |
| API and proxy | FastAPI, httpx |
| Language | Python 3.11 |
| Database | PostgreSQL, SQLAlchemy 2.0 (async), asyncpg |
| Cache and rate limit counters | Redis |
| Config | pydantic-settings |
| Dashboard | React, TypeScript, Vite |
| Charts | Recharts |
| Data fetching | TanStack Query |
| Styling | Tailwind CSS |
| Schema changes | Alembic |
| Local setup | Docker Compose |
| Hosting | Fly.io, with Neon for Postgres and Upstash for Redis |

## The database

Three tables.

**`request_logs`** is the important one. One row per forwarded call:

| Column | Meaning |
| --- | --- |
| `created_at` | When the call happened. Indexed, because every chart filters on it. |
| `project_id` | Which project made the call, if auth was on. |
| `model` | Which model was actually billed. |
| `endpoint` | Which path was called, e.g. `/v1/chat/completions`. |
| `status_code` | What OpenAI returned. |
| `input_tokens`, `output_tokens` | Token counts, or NULL if OpenAI didn't report any. |
| `cost_usd` | Tokens multiplied by that model's price. |
| `latency_ms` | How long the whole call took. |
| `ttft_ms` | For streamed calls, how long until the first word arrived. NULL otherwise. |
| `cache_hit` | True if this was answered from Redis instead of OpenAI. |
| `request_body`, `response_body` | The actual JSON, stored as JSONB. |
| `error` | Set when the request never reached OpenAI at all. |

**`projects`** is a name to group keys under. **`api_keys`** holds issued keys.
Keys are stored as a SHA-256 hash, never as plain text, so a stolen database
dump doesn't hand over working keys. This also means a key is shown exactly
once, when you create it. Lose it and you issue a new one.

## The dashboard numbers are all live queries

There is no separate stats table. Every chart is a SQL query over
`request_logs`, run when you load the page:

- **Volume** groups rows into time buckets with `date_trunc`.
- **Cost by model** is a `GROUP BY model` with a `SUM`.
- **Latency** uses Postgres's `percentile_cont` to get the median and the 95th
  percentile.
- **Cache hit rate** and **error rate** are counts divided by totals.

The upside is the charts can never disagree with the raw rows, because they're
reading the raw rows. The downside is that deleting old rows also deletes the
history behind the charts.

## Status

Everything described above is built and working: forwarding, streaming, API
keys, rate limiting, caching, saving rows, the five metrics endpoints, and the
dashboard that reads them.

It's also deployable. Alembic owns the database schema, the dashboard and
metrics sit behind a password, the production Docker image runs as a normal user
with no test tools in it, and one Fly machine serves both the API and the
dashboard against hosted Postgres and Redis. Every push runs the linter, 139
tests, and both Docker builds.

## Known limitations

Worth knowing before you rely on any of this:

- **Rejected requests aren't recorded.** A 401 or a 429 is turned away before
  the row-writing step, so they never show up in the error rate. This is on
  purpose: writing a row for every rejected request would let a flood of them
  fill up the database.
- **The cache is shared between projects.** The cache key is built from the
  request body only, so the same prompt from a different project is a cache
  hit. That's what makes it save money. If you need projects kept separate, add
  the project id to the key in `cache_key`.
- **The rate limiter allows requests through if Redis is down.** Staying up is
  treated as more important than enforcing the limit. If you'd rather block, see
  the comment in `check_rate_limit`.
- **Only three models have prices.** `gpt-4o`, `gpt-4o-mini`, and
  `gpt-3.5-turbo`, in `cost.py`. Anything else records a cost of 0. Add prices
  there as you need them.
- **One machine, scaled to zero.** Cheap, but there's no backup machine and the
  first request after an idle period is slow while the machine wakes up.

## Ideas for later

Roughly in the order I'd do them:

1. Support providers other than OpenAI.
2. Limit by tokens per minute, not just requests per minute.
3. Save daily summary rows, so charts survive deleting old detail rows.
4. Separate cache per project, for setups that need it.

## Getting it running

See [SETUP.md](SETUP.md). It takes about five minutes and doesn't need an OpenAI
key.
