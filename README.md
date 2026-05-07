# LectureKit

**Turn any YouTube lecture into a complete study environment — instantly.**

LectureKit is a multi-agent AI system built for the **Cloudforce Frontier Internship** hackathon. Paste any **public YouTube lecture URL** and get a complete study kit: timestamped outline, multi-depth summaries, flashcards with source citations, semantic search, and bilingual support in five languages.

## Live demo

Coming after deployment — add Vercel URL here

## Features

- **Structured outline** with timestamped jump-points back into the video
- **Summaries at three depths** — 90 seconds, 5 minutes, and full
- **10 flashcards** with source timestamp citations
- **Semantic search** that finds the exact moment in the video that answers any question
- **Bilingual support** in English, Spanish, French, Bengali, and Arabic
- **Beautiful Linear-inspired dark UI** with a polished marketing landing page and animated hero

## Architecture

LectureKit is built as a clear, testable pipeline of agents with strict data contracts (Pydantic on the backend, TypeScript on the frontend).

### Agent 1 — Transcript Agent

- Fetches transcript via `youtube-transcript-api` with a **`yt-dlp` fallback**
- Cleans transcript text by removing filler words and **collapsing consecutive duplicate sentences/phrases**
- Chunks the transcript into ~500-word segments while preserving timestamps

### Agent 2 — Content Agent

- Uses **Claude Sonnet** via the **Anthropic SDK**
- Generates **outline + three summaries + 10 flashcards** in a **single API call**
- Returns structured JSON with timestamps that map back to the video

### Agent 3 — Search Agent

- Embeds transcript chunks **locally** using `sentence-transformers` (`all-MiniLM-L6-v2`)
- Stores vectors in a **persistent ChromaDB** vector store (path configurable via `CHROMA_DB_PATH`)
- Returns the top 3 most relevant transcript chunks for any query (with timestamps for jump-to-moment)

### Translation Agent (bonus)

- Translates study materials to a target language via Claude (with robust JSON parsing and a split-call fallback for large sessions)
- The frontend caches translations **in component state** per language to avoid repeat calls

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11 |
| LLM | Claude Sonnet (Anthropic SDK) |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` |
| Vector Store | ChromaDB (persistent) |
| Transcript | `youtube-transcript-api` + `yt-dlp` fallback |
| Design | Linear design system via `DESIGN.md` |
| Deployment | Vercel (frontend) + Railway (backend) |

## Local development setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

## Environment variables

### Backend (`backend/.env`)

- **ANTHROPIC_API_KEY**: required for Content Agent and Translation Agent
- **CORS_ORIGINS**: comma separated list of allowed frontend origins
- **CHROMA_DB_PATH**: path to persistent ChromaDB storage (default `./chroma_db`)
- **ANTHROPIC_MODEL**: Claude model to use (default `claude-sonnet-4-6`)
- **YTDLP_COOKIE_FILE** / **YOUTUBE_COOKIES_PATH** (optional): path to a Netscape `cookies.txt` (mount a small file on Railway rather than huge base64 env vars). Generate a minimal set locally with `python backend/scripts/extract_yt_cookies.py`
- **YOUTUBE_PROXY_URL** (optional): one proxy URL used for **all** transcript-related HTTP traffic (`youtube-transcript-api`, `yt-dlp`, VTT download) — typical fix for datacenter IP blocks (e.g. Webshare)
- **YOUTUBE_PO_TOKEN** / **YOUTUBE_VISITOR_DATA** (optional): passed to yt-dlp’s YouTube extractor for PO-token flows (see [yt-dlp PO Token guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)); token format is usually like `web.gvs+...`
- **YOUTUBE_TRANSCRIPT_PROXIES** (optional): JSON `{"http":"...","https":"..."}` or a single proxy URL — used when `YOUTUBE_PROXY_URL` is not set

### Frontend (`frontend/.env.local`)

- **NEXT_PUBLIC_API_URL**: backend URL (default `http://localhost:8000`)

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/health` | Health check |
| POST | `/process` | Full pipeline — transcript + content + search indexing |
| POST | `/search` | Semantic search for a processed video |
| POST | `/translate` | Translate study materials to a target language |

## Project structure

```text
lectureKit/
├── DESIGN.md                    # Linear design tokens
├── backend/
│   ├── main.py                  # FastAPI app + endpoints
│   ├── agents/
│   │   ├── transcript_agent.py  # Agent 1: fetch + chunk transcript
│   │   ├── content_agent.py     # Agent 2: Claude outline + summaries + flashcards
│   │   ├── search_agent.py      # Agent 3: embeddings + ChromaDB semantic search
│   │   └── translate_agent.py   # Translation via Claude
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── utils/
│   │   └── youtube.py           # YouTube URL parsing utilities
│   └── requirements.txt
└── frontend/
    ├── app/
    │   ├── page.tsx             # Marketing landing page
    │   ├── app/page.tsx         # URL input + loading stepper
    │   └── study/page.tsx       # Full study dashboard
    ├── components/
    │   ├── marketing/           # Landing page components
    │   └── app/                 # App components
    ├── types/lecture.ts         # TypeScript types
    └── utils/format.ts          # Timestamp formatting
```

## Hackathon context

Built for the **Cloudforce Frontier Internship — No Resume Required** hackathon (May 4–11, 2026). **Capability 1 (Student)** is implemented completely. The architecture prioritizes reliability and craftsmanship over broad but shallow scope.

## Tradeoffs (for defense video)

- Focused on **Capability 1** rather than attempting all three: one polished capability beats three incomplete ones
- Used **local** `sentence-transformers` embeddings instead of OpenAI: eliminates external dependency and per-request embedding costs
- Added **`yt-dlp` fallback** for transcript fetching to handle YouTube’s inconsistent transcript availability
- Split translation into **two Claude calls** as a fallback for large sessions to reduce truncation/token-limit failures
- Used **localStorage** instead of a database: appropriate for hackathon scope and avoids infrastructure complexity
