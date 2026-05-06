"""
Purpose: Shared Pydantic request/response models for the FastAPI layer.

Agents & data flow (future parts):
- Transcript Agent, Content Agent, and Search Agent will populate richer
  response payloads once orchestration is wired. Part 1 only validates
  incoming URLs for `/process` and returns an acknowledgement JSON.

This module is imported by `main.py` for request bodies and can be extended
by agent modules as pipelines stabilize.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class ProcessYouTubeRequest(BaseModel):
    """Payload for POST `/process`: a single lecture URL to analyze."""

    youtube_url: HttpUrl = Field(
        ...,
        description="Full YouTube watch or youtu.be URL for the lecture.",
    )


class ProcessYouTubeResponse(BaseModel):
    """Minimal acknowledgement returned in Part 1 until agents are implemented."""

    status: str = Field(..., description="Processing lifecycle hint for the client.")
    youtube_url: str = Field(..., description="Echo of the submitted URL as string.")
