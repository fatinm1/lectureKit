# Cloudforce Frontier — Lecture → Study Environment

Multi-agent pipeline (LangChain + Claude + OpenAI embeddings + ChromaDB) that transforms a YouTube lecture URL into outlines, multi-depth summaries, flashcards with citations, and semantic jump-to-moment search. **Part 1** establishes the monorepo skeleton, FastAPI surface area, Next.js 14 shell, and landing-page wiring against `POST /process`.

## Repository layout

```
├── DESIGN.md              # Linear design tokens — source of truth for UI
├── README.md
├── backend/               # FastAPI + future LangChain agents
└── frontend/              # Next.js 14 (App Router) + Tailwind
```

## Prerequisites

- Python **3.11+** (virtualenv recommended)
- Node.js **18+** and npm

## Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env .env.local                 # optional — edit keys when agents go live
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- `GET http://localhost:8000/health` → `{"status":"ok","service":"cloudforce-frontier-api"}`
- `POST http://localhost:8000/process` with JSON `{"youtube_url":"https://www.youtube.com/watch?v=..."}`
  - Returns `{"status":"accepted","youtube_url":"..."}` until agents are implemented.

**CORS:** defaults to `http://localhost:3000`. Override with `CORS_ORIGINS=https://your-vercel.app,http://localhost:3000` in `backend/.env` for previews/production.

## Frontend (Next.js 14)

```bash
cd frontend
# Ensure `.env.local` defines NEXT_PUBLIC_API_URL (defaults assumed in code if blank)
npm install                         # already done if you scaffolded with create-next-app
npm run dev                         # Turbopack (`next dev --turbo`). Fallback: `npm run dev:webpack`
```

Open `http://localhost:3000/` for the **LectureKit marketing page**, or `http://localhost:3000/app` for the **URL workspace**. Submitting the form on `/app` issues:

```
POST ${NEXT_PUBLIC_API_URL}/process
```

and logs the JSON response in the browser console (`[LectureKit] POST /process response`).

### Frontend troubleshooting (unstyled white page)

If you see **Times/New Roman on white** with blue links, the HTML loaded but **`/_next/static/css/app/layout.css` did not** (stale build or wrong server).

1. Stop every running `next dev` / `next start` process.
2. From `frontend/`: `npm run dev:fresh` (clears `.next` **and** `node_modules/.cache`, then starts dev).
3. Hard refresh the tab (Shift+Reload). In DevTools → **Network**, confirm `layout.css` returns **200**.
4. Ensure you are on the **Next.js** port (default **3000**), not the FastAPI port (**8000**).

## Design system

Visual language follows `DESIGN.md` (Linear canvas `#010102`, lavender accent `#5e6ad2`, hairline borders, Inter as the open-font substitute). Tailwind maps these tokens under `frontend/tailwind.config.ts`.

## Part 1 verification checklist

1. Backend health responds with `status: ok`.
2. Frontend loads with dark canvas + lavender CTA.
3. Submitting a valid YouTube URL logs an `accepted` payload without network errors.

Pause here for hackathon review — subsequent parts add transcript fetching, LangChain orchestration, embeddings, and the study dashboard UI.
