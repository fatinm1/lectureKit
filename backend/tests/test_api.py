"""API tests with every external dependency mocked."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

import services
from models.schemas import ContentAgentResult, Flashcard, OutlineItem, TranscriptChunk

VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _chunks():
    return [
        TranscriptChunk(text=f"chunk {i} about topic {i}", start=i * 30.0, end=i * 30.0 + 29, chunk_index=i, word_count=5)
        for i in range(4)
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
def api(monkeypatch):
    import main

    monkeypatch.setattr(services.transcript_agent, "process", lambda url: ("jNQXAC9IVRw", _chunks()))
    return main, TestClient(main.app)


def test_health(api):
    _, client = api
    assert client.get("/health").json()["status"] == "ok"


def test_process_runs_content_and_indexing_concurrently(api, monkeypatch):
    main, client = api
    seen = {}
    barrier = threading.Barrier(2, timeout=5)

    class SlowContent:
        def process(self, chunks):
            barrier.wait()  # only passes if indexing is running at the same time
            return _content()

    def slow_index(video_id, chunks):
        seen["thread"] = threading.current_thread().name
        barrier.wait()
        return True

    monkeypatch.setattr(services, "get_content_agent", lambda: SlowContent())
    monkeypatch.setattr(services.search_agent, "index_chunks", slow_index)

    r = client.post("/process", json={"youtube_url": VIDEO_URL})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indexed"] is True and body["summary_90s"] == "s90" and body["chunk_count"] == 4


def test_process_still_returns_when_indexing_fails(api, monkeypatch):
    main, client = api

    class Content:
        def process(self, chunks):
            return _content()

    def boom(*_a, **_k):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(services, "get_content_agent", lambda: Content())
    monkeypatch.setattr(services.search_agent, "index_chunks", boom)
    r = client.post("/process", json={"youtube_url": VIDEO_URL})
    assert r.status_code == 200 and r.json()["indexed"] is False


def test_validation_error_names_the_real_field(api):
    _, client = api
    r = client.post("/search", json={"youtube_url": VIDEO_URL})
    assert r.status_code == 422
    assert "query" in r.json()["detail"]


def test_faculty_does_not_block_other_requests(api, monkeypatch):
    """A slow /faculty call must not freeze /health (it used to be async def + blocking code)."""
    main, client = api

    class SlowFaculty:
        def generate_report(self, chunks, video_id):
            time.sleep(1.5)
            return {"overall_score": 7}

    monkeypatch.setattr(services, "get_faculty_agent", lambda: SlowFaculty())

    result = {}
    # `with TestClient(...)` shares ONE event loop across requests, like a real uvicorn worker.
    with TestClient(main.app) as shared:

        def call_faculty():
            result["r"] = shared.post("/faculty", json={"youtube_url": VIDEO_URL})

        t = threading.Thread(target=call_faculty)
        t.start()
        time.sleep(0.2)
        start = time.perf_counter()
        assert shared.get("/health").status_code == 200
        health_latency = time.perf_counter() - start
        t.join()
    assert result["r"].status_code == 200
    assert health_latency < 0.5


def test_provost_reports_failed_urls(api, monkeypatch):
    main, client = api

    def process(url):
        if "bad" in url:
            raise RuntimeError("no transcript")
        return ("jNQXAC9IVRw", _chunks())

    class Provost:
        def generate_curriculum_map(self, lectures, objectives):
            return {"overall_coverage_score": 5, "n": len(lectures)}

    monkeypatch.setattr(services.transcript_agent, "process", process)
    monkeypatch.setattr(services, "get_provost_agent", lambda: Provost())
    r = client.post(
        "/provost",
        json={"youtube_urls": [VIDEO_URL, "https://youtu.be/badbadbad12"], "learning_objectives": "1) x"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lecture_count"] == 1 and len(body["failed_urls"]) == 1


def test_provost_rejects_more_than_ten(api):
    _, client = api
    r = client.post("/provost", json={"youtube_urls": [VIDEO_URL] * 11, "learning_objectives": "x"})
    assert r.status_code == 422


def test_jobs_return_503_without_redis(api, monkeypatch):
    main, _ = api
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(main.app) as client:
        r = client.post("/jobs", json={"mode": "student", "youtube_url": VIDEO_URL})
    assert r.status_code == 503
