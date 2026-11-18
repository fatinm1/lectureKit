"""
Purpose: FastAPI application entrypoint for LectureKit.

Endpoints:
- GET  /health     liveness probe
- POST /process    Student mode: Transcript -> (Content || Search indexing)
- POST /search     semantic search over a processed video
- POST /translate  translate study materials
- POST /faculty    Faculty audit report
- POST /provost    Provost curriculum map (multiple URLs)

Note on concurrency: every endpoint that calls a blocking agent is a plain `def`, so
FastAPI runs it in its threadpool. An `async def` endpoint that calls blocking code
would stall the event loop and freeze every other request on the worker.

Environment: Loads `backend/.env` via python-dotenv.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import time
import traceback
from urllib.parse import urlparse

import services
from budget import AIBudgetMiddleware
from limits import GuardMiddleware
from observability import RequestContextMiddleware, setup_logging, setup_sentry
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from jobs.routes import lifespan, router as jobs_router
from models.schemas import (
    FacultyRequest,
    ProcessYouTubeRequest,
    ProcessYouTubeResponse,
    ProvostRequest,
    SearchRequest,
    SearchResponse,
    SearchResult,
    TranslateRequest,
    TranslateResponse,
)
from services import (
    ContentAgentError,
    FacultyAgentError,
    ProvostAgentError,
    SearchAgentError,
    TranscriptAgentError,
    TranscriptFetchTimeoutError,
    TranscriptUnavailableError,
    TranslateAgentError,
)
from utils.youtube import InvalidYouTubeUrlError, extract_youtube_video_id

setup_logging()
SENTRY_ENABLED = setup_sentry()
logger = logging.getLogger("lecturekit")


app = FastAPI(
    title="LectureKit API",
    version="0.2.0",
    description="Multi-agent lecture → study environment backend",
    lifespan=lifespan,
)

# Per-process rolling budget on the endpoints that spend Claude / Supadata credits.
app.add_middleware(
    AIBudgetMiddleware, paths=["/process", "/faculty", "/provost", "/translate", "/jobs", "/ask"]
)

# Per-IP hourly limits and the daily spend cap (limits.py), then request IDs + one JSON log line
# per request (observability.py). Middleware added later wraps earlier ones, so CORS (added
# below) stays outermost and even 429/503 responses carry CORS headers.
app.add_middleware(
    GuardMiddleware,
    redis_client=lambda: services.cache.redis,
    spent_today=lambda: services.cache.spent_today_usd(),
)
app.add_middleware(RequestContextMiddleware)

# Step: Return a concise, user-friendly 422 instead of a large Pydantic error tree.
@app.exception_handler(RequestValidationError)
def _request_validation_error_handler(_request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        field = ".".join(str(p) for p in first.get("loc", ()) if p != "body") or "request body"
        detail = f"Invalid request: '{field}' {first.get('msg', 'is invalid')}".rstrip(".") + "."
    else:
        detail = "Invalid request body."
    return JSONResponse(status_code=422, content={"detail": detail})


# Parse CORS origins from environment variable
cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")

# Build list of allowed origins - strip whitespace and trailing slashes
allowed_origins: list[str] = []
for origin in cors_origins_raw.split(","):
    origin = origin.strip().rstrip("/")
    if origin:
        allowed_origins.append(origin)
        # Also allow with trailing slash just in case
        allowed_origins.append(origin + "/")

# Always include localhost for development
dev_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
]
for dev in dev_origins:
    if dev not in allowed_origins:
        allowed_origins.append(dev)

logger.info("CORS allowed origins: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(jobs_router)

import accounts_routes  # noqa: E402

app.include_router(accounts_routes.router)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """
    Liveness probe for deploy targets and local sanity checks.

    Returns:
        JSON object confirming the API process is running.

    Steps:
        1. Return a tiny payload without touching external services.
    """
    # Step: Keep this endpoint cheap; do not load embedding models or call Claude here.
    key_ok = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
    return {
        "status": "ok",
        "service": "lecturekit-api",
        "anthropic_configured": key_ok,
        "database": services.store is not None,
        "cache": services.cache.redis is not None,
        "sentry": SENTRY_ENABLED,
        "version": (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "dev")[:7],
    }


@app.post("/faculty")
def faculty_report(payload: FacultyRequest) -> dict:
    youtube_url = payload.youtube_url.strip()
    if not youtube_url:
        raise HTTPException(status_code=422, detail="youtube_url is required")

    try:
        video_id = extract_youtube_video_id(youtube_url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YouTube URL: {str(exc)}") from exc

    try:
        _, chunks = services.transcript_agent.process(youtube_url)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TranscriptFetchTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except TranscriptAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        report = services.get_faculty_agent().generate_report(chunks, video_id)
    except FacultyAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    return {"status": "success", "video_id": video_id, "youtube_url": youtube_url, "report": report}


@app.post("/provost")
def provost_report(payload: ProvostRequest) -> dict:
    youtube_urls = [u.strip() for u in payload.youtube_urls if u and u.strip()]
    learning_objectives = payload.learning_objectives.strip()

    if not youtube_urls:
        raise HTTPException(status_code=422, detail="youtube_urls array is required")
    if len(youtube_urls) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 URLs allowed")
    if not learning_objectives:
        raise HTTPException(status_code=422, detail="learning_objectives is required")

    lectures: list[dict] = []
    failed_urls: list[dict] = []

    for url in youtube_urls:
        try:
            video_id = extract_youtube_video_id(url)
            _, chunks = services.transcript_agent.process(url)
            lectures.append(
                {
                    "video_id": video_id,
                    "youtube_url": url,
                    "chunks": [c.model_dump() for c in chunks],
                }
            )
        except Exception as exc:
            failed_urls.append({"url": url, "error": str(exc)})

    if not lectures:
        raise HTTPException(
            status_code=404, detail="Could not retrieve transcripts for any provided URLs"
        )

    try:
        curriculum_map = services.get_provost_agent().generate_curriculum_map(lectures, learning_objectives)
    except ProvostAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "success",
        "lecture_count": len(lectures),
        "failed_urls": failed_urls,
        "video_ids": [l["video_id"] for l in lectures],
        "curriculum_map": curriculum_map,
    }


@app.post("/process", response_model=ProcessYouTubeResponse)
def process_youtube_lecture(payload: ProcessYouTubeRequest) -> ProcessYouTubeResponse:
    """
    Student mode: Transcript Agent, then Content Agent and Search indexing in parallel.

    Steps:
        1. Convert validated HttpUrl → string.
        2. TranscriptAgent fetches + cleans + chunks.
        3. ContentAgent and SearchAgent.index_chunks run concurrently on the chunks.
        4. Map domain errors to descriptive HTTP errors.
    """
    # Step: Use the original submitted URL string for echoing back to clients.
    youtube_url_str = str(payload.youtube_url)

    try:
        t0 = time.perf_counter()
        video_id, chunks = services.transcript_agent.process(youtube_url_str)
        t1 = time.perf_counter()
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        # Step: Missing/disabled transcripts and unavailable videos are “not found” from the user’s POV.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TranscriptFetchTimeoutError as exc:
        # Step: Timeouts are distinct from generic 500s; clients can retry.
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except TranscriptAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    # Step: Agent 2 (Content, network-bound on Claude) and Agent 3 (Search indexing,
    # CPU-bound embeddings) both only need Agent 1's chunks, so run them concurrently.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        content_future = pool.submit(lambda: services.get_content_agent().process(chunks))
        index_future = pool.submit(services.search_agent.index_chunks, video_id, chunks)

        try:
            content_result = content_future.result()
        except ContentAgentError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - safety net
            raise HTTPException(status_code=500, detail="Unexpected server error") from exc

        indexed = False
        try:
            indexed = bool(index_future.result())
        except Exception as exc:
            # Step: Indexing failures should not block study materials delivery.
            logger.exception("SearchAgent indexing failed for %s: %s", video_id, type(exc).__name__)
            indexed = False
    t2 = time.perf_counter()

    logger.info(
        "Processed %s | transcript=%.2fs content+index=%.2fs chunks=%d",
        video_id,
        (t1 - t0),
        (t2 - t1),
        len(chunks),
    )

    return ProcessYouTubeResponse(
        status="success",
        youtube_url=youtube_url_str,
        video_id=video_id,
        chunk_count=len(chunks),
        chunks=chunks,
        outline=content_result.outline,
        summary_90s=content_result.summary_90s,
        summary_5min=content_result.summary_5min,
        summary_full=content_result.summary_full,
        flashcards=content_result.flashcards,
        indexed=indexed,
    )


@app.post("/search", response_model=SearchResponse)
def search_video(payload: SearchRequest) -> SearchResponse:
    """
    Search within a previously processed video's transcript chunks.

    Error handling (per requirements):
    - 404 if video has not been processed yet (no collection exists)
    - 422 if query is empty
    - 500 for unexpected errors
    """
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query must be a non-empty string.")

    # Step: For `/search`, require a real URL (not a raw token). This keeps error messages clear.
    parsed = urlparse((payload.youtube_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Invalid YouTube URL format.")

    try:
        video_id = extract_youtube_video_id(payload.youtube_url)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Step: Hot search cache (Redis). Embeddings never change for a lecture, so a cached
    # answer for the same normalized query can't go stale.
    cached = services.cache.get_search(video_id, query, 3)
    if cached is not None:
        return SearchResponse(results=[SearchResult(**r) for r in cached], query=query, video_id=video_id)

    try:
        hits = services.search_agent.search(video_id=video_id, query=query, n_results=3)
    except SearchAgentError as exc:
        msg = str(exc)
        if "not processed" in msg or "Collection not found" in msg:
            raise HTTPException(status_code=404, detail="Video has not been processed yet.") from exc
        raise HTTPException(status_code=500, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    results = [
        SearchResult(
            text=h.text,
            start=h.start,
            end=h.end,
            chunk_index=h.chunk_index,
            relevance_score=h.relevance_score,
        )
        for h in hits
    ]
    services.cache.save_search(video_id, query, 3, [r.model_dump() for r in results])

    return SearchResponse(results=results, query=query, video_id=video_id)


class AskTurn(BaseModel):
    question: str
    answer: str


class AskRequest(BaseModel):
    youtube_url: str = Field(..., description="Full YouTube URL of a processed lecture.")
    question: str = Field(..., description="The student's question.")
    history: list[AskTurn] = Field(default_factory=list, description="Earlier turns, oldest first.")


@app.post("/ask")
def ask_lecture(payload: AskRequest) -> StreamingResponse:
    """
    "Ask the lecture": a grounded answer with inline [n] citations, streamed as SSE.

    Events: `sources` (the numbered excerpts, with time ranges) → `delta` × N (answer text)
    → `done` ({answer, citations, grounded, cached}) | `error`. Validation and "not processed"
    errors are normal HTTP errors, returned before the stream starts.
    """
    from agents.ask_agent import (
        MAX_QUESTION_CHARS,
        N_SOURCES,
        normalize_question,
        sources_from_hits,
        sse,
    )

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must be a non-empty string.")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(status_code=422, detail=f"Question is too long (max {MAX_QUESTION_CHARS} characters).")
    try:
        video_id = extract_youtube_video_id(payload.youtube_url)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        hits = services.search_agent.search(video_id=video_id, query=question, n_results=N_SOURCES)
    except SearchAgentError as exc:
        if "not processed" in str(exc) or "Collection not found" in str(exc):
            raise HTTPException(status_code=404, detail="Video has not been processed yet.") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    sources = sources_from_hits(hits)
    public_sources = [s.public() for s in sources]

    agent = services.get_ask_agent()
    history = [t.model_dump() for t in payload.history]
    # Only first questions are cached: a follow-up's answer depends on the conversation.
    cache_key = None if history else f"{video_id}:{agent.prompt_version}:{normalize_question(question)}"
    cached = services.cache.get_answer(cache_key) if cache_key else None

    def events():
        yield sse("sources", {"video_id": video_id, "sources": public_sources})
        if cached is not None:
            yield sse("delta", {"text": cached["answer"]})
            yield sse("done", {**cached, "cached": True})
            return
        it = agent.answer_stream(question, sources, history)
        try:
            while True:
                try:
                    piece = next(it)
                except StopIteration as stop:
                    result = stop.value
                    break
                yield sse("delta", {"text": piece})
        except Exception as exc:  # mid-stream: the HTTP status is already 200
            logger.warning("ask failed for %s: %s: %s", video_id, type(exc).__name__, exc)
            yield sse("error", {"message": "Could not answer that right now. Please try again."})
            return
        finally:
            it.close()  # client disconnected → stop Claude too
        done = {"answer": result.answer, "citations": result.citations, "grounded": result.grounded}
        services.cache.record_ask(grounded=result.grounded)
        if cache_key:
            services.cache.save_answer(cache_key, done)
        yield sse("done", {**done, "cached": False})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/metrics")
def metrics() -> dict:
    """
    Cache effectiveness and Claude usage.

    - counters: Redis hit/miss counts for the result and search caches, plus Claude tokens
      spent on fresh generations and tokens *saved* by serving cached results.
    - jobs: from Postgres — job count, cache hit rate, median latency for hits vs misses.
    - estimated_usd: tokens × per-million-token prices (env-configurable; defaults are
      Claude Sonnet list prices and only an estimate).
    """
    counters = services.cache.counters()
    jobs = services.store.job_metrics() if services.store is not None else None

    from db.cache import usd as usd_of

    def usd(prefix: str) -> float:
        return usd_of(counters, f"{prefix}_")

    # Every Claude call reports its tokens (usage.py), so this covers all modes, retries and
    # fallbacks. Prices are Sonnet's unless PRICE_* is set, so cheaper models read high.
    agents = sorted({k.split("_")[1] for k in counters if k.startswith("agent_")})
    by_agent = {a: usd(f"agent_{a}") for a in agents}

    def rate(hit_keys: list[str], miss_key: str) -> float | None:
        hits = sum(counters.get(k, 0) for k in hit_keys)
        total = hits + counters.get(miss_key, 0)
        return round(hits / total, 4) if total else None

    # Structured outputs: how often each path was needed, per agent. "parse_failure_rate" is
    # the share of calls whose first tool call did not validate.
    structured: dict[str, dict] = {}
    for agent in ("student", "faculty", "provost", "map"):
        counts = {p: counters.get(f"structured_{agent}_{p}", 0) for p in ("tool", "tool_retry", "legacy_fallback", "failed")}
        total = sum(counts.values())
        if total:
            structured[agent] = {
                **counts,
                "total": total,
                "first_try_rate": round(counts["tool"] / total, 4),
                "parse_failure_rate": round(1 - counts["tool"] / total, 4),
            }

    answers = counters.get("ask_answers", 0)
    ask_lookups = counters.get("ask_cache_hits", 0) + counters.get("ask_cache_misses", 0)
    ask = {
        "answers": answers,
        "ungrounded_rate": round(counters.get("ask_ungrounded", 0) / answers, 4) if answers else None,
        "cache_hit_rate": round(counters.get("ask_cache_hits", 0) / ask_lookups, 4) if ask_lookups else None,
    }

    return {
        "structured_outputs": structured,
        "ask": ask,
        "result_cache_hit_rate": rate(["result_redis_hits", "result_db_hits"], "result_misses"),
        "search_cache_hit_rate": rate(["search_hits"], "search_misses"),
        "estimated_usd": {
            "spent": usd("spent"),
            "saved_by_cache": usd("saved"),
            "by_agent": by_agent,
            "today": services.cache.spent_today_usd(),
            "daily_budget": float(os.getenv("DAILY_BUDGET_USD", "0") or 0) or None,
        },
        "counters": counters,
        "jobs": jobs,
    }


@app.post("/translate", response_model=TranslateResponse)
def translate_content(payload: TranslateRequest) -> TranslateResponse:
    """
    Translate structured study materials into a target language.

    One Claude call normally; split into two calls only if the output was truncated
    or unparseable. Timestamps and numeric fields are never translated.
    """
    target = (payload.target_language or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="target_language must be a non-empty string.")

    try:
        translated = services.get_translate_agent().translate(content=payload.content, target_language=target)
    except TranslateAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Translation failed: %s", str(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    return TranslateResponse(content=translated)
