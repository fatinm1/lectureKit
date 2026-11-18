"""
Purpose: Shared Pydantic request/response models for the FastAPI layer.

Imported by `main.py` for request/response bodies and by the agents for the
shared TranscriptChunk / OutlineItem / Flashcard types.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, HttpUrl


class ProcessYouTubeRequest(BaseModel):
    """Payload for POST `/process`: a single lecture URL to analyze."""

    youtube_url: HttpUrl = Field(
        ...,
        description="Full YouTube watch or youtu.be URL for the lecture.",
    )


class FacultyRequest(BaseModel):
    """Payload for POST `/faculty`: a single lecture URL to audit."""

    youtube_url: str = Field(..., description="Full YouTube watch or youtu.be URL for the lecture.")


class ProvostRequest(BaseModel):
    """Payload for POST `/provost`: up to 10 lecture URLs plus the course learning objectives."""

    youtube_urls: List[str] = Field(..., description="YouTube lecture URLs (max 10).")
    learning_objectives: str = Field(..., description="Course learning objectives, free text.")


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


class OutlineItem(BaseModel):
    """One chronological topic in the lecture outline, anchored to a timestamp."""

    timestamp: float = Field(..., description="Start time in seconds for this topic.")
    title: str = Field(..., description="Short topic title.")
    description: str = Field(..., description="One-sentence topic description.")


class Flashcard(BaseModel):
    """A single study flashcard with a source timestamp citation."""

    question: str = Field(..., description="Question testing understanding/application.")
    answer: str = Field(..., description="2 to 4 sentence self-contained answer.")
    source_timestamp: float = Field(..., description="Seconds pointing to where the concept appears.")


class ContentAgentResult(BaseModel):
    """
    Output of ContentAgent (Agent 2).

    Produced from TranscriptAgent chunks; returned to the API layer for rendering in the UI.
    """

    outline: List[OutlineItem]
    summary_90s: str
    summary_5min: str
    summary_full: str
    flashcards: List[Flashcard]


class ProcessYouTubeResponse(BaseModel):
    """
    Response for POST `/process`.

    TranscriptAgent output (video_id + chunks), ContentAgent output (outline +
    summaries + flashcards) and whether SearchAgent indexing succeeded.
    """

    status: str = Field(..., description="Request outcome status.")
    youtube_url: str = Field(..., description="Echo of the submitted URL as string.")
    video_id: str = Field(..., description="Extracted YouTube video ID.")
    chunk_count: int = Field(..., ge=0, description="Total number of transcript chunks.")
    chunks: List[TranscriptChunk] = Field(..., description="Full list of transcript chunks.")
    outline: List[OutlineItem] = Field(..., description="Chronological lecture outline.")
    summary_90s: str = Field(..., description="2–3 sentence summary of the key takeaway.")
    summary_5min: str = Field(..., description="3–4 paragraph summary covering main topics.")
    summary_full: str = Field(..., description="Comprehensive paragraph-by-paragraph summary.")
    flashcards: List[Flashcard] = Field(..., description="Exactly 10 flashcards with citations.")
    indexed: bool = Field(..., description="Whether vector indexing into ChromaDB succeeded.")


class SearchRequest(BaseModel):
    """
    Request body for POST `/search`.

    Data flow:
    - Client provides a YouTube URL and a natural-language query.
    - API extracts video_id and searches the corresponding persisted collection.
    """

    youtube_url: str = Field(..., description="Full YouTube URL (watch/youtu.be/embed).")
    query: str = Field(..., description="Natural-language search query.")
    n_results: int = Field(3, ge=1, le=10, description="How many matches to return (default 3).")


class SearchResult(BaseModel):
    """One semantic match from SearchAgent with timestamp metadata."""

    text: str
    start: float
    end: float
    chunk_index: int
    relevance_score: float = Field(..., ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    """Response for POST `/search` with top-N semantic matches."""

    results: List[SearchResult]
    query: str
    video_id: str


class TranslateRequest(BaseModel):
    """
    Request body for POST `/translate`.

    Data flow:
    - Client sends study materials (outline + summaries + flashcards) and a target language.
    - Backend returns translated content with the same structure.
    """

    content: Dict[str, Any] = Field(..., description="Content object to translate (JSON).")
    target_language: str = Field(..., description="Target language (e.g. Spanish, French).")


class TranslateResponse(BaseModel):
    """Response for POST `/translate` with translated content JSON."""

    content: Dict[str, Any]

