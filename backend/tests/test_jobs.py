"""
Background jobs: pipeline event order, failure reporting, SSE streaming and resume.

Needs a real Redis (streams + blocking XREAD). Set TEST_REDIS_URL, or these tests skip.
CI starts a Redis service container for them.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import pytest
import redis
from fastapi.testclient import TestClient
from redis.asyncio import Redis as AsyncRedis

import services
from agents.transcript_agent import TranscriptUnavailableError
from jobs import pipeline
from jobs.events import JobEventBus
from models.schemas import ContentAgentResult, Flashcard, OutlineItem, TranscriptChunk

REDIS_URL = os.getenv("TEST_REDIS_URL", "")
VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

needs_redis = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")


def _redis_up() -> bool:
    try:
        return bool(REDIS_URL) and redis.Redis.from_url(REDIS_URL).ping()
    except Exception:
        return False


pytestmark = needs_redis


@pytest.fixture(autouse=True)
def _flush():
    if not _redis_up():
        pytest.skip("Redis not reachable")
    redis.Redis.from_url(REDIS_URL).flushdb()
    yield


def _chunks():
    return [
        TranscriptChunk(text=f"chunk {i}", start=i * 30.0, end=i * 30.0 + 29, chunk_index=i, word_count=2)
        for i in range(3)
    ]


def _content():
    return ContentAgentResult(
        outline=[OutlineItem(timestamp=0, title="Intro", description="d")],
        summary_90s="s90",
        summary_5min="s5",
        summary_full="sf",
        flashcards=[Flashcard(question="q", answer="a", source_timestamp=0)] * 10,
    )


@pytest.fixture()
def fake_agents(monkeypatch):
    """Transcript 0.1s, indexing 0.1s, Claude content 0.5s: indexing must surface first."""

    def transcript(url):
        time.sleep(0.1)
        return "jNQXAC9IVRw", _chunks()

    class Content:
        def process(self, chunks):
            time.sleep(0.5)
            return _content()

    def index(video_id, chunks):
        time.sleep(0.1)
        return True

    monkeypatch.setattr(services.transcript_agent, "process", transcript)
    monkeypatch.setattr(services, "get_content_agent", lambda: Content())
    monkeypatch.setattr(services.search_agent, "index_chunks", index)


async def _events(job_id: str) -> list:
    r = AsyncRedis.from_url(REDIS_URL)
    try:
        return await JobEventBus(r).history(job_id)
    finally:
        await r.aclose()


def test_student_pipeline_streams_stages_in_order(fake_agents):
    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("j1", "student", {})
        await pipeline.run_student(bus, "j1", VIDEO_URL)
        job = await bus.get("j1")
        await r.aclose()
        return job

    job = asyncio.run(run())
    events = asyncio.run(_events("j1"))
    types = [e.type for e in events]
    assert types == [
        "queued",
        "started",
        "transcript_fetched",
        "chunks_indexed",  # indexing finishes before Claude, so it arrives first
        "outline_ready",
        "summaries_ready",
        "flashcards_ready",
        "done",
    ]
    by_type = {e.type: e.data for e in events}
    assert by_type["transcript_fetched"]["video_id"] == "jNQXAC9IVRw"
    assert by_type["chunks_indexed"]["indexed"] is True
    # The first visible content (video + search) is ready long before the full kit.
    assert by_type["transcript_fetched"]["t"] < by_type["done"]["t"]
    timings = by_type["done"]["timings"]
    assert {"transcript_s", "index_s", "content_s", "total_s"} <= set(timings)
    # Content and indexing ran concurrently: total ≈ transcript + max(content, index).
    assert timings["total_s"] < timings["transcript_s"] + timings["content_s"] + timings["index_s"]
    assert job["status"] == "done"
    assert job["result"]["summary_90s"] == "s90" and "chunks" not in job["result"]


def test_failure_is_reported_as_event(monkeypatch):
    def transcript(url):
        raise TranscriptUnavailableError("No transcript found for this video.")

    monkeypatch.setattr(services.transcript_agent, "process", transcript)

    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("j2", "student", {})
        await pipeline.run_student(bus, "j2", VIDEO_URL)
        job = await bus.get("j2")
        await r.aclose()
        return job

    job = asyncio.run(run())
    last = asyncio.run(_events("j2"))[-1]
    assert last.type == "failed"
    assert last.data["status"] == 404 and "No transcript" in last.data["message"]
    assert job["status"] == "failed"


def test_provost_reports_each_lecture(monkeypatch):
    def transcript(url):
        if "bad" in url:
            raise TranscriptUnavailableError("This video is private or unavailable.")
        return "jNQXAC9IVRw", _chunks()

    class Provost:
        def generate_curriculum_map(self, lectures, objectives):
            return {"overall_coverage_score": 6}

    monkeypatch.setattr(services.transcript_agent, "process", transcript)
    monkeypatch.setattr(services, "get_provost_agent", lambda: Provost())

    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("j3", "provost", {})
        await pipeline.run_provost(bus, "j3", [VIDEO_URL, "https://youtu.be/badbadbad12"], "1) x")
        await r.aclose()

    asyncio.run(run())
    events = asyncio.run(_events("j3"))
    types = [e.type for e in events]
    assert types == ["queued", "started", "lecture_fetched", "lecture_failed", "analyzing", "done"]
    assert events[-1].data["result"]["failed_urls"][0]["error"].startswith("This video is private")


# ---------- HTTP + SSE, with the ARQ worker running inside the API process ----------


@pytest.fixture()
def live_client(monkeypatch, fake_agents):
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("RUN_WORKER_IN_PROCESS", "true")
    import main

    with TestClient(main.app) as client:  # runs lifespan: Redis pool + in-process worker
        yield client


def _read_sse(client, url, headers=None, stop_at=("done", "failed"), max_events=50):
    events = []
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        cur = {}
        for line in r.iter_lines():
            if line.startswith("id: "):
                cur["id"] = line[4:]
            elif line.startswith("event: "):
                cur["event"] = line[7:]
            elif line.startswith("data: "):
                cur["data"] = json.loads(line[6:])
            elif line == "" and "event" in cur:
                events.append(cur)
                if cur["event"] in stop_at or len(events) >= max_events:
                    break
                cur = {}
    return events


def test_post_jobs_returns_immediately_and_sse_delivers_everything(live_client):
    t = time.perf_counter()
    r = live_client.post("/jobs", json={"mode": "student", "youtube_url": VIDEO_URL})
    enqueue_latency = time.perf_counter() - t
    assert r.status_code == 202, r.text
    assert enqueue_latency < 0.5  # no agent work happens in the request
    job_id = r.json()["job_id"]

    events = _read_sse(live_client, f"/jobs/{job_id}/events")
    names = [e["event"] for e in events]
    assert names[0] == "queued" and names[-1] == "done"
    assert "transcript_fetched" in names and "flashcards_ready" in names

    status = live_client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "done" and status["result"]["video_id"] == "jNQXAC9IVRw"


def test_sse_resumes_from_last_event_id(live_client):
    job_id = live_client.post("/jobs", json={"mode": "student", "youtube_url": VIDEO_URL}).json()["job_id"]
    first = _read_sse(live_client, f"/jobs/{job_id}/events", stop_at=("transcript_fetched",))
    resumed = _read_sse(live_client, f"/jobs/{job_id}/events", headers={"Last-Event-ID": first[-1]["id"]})
    names = [e["event"] for e in resumed]
    assert "transcript_fetched" not in names and "queued" not in names  # nothing replayed twice
    assert names[-1] == "done"


def test_sse_does_not_block_other_requests(live_client):
    job_id = live_client.post("/jobs", json={"mode": "student", "youtube_url": VIDEO_URL}).json()["job_id"]
    done = threading.Event()

    def consume():
        _read_sse(live_client, f"/jobs/{job_id}/events")
        done.set()

    th = threading.Thread(target=consume)
    th.start()
    time.sleep(0.05)
    t = time.perf_counter()
    assert live_client.get("/health").status_code == 200
    assert time.perf_counter() - t < 0.3
    th.join(5)
    assert done.is_set()


def test_invalid_url_rejected_before_enqueue(live_client):
    r = live_client.post("/jobs", json={"mode": "student", "youtube_url": "https://example.com/x"})
    assert r.status_code == 422


def test_unknown_job_is_404(live_client):
    assert live_client.get("/jobs/nope").status_code == 404
    assert live_client.get("/jobs/nope/events").status_code == 404
