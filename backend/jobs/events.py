"""
Purpose: Job state + progress events, stored in Redis.

Design:
- Each job has a Redis Stream `lk:job:{id}:events`. The worker XADDs one entry per stage
  (transcript_fetched, chunks_indexed, outline_ready, ...). Streams give us three things a
  plain pub/sub channel doesn't:
    1. Replay: a browser that connects late (or refreshes) still gets every event.
    2. Resume: the stream entry id doubles as the SSE `id:`, so EventSource's automatic
       reconnect sends `Last-Event-ID` and we continue exactly where it stopped.
    3. Blocking reads: XREAD BLOCK waits for the next event without polling.
- A small hash `lk:job:{id}` keeps status/kind/timestamps, and `lk:job:{id}:result` the
  final JSON, so `GET /jobs/{id}` works without reading the stream.
- Everything expires after JOB_TTL_SECONDS so Redis doesn't grow forever.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from redis.asyncio import Redis

JOB_TTL_SECONDS = 24 * 3600

TERMINAL_EVENTS = frozenset({"done", "failed"})


def _key(job_id: str) -> str:
    return f"lk:job:{job_id}"


def _events_key(job_id: str) -> str:
    return f"lk:job:{job_id}:events"


def _result_key(job_id: str) -> str:
    return f"lk:job:{job_id}:result"


def _decode(v: Any) -> str:
    return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)


@dataclass(frozen=True)
class JobEvent:
    """One progress event as read back from the stream."""

    id: str
    type: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {self.id}\nevent: {self.type}\ndata: {payload}\n\n"


class JobEventBus:
    """Thin wrapper over a redis.asyncio client for job state and events."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def create(self, job_id: str, kind: str, meta: dict[str, Any]) -> None:
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.hset(
            _key(job_id),
            mapping={
                "kind": kind,
                "status": "queued",
                "created_at": f"{now:.3f}",
                "meta": json.dumps(meta),
            },
        )
        pipe.expire(_key(job_id), JOB_TTL_SECONDS)
        await pipe.execute()
        await self.emit(job_id, "queued", {"kind": kind})

    async def emit(self, job_id: str, event_type: str, data: Optional[dict[str, Any]] = None) -> str:
        """Append an event. `t` = seconds since the job was created (for timing metrics)."""
        created = await self.redis.hget(_key(job_id), "created_at")
        t = round(time.time() - float(_decode(created)), 3) if created else 0.0
        body = dict(data or {})
        body.setdefault("t", t)
        pipe = self.redis.pipeline()
        pipe.xadd(_events_key(job_id), {"type": event_type, "data": json.dumps(body, ensure_ascii=False)})
        pipe.expire(_events_key(job_id), JOB_TTL_SECONDS)
        if event_type in TERMINAL_EVENTS:
            pipe.hset(_key(job_id), mapping={"status": event_type, "finished_at": f"{time.time():.3f}"})
        elif event_type != "queued":
            pipe.hset(_key(job_id), "status", "running")
        results = await pipe.execute()
        return _decode(results[0])

    async def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        await self.redis.set(_result_key(job_id), json.dumps(result, ensure_ascii=False), ex=JOB_TTL_SECONDS)

    async def get(self, job_id: str) -> Optional[dict[str, Any]]:
        raw = await self.redis.hgetall(_key(job_id))
        if not raw:
            return None
        job = {_decode(k): _decode(v) for k, v in raw.items()}
        job["meta"] = json.loads(job.get("meta") or "{}")
        result = await self.redis.get(_result_key(job_id))
        job["result"] = json.loads(_decode(result)) if result else None
        return job

    async def history(self, job_id: str) -> list[JobEvent]:
        entries = await self.redis.xrange(_events_key(job_id))
        return [self._to_event(eid, fields) for eid, fields in entries]

    async def stream(
        self,
        job_id: str,
        *,
        last_id: str = "0-0",
        block_ms: int = 15000,
    ) -> AsyncIterator[Optional[JobEvent]]:
        """
        Yield events after `last_id`, blocking for new ones. Yields None on each idle
        timeout so the caller can send an SSE keep-alive. Stops after a terminal event.
        """
        cursor = last_id or "0-0"
        while True:
            resp = await self.redis.xread({_events_key(job_id): cursor}, block=block_ms, count=100)
            if not resp:
                yield None
                continue
            for _stream, entries in resp:
                for eid, fields in entries:
                    event = self._to_event(eid, fields)
                    cursor = event.id
                    yield event
                    if event.type in TERMINAL_EVENTS:
                        return

    @staticmethod
    def _to_event(eid: Any, fields: dict[Any, Any]) -> JobEvent:
        f = {_decode(k): _decode(v) for k, v in fields.items()}
        return JobEvent(id=_decode(eid), type=f.get("type", "message"), data=json.loads(f.get("data") or "{}"))
