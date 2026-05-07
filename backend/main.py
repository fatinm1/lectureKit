"""
Purpose: FastAPI application entrypoint for the Cloudforce Frontier study pipeline.

Agents & data flow:
- Part 1 exposes `GET /health` and `POST /process`. The latter validates a
  YouTube URL and returns an acknowledgement JSON. Later parts will invoke
  Transcript → Content → Search agents in sequence and return full materials.

Environment: Loads `backend/.env` via python-dotenv for API keys used in future parts.
"""

from __future__ import annotations

import base64
import logging
import os
import time
import traceback
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.content_agent import ContentAgent, ContentAgentError
from agents.search_agent import SearchAgent, SearchAgentError
from agents.transcript_agent import (
    TranscriptAgent,
    TranscriptAgentError,
    TranscriptFetchTimeoutError,
    TranscriptUnavailableError,
)
from agents.translate_agent import TranslateAgent, TranslateAgentError
from models.schemas import (
    ProcessYouTubeRequest,
    ProcessYouTubeResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    TranslateRequest,
    TranslateResponse,
)
from utils.youtube import InvalidYouTubeUrlError
from utils.youtube import extract_youtube_video_id

# Step: Load environment variables from backend/.env before reading configuration.
load_dotenv()

# Decode YouTube cookies from base64 on startup (Railway: set YOUTUBE_COOKIES_BASE64 + YTDLP_COOKIE_FILE).
_cookies_b64 = os.getenv("YOUTUBE_COOKIES_BASE64", "").strip()
if _cookies_b64:
    _cookies_path = os.getenv("YTDLP_COOKIE_FILE", "/data/cookies.txt")
    try:
        _parent = os.path.dirname(_cookies_path)
        if _parent:
            os.makedirs(_parent, exist_ok=True)
        with open(_cookies_path, "wb") as _f:
            _f.write(base64.b64decode(_cookies_b64))
        print(f"YouTube cookies written to {_cookies_path}")
    except Exception as _e:
        print(f"Warning: Could not write cookies file: {_e}")

logger = logging.getLogger("lecturekit")


app = FastAPI(
    title="Cloudforce Frontier API",
    version="0.1.0",
    description="Multi-agent lecture → study environment backend",
)

# Step: Return a concise, user-friendly 422 instead of a large Pydantic error tree.
@app.exception_handler(RequestValidationError)
def _request_validation_error_handler(_request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request: 'youtube_url' must be a valid URL."},
    )

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

print(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Step: Create the Agent 1 instance once; it is stateless and safe to reuse per request.
transcript_agent = TranscriptAgent()
# Step: Create Agent 3 once; it loads a local embedding model and persistent Chroma client.
search_agent = SearchAgent()

# Step: Lazy-init Claude-backed agents so Railway healthchecks pass before ANTHROPIC_API_KEY is set.
_content_agent: Optional[ContentAgent] = None
_translate_agent: Optional[TranslateAgent] = None


def get_content_agent() -> ContentAgent:
    """Return a singleton ContentAgent; raises ContentAgentError if API key is missing."""
    global _content_agent
    if _content_agent is None:
        _content_agent = ContentAgent()
    return _content_agent


def get_translate_agent() -> TranslateAgent:
    """Return a singleton TranslateAgent; raises TranslateAgentError if API key is missing."""
    global _translate_agent
    if _translate_agent is None:
        _translate_agent = TranslateAgent()
    return _translate_agent


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
        "service": "cloudforce-frontier-api",
        "anthropic_configured": key_ok,
    }


@app.post("/process", response_model=ProcessYouTubeResponse)
def process_youtube_lecture(payload: ProcessYouTubeRequest) -> ProcessYouTubeResponse:
    """
    Accept a lecture URL and run TranscriptAgent (Part 2).

    Args:
        payload: Validated body containing `youtube_url`.

    Returns:
        TranscriptAgent output with extracted video_id and timestamped chunks.

    Steps:
        1. Convert validated HttpUrl → string.
        2. Call TranscriptAgent to fetch + clean + chunk.
        3. Map domain errors to descriptive HTTP errors.

    """
    # Step: Use the original submitted URL string for echoing back to clients.
    youtube_url_str = str(payload.youtube_url)

    try:
        t0 = time.perf_counter()
        video_id, chunks = transcript_agent.process(youtube_url_str)
        t1 = time.perf_counter()
        content_result = get_content_agent().process(chunks)
        t2 = time.perf_counter()

        logger.info(
            "Processed %s | transcript=%.2fs content=%.2fs chunks=%d",
            video_id,
            (t1 - t0),
            (t2 - t1),
            len(chunks),
        )
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
    except ContentAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    indexed = False
    try:
        indexed = search_agent.index_chunks(video_id, chunks)
    except Exception as exc:
        # Step: Indexing failures should not block study materials delivery.
        logger.exception("SearchAgent indexing failed for %s: %s", video_id, type(exc).__name__)
        indexed = False

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

    try:
        hits = search_agent.search(video_id=video_id, query=query, n_results=3)
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

    return SearchResponse(results=results, query=query, video_id=video_id)


@app.post("/translate", response_model=TranslateResponse)
def translate_content(payload: TranslateRequest) -> TranslateResponse:
    """
    Translate structured study materials into a target language.

    Requirements:
    - Single Claude call
    - Return JSON only with same structure as input
    - Do not translate timestamps / numeric fields
    """
    target = (payload.target_language or "").strip()
    if not target:
        raise HTTPException(status_code=422, detail="target_language must be a non-empty string.")

    try:
        translated = get_translate_agent().translate(content=payload.content, target_language=target)
    except TranslateAgentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Translation failed: %s", str(exc))
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Unexpected server error") from exc

    return TranslateResponse(content=translated)
