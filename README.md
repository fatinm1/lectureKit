# LectureKit

**Turn any YouTube lecture into intelligence — instantly.**

LectureKit is a multi-agent AI system built for the **Cloudforce Frontier Internship Hackathon**. Paste any public YouTube lecture URL and get a complete study environment, a private faculty audit, or a curriculum coverage map — powered by six distinct AI agents.

**Live:** https://lecture-kit.vercel.app  
**Backend:** https://lecturekit-production.up.railway.app  
**GitHub:** https://github.com/fatinm1/lectureKit

---

## Three Capabilities. One URL.

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
- Cleans text: strips filler words, HTML tags, collapses whitespace, deduplicates consecutive phrases
- Chunks into ~500-word segments with precise timestamps
- Validates video ID format before attempting fetch to fail fast on invalid URLs

### Agent 2 — Content Agent

- Uses **Claude Sonnet** via Anthropic SDK
- Generates outline + three summaries + 10 flashcards in a **single API call**
- 4-strategy JSON fallback parser handles markdown fences and preamble text
- Explicit English output regardless of transcript language

### Agent 3 — Search Agent

- Embeds transcript chunks **locally** using `sentence-transformers` `all-MiniLM-L6-v2`
- Stores vectors in **persistent ChromaDB** (one collection per video_id)
- Skips reindexing if collection already exists
- Under 0.02s search latency across 142-chunk corpora

### Agent 4 — Translation Agent

- Translates outline, summaries, and flashcards via **Claude Sonnet**
- Supports English, Spanish, French, Bengali, Arabic
- Splits large payloads into two Claude calls to avoid token limits
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

## Data Flow

User pastes URL + selects mode  
↓  
Next.js Frontend (Vercel)  
↓  
FastAPI Backend (Railway EU West)  
↓  
Agent 1: Transcript Agent  ←── Supadata API / yt-dlp  
↓  
┌────┴────┐─────────────────┐  
↓         ↓                 ↓  
Agent 2    Agent 3          Agent 5/6  
Content    Search           Faculty/Provost  
(Claude)   (MiniLM+         (Claude)  
ChromaDB)  
↓         ↓                 ↓  
└────┬────┘                 │  
↓                     ↓  
localStorage           localStorage  
↓                     ↓  
/study               /report or /curriculum  
↓                     ↓  
YouTube iframe          YouTube iframe  
(seekTo via             (seekTo via  
postMessage)            postMessage)

Agent 2 and Agent 3 run in parallel in Student mode. Agent 4 (Translation) runs on demand when the user selects a language — separate /translate call, cached per session.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Design | Lumina design system — Playfair Display + Inter |
| Backend | FastAPI, Python 3.11, uvicorn |
| LLM | Claude Sonnet — claude-sonnet-4-6 |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (local) |
| Vector Store | ChromaDB (persistent, /tmp/chroma_db on Railway) |
| Transcript | Supadata API (primary) + yt-dlp (fallback) |
| Deployment | Vercel (frontend) + Railway EU West (backend) |

---

## Performance

| Metric | Value |
|--------|-------|
| End-to-end processing | ~80 seconds |
| Semantic search latency | <0.02 seconds |
| Chunks from 2.5hr lecture | 142 |
| Languages supported | 5 |
| Flashcards per lecture | 10 |
| Max Provost lectures | 10 |

---

## Local Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY and SUPADATA_API_KEY to .env
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

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| NEXT_PUBLIC_API_URL | Backend URL (default: http://localhost:8000) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /process | Student mode — transcript + content + search indexing |
| POST | /search | Semantic search for a processed video |
| POST | /translate | Translate study materials to a target language |
| POST | /faculty | Faculty audit report |
| POST | /provost | Provost curriculum map (multiple URLs) |

All endpoints have explicit OPTIONS handlers for CORS preflight.

---

## Project Structure

```
lectureKit/
├── backend/
│   ├── main.py                   # FastAPI app, all endpoints, CORS, OPTIONS handlers
│   ├── agents/
│   │   ├── transcript_agent.py   # Agent 1: Supadata + yt-dlp + clean + chunk
│   │   ├── content_agent.py      # Agent 2: Claude outline + summaries + flashcards
│   │   ├── search_agent.py       # Agent 3: MiniLM embeddings + ChromaDB
│   │   ├── translate_agent.py    # Agent 4: Claude translation, 5 languages
│   │   ├── faculty_agent.py      # Agent 5: pedagogical audit
│   │   └── provost_agent.py      # Agent 6: curriculum map
│   ├── models/
│   │   └── schemas.py            # Pydantic request/response models
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
        │   ├── marketing/                   # Landing page components
        │   └── shared/
        └── types/
            └── lecture.ts        # All TypeScript types
```

---

## Key Engineering Decisions

**YouTube bot detection:** Railway cloud IPs are blocked by YouTube. Tried 10 datacenter proxies, cookies, and region changes — all failed. Supadata API handles bot detection on their end and became the primary transcript source.

**Local embeddings:** sentence-transformers all-MiniLM-L6-v2 runs locally on Railway with no external API cost, no rate limits, and under 0.02s search latency after indexing.

**Parallel agent execution:** In Student mode, Agent 2 (Content) and Agent 3 (Search) run in parallel from Agent 1's output — not sequentially. This reduces total processing time.

**localStorage session management:** Results are stored in localStorage immediately after the API response. Output pages read from localStorage on mount. No database required for hackathon scope.

**YouTube seekTo:** Every timestamp in the app seeks the embedded YouTube player using the iframe postMessage API with enablejsapi=1 and the page origin in the embed URL.

**4-strategy JSON parser:** Claude occasionally wraps responses in markdown fences or adds preamble text. The parser tries: strip fences → extract outermost braces → raw loads → raise with first 200 chars.

---

Built by **Fatin Mojumder**.
