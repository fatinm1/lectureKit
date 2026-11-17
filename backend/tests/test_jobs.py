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
from agents.content_streaming import StreamingContentAgent
from fake_claude import FakeClaude
from jobs import pipeline
from jobs.events import JobEventBus
from models.schemas import TranscriptChunk

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


def _streaming_agent(**fake_kwargs) -> StreamingContentAgent:
    agent = StreamingContentAgent()
    agent._client = FakeClaude(**fake_kwargs)
    return agent


@pytest.fixture()
def fake_agents(monkeypatch):
    """Transcript 0.1s, indexing 0.1s; summaries stream for ~0.6s, structured JSON ~0.4s."""

    def transcript(url):
        time.sleep(0.1)
        return "jNQXAC9IVRw", _chunks()

    def index(video_id, chunks):
        time.sleep(0.1)
        return True

    agent = _streaming_agent(summary_delay=0.02, structured_delay=0.05)
    monkeypatch.setattr(services.transcript_agent, "process", transcript)
    monkeypatch.setattr(services, "get_streaming_content_agent", lambda: agent)
    monkeypatch.setattr(services.search_agent, "index_chunks", index)
    return agent


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
    assert types[:3] == ["queued", "started", "transcript_fetched"]
    assert types[-1] == "done"
    # Summary text streams in many small events, and the first one arrives before the
    # structured outline/flashcards are ready.
    deltas = [e for e in events if e.type == "summary_delta"]
    assert len(deltas) >= 3
    assert types.index("summary_delta") < types.index("outline_ready")
    assert types.index("outline_ready") < types.index("flashcards_ready")
    assert {"chunks_indexed", "summaries_ready"} <= set(types)
    # Concatenated deltas == the final summaries.
    by_type = {e.type: e.data for e in events}
    streamed = "".join(d.data["text"] for d in deltas if d.data["section"] == "summary_90s").strip()
    assert streamed == by_type["summaries_ready"]["summary_90s"]
    timings = by_type["done"]["timings"]
    assert timings["first_summary_token_s"] < timings["structured_s"] < timings["total_s"]
    # The structured call read the transcript from the prompt cache written by the stream.
    assert timings["usage"]["structured"]["cache_read_input_tokens"] > 0
    assert job["status"] == "done"
    assert job["result"]["summary_90s"].startswith("Gradient descent") and "chunks" not in job["result"]
    assert len(job["result"]["flashcards"]) == 10


def test_stop_cancels_claude_streams_and_keeps_partial_kit(monkeypatch, fake_agents):
    # Slow summaries so we can stop half-way.
    agent = _streaming_agent(summary_delay=0.05, structured_delay=0.2)
    monkeypatch.setattr(services, "get_streaming_content_agent", lambda: agent)

    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("jc", "student", {})
        task = asyncio.create_task(pipeline.run_student(bus, "jc", VIDEO_URL))
        # Wait for some summary text, then press Stop.
        for _ in range(100):
            if any(e.type == "summary_delta" for e in await bus.history("jc")):
                break
            await asyncio.sleep(0.05)
        t = time.perf_counter()
        await bus.request_cancel("jc")
        await task
        stop_latency = time.perf_counter() - t
        job = await bus.get("jc")
        await r.aclose()
        return job, stop_latency

    job, stop_latency = asyncio.run(run())
    events = asyncio.run(_events("jc"))
    types = [e.type for e in events]
    assert types[-1] == "cancelled" and "done" not in types
    assert stop_latency < 1.5
    assert agent._client.closed_early.get("summaries") is True  # stream closed → generation stops
    partial = events[-1].data["result"]
    assert partial["video_id"] == "jNQXAC9IVRw"
    assert partial["summary_90s"]  # what streamed before Stop is kept
    assert job["status"] == "cancelled"


def test_claude_failure_stops_the_other_call(monkeypatch, fake_agents):
    agent = _streaming_agent(summary_delay=0.01, structured_delay=0.05, fail={"summaries"})
    monkeypatch.setattr(services, "get_streaming_content_agent", lambda: agent)

    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("jf", "student", {})
        await pipeline.run_student(bus, "jf", VIDEO_URL)
        await r.aclose()

    asyncio.run(run())
    events = asyncio.run(_events("jf"))
    assert events[-1].type == "failed" and events[-1].data["stage"] == "content"
    assert "summary stream failed" in events[-1].data["message"]
    assert "done" not in [e.type for e in events]


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


def _read_sse(client, url, headers=None, stop_at=("done", "failed", "cancelled"), max_events=500):
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


def test_cancel_endpoint(live_client):
    job_id = live_client.post("/jobs", json={"mode": "student", "youtube_url": VIDEO_URL}).json()["job_id"]
    first = _read_sse(live_client, f"/jobs/{job_id}/events", stop_at=("transcript_fetched",))
    assert live_client.post(f"/jobs/{job_id}/cancel").json()["status"] in ("cancelling", "done")
    rest = _read_sse(
        live_client,
        f"/jobs/{job_id}/events",
        headers={"Last-Event-ID": first[-1]["id"]},
        stop_at=("done", "failed", "cancelled"),
    )
    assert rest[-1]["event"] in ("cancelled", "done")
    # Cancelling a finished job is a no-op.
    assert live_client.post(f"/jobs/{job_id}/cancel").json()["status"] in ("cancelled", "done")
    assert live_client.post("/jobs/nope/cancel").status_code == 404


def test_unknown_job_is_404(live_client):
    assert live_client.get("/jobs/nope").status_code == 404
    assert live_client.get("/jobs/nope/events").status_code == 404
