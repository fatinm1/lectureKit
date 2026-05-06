"""
Purpose: YouTube URL/video ID helpers shared by the Transcript Agent.

Part 1: Stub module so the repository matches the target layout. Part 2 will
implement ID extraction, URL normalization, and validation helpers used when
calling youtube-transcript-api.

Agents: Used exclusively by `agents/transcript_agent.py` once implemented.
"""

from __future__ import annotations


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
