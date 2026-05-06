"""
Purpose: YouTube URL/video ID helpers shared by the Transcript Agent.

Part 2: Implements robust YouTube video ID extraction from common URL formats:
- youtube.com/watch?v=VIDEO_ID
- youtu.be/VIDEO_ID
- youtube.com/embed/VIDEO_ID

The Transcript Agent uses these helpers to convert a user-submitted URL into the
canonical video ID required by `youtube-transcript-api`.

Agents: Used exclusively by `agents/transcript_agent.py` once implemented.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


class InvalidYouTubeUrlError(ValueError):
    """
    Raised when a string cannot be parsed into a YouTube video ID.

    This is treated as a 422 at the API layer because the user input is invalid.
    """


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_youtube_video_id(youtube_url: str) -> str:
    """
    Extract a YouTube video ID from supported URL formats.

    Args:
        youtube_url: User-supplied URL string.

    Returns:
        11-character YouTube video ID.

    Steps:
        1. Parse the URL (scheme/host/path/query).
        2. Support watch URLs via `v` query param.
        3. Support short URLs (`youtu.be/<id>`).
        4. Support embed URLs (`/embed/<id>`).
        5. Validate the candidate looks like a real YouTube video ID.

    Raises:
        InvalidYouTubeUrlError: If no valid video ID can be extracted.
    """
    # Step: Normalize whitespace — users often paste with leading/trailing spaces.
    raw = (youtube_url or "").strip()
    if not raw:
        raise InvalidYouTubeUrlError("Invalid YouTube URL format: empty input")

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    candidate: str | None = None

    # Step: youtube.com/watch?v=VIDEO_ID
    if "youtube.com" in host or "m.youtube.com" in host or "www.youtube.com" in host:
        if path == "/watch":
            query = parse_qs(parsed.query or "")
            v_values = query.get("v", [])
            candidate = v_values[0] if v_values else None

        # Step: youtube.com/embed/VIDEO_ID
        if candidate is None:
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2 and parts[0] == "embed":
                candidate = parts[1]

    # Step: youtu.be/VIDEO_ID
    if candidate is None and "youtu.be" in host:
        parts = [p for p in path.split("/") if p]
        candidate = parts[0] if parts else None

    # Step: Some users paste raw IDs; accept as convenience.
    if candidate is None and _VIDEO_ID_RE.match(raw):
        candidate = raw

    if not candidate:
        raise InvalidYouTubeUrlError(
            "Invalid YouTube URL format: cannot extract video ID from the provided URL"
        )

    # Step: Strip any accidental extra path/query fragments.
    candidate = candidate.split("?")[0].split("&")[0].strip()

    if not _VIDEO_ID_RE.match(candidate):
        raise InvalidYouTubeUrlError(
            "Invalid YouTube URL format: extracted video ID is not valid"
        )

    return candidate


def normalize_youtube_url_placeholder(url: str) -> str:
    """
    Future helper to canonicalize watch vs short URLs.

    Args:
        url: Raw user-supplied string from the API layer.

    Returns:
        Normalized URL string (not implemented in Part 1).

    Steps:
        1. Reserved for parsing and validation logic.
    """
    # Step: Implement normalization in Part 2 alongside transcript fetching.
    return url
