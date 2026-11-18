"""
Purpose: One place every Claude call reports its token usage.

Agents call `report(agent, message)` right after each Anthropic response, including retries,
fallbacks and calls whose output was later rejected, because those are billed too. `services`
points the sink at the cache, which keeps lifetime, per-agent and per-day spend counters
(/metrics and the daily budget guard read them). Without a sink (tests, scripts) reports are
dropped. A failing sink never breaks the call that reported to it.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")

logger = logging.getLogger("lecturekit.usage")

_sink: Optional[Callable[[str, dict[str, int]], None]] = None


def set_sink(fn: Optional[Callable[[str, dict[str, int]], None]]) -> None:
    global _sink
    _sink = fn


def tokens(message_or_usage: Any) -> dict[str, int]:
    """Token counts from an Anthropic Message, its `.usage`, or a plain dict."""
    u = getattr(message_or_usage, "usage", message_or_usage)
    if isinstance(u, dict):
        return {f: int(u.get(f) or 0) for f in FIELDS}
    return {f: int(getattr(u, f, 0) or 0) for f in FIELDS}


def report(agent: str, message_or_usage: Any) -> None:
    if _sink is None or message_or_usage is None:
        return
    try:
        counts = tokens(message_or_usage)
        if any(counts.values()):
            _sink(agent, counts)
    except Exception as exc:  # accounting must never fail a request
        logger.warning("usage report for %s failed: %s: %s", agent, type(exc).__name__, exc)
