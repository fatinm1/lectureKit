"""
Purpose: Shared agent singletons + error classification.

Used by both the HTTP layer (`main.py`) and the background job pipeline (`jobs/`), so a
Railway API service, an in-process worker and a standalone `arq` worker all build agents
the same way. Tests monkeypatch attributes on this module.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from dotenv import load_dotenv

from agents.content_agent import ContentAgent, ContentAgentError
from agents.content_streaming import StreamingContentAgent
from agents.faculty_agent import FacultyAgent, FacultyAgentError
from agents.provost_agent import ProvostAgent, ProvostAgentError
from agents.search_agent import SearchAgent, SearchAgentError
from agents.transcript_agent import (
    TranscriptAgent,
    TranscriptAgentError,
    TranscriptFetchTimeoutError,
    TranscriptUnavailableError,
)
from agents.translate_agent import TranslateAgent, TranslateAgentError
from db.cache import Cache
from db.store import Store
from utils.youtube import InvalidYouTubeUrlError

# Step: Load environment variables from backend/.env before reading configuration.
load_dotenv()


def _write_youtube_cookies() -> None:
    """Decode YouTube cookies from base64 on startup (Railway: YOUTUBE_COOKIES_BASE64 + YTDLP_COOKIE_FILE)."""
    cookies_b64 = os.getenv("YOUTUBE_COOKIES_BASE64", "").strip()
    if not cookies_b64:
        return
    cookies_path = os.getenv("YTDLP_COOKIE_FILE", "/data/cookies.txt")
    try:
        parent = os.path.dirname(cookies_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(cookies_path, "wb") as f:
            f.write(base64.b64decode(cookies_b64))
        print(f"YouTube cookies written to {cookies_path}")
    except Exception as e:  # pragma: no cover - deploy-time convenience
        print(f"Warning: Could not write cookies file: {e}")


_write_youtube_cookies()

# Step: Optional persistence. With DATABASE_URL: transcripts, embeddings (pgvector) and
# generated results live in Postgres; with REDIS_URL too, hot reads are cached in Redis.
store = Store.from_env()
cache = Cache.from_env(store)

# Count which path each structured Claude output took (tool / tool_retry / legacy_fallback /
# failed) in Redis, so /metrics can report the parse-failure rate.
import agents.structured_call as _structured_call  # noqa: E402

_structured_call.record_path = lambda agent, path: cache._incr(f"structured_{agent}_{path}")

# Step: Agent 1 is stateless and safe to reuse.
transcript_agent = TranscriptAgent()
# Step: Agent 3 loads the embedding model once; vectors go to pgvector when `store` is set,
# otherwise to a local ChromaDB directory.
search_agent = SearchAgent(store=store)

# Step: Lazy-init Claude-backed agents so Railway healthchecks pass before ANTHROPIC_API_KEY is set.
_content_agent: Optional[ContentAgent] = None
_streaming_content_agent: Optional[StreamingContentAgent] = None
_translate_agent: Optional[TranslateAgent] = None
_faculty_agent: Optional[FacultyAgent] = None
_provost_agent: Optional[ProvostAgent] = None


def get_content_agent() -> ContentAgent:
    global _content_agent
    if _content_agent is None:
        _content_agent = ContentAgent()
    return _content_agent


def get_streaming_content_agent() -> StreamingContentAgent:
    global _streaming_content_agent
    if _streaming_content_agent is None:
        _streaming_content_agent = StreamingContentAgent()
    return _streaming_content_agent


def get_translate_agent() -> TranslateAgent:
    global _translate_agent
    if _translate_agent is None:
        _translate_agent = TranslateAgent()
    return _translate_agent


def get_faculty_agent() -> FacultyAgent:
    global _faculty_agent
    if _faculty_agent is None:
        _faculty_agent = FacultyAgent()
    return _faculty_agent


def get_provost_agent() -> ProvostAgent:
    global _provost_agent
    if _provost_agent is None:
        _provost_agent = ProvostAgent()
    return _provost_agent


def classify_error(exc: BaseException) -> tuple[int, str]:
    """
    Map a pipeline exception to (HTTP-style status, user-facing message).

    Shared by the synchronous endpoints and the background jobs so both report
    the same errors the same way.
    """
    if isinstance(exc, InvalidYouTubeUrlError):
        return 422, str(exc)
    if isinstance(exc, TranscriptUnavailableError):
        return 404, str(exc)
    if isinstance(exc, TranscriptFetchTimeoutError):
        return 504, str(exc)
    if isinstance(
        exc,
        (
            TranscriptAgentError,
            ContentAgentError,
            FacultyAgentError,
            ProvostAgentError,
            TranslateAgentError,
            SearchAgentError,
        ),
    ):
        return 500, str(exc)
    return 500, "Unexpected server error"
