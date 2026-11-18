# Deploying background jobs on Railway

Background jobs need one extra Railway service: **Redis**. The API process also runs the job
worker (`RUN_WORKER_IN_PROCESS=true`, the default), so there is no separate worker service yet.

Until `REDIS_URL` is set, the backend answers `POST /jobs` with 503 and the frontend automatically
falls back to the original blocking endpoints. You can deploy the code first and add Redis after,
in either order.

## 1. Add Redis

1. Open the LectureKit project on Railway.
2. **+ New** → **Database** → **Add Redis**. Railway creates a `Redis` service with a private URL.

## 2. Point the backend at it

1. Open the backend service (`lecturekit-production`) → **Variables**.
2. Add a variable using a reference, so it stays correct if Railway rotates the password:

   | Name | Value |
   |---|---|
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |

   Optional:

   | Name | Default | What it does |
   |---|---|---|
   | `WORKER_MAX_JOBS` | `2` | Lectures processed at the same time. Each one makes Claude calls, so keep it small. |
   | `RUN_WORKER_IN_PROCESS` | `true` | Set `false` only if you run a separate worker service (see below). |

3. Railway redeploys. In the deploy logs you should see `Background jobs enabled (Redis connected)`
   and `In-process ARQ worker started`.

## 3. Check it

```bash
API=https://lecturekit-production.up.railway.app
JOB=$(curl -s -X POST $API/jobs -H 'content-type: application/json' \
  -d '{"mode":"student","youtube_url":"https://www.youtube.com/watch?v=VMj-3S1tku0"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')
curl -N $API/jobs/$JOB/events     # events stream in as each stage finishes
```

Then measure before/after with real lectures:

```bash
cd backend
python scripts/measure_ttfc.py --api $API <url1> <url2> <url3>
```

## Postgres + pgvector (result cache, persistent search)

1. **+ New** → **Template** → search **pgvector** → deploy the `pgvector` template
   (`pgvector/pgvector` image on a persistent volume; it generates its own password).
2. On the backend service → **Variables**, add the *private* URL so traffic stays on Railway's
   internal network:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | `${{pgvector.DATABASE_URL_PRIVATE}}` |

3. On redeploy the backend creates the `vector` extension and its tables itself. `GET /health`
   should show `"database": true`, and `GET /metrics` starts counting cache hits.

The template also exposes a public TCP proxy for desktop SQL clients. If you don't need that,
remove the TCP proxy in the pgvector service's **Settings → Networking**.

## Protecting your Anthropic balance (recommended)

Set these on the backend service. Each takes effect on the next deploy.

| Name | Suggested value | What it does |
|---|---|---|
| `DAILY_BUDGET_USD` | `0.50` | Once today's estimated Claude spend (UTC) reaches this, new AI requests get a 503 until midnight UTC. Unset or `0` turns it off. |
| `RATE_LIMIT_PER_HOUR` | `20` (default) | Runs (study kits, audits, maps, translations) per visitor IP per hour. `0` turns it off. |
| `ASK_RATE_LIMIT_PER_HOUR` | `60` (default) | Chat questions per visitor IP per hour. |
| `ANTHROPIC_MAP_MODEL` / `ANTHROPIC_ASK_MODEL` | a Haiku model ID | Runs the long-lecture notes and the chat on a cheaper model. |

`GET /metrics` shows `estimated_usd.today`, `daily_budget` and spend per agent. Estimates use
Sonnet prices unless you set `PRICE_*`, so with cheaper models they read high, which errs on the
safe side for the budget.

## Errors and logs

- Logs are JSON, one line per event, so Railway's log search can filter on fields:
  `@level:error`, `@path:/ask`, `@status:429`, or `@request_id:<id>` to follow one request.
  Every response carries an `X-Request-ID` header to search by.
- Error tracking: create a free Sentry project (platform: FastAPI), then set `SENTRY_DSN` on the
  backend. `/health` shows `"sentry": true` once it's on. Request bodies and cookies are never
  sent. Leave it unset to disable.
- Product analytics: set `NEXT_PUBLIC_POSTHOG_KEY` (and `NEXT_PUBLIC_POSTHOG_HOST` if you're on
  PostHog EU) in Vercel, then redeploy the frontend. Unset, posthog-js isn't even downloaded.

## Later: a separate worker service

You can run the worker on its own (`arq jobs.worker.WorkerSettings`) to scale it independently of the
API. This needs Postgres configured: with `DATABASE_URL` set, vectors live in pgvector, so any
process can write them and the API can read them. (Without it they go to a local ChromaDB
directory that a separate service couldn't see.) Add a second service from the same repo with
start command `arq jobs.worker.WorkerSettings`, give it the same variables, and set
`RUN_WORKER_IN_PROCESS=false` on the API.
