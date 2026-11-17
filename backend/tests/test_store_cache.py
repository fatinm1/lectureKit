"""
Postgres + pgvector storage, the Redis read-through cache, and cached job replays.

Needs TEST_DATABASE_URL (Postgres with the `vector` extension available) and TEST_REDIS_URL.
CI starts both as service containers; locally these tests skip without them.
"""

from __future__ import annotations

import asyncio
import os
import time

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from redis.asyncio import Redis as AsyncRedis

import services
from agents.content_streaming import StreamingContentAgent
from agents.search_agent import SearchAgent
from db.cache import Cache
from db.store import Store
from fake_claude import FakeClaude
from jobs import pipeline
from jobs.events import JobEventBus
from models.schemas import TranscriptChunk

DB_URL = os.getenv("TEST_DATABASE_URL", "")
REDIS_URL = os.getenv("TEST_REDIS_URL", "")
VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
VIDEO_ID = "jNQXAC9IVRw"

pytestmark = pytest.mark.skipif(not (DB_URL and REDIS_URL), reason="TEST_DATABASE_URL / TEST_REDIS_URL not set")


def _chunks():
    texts = [
        "gradient descent updates weights using the gradient of the loss",
        "backpropagation applies the chain rule through the computation graph",
        "the course logistics include homework deadlines and office hours",
    ]
    return [
        TranscriptChunk(text=t, start=i * 60.0, end=i * 60.0 + 59, chunk_index=i, word_count=len(t.split()))
        for i, t in enumerate(texts)
    ]


@pytest.fixture(scope="module")
def store():
    s = Store(DB_URL)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clean(store):
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE lectures, jobs CASCADE")
    redis.Redis.from_url(REDIS_URL).flushdb()
    yield


@pytest.fixture()
def cache(store):
    return Cache(store, redis.Redis.from_url(REDIS_URL))


# ---------- Store ----------


def test_migrate_is_idempotent(store):
    store.migrate()
    store.migrate()


def test_transcript_round_trip(store):
    assert store.get_transcript(VIDEO_ID) is None
    store.save_transcript(VIDEO_ID, VIDEO_URL, _chunks())
    got = store.get_transcript(VIDEO_ID)
    assert [c.text for c in got] == [c.text for c in _chunks()]
    assert got[2].start == 120.0


def test_pgvector_search_ranks_and_scores(store):
    agent = SearchAgent(store=store)
    assert agent.index_chunks(VIDEO_ID, _chunks())
    assert store.has_embeddings(VIDEO_ID)
    hits = agent.search(VIDEO_ID, "chain rule backpropagation", n_results=3)
    assert hits[0].chunk_index == 1
    assert hits[0].relevance_score > hits[-1].relevance_score
    assert all(0.0 <= h.relevance_score <= 1.0 for h in hits)


def test_search_survives_a_new_process(store):
    """The /tmp ChromaDB bug: vectors must outlive the process that wrote them."""
    SearchAgent(store=store).index_chunks(VIDEO_ID, _chunks())
    fresh_store = Store(DB_URL)  # simulates a redeployed API with an empty local disk
    try:
        hits = SearchAgent(store=fresh_store).search(VIDEO_ID, "homework deadlines")
        assert hits[0].chunk_index == 2
    finally:
        fresh_store.close()


def test_reindex_skips_embedding(store, monkeypatch):
    agent = SearchAgent(store=store)
    agent.index_chunks(VIDEO_ID, _chunks())
    monkeypatch.setattr(agent.model, "encode", lambda *a, **k: pytest.fail("re-embedded"))
    assert agent.index_chunks(VIDEO_ID, _chunks())


def test_unprocessed_video_search_is_not_found(store):
    from agents.search_agent import SearchAgentError

    with pytest.raises(SearchAgentError, match="not processed"):
        SearchAgent(store=store).search("zzzzzzzzzzz", "anything")


def test_results_are_keyed_by_prompt_version(store):
    store.save_transcript(VIDEO_ID, VIDEO_URL, _chunks())
    store.save_result(VIDEO_ID, "student", "en", "student-aaa", {"summary_90s": "old"}, {"input_tokens": 5})
    assert store.get_result(VIDEO_ID, "student", "en", "student-aaa").payload["summary_90s"] == "old"
    assert store.get_result(VIDEO_ID, "student", "en", "student-bbb") is None
    assert store.get_result(VIDEO_ID, "student", "es", "student-aaa") is None


# ---------- Cache ----------


