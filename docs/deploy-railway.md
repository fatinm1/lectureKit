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

## Later: a separate worker service

You can run the worker on its own (`arq jobs.worker.WorkerSettings`) to scale it independently of the
API. **Don't do this yet:** the worker writes search vectors to ChromaDB on its own disk, and a
separate Railway service has a separate disk, so `/search` on the API wouldn't see them. Roadmap #3
moves vectors into Postgres/pgvector, which removes that coupling. After that, add a second service
from the same repo with start command `arq jobs.worker.WorkerSettings` and set
`RUN_WORKER_IN_PROCESS=false` on the API.
