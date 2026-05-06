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

from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class ProcessYouTubeRequest(BaseModel):
    """Payload for POST `/process`: a single lecture URL to analyze."""

    youtube_url: HttpUrl = Field(
        ...,
        description="Full YouTube watch or youtu.be URL for the lecture.",
    )


class TranscriptChunk(BaseModel):
    """
    A cleaned transcript chunk with timestamp bounds.

    Agents/data flow:
    - Produced by TranscriptAgent (Agent 1).
    - Consumed by ContentAgent (Agent 2) and SearchAgent (Agent 3).
    """

    text: str = Field(..., description="Cleaned transcript text for this chunk.")
    start: float = Field(..., description="Chunk start time in seconds (float).")
    end: float = Field(..., description="Chunk end time in seconds (float).")
    chunk_index: int = Field(..., ge=0, description="0-based chunk index.")
    word_count: int = Field(..., ge=0, description="Approximate word count for this chunk.")


class ProcessYouTubeResponse(BaseModel):
    """
    Response for POST `/process`.

    Part 2: Includes TranscriptAgent output (video_id + chunks).
    """

    status: str = Field(..., description="Request outcome status.")
    youtube_url: str = Field(..., description="Echo of the submitted URL as string.")
    video_id: str = Field(..., description="Extracted YouTube video ID.")
    chunk_count: int = Field(..., ge=0, description="Total number of transcript chunks.")
    chunks: List[TranscriptChunk] = Field(..., description="Full list of transcript chunks.")


class ProcessYouTubeError(BaseModel):
    """
    Structured error payload for `/process` failures (documented shape).

    Note: FastAPI returns these via HTTPException; this model exists for schema clarity.
    """

    status: str = Field("error", description="Always 'error' for failure payloads.")
    message: str = Field(..., description="Human-readable error message.")
    error_type: Optional[str] = Field(None, description="Machine-friendly error category.")
