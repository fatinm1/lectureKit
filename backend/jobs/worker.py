"""
Purpose: ARQ worker that runs the agent pipelines in the background.

Two ways to run it:

1. In-process (default, RUN_WORKER_IN_PROCESS=true): `jobs.routes.lifespan` starts an ARQ
   Worker on the API's event loop. One Railway service, and the worker shares the API's
   ChromaDB directory, so `/search` sees what the worker indexed.
2. Standalone: `arq jobs.worker.WorkerSettings` as a separate process/service. Use this to
   scale workers independently, once embeddings live in a shared store (pgvector, roadmap #3);
   until then a separate service would index into its own disk, not the API's.

Jobs are not retried (max_tries=1): a retry would silently re-spend Claude/Supadata credits,
and the pipeline already reports failures to the user as a `failed` event.
"""

from __future__ import annotations

import os
from typing import Any

from arq.connections import RedisSettings
from arq.worker import Worker, func

from jobs import pipeline
from jobs.events import JobEventBus

QUEUE_NAME = "lecturekit:jobs"
JOB_TIMEOUT_S = 15 * 60  # Provost with 10 lectures can legitimately take several minutes.


async def student_job(ctx: dict[str, Any], job_id: str, youtube_url: str) -> None:
    await pipeline.run_student(JobEventBus(ctx["redis"]), job_id, youtube_url)


async def faculty_job(ctx: dict[str, Any], job_id: str, youtube_url: str) -> None:
    await pipeline.run_faculty(JobEventBus(ctx["redis"]), job_id, youtube_url)


async def provost_job(
    ctx: dict[str, Any], job_id: str, youtube_urls: list[str], learning_objectives: str
) -> None:
    await pipeline.run_provost(JobEventBus(ctx["redis"]), job_id, youtube_urls, learning_objectives)


FUNCTIONS = [
    func(student_job, name="student_job", max_tries=1, timeout=JOB_TIMEOUT_S),
    func(faculty_job, name="faculty_job", max_tries=1, timeout=JOB_TIMEOUT_S),
    func(provost_job, name="provost_job", max_tries=1, timeout=JOB_TIMEOUT_S),
]


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))


def max_jobs() -> int:
    """Concurrent pipelines per worker. Each one runs Claude calls, so keep this small."""
    return max(1, int(os.getenv("WORKER_MAX_JOBS", "2")))


def build_worker(**overrides: Any) -> Worker:
    opts: dict[str, Any] = dict(
        functions=FUNCTIONS,
        queue_name=QUEUE_NAME,
        redis_settings=redis_settings(),
        max_jobs=max_jobs(),
        job_timeout=JOB_TIMEOUT_S,
        keep_result=3600,
        handle_signals=False,
    )
    opts.update(overrides)
    return Worker(**opts)


class WorkerSettings:
    """Entry point for a standalone worker: `arq jobs.worker.WorkerSettings`."""

    functions = FUNCTIONS
    queue_name = QUEUE_NAME
    redis_settings = redis_settings()
    max_jobs = max_jobs()
    job_timeout = JOB_TIMEOUT_S
    keep_result = 3600
