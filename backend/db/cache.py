"""
Purpose: Read-through cache: Redis in front of Postgres for the hottest reads.

- Generated results (study kits, faculty reports): Redis key per
  (video_id, kind, language, prompt_version), 1 h TTL, falling back to Postgres.
- Search queries: Redis key per (video_id, normalized query, n), 10 min TTL. Embeddings
  for a lecture never change once written, so a cached answer can't go stale.

Every lookup increments hit/miss counters in Redis, and every result-cache hit adds the
Claude tokens that the original generation used to a "saved" counter. GET /metrics reports
these, which is where the cache-hit-rate and spend-saved numbers come from.

Redis and Postgres are both optional: with neither configured every call is a miss and
nothing is stored, so the app behaves exactly as before.
"""

from __future__ import annotations

import hashlib
import json
import time
import logging
import os
from typing import Any, Optional

import redis

from db.store import Store, StoredResult

logger = logging.getLogger("lecturekit.cache")

RESULT_TTL_S = 3600
SEARCH_TTL_S = 600
ANSWER_TTL_S = 7 * 24 * 3600  # a lecture's transcript never changes, so answers stay valid
_PREFIX = "lk:cache"
_METRICS = "lk:metrics"
_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def sum_usage(usage: Optional[dict[str, Any]]) -> dict[str, int]:
    """Collapse per-call usage ({'summaries': {...}, 'structured': {...}} or flat) into token totals."""
    totals = {f: 0 for f in _USAGE_FIELDS}
    if not usage:
        return totals
    calls = usage.values() if all(isinstance(v, dict) for v in usage.values()) else [usage]
    for call in calls:
        for f in _USAGE_FIELDS:
            totals[f] += int(call.get(f) or 0)
    return totals


def prices() -> dict[str, float]:
    """USD per million tokens. Defaults are Claude Sonnet list prices; override per deployment."""

    def price(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, "") or default)
        except ValueError:
            return default

    return {
        "input_tokens": price("PRICE_INPUT_PER_MTOK", 3.0),
        "output_tokens": price("PRICE_OUTPUT_PER_MTOK", 15.0),
        "cache_creation_input_tokens": price("PRICE_CACHE_WRITE_PER_MTOK", 3.75),
        "cache_read_input_tokens": price("PRICE_CACHE_READ_PER_MTOK", 0.30),
    }


