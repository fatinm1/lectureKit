"""
Purpose: The agent pipelines for each mode, written as background jobs that report progress.

Each function runs the same agents as the synchronous endpoints in `main.py`, but emits an
event the moment each stage finishes instead of returning one response at the end:

Student:  started → transcript_fetched → chunks_indexed ─┐
                                      └→ outline_ready → summaries_ready → flashcards_ready
                                                         (content + indexing run concurrently)
          → done | failed
Faculty:  started → transcript_fetched → analyzing → done | failed
Provost:  started → lecture_fetched / lecture_failed (per URL) → analyzing → done | failed

Agents are synchronous (Anthropic SDK, yt-dlp, sentence-transformers), so every call goes
through `asyncio.to_thread` to keep the worker's event loop free for other jobs and for the
SSE connections when the worker runs inside the API process.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import services
from jobs.events import JobEventBus
from services import classify_error
from utils.youtube import extract_youtube_video_id

logger = logging.getLogger("lecturekit.jobs")


async def _fail(bus: JobEventBus, job_id: str, stage: str, exc: BaseException) -> None:
    status, message = classify_error(exc)
    logger.warning("Job %s failed at %s: %s: %s", job_id, stage, type(exc).__name__, exc)
    await bus.emit(job_id, "failed", {"stage": stage, "status": status, "message": message})


async def run_student(bus: JobEventBus, job_id: str, youtube_url: str) -> None:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    stage = "transcript"
    try:
        await bus.emit(job_id, "started", {"mode": "student"})

        video_id, chunks = await asyncio.to_thread(services.transcript_agent.process, youtube_url)
        timings["transcript_s"] = round(time.perf_counter() - t0, 3)
        await bus.emit(
            job_id,
            "transcript_fetched",
            {
                "video_id": video_id,
                "youtube_url": youtube_url,
                "chunk_count": len(chunks),
                "duration_s": float(chunks[-1].end) if chunks else 0.0,
            },
        )

        async def index() -> bool:
            t = time.perf_counter()
            try:
                ok = bool(await asyncio.to_thread(services.search_agent.index_chunks, video_id, chunks))
            except Exception as exc:  # Indexing failure must not fail the study kit.
                logger.exception("Indexing failed for %s: %s", video_id, type(exc).__name__)
                ok = False
            timings["index_s"] = round(time.perf_counter() - t, 3)
            await bus.emit(job_id, "chunks_indexed", {"indexed": ok})
            return ok

        async def content() -> Any:
            t = time.perf_counter()
            result = await asyncio.to_thread(lambda: services.get_content_agent().process(chunks))
            timings["content_s"] = round(time.perf_counter() - t, 3)
            await bus.emit(job_id, "outline_ready", {"outline": [o.model_dump() for o in result.outline]})
            await bus.emit(
                job_id,
                "summaries_ready",
                {
                    "summary_90s": result.summary_90s,
                    "summary_5min": result.summary_5min,
                    "summary_full": result.summary_full,
                },
            )
            await bus.emit(job_id, "flashcards_ready", {"flashcards": [f.model_dump() for f in result.flashcards]})
            return result

        stage = "content"
        index_task = asyncio.create_task(index())
        try:
            content_result = await content()
        except BaseException:
            index_task.cancel()
            raise
        indexed = await index_task

        timings["total_s"] = round(time.perf_counter() - t0, 3)
        result = {
            "video_id": video_id,
            "youtube_url": youtube_url,
            "chunk_count": len(chunks),
            "outline": [o.model_dump() for o in content_result.outline],
            "summary_90s": content_result.summary_90s,
            "summary_5min": content_result.summary_5min,
            "summary_full": content_result.summary_full,
            "flashcards": [f.model_dump() for f in content_result.flashcards],
            "indexed": indexed,
        }
        await bus.set_result(job_id, result)
        logger.info("Job %s student done %s", job_id, timings)
        await bus.emit(job_id, "done", {"result": result, "timings": timings})
    except Exception as exc:
        await _fail(bus, job_id, stage, exc)


async def run_faculty(bus: JobEventBus, job_id: str, youtube_url: str) -> None:
    t0 = time.perf_counter()
    stage = "transcript"
    try:
        await bus.emit(job_id, "started", {"mode": "faculty"})
        video_id, chunks = await asyncio.to_thread(services.transcript_agent.process, youtube_url)
        transcript_s = round(time.perf_counter() - t0, 3)
        await bus.emit(
            job_id,
            "transcript_fetched",
            {"video_id": video_id, "youtube_url": youtube_url, "chunk_count": len(chunks)},
        )

        stage = "analysis"
        await bus.emit(job_id, "analyzing", {})
        report = await asyncio.to_thread(lambda: services.get_faculty_agent().generate_report(chunks, video_id))
        result = {"video_id": video_id, "youtube_url": youtube_url, "report": report}
        await bus.set_result(job_id, result)
        timings = {"transcript_s": transcript_s, "total_s": round(time.perf_counter() - t0, 3)}
        await bus.emit(job_id, "done", {"result": result, "timings": timings})
    except Exception as exc:
        await _fail(bus, job_id, stage, exc)


async def run_provost(bus: JobEventBus, job_id: str, youtube_urls: list[str], learning_objectives: str) -> None:
    t0 = time.perf_counter()
    stage = "transcript"
    try:
        await bus.emit(job_id, "started", {"mode": "provost", "total": len(youtube_urls)})
        lectures: list[dict[str, Any]] = []
        failed_urls: list[dict[str, str]] = []

        for i, url in enumerate(youtube_urls):
            try:
                video_id = extract_youtube_video_id(url)
                _, chunks = await asyncio.to_thread(services.transcript_agent.process, url)
                lectures.append(
                    {"video_id": video_id, "youtube_url": url, "chunks": [c.model_dump() for c in chunks]}
                )
                await bus.emit(
                    job_id,
                    "lecture_fetched",
                    {"index": i, "total": len(youtube_urls), "video_id": video_id},
                )
            except Exception as exc:
                _, message = classify_error(exc)
                failed_urls.append({"url": url, "error": message})
                await bus.emit(
                    job_id,
                    "lecture_failed",
                    {"index": i, "total": len(youtube_urls), "url": url, "error": message},
                )

        if not lectures:
            await bus.emit(
                job_id,
                "failed",
                {"stage": "transcript", "status": 404, "message": "Could not retrieve transcripts for any provided URLs"},
            )
            return

        stage = "analysis"
        await bus.emit(job_id, "analyzing", {"lecture_count": len(lectures)})
        curriculum_map = await asyncio.to_thread(
            lambda: services.get_provost_agent().generate_curriculum_map(lectures, learning_objectives)
        )
        result = {
            "lecture_count": len(lectures),
            "failed_urls": failed_urls,
            "video_ids": [l["video_id"] for l in lectures],
            "curriculum_map": curriculum_map,
        }
        await bus.set_result(job_id, result)
        await bus.emit(job_id, "done", {"result": result, "timings": {"total_s": round(time.perf_counter() - t0, 3)}})
    except Exception as exc:
        await _fail(bus, job_id, stage, exc)
