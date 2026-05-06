"""
Purpose: FastAPI application entrypoint for the Cloudforce Frontier study pipeline.

Agents & data flow:
- Part 1 exposes `GET /health` and `POST /process`. The latter validates a
  YouTube URL and returns an acknowledgement JSON. Later parts will invoke
  Transcript → Content → Search agents in sequence and return full materials.

Environment: Loads `backend/.env` via python-dotenv for API keys used in future parts.
"""

from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.transcript_agent import (
    TranscriptAgent,
    TranscriptAgentError,
    TranscriptFetchTimeoutError,
    TranscriptUnavailableError,
)
from models.schemas import ProcessYouTubeRequest, ProcessYouTubeResponse
from utils.youtube import InvalidYouTubeUrlError

# Step: Load environment variables from backend/.env before reading configuration.
load_dotenv()


def _allowed_origins() -> List[str]:
    """
    Build the CORS allowlist for browser clients.

    Returns:
        List of origins permitted to call this API with credentials disabled.

    Steps:
        1. Start with local Next.js dev server defaults.
        2. Allow override via CORS_ORIGINS (comma-separated) for staging/production.
    """
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    # Step: Split and strip whitespace so `.env` formatting is forgiving.
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Cloudforce Frontier API",
    version="0.1.0",
    description="Multi-agent lecture → study environment backend",
)

# Step: Enable cross-origin requests from the Next.js app during local dev and deploy previews.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Step: Create the Agent 1 instance once; it is stateless and safe to reuse per request.
transcript_agent = TranscriptAgent()


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    Liveness probe for deploy targets and local sanity checks.

    Returns:
        JSON object confirming the API process is running.

    Steps:
        1. Return a tiny payload without touching external services.
    """
    # Step: Keep this endpoint dependency-free so orchestrators can ping cheaply.
    return {"status": "ok", "service": "cloudforce-frontier-api"}


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
        video_id, chunks = transcript_agent.process(youtube_url_str)
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

    return ProcessYouTubeResponse(
        status="success",
        youtube_url=youtube_url_str,
        video_id=video_id,
        chunk_count=len(chunks),
        chunks=chunks,
    )
