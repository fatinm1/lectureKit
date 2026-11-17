"""
Purpose: The agent pipelines for each mode, written as background jobs that report progress.

Each function runs the same agents as the synchronous endpoints in `main.py`, but emits an
event the moment each stage finishes instead of returning one response at the end:

Student:  started → transcript_fetched ─┬→ summary_delta × N → summaries_ready   (streamed Claude call)
                                        ├→ outline_ready → flashcards_ready      (structured Claude call)
                                        └→ chunks_indexed                        (embeddings)
          → done | failed | cancelled     (the three branches run concurrently)
Faculty:  started → transcript_fetched → analyzing → done | failed
Provost:  started → lecture_fetched / lecture_failed (per URL) → analyzing → done | failed

Agents are synchronous (Anthropic SDK, yt-dlp, sentence-transformers), so every call goes
through `asyncio.to_thread` to keep the worker's event loop free for other jobs and for the
SSE connections when the worker runs inside the API process.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import asdict
from typing import Any

import services
from agents.content_streaming import SECTIONS, ContentCancelled, StreamedSummaries, StructuredContent
from jobs.events import JobEventBus
from services import classify_error
from utils.youtube import extract_youtube_video_id

logger = logging.getLogger("lecturekit.jobs")

CANCEL_POLL_S = 0.5
DELTA_BATCH_S = 0.1


async def _fail(bus: JobEventBus, job_id: str, stage: str, exc: BaseException) -> None:
    status, message = classify_error(exc)
    logger.warning("Job %s failed at %s: %s: %s", job_id, stage, type(exc).__name__, exc)
    await bus.emit(job_id, "failed", {"stage": stage, "status": status, "message": message})


class _Cancelled(Exception):
    """Raised inside the pipeline when the user pressed Stop."""


# ---------- persistence helpers (never fail a job because of the cache) ----------


async def _safe(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        logger.warning("Cache/DB call %s failed: %s: %s", getattr(fn, "__name__", fn), type(exc).__name__, exc)
        return None


async def _record_job(job_id: str, kind: str, video_id: Any, status: str, **kw: Any) -> None:
    if services.store is not None:
        await _safe(services.store.record_job, job_id, kind, video_id, status, **kw)


async def _load_or_fetch_transcript(youtube_url: str) -> tuple[str, list, bool]:
    """
    Return (video_id, chunks, from_db). A transcript already in Postgres is reused, which
    skips Supadata/YouTube entirely; a freshly fetched one is saved for next time.
    """
    video_id = extract_youtube_video_id(youtube_url)
    if services.store is not None:
        stored = await _safe(services.store.get_transcript, video_id)
        if stored:
            return video_id, stored, True
    video_id, chunks = await asyncio.to_thread(services.transcript_agent.process, youtube_url)
    if services.store is not None:
        await _safe(services.store.save_transcript, video_id, youtube_url, chunks)
    return video_id, chunks, False


async def _replay_cached_student(
    bus: JobEventBus, job_id: str, youtube_url: str, video_id: str, cached: Any, t0: float
) -> None:
    """Serve a stored study kit as the same event sequence a fresh run produces, minus the deltas."""
    result = dict(cached.payload)
    result["youtube_url"] = youtube_url
    await bus.emit(
        job_id,
        "transcript_fetched",
        {
            "video_id": video_id,
            "youtube_url": youtube_url,
            "chunk_count": result.get("chunk_count", 0),
            "cached": True,
        },
    )
    await bus.emit(job_id, "chunks_indexed", {"indexed": bool(result.get("indexed"))})
    await bus.emit(
        job_id,
        "summaries_ready",
        {k: result.get(k, "") for k in ("summary_90s", "summary_5min", "summary_full")},
    )
    await bus.emit(job_id, "outline_ready", {"outline": result.get("outline", [])})
    await bus.emit(job_id, "flashcards_ready", {"flashcards": result.get("flashcards", [])})
    timings = {"cache_hit": True, "total_s": round(time.perf_counter() - t0, 3)}
    await bus.set_result(job_id, result)
    await bus.emit(job_id, "done", {"result": result, "timings": timings, "cached": True})
    await _record_job(job_id, "student", video_id, "done", cache_hit=True, timings=timings)


async def _cancel_watcher(bus: JobEventBus, job_id: str, stop: threading.Event) -> None:
    """Poll the cancel flag and trip `stop`, which the agent threads check between pieces."""
    while not stop.is_set():
        if await bus.cancel_requested(job_id):
            stop.set()
            return
        await asyncio.sleep(CANCEL_POLL_S)


async def _finish_cancelled(bus: JobEventBus, job_id: str, partial: dict[str, Any]) -> None:
    await bus.set_result(job_id, partial)
    await bus.emit(job_id, "cancelled", {"result": partial})


async def run_student(bus: JobEventBus, job_id: str, youtube_url: str) -> None:
    t0 = time.perf_counter()
    timings: dict[str, Any] = {}
    stage = "transcript"
    loop = asyncio.get_running_loop()
    stop = threading.Event()
    watcher = asyncio.create_task(_cancel_watcher(bus, job_id, stop))

    # What the student has received so far, kept so a Stop can return the partial kit.
    partial: dict[str, Any] = {"youtube_url": youtube_url}
    summary_text = {s: "" for s in SECTIONS}

    try:
        await bus.emit(job_id, "started", {"mode": "student"})
        if stop.is_set() or await bus.cancel_requested(job_id):
            raise _Cancelled()

        # Step: Result cache. Same lecture + same prompts/model → serve the stored kit.
        agent = services.get_streaming_content_agent()
        prompt_version = agent.prompt_version
        video_id = extract_youtube_video_id(youtube_url)
        cached = await _safe(services.cache.get_result, video_id, "student", "en", prompt_version)
        if cached is not None:
            await _replay_cached_student(bus, job_id, youtube_url, video_id, cached, t0)
            return

        video_id, chunks, transcript_from_db = await _load_or_fetch_transcript(youtube_url)
        timings["transcript_s"] = round(time.perf_counter() - t0, 3)
        timings["transcript_cached"] = transcript_from_db
        partial.update({"video_id": video_id, "chunk_count": len(chunks)})
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
        if stop.is_set():
            raise _Cancelled()

        stage = "content"
        cache_warm = threading.Event()
        deltas: asyncio.Queue = asyncio.Queue()

        def on_delta(section: str, text: str) -> None:
            # Called from the agent's worker thread.
            loop.call_soon_threadsafe(deltas.put_nowait, (section, text))

        async def pump_deltas() -> None:
            """Forward summary text in small batches so Redis gets ~10 events/s, not one per token."""
            first = True
            while True:
                item = await deltas.get()
                if item is None:
                    return
                await asyncio.sleep(DELTA_BATCH_S)
                batch = [item]
                done = False
                while not deltas.empty():
                    nxt = deltas.get_nowait()
                    if nxt is None:
                        done = True
                        break
                    batch.append(nxt)
                merged: list[list[str]] = []
                for section, text in batch:
                    summary_text[section] += text
                    if merged and merged[-1][0] == section:
                        merged[-1][1] += text
                    else:
                        merged.append([section, text])
                for section, text in merged:
                    if first:
                        timings["first_summary_token_s"] = round(time.perf_counter() - t0, 3)
                        first = False
                    await bus.emit(job_id, "summary_delta", {"section": section, "text": text})
                if done:
                    return

        async def index() -> bool:
            t = time.perf_counter()
            try:
                ok = bool(await asyncio.to_thread(services.search_agent.index_chunks, video_id, chunks))
            except Exception as exc:  # Indexing failure must not fail the study kit.
                logger.exception("Indexing failed for %s: %s", video_id, type(exc).__name__)
                ok = False
            timings["index_s"] = round(time.perf_counter() - t, 3)
            partial["indexed"] = ok
            await bus.emit(job_id, "chunks_indexed", {"indexed": ok})
            return ok

        async def summaries() -> StreamedSummaries:
            pump = asyncio.create_task(pump_deltas())
            try:
                result = await asyncio.to_thread(
                    agent.stream_summaries, chunks, on_delta, stop.is_set, cache_warm
                )
            except BaseException:
                stop.set()
                deltas.put_nowait(None)
                await pump
                raise
            deltas.put_nowait(None)
            await pump
            timings["summaries_s"] = round(time.perf_counter() - t0, 3)
            final = {
                "summary_90s": result.summary_90s,
                "summary_5min": result.summary_5min,
                "summary_full": result.summary_full,
            }
            partial.update(final)
            await bus.emit(job_id, "summaries_ready", final)
            return result

        async def structured() -> StructuredContent:
            try:
                # No cache_warm wait: the two calls no longer share a cache prefix, so the
                # structured call starts at once instead of waiting for the summaries stream.
                result = await asyncio.to_thread(agent.generate_structured, chunks, stop.is_set)
            except BaseException:
                stop.set()
                raise
            timings["structured_s"] = round(time.perf_counter() - t0, 3)
            outline = [o.model_dump() for o in result.outline]
            flashcards = [f.model_dump() for f in result.flashcards]
            partial.update({"outline": outline, "flashcards": flashcards})
            await bus.emit(job_id, "outline_ready", {"outline": outline})
            await bus.emit(job_id, "flashcards_ready", {"flashcards": flashcards})
            return result

        results = await asyncio.gather(summaries(), structured(), index(), return_exceptions=True)
        errors = [r for r in results[:2] if isinstance(r, BaseException)]
        if errors and all(isinstance(e, ContentCancelled) for e in errors):
            raise _Cancelled()
        real = [e for e in errors if not isinstance(e, ContentCancelled)]
        if real:
            raise real[0]

        summ: StreamedSummaries = results[0]  # type: ignore[assignment]
        struct: StructuredContent = results[1]  # type: ignore[assignment]
        indexed = results[2] if isinstance(results[2], bool) else False

        timings["total_s"] = round(time.perf_counter() - t0, 3)
        timings["usage"] = {"summaries": asdict(summ.usage), "structured": asdict(struct.usage)}
        result = {
            "video_id": video_id,
            "youtube_url": youtube_url,
            "chunk_count": len(chunks),
            "outline": [o.model_dump() for o in struct.outline],
            "summary_90s": summ.summary_90s,
            "summary_5min": summ.summary_5min,
            "summary_full": summ.summary_full,
            "flashcards": [f.model_dump() for f in struct.flashcards],
            "indexed": indexed,
        }
        await bus.set_result(job_id, result)
        await _safe(
            services.cache.save_result, video_id, "student", "en", prompt_version, result, timings["usage"]
        )
        logger.info("Job %s student done %s", job_id, timings)
        await bus.emit(job_id, "done", {"result": result, "timings": timings})
        await _record_job(job_id, "student", video_id, "done", timings=timings, usage=timings["usage"])
    except _Cancelled:
        for section, text in summary_text.items():
            partial.setdefault(section, text.strip())
        partial.setdefault("outline", [])
        partial.setdefault("flashcards", [])
        partial.setdefault("indexed", False)
        logger.info("Job %s cancelled at %s", job_id, stage)
        await _finish_cancelled(bus, job_id, partial)
        await _record_job(job_id, "student", partial.get("video_id"), "cancelled", timings=timings)
    except Exception as exc:
        await _fail(bus, job_id, stage, exc)
        await _record_job(job_id, "student", partial.get("video_id"), "failed", timings=timings)
    finally:
        stop.set()
        watcher.cancel()


async def run_faculty(bus: JobEventBus, job_id: str, youtube_url: str) -> None:
    t0 = time.perf_counter()
    stage = "transcript"
    video_id = None
    try:
        await bus.emit(job_id, "started", {"mode": "faculty"})
        agent = services.get_faculty_agent()
        prompt_version = agent.prompt_version
        video_id = extract_youtube_video_id(youtube_url)

        cached = await _safe(services.cache.get_result, video_id, "faculty", "en", prompt_version)
        if cached is not None:
            result = dict(cached.payload)
            result["youtube_url"] = youtube_url
            await bus.emit(job_id, "transcript_fetched", {"video_id": video_id, "youtube_url": youtube_url, "cached": True})
            timings = {"cache_hit": True, "total_s": round(time.perf_counter() - t0, 3)}
            await bus.set_result(job_id, result)
            await bus.emit(job_id, "done", {"result": result, "timings": timings, "cached": True})
            await _record_job(job_id, "faculty", video_id, "done", cache_hit=True, timings=timings)
            return

        video_id, chunks, transcript_from_db = await _load_or_fetch_transcript(youtube_url)
        transcript_s = round(time.perf_counter() - t0, 3)
        await bus.emit(
            job_id,
            "transcript_fetched",
            {"video_id": video_id, "youtube_url": youtube_url, "chunk_count": len(chunks)},
        )

        stage = "analysis"
        await bus.emit(job_id, "analyzing", {})
        report = await asyncio.to_thread(lambda: agent.generate_report(chunks, video_id))
        result = {"video_id": video_id, "youtube_url": youtube_url, "report": report}
        await bus.set_result(job_id, result)
        timings = {
            "transcript_s": transcript_s,
            "transcript_cached": transcript_from_db,
            "total_s": round(time.perf_counter() - t0, 3),
        }
        await _safe(services.cache.save_result, video_id, "faculty", "en", prompt_version, result, None)
        await bus.emit(job_id, "done", {"result": result, "timings": timings})
        await _record_job(job_id, "faculty", video_id, "done", timings=timings)
    except Exception as exc:
        await _fail(bus, job_id, stage, exc)
        await _record_job(job_id, "faculty", video_id, "failed")


async def run_provost(bus: JobEventBus, job_id: str, youtube_urls: list[str], learning_objectives: str) -> None:
    t0 = time.perf_counter()
    stage = "transcript"
    try:
        await bus.emit(job_id, "started", {"mode": "provost", "total": len(youtube_urls)})
        lectures: list[dict[str, Any]] = []
        failed_urls: list[dict[str, str]] = []

        for i, url in enumerate(youtube_urls):
            try:
                video_id, chunks, _ = await _load_or_fetch_transcript(url)
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
