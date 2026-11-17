"""
Purpose: HTTP surface for background jobs.

- POST /jobs                  enqueue a student / faculty / provost run, returns {job_id} immediately
- GET  /jobs/{job_id}         current status + final result (polling fallback, page reloads)
- GET  /jobs/{job_id}/events  Server-Sent Events: every progress event, replayed from the start
                              (or from Last-Event-ID), then live until `done` / `failed`

If REDIS_URL is not set, POST /jobs answers 503 and the frontend falls back to the original
synchronous endpoints, so the app keeps working before Redis is provisioned.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from typing import Any, AsyncIterator, List, Literal, Optional

from arq.connections import ArqRedis, create_pool
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jobs.events import JobEventBus
from jobs.worker import QUEUE_NAME, build_worker, redis_settings
from utils.youtube import InvalidYouTubeUrlError, extract_youtube_video_id

logger = logging.getLogger("lecturekit.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])

SSE_KEEPALIVE_MS = 15000


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect to Redis (if configured) and optionally run the ARQ worker in-process."""
    app.state.arq = None
    worker = None
    worker_task: Optional[asyncio.Task] = None

    if (os.getenv("REDIS_URL") or "").strip():
        try:
            app.state.arq = await create_pool(redis_settings())
            logger.info("Background jobs enabled (Redis connected)")
        except Exception as exc:
            logger.error("REDIS_URL is set but Redis is unreachable; jobs disabled: %s", exc)
            app.state.arq = None

        if app.state.arq is not None and os.getenv("RUN_WORKER_IN_PROCESS", "true").lower() != "false":
            worker = build_worker(redis_pool=app.state.arq)
            worker_task = asyncio.create_task(worker.async_run())
            logger.info("In-process ARQ worker started")
    else:
        logger.info("REDIS_URL not set: background jobs disabled, sync endpoints only")

    try:
        yield
    finally:
        if worker is not None:
            await worker.close()
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker_task
        if app.state.arq is not None:
            await app.state.arq.aclose()


class CreateJobRequest(BaseModel):
    mode: Literal["student", "faculty", "provost"]
    youtube_url: Optional[str] = Field(None, description="Student / faculty: the lecture URL.")
    youtube_urls: Optional[List[str]] = Field(None, description="Provost: up to 10 lecture URLs.")
    learning_objectives: Optional[str] = Field(None, description="Provost: course learning objectives.")


class CreateJobResponse(BaseModel):
    job_id: str
    mode: str
    events_url: str
    status_url: str


def _pool(request: Request) -> ArqRedis:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Background jobs are not configured on this server.")
    return pool


def _validate_url(url: Optional[str]) -> str:
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="youtube_url is required")
    try:
        extract_youtube_video_id(url)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return url


@router.post("", response_model=CreateJobResponse, status_code=202)
async def create_job(payload: CreateJobRequest, request: Request) -> CreateJobResponse:
    pool = _pool(request)
    job_id = uuid.uuid4().hex
    bus = JobEventBus(pool)

    args: tuple[Any, ...]
    if payload.mode == "provost":
        urls = [u.strip() for u in (payload.youtube_urls or []) if u and u.strip()]
        objectives = (payload.learning_objectives or "").strip()
        if not urls:
            raise HTTPException(status_code=422, detail="youtube_urls array is required")
        if len(urls) > 10:
            raise HTTPException(status_code=422, detail="Maximum 10 URLs allowed")
        if not objectives:
            raise HTTPException(status_code=422, detail="learning_objectives is required")
        args = (urls, objectives)
        meta: dict[str, Any] = {"youtube_urls": urls}
    else:
        url = _validate_url(payload.youtube_url)
        args = (url,)
        meta = {"youtube_url": url}

    # Create state first so an SSE client that connects instantly finds the job.
    await bus.create(job_id, payload.mode, meta)
    await pool.enqueue_job(f"{payload.mode}_job", job_id, *args, _job_id=job_id, _queue_name=QUEUE_NAME)

    return CreateJobResponse(
        job_id=job_id,
        mode=payload.mode,
        events_url=f"/jobs/{job_id}/events",
        status_url=f"/jobs/{job_id}",
    )


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    job = await JobEventBus(_pool(request)).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return {"job_id": job_id, **job}


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request, last_event_id: Optional[str] = None) -> StreamingResponse:
    bus = JobEventBus(_pool(request))
    if await bus.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    # EventSource sends Last-Event-ID automatically when it reconnects.
    start = request.headers.get("last-event-id") or last_event_id or "0-0"

    async def gen() -> AsyncIterator[str]:
        # Tell EventSource to wait 2s before reconnecting after a dropped connection.
        yield "retry: 2000\n\n"
        async for event in bus.stream(job_id, last_id=start, block_ms=SSE_KEEPALIVE_MS):
            if await request.is_disconnected():
                return
            if event is None:
                # SSE comment line: keeps proxies (Railway, Vercel) from closing an idle stream.
                yield ": keep-alive\n\n"
                continue
            yield event.to_sse()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