def test_cache_reads_through_redis_then_postgres(store, cache):
    store.save_transcript(VIDEO_ID, VIDEO_URL, _chunks())
    usage = {"summaries": {"input_tokens": 100, "output_tokens": 50}, "structured": {"output_tokens": 25}}
    assert cache.get_result(VIDEO_ID, "student", "en", "pv") is None
    cache.save_result(VIDEO_ID, "student", "en", "pv", {"x": 1}, usage)

    assert cache.get_result(VIDEO_ID, "student", "en", "pv").payload == {"x": 1}  # Redis
    cache.redis.delete(cache._result_key(VIDEO_ID, "student", "en", "pv"))
    assert cache.get_result(VIDEO_ID, "student", "en", "pv").payload == {"x": 1}  # Postgres, refills Redis
    assert cache.redis.exists(cache._result_key(VIDEO_ID, "student", "en", "pv"))

    c = cache.counters()
    assert c["result_misses"] == 1 and c["result_redis_hits"] == 1 and c["result_db_hits"] == 1
    assert c["saved_output_tokens"] == 2 * 75 and c["spent_input_tokens"] == 100


def test_search_cache_normalizes_queries(cache):
    cache.save_search(VIDEO_ID, "  Chain   RULE ", 3, [{"chunk_index": 1}])
    assert cache.get_search(VIDEO_ID, "chain rule", 3) == [{"chunk_index": 1}]
    assert cache.get_search(VIDEO_ID, "chain rule", 5) is None


# ---------- cached job replays ----------


@pytest.fixture()
def wired(monkeypatch, store, cache):
    """Point services at the test DB/cache with a fake Claude and a counting transcript fetch."""
    agent = StreamingContentAgent()
    agent._client = FakeClaude(summary_delay=0.005, structured_delay=0.01)
    fetches = {"n": 0}

    def transcript(url):
        fetches["n"] += 1
        return VIDEO_ID, _chunks()

    monkeypatch.setattr(services, "store", store)
    monkeypatch.setattr(services, "cache", cache)
    monkeypatch.setattr(services, "search_agent", SearchAgent(store=store))
    monkeypatch.setattr(services, "get_streaming_content_agent", lambda: agent)
    monkeypatch.setattr(services.transcript_agent, "process", transcript)
    return agent, fetches


def _run(job_id: str):
    async def go():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create(job_id, "student", {})
        t = time.perf_counter()
        await pipeline.run_student(bus, job_id, VIDEO_URL)
        elapsed = time.perf_counter() - t
        events = await bus.history(job_id)
        await r.aclose()
        return events, elapsed

    return asyncio.run(go())


def test_second_request_is_served_from_cache(wired, store):
    agent, fetches = wired
    first, t_first = _run("c1")
    assert first[-1].type == "done" and not first[-1].data.get("cached")
    calls_after_first = len(agent._client.calls)
    assert calls_after_first == 2 and fetches["n"] == 1

    second, t_second = _run("c2")
    done = second[-1]
    assert done.type == "done" and done.data["cached"] is True and done.data["timings"]["cache_hit"]
    assert len(agent._client.calls) == calls_after_first  # no Claude calls
    assert fetches["n"] == 1  # no transcript fetch
    assert "summary_delta" not in [e.type for e in second]
    for key in ("summary_90s", "outline", "flashcards"):
        assert done.data["result"][key] == first[-1].data["result"][key]
    assert t_second < t_first and done.data["timings"]["total_s"] < 0.5

    m = store.job_metrics()
    assert m["jobs"] == 2 and m["cache_hits"] == 1 and m["cache_hit_rate"] == 0.5


def test_prompt_change_regenerates_but_reuses_transcript(wired, monkeypatch):
    agent, fetches = wired
    _run("p1")
    monkeypatch.setattr(StreamingContentAgent, "_summaries_instruction", staticmethod(lambda: "new prompt @@SUMMARY_90S@@"))
    events, _ = _run("p2")
    assert events[-1].type == "done" and not events[-1].data.get("cached")
    assert len(agent._client.calls) == 4  # regenerated with the new prompt
    assert fetches["n"] == 1  # transcript came from Postgres
    assert events[-1].data["timings"]["transcript_cached"] is True


def test_api_search_cache_metrics_and_health(wired, monkeypatch):
    import main

    _run("a1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    client = TestClient(main.app)
    body = {"youtube_url": VIDEO_URL, "query": "chain rule"}
    first = client.post("/search", json=body).json()
    second = client.post("/search", json=body).json()
    assert first == second and first["results"][0]["chunk_index"] == 1

    _run("a2")  # cache hit
    m = client.get("/metrics").json()
    assert m["search_cache_hit_rate"] == 0.5
    assert m["result_cache_hit_rate"] == 0.5
    assert m["estimated_usd"]["saved_by_cache"] > 0
    assert m["jobs"]["cache_hits"] == 1

    h = client.get("/health").json()
    assert h["database"] is True and h["cache"] is True
