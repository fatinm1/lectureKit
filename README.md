# LectureKit

## 60-second demo



https://github.com/user-attachments/assets/995f1709-85bb-4c6b-8cf3-573899152b49



**[Watch or download the demo](https://github.com/fatinm1/lectureKit/releases/download/demo-v1/LectureKit-Demo.mp4)** · 60 seconds

See how a YouTube lecture becomes an outline, summaries, semantic search, flashcards, and translated study material.

**Turn any YouTube lecture into intelligence — instantly.**

LectureKit is a multi-agent AI system built for the **Cloudforce Frontier Internship Hackathon**. Paste any public YouTube lecture URL and get a complete study environment, a private faculty audit, or a curriculum coverage map — powered by six distinct AI agents.

**Live:** https://lecture-kit.vercel.app  
**Backend:** https://lecturekit-production.up.railway.app  
**GitHub:** https://github.com/fatinm1/lectureKit

---

## Three Capabilities. One URL

### Capability 1 — Student

A college student pastes a lecture URL and gets:

- Structured outline with timestamped jump-points back into the video
- Summaries at three depths — 90 seconds, 5 minutes, and full
- 10 flashcards with source timestamp citations
- Semantic search — finds the exact moment in the video that answers any question
- Bilingual support in English, Spanish, French, Bengali, and Arabic

### Capability 2 — Faculty

A faculty member pastes their lecture URL and gets a private audit across:

- Pedagogical quality
- Accessibility
- Equity and inclusion
- Clarity and delivery

Each dimension has a score, strengths, timestamped issues, and specific suggested rewrites. A single top priority fix is highlighted at the top.

### Capability 3 — Provost

A provost pastes multiple lecture URLs and their course learning objectives and gets:

- A curriculum coverage map showing which objectives were covered, partially covered, or missing
- Evidence from the lectures with specific timestamps
- Critical gaps with impact analysis
- Five prioritized recommendations

---

## Architecture — Six AI Agents

### Agent 1 — Transcript Agent

- Fetches transcript via **Supadata API** (primary — handles YouTube bot detection on cloud servers)
- Falls back to **yt-dlp** with multi-proxy support
- Cleans text: strips disfluencies (um/uh), HTML tags, collapses whitespace, deduplicates consecutive phrases
- Chunks into ~500-word segments with precise timestamps
- Validates video ID format before attempting fetch to fail fast on invalid URLs

### Agent 2 — Content Agent

- Uses **Claude Sonnet** via Anthropic SDK
- **Two parallel calls** (background jobs): the three summaries are **streamed** as plain text and shown as Claude writes them, while a second call returns the outline + 10 flashcards as JSON
- **Prompt caching:** both calls share a system prompt holding the transcript (`cache_control: ephemeral`). The structured call starts once the streaming call has begun responding, so it reads the transcript from cache instead of paying for it twice. Token usage, including cache reads, is reported per call in each job's `done` event
- **Stop button:** both calls stream, so pressing Stop closes them within about half a second, which stops generation and billing. Whatever was written so far is kept
- The blocking `/process` fallback still uses a single call
- 4-strategy JSON fallback parser handles markdown fences and preamble text
- Explicit English output regardless of transcript language

### Agent 3 — Search Agent

- Embeds transcript chunks **locally** using `sentence-transformers` `all-MiniLM-L6-v2`
- Stores vectors in **ChromaDB** with cosine distance (one collection per video_id)
- Skips reindexing if collection already exists
- Under 0.02s search latency

### Agent 4 — Translation Agent

- Translates outline, summaries, and flashcards via **Claude Sonnet**
- Supports English, Spanish, French, Bengali, Arabic
- Falls back to two smaller Claude calls only when the single-call output is truncated or unparseable
- Frontend caches translations per language in component state

### Agent 5 — Faculty Agent

- Audits lecture across pedagogy, accessibility, equity, and clarity
- Uses **Claude Sonnet** with max 8000 tokens
- Transcript truncated at 6000 words before sending
- Returns overall score, top priority fix, 4 category audits, 5 prioritized fixes with timestamps and suggested rewrites

### Agent 6 — Provost Agent

- Accepts up to 10 YouTube URLs + learning objectives text
- Truncates each lecture to 4000 words
- Maps objectives to covered/partial/missing with evidence and timestamps
- Handles partial failures gracefully — processes successful URLs and reports which ones failed

---

## Background Jobs and Live Progress

Processing a lecture takes over a minute, mostly waiting on Claude. Instead of holding one HTTP request open for that long:

1. `POST /jobs` validates the URL, enqueues an **ARQ** job in **Redis**, and returns a `job_id` in milliseconds.
2. The worker runs the agents and appends an event to a **Redis Stream** as each stage finishes: `transcript_fetched`, then concurrently `chunks_indexed`, `summary_delta` (summary text as Claude writes it, batched about every 100 ms) → `summaries_ready`, and `outline_ready` → `flashcards_ready`; finally `done`, `failed` or `cancelled`.
3. `GET /jobs/{id}/events` streams those events to the browser as **Server-Sent Events**.
4. Student mode opens `/study` as soon as the transcript is ready. The video player appears first, search becomes usable when indexing finishes (usually before Claude is done), and the outline, summaries and flashcards fill in as they arrive.

Why a Redis Stream rather than pub/sub: every event is kept, so a browser that connects late, refreshes, or drops its connection gets the full history. The stream entry id is used as the SSE `id`, so `EventSource` resumes from `Last-Event-ID` without receiving anything twice.

The worker runs inside the API process by default, so the API and worker share one ChromaDB directory. Jobs are never retried automatically, because a retry would quietly spend Claude credits again. If `REDIS_URL` isn't set, `POST /jobs` returns 503 and the frontend falls back to the blocking endpoints, so the frontend and backend can be deployed in either order. Deployment steps: [docs/deploy-railway.md](docs/deploy-railway.md).

To measure time to first visible content before and after against a live backend:

```bash
cd backend && python scripts/measure_ttfc.py --api <backend-url> <lecture-url> [...]
```

---

## Data Flow

```text
User pastes URL + selects mode
              │
              ▼
   Next.js Frontend (Vercel)
              │
              ▼
FastAPI Backend (Railway EU West)
              │
              ▼
Agent 1: Transcript Agent ◄── Supadata API / yt-dlp
              │
      ┌───────┼─────────┐
      │       │         │
      ▼       ▼         ▼
   Agent 2    Agent 3     Agent 5/6
   Content    Search      Faculty / Provost
  (Claude) (MiniLM+ChromaDB) (Claude)
      │       │               │
      └───┬───┘               │
          │                   │
          ▼                   ▼
    localStorage        localStorage
          │                   │
          ▼                   ▼
       /study        /report or /curriculum
          │                   │
          ▼                   ▼
   YouTube iframe       YouTube iframe
   (seekTo via postMessage)
```

Agent 2 and Agent 3 run in parallel in Student mode. With background jobs, every arrow above becomes an SSE event, and the study page renders each section as soon as its event arrives. Agent 4 (Translation) runs on demand when the user selects a language — separate /translate call, cached per session.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Design | Lumina design system — Playfair Display + Inter |
| Backend | FastAPI, Python 3.11, uvicorn |
| Jobs | ARQ worker + Redis Streams, Server-Sent Events |
| LLM | Claude Sonnet — claude-sonnet-4-6 |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (local) |
| Vector Store | ChromaDB (`CHROMA_DB_PATH`; `/tmp` on Railway is wiped on redeploy, so mount a volume) |
| Transcript | Supadata API (primary) + yt-dlp (fallback) |
| Deployment | Vercel (frontend) + Railway EU West (backend) |

---

## Performance

Measured in production on Nov 17, 2026, with three lectures (19 min, 50 min, 2.5 h):

| Metric | Value |
|--------|-------|
| Time to first content, blocking `/process` (before) | 69–77 s |
| Time to first content, background jobs + SSE | **2.7–3.1 s** |
| Search usable after submit | 4.2–6.4 s |
| Full study kit (single Claude call) | 70–81 s |
| `POST /jobs` server time | 14 ms |
| Semantic search latency | <0.02 seconds |
| Chunks from 2.5hr lecture | 50 |
| Languages supported | 5 |
| Flashcards per lecture | 10 |
| Max Provost lectures | 10 |

---

## Local Development

### Backend

```bash
docker compose up -d            # Redis, for background jobs (optional)
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY and SUPADATA_API_KEY to .env
# Optional: REDIS_URL=redis://localhost:6379 for background jobs + live progress
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Tests

```bash
cd backend
pip install pytest
python -m pytest -q
# Job/SSE tests also need Redis:
TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest -q
```

No API keys or network needed: Claude, transcript fetching and the embedding model are mocked.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| ANTHROPIC_API_KEY | Required for Content, Translation, Faculty, Provost agents |
| ANTHROPIC_MODEL | Claude model (default: claude-sonnet-4-6) |
| SUPADATA_API_KEY | Required for YouTube transcript fetching |
| CORS_ORIGINS | Comma-separated list of allowed frontend origins |
| CHROMA_DB_PATH | Path to ChromaDB storage (default: /tmp/chroma_db) |
| YOUTUBE_COOKIES_BASE64 | Base64-encoded cookies.txt for yt-dlp fallback |
| YTDLP_COOKIE_FILE | Path to decoded cookies file (default: /tmp/cookies.txt) |
| YOUTUBE_PROXY_URL | Primary proxy URL for yt-dlp fallback |
| YOUTUBE_PROXY_URL_1 through _9 | Additional proxy URLs tried in sequence |
| REDIS_URL | Enables background jobs + live progress (unset → blocking endpoints only) |
| RUN_WORKER_IN_PROCESS | Run the ARQ worker inside the API process (default `true`) |
| WORKER_MAX_JOBS | Lectures processed concurrently per worker (default `2`) |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| NEXT_PUBLIC_API_URL | Backend URL (default: http://localhost:8000) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /jobs | Enqueue a student / faculty / provost run; returns `job_id` immediately (202) |
| GET | /jobs/{job_id} | Job status and final result |
| POST | /jobs/{job_id}/cancel | Stop a running student job; keeps what was generated so far |
| GET | /jobs/{job_id}/events | Server-Sent Events progress stream (replays from start or `Last-Event-ID`) |
| POST | /process | Student mode, blocking (fallback when Redis isn't configured) |
| POST | /search | Semantic search for a processed video |
| POST | /translate | Translate study materials to a target language |
| POST | /faculty | Faculty audit report |
| POST | /provost | Provost curriculum map (multiple URLs) |

CORS preflight is handled by FastAPI's `CORSMiddleware` using `CORS_ORIGINS`.

---

## Project Structure

```
lectureKit/
├── backend/
│   ├── main.py                   # FastAPI app, all endpoints, CORS
│   ├── services.py               # Shared agent singletons + error classification
│   ├── budget.py                 # Per-process rate/concurrency guard for AI routes
│   ├── jobs/
│   │   ├── routes.py             # POST /jobs, GET /jobs/{id}, SSE /jobs/{id}/events, lifespan
│   │   ├── pipeline.py           # Student / Faculty / Provost pipelines that emit stage events
│   │   ├── events.py             # Redis Streams job state + event bus
│   │   └── worker.py             # ARQ worker (in-process or `arq jobs.worker.WorkerSettings`)
│   ├── agents/
│   │   ├── transcript_agent.py   # Agent 1: Supadata + yt-dlp + clean + chunk
│   │   ├── content_agent.py      # Agent 2: Claude outline + summaries + flashcards
│   │   ├── search_agent.py       # Agent 3: MiniLM embeddings + ChromaDB
│   │   ├── translate_agent.py    # Agent 4: Claude translation, 5 languages
│   │   ├── faculty_agent.py      # Agent 5: pedagogical audit
│   │   └── provost_agent.py      # Agent 6: curriculum map
│   ├── models/
│   │   └── schemas.py            # Pydantic request/response models
│   ├── tests/                    # pytest suite (Claude, transcripts, embeddings mocked)
│   └── requirements.txt
└── frontend/
    └── app/
        ├── layout.tsx            # Playfair Display font, lumina.css
        ├── page.tsx              # Marketing landing page
        ├── app/page.tsx          # URL input + mode toggle + loading stepper
        ├── study/page.tsx        # Student study dashboard
        ├── report/page.tsx       # Faculty audit report
        ├── curriculum/page.tsx   # Provost curriculum map
        ├── components/
        │   ├── app/
        │   │   ├── ProcessUrlPanel.tsx      # Main input + mode toggle
        │   │   ├── AppWorkspaceNavbar.tsx   # Shared navbar
        │   │   └── AppSubpageHeader.tsx     # Back arrow + page title
        │   └── marketing/                   # Landing page components
    ├── types/
    │   └── lecture.ts            # All TypeScript types
    └── utils/
        ├── format.ts             # Timestamp formatting
        └── jobs.ts               # POST /jobs + EventSource client
```

---

## Key Engineering Decisions

**YouTube bot detection:** Railway cloud IPs are blocked by YouTube. Tried 10 datacenter proxies, cookies, and region changes — all failed. Supadata API handles bot detection on their end and became the primary transcript source.

**Local embeddings:** sentence-transformers all-MiniLM-L6-v2 runs locally on Railway with no external API cost, no rate limits, and under 0.02s search latency after indexing.

**Parallel agent execution:** In Student mode, Agent 2 (Content, network-bound on Claude) and Agent 3 (Search indexing, CPU-bound embeddings) run concurrently in a thread pool once Agent 1's chunks are ready, so total time is max(content, indexing) instead of the sum.

**Non-blocking endpoints:** Every endpoint that calls a blocking agent is a plain `def`, so FastAPI runs it in its threadpool. An `async def` endpoint calling blocking code would freeze the event loop for every other user (a regression test guards this).

**localStorage session management:** Results are stored in localStorage immediately after the API response. Output pages read from localStorage on mount. No database required for hackathon scope.

**YouTube seekTo:** Every timestamp in the app seeks the embedded YouTube player using the iframe postMessage API with enablejsapi=1 and the page origin in the embed URL.

**4-strategy JSON parser:** Claude occasionally wraps responses in markdown fences or adds preamble text. The parser tries: strip fences → extract outermost braces → raw loads → raise with first 200 chars. If all fail, one repair call sends back only the broken output (not the whole transcript).

---

Built by **Fatin Mojumder**.

## Verification and operating limits

Run `cd backend && python -m pytest -q` for the offline suite (parser, repair, schema rejection, URLs, cleaning, search ranking, API concurrency); Claude, transcripts and the embedding model are mocked. The existing frontend smoke script expects a running frontend/backend and can call the configured model, so it is separate from free offline CI.

The multi-agent design is a staged application workflow, not a guarantee of autonomous reasoning or factual correctness. Retrieval latency is not a retrieval-quality score. Evaluate timestamp grounding and retrieval on a labeled set before claiming accuracy. Public demo operators should enforce authenticated usage quotas, concurrency limits, retention policies, and cost monitoring before accepting untrusted workloads at scale. Faculty/curriculum routes are plain `def` endpoints, so FastAPI runs their blocking work in its threadpool instead of on the event loop.

Public AI routes have a per-process rolling budget (default 10 starts/minute, 2 concurrent). Configure `AI_REQUESTS_PER_MINUTE` and `AI_MAX_CONCURRENT` explicitly for the deployment. Rejected requests return 429 without starting provider work. This intentionally bounds the whole demo, not individual identities; multi-worker deployments need a shared external quota and authentication.