def usd(counts: dict[str, int], prefix: str = "") -> float:
    """Estimated dollars for token counts keyed `<prefix><field>` (e.g. "spent_input_tokens")."""
    return round(sum(int(counts.get(f"{prefix}{k}", 0) or 0) * p / 1e6 for k, p in prices().items()), 4)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class Cache:
    def __init__(self, store: Optional[Store], redis_client: Optional[redis.Redis]) -> None:
        self.store = store
        self.redis = redis_client

    @classmethod
    def from_env(cls, store: Optional[Store]) -> "Cache":
        url = (os.getenv("REDIS_URL") or "").strip()
        client = None
        if url:
            try:
                client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
                client.ping()
            except Exception as exc:
                logger.error("Redis unreachable for caching (%s); continuing without it", exc)
                client = None
        return cls(store, client)

    # ---------- helpers ----------

    def _incr(self, name: str, amount: int = 1) -> None:
        if self.redis is None or amount == 0:
            return
        try:
            self.redis.hincrby(_METRICS, name, amount)
        except redis.RedisError:
            pass

    def _rget(self, key: str) -> Optional[Any]:
        if self.redis is None:
            return None
        try:
            raw = self.redis.get(key)
        except redis.RedisError:
            return None
        return json.loads(raw) if raw else None

    def _rset(self, key: str, value: Any, ttl: int) -> None:
        if self.redis is None:
            return
        try:
            self.redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except redis.RedisError:
            pass

    # ---------- generated results ----------

    @staticmethod
    def _result_key(video_id: str, kind: str, language: str, prompt_version: str) -> str:
        return f"{_PREFIX}:result:{video_id}:{kind}:{language}:{prompt_version}"

    def peek_result(self, video_id: str, kind: str, language: str, prompt_version: str) -> Optional[dict[str, Any]]:
        """A cached payload without touching the hit/miss/saved counters (evals, inspection)."""
        hot = self._rget(self._result_key(video_id, kind, language, prompt_version))
        if hot is not None:
            return hot["payload"]
        if self.store is not None:
            found = self.store.get_result(video_id, kind, language, prompt_version)
            return found.payload if found is not None else None
        return None

    def get_result(self, video_id: str, kind: str, language: str, prompt_version: str) -> Optional[StoredResult]:
        key = self._result_key(video_id, kind, language, prompt_version)
        hot = self._rget(key)
        found: Optional[StoredResult] = None
        if hot is not None:
            found = StoredResult(payload=hot["payload"], usage=hot.get("usage"))
            self._incr("result_redis_hits")
        elif self.store is not None:
            found = self.store.get_result(video_id, kind, language, prompt_version)
            if found is not None:
                self._incr("result_db_hits")
                self._rset(key, {"payload": found.payload, "usage": found.usage}, RESULT_TTL_S)
        if found is None:
            self._incr("result_misses")
            return None
        # A hit means the Claude calls behind this result were not made again.
        for field, n in sum_usage(found.usage).items():
            self._incr(f"saved_{field}", n)
        return found

    def save_result(
        self,
        video_id: str,
        kind: str,
        language: str,
        prompt_version: str,
        payload: dict[str, Any],
        usage: Optional[dict[str, Any]] = None,
    ) -> None:
        if self.store is not None:
            self.store.save_result(video_id, kind, language, prompt_version, payload, usage)
        self._rset(
            self._result_key(video_id, kind, language, prompt_version),
            {"payload": payload, "usage": usage},
            RESULT_TTL_S,
        )
    # ---------- search ----------

    @staticmethod
    def _search_key(video_id: str, query: str, n: int) -> str:
        norm = " ".join(query.lower().split())
        digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]
        return f"{_PREFIX}:search:{video_id}:{n}:{digest}"

    def get_search(self, video_id: str, query: str, n: int) -> Optional[list[dict[str, Any]]]:
        hit = self._rget(self._search_key(video_id, query, n))
        self._incr("search_hits" if hit is not None else "search_misses")
        return hit

    def save_search(self, video_id: str, query: str, n: int, results: list[dict[str, Any]]) -> None:
        self._rset(self._search_key(video_id, query, n), results, SEARCH_TTL_S)

    # ---------- ask the lecture ----------

    def get_answer(self, key: str) -> Optional[dict[str, Any]]:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        hit = self._rget(f"{_PREFIX}:ask:{digest}")
        self._incr("ask_cache_hits" if hit is not None else "ask_cache_misses")
        return hit

    def save_answer(self, key: str, answer: dict[str, Any]) -> None:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        self._rset(f"{_PREFIX}:ask:{digest}", answer, ANSWER_TTL_S)

    def record_ask(self, *, grounded: bool) -> None:
        self._incr("ask_answers")
        if not grounded:
            self._incr("ask_ungrounded")

    # ---------- spend (fed by usage.report from every Claude call) ----------

    def record_spend(self, agent: str, counts: dict[str, int]) -> None:
        """Lifetime, per-agent and per-UTC-day token counters, in one round trip."""
        if self.redis is None:
            return
        day_key = f"{_PREFIX}:spend:{_today()}"
        try:
            pipe = self.redis.pipeline()
            for field, n in counts.items():
                if n:
                    pipe.hincrby(_METRICS, f"spent_{field}", n)
                    pipe.hincrby(_METRICS, f"agent_{agent}_{field}", n)
                    pipe.hincrby(day_key, field, n)
            pipe.expire(day_key, 3 * 24 * 3600)
            pipe.execute()
        except redis.RedisError:
            pass

    def spent_today_usd(self) -> float:
        if self.redis is None:
            return 0.0
        try:
            raw = self.redis.hgetall(f"{_PREFIX}:spend:{_today()}")
        except redis.RedisError:
            return 0.0
        return usd({(k.decode() if isinstance(k, bytes) else k): int(v) for k, v in raw.items()})

    # ---------- metrics ----------

    def counters(self) -> dict[str, int]:
        if self.redis is None:
            return {}
        try:
            raw = self.redis.hgetall(_METRICS)
        except redis.RedisError:
            return {}
        return {k.decode() if isinstance(k, bytes) else k: int(v) for k, v in raw.items()}
