"""
Purpose: Keep one visitor, or one bad day, from spending the whole Anthropic balance.

Two checks on the endpoints that can call Claude, before any work starts:

1. **Daily budget** (`DAILY_BUDGET_USD`, off when unset or 0). Estimated spend today (UTC), summed
   from the per-day counters every Claude call feeds (usage.py → Cache.record_spend). Over budget
   → 503 until midnight UTC. Prices are Sonnet's unless PRICE_* is set, so it errs high.
2. **Per-IP rate limit**, a fixed one-hour window in Redis so it holds across workers and
   restarts: `RATE_LIMIT_PER_HOUR` (default 20) for runs (jobs, process, faculty, provost,
   translate) and `ASK_RATE_LIMIT_PER_HOUR` (default 60) for chat questions. 0 turns a limit off.
   Over → 429 with Retry-After. Without Redis it falls back to an in-process counter.

These sit alongside the existing AIBudgetMiddleware (a per-process concurrency cap).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from observability import client_ip

logger = logging.getLogger("lecturekit.limits")

RUN_PATHS = ("/jobs", "/process", "/faculty", "/provost", "/translate")
ASK_PATHS = ("/ask",)
AUTH_PATHS = ("/auth/login", "/auth/signup")  # slows password guessing; no Claude cost


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


class RateLimiter:
    """Fixed-window counter: `limit` hits per `window_s` per key."""

    def __init__(self, redis_client: Any = None, window_s: int = 3600) -> None:
        self.redis = redis_client
        self.window_s = window_s
        self._local: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, now: Optional[float] = None) -> tuple[bool, int]:
        """Count one hit. Returns (allowed, seconds until the window resets)."""
        now = time.time() if now is None else now
        window = int(now // self.window_s)
        retry_after = int((window + 1) * self.window_s - now) + 1
        full_key = f"lk:rl:{key}:{window}"
        count: Optional[int] = None
        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                pipe.incr(full_key)
                pipe.expire(full_key, self.window_s + 60)
                count = int(pipe.execute()[0])
            except Exception as exc:  # Redis down: degrade to per-process counting
                logger.warning("rate limit redis error: %s", exc)
        if count is None:
            with self._lock:
                self._local = {k: v for k, v in self._local.items() if k.endswith(f":{window}")}
                count = self._local[full_key] = self._local.get(full_key, 0) + 1
        return count <= limit, retry_after


class GuardMiddleware:
    """Pure ASGI, so streamed responses (SSE) pass through untouched."""

    def __init__(
        self,
        app: Any,
        *,
        redis_client: Callable[[], Any],
        spent_today: Callable[[], float],
    ) -> None:
        self.app = app
        self._redis_client = redis_client  # looked up per request: services.cache can be swapped
        self.limiter = RateLimiter()
        self._spent_today = spent_today

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in AUTH_PATHS:
            group, limit = "auth", _env_int("AUTH_RATE_LIMIT_PER_HOUR", 10)
        elif path in ASK_PATHS:
            group, limit = "ask", _env_int("ASK_RATE_LIMIT_PER_HOUR", 60)
        elif path in RUN_PATHS:
            group, limit = "run", _env_int("RATE_LIMIT_PER_HOUR", 20)
        else:
            await self.app(scope, receive, send)
            return

        budget = _env_float("DAILY_BUDGET_USD", 0.0)
        if budget > 0 and group != "auth":
            spent = await asyncio.to_thread(self._spent_today)
            if spent >= budget:
                logger.warning("daily budget reached", extra={"spent_usd": spent, "budget_usd": budget, "path": path})
                await _respond(
                    send,
                    503,
                    "LectureKit has used today's AI budget. Lectures you've already opened still work; "
                    "new ones will be back tomorrow.",
                    retry_after=_seconds_to_utc_midnight(),
                )
                return

        if limit > 0:
            ip = client_ip(scope)
            self.limiter.redis = self._redis_client()
            allowed, retry_after = await asyncio.to_thread(self.limiter.hit, f"{group}:{ip}", limit)
            if not allowed:
                logger.info("rate limited", extra={"group": group, "client_ip": ip, "path": path})
                minutes = max(1, round(retry_after / 60))
                await _respond(
                    send,
                    429,
                    (
                        f"Too many sign-in attempts from your network. Try again in about {minutes} minutes."
                        if group == "auth"
                        else f"You've hit the limit of {limit} {'questions' if group == 'ask' else 'requests'} an hour. "
                        f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
                    ),
                    retry_after=retry_after,
                )
                return

        await self.app(scope, receive, send)


def _seconds_to_utc_midnight(now: Optional[float] = None) -> int:
    now = time.time() if now is None else now
    return int(86400 - (now % 86400)) + 1


async def _respond(send: Any, status: int, detail: str, *, retry_after: int) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(retry_after).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
