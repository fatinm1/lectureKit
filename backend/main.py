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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import ProcessYouTubeRequest, ProcessYouTubeResponse

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
    Accept a lecture URL and acknowledge receipt (Part 1 stub).

    Args:
        payload: Validated body containing `youtube_url`.

    Returns:
        Acknowledgement describing acceptance; future versions will embed job IDs.

    Steps:
        1. Rely on Pydantic to validate URL shape.
        2. Respond with a deterministic stub so the frontend can be wired early.

    """
    # Step: Part 1 — no agent orchestration yet; echo URL for client verification.
    url_str = str(payload.youtube_url)
    return ProcessYouTubeResponse(status="accepted", youtube_url=url_str)
