"""
Map-reduce for long lectures (agents/map_reduce.py): splitting, the map step's validation
and cancellation, the digest handed to the reduce agents, and the pipeline wiring per mode.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time

import pytest
import redis
from redis.asyncio import Redis as AsyncRedis

import agents.structured_call as sc
import services
from agents import map_reduce as mr
from agents.content_streaming import StreamingContentAgent
from agents.structured_call import StructuredCallCancelled, StructuredOutputError
from fake_claude import FakeClaude
from jobs import pipeline
from jobs.events import JobEventBus
from models.schemas import TranscriptChunk

REDIS_URL = os.getenv("TEST_REDIS_URL", "")


def _lecture(minutes: int, words_per_chunk: int = 150) -> list[TranscriptChunk]:
    """One 60-second chunk per minute, ~150 words each (normal speaking pace)."""
    return [
        TranscriptChunk(
            text=" ".join(f"w{i}" for _ in range(words_per_chunk)),
            start=i * 60.0,
            end=i * 60.0 + 59,
            chunk_index=i,
            word_count=words_per_chunk,
        )
        for i in range(minutes)
    ]


@pytest.fixture()
def paths(monkeypatch):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(sc, "record_path", lambda agent, path: seen.append((agent, path)))
    return seen


# ---------- splitting ----------


def test_split_respects_chunk_boundaries_and_folds_a_short_tail():
    chunks = _lecture(150)  # 2.5 h, 22,500 words
    sections = mr.split_sections(chunks, 4000)
    assert [c for s in sections for c in s] == chunks  # nothing lost, nothing reordered
    assert all(mr.word_count(s) <= 4000 for s in sections[:-1])
    assert len(sections) == 6  # 5 × 26 chunks + a 20-chunk tail (big enough to stand alone)
    # A tail under a quarter of the target joins the previous section instead.
    short_tail = mr.split_sections(_lecture(27), 4000)
    assert len(short_tail) == 1 and len(short_tail[0]) == 27


def test_budgets_decide_the_path():
    hour = _lecture(60)  # 9,000 words
    assert not mr.needs_map(hour, mr.STUDENT_WORD_BUDGET)
    assert mr.needs_map(hour, mr.FACULTY_WORD_BUDGET)  # Faculty used to silently drop the last 20 min
    assert mr.needs_map(_lecture(61), mr.STUDENT_WORD_BUDGET)
    assert not mr.needs_map(_lecture(20), mr.PROVOST_WORD_BUDGET)


# ---------- the map step ----------


def test_notes_for_maps_every_section_in_parallel_and_reports_progress(paths):
    fake = FakeClaude(structured_delay=0.05)
    agent = mr.NotesAgent(client=fake, model="m")
    progress: list[tuple[int, int]] = []
    t = time.perf_counter()
    notes = agent.notes_for(_lecture(150), on_progress=lambda d, n: progress.append((d, n)))
    elapsed = time.perf_counter() - t

    assert len(notes.sections) == 6 and len(fake.calls) == 6
    assert [s["start"] for s in notes.sections] == sorted(s["start"] for s in notes.sections)
    assert progress[-1] == (6, 6) and len(progress) == 6
    assert paths == [("map", "tool")] * 6
    assert all(c["tools"] == [mr.NOTES_TOOL] for c in fake.calls)
    assert notes.usage["attempts"] == 6
    # 6 sections × ~0.4s each, 4 at a time → well under the sequential time.
    sequential = sum(1 for _ in fake.calls) * 0.4
    assert elapsed < sequential * 0.75


def test_a_timestamp_outside_its_section_is_sent_back_and_corrected(paths):
    good = {
        "title": "Intro",
        "summary": "s",
        "key_points": [{"timestamp": t, "point": "p"} for t in (0, 60, 120)],
    }
    wrong = {**good, "key_points": [{"timestamp": t, "point": "p"} for t in (0, 60, 9000)]}
    fake = FakeClaude(notes_inputs=[wrong, good])
    notes = mr.NotesAgent(client=fake, model="m").notes_for(_lecture(10))
    assert paths == [("map", "tool_retry")]
    retry = fake.calls[1]["messages"][2]["content"][0]
    assert retry["is_error"] and "outside this section" in retry["content"]
    assert [k["timestamp"] for k in notes.sections[0]["key_points"]] == [0, 60, 120]


def test_one_failed_section_fails_the_map_and_stops_the_rest(paths):
    bad = {"title": "x", "summary": "s", "key_points": []}  # < 3 key points, every time
    fake = FakeClaude(notes_inputs=[bad] * 50, structured_delay=0.02)
    with pytest.raises(StructuredOutputError):
        mr.NotesAgent(client=fake, model="m").notes_for(_lecture(150))
    assert ("map", "failed") in paths
    assert len(fake.calls) < 12  # 6 sections × 2 attempts if nothing stopped


def test_stop_cancels_the_map():
    stop = threading.Event()
    fake = FakeClaude(structured_delay=0.05)
    agent = mr.NotesAgent(client=fake, model="m")
    threading.Timer(0.15, stop.set).start()
    with pytest.raises(StructuredCallCancelled):
        agent.notes_for(_lecture(150), should_stop=stop.is_set)
    assert len(fake.calls) <= 6


def test_prompt_version_tracks_model_and_prompt():
    a = mr.NotesAgent(client=FakeClaude(), model="m1")
    b = mr.NotesAgent(client=FakeClaude(), model="m2")
    assert a.prompt_version.startswith("notes-") and a.prompt_version != b.prompt_version


# ---------- the reduce input ----------


def test_digest_is_ordered_timestamped_and_spans_the_whole_lecture():
    chunks = _lecture(150)
    notes = mr.NotesAgent(client=FakeClaude(), model="m").notes_for(chunks)
    digest = mr.digest_chunks(notes, chunks)

    starts = [c.start for c in digest]
    assert starts == sorted(starts)
    assert digest[0].text.startswith(mr.DIGEST_NOTE)
    assert digest[-1].end == chunks[-1].end  # max_timestamp for validation = real lecture end
    assert sum(1 for c in digest if c.text.startswith("SECTION") or "SECTION \"" in c.text) == 6
    assert any(c.text.startswith("Definition — gradient") for c in digest)
    # The whole point: the reduce step reads a fraction of the transcript.
    assert mr.word_count(digest) < mr.word_count(chunks) / 10


def test_reduce_agents_accept_the_digest(paths):
    chunks = _lecture(150)
    notes = mr.NotesAgent(client=FakeClaude(), model="m").notes_for(chunks)
    digest = mr.digest_chunks(notes, chunks)
    agent = StreamingContentAgent()
    fake = FakeClaude()
    agent._client = fake
    agent.generate_structured(digest)
    system_text = fake.calls[0]["system"][-1]["text"]
    assert mr.DIGEST_NOTE in system_text and "w0 w0" not in system_text


# ---------- pipeline wiring (needs Redis, like test_jobs) ----------


def _redis_up() -> bool:
    try:
        return bool(REDIS_URL) and redis.Redis.from_url(REDIS_URL).ping()
    except Exception:
        return False


needs_redis = pytest.mark.skipif(not _redis_up(), reason="Redis not reachable")


@pytest.fixture()
def long_lecture(monkeypatch):
    redis.Redis.from_url(REDIS_URL).flushdb()
    chunks = _lecture(150)
    monkeypatch.setattr(services.transcript_agent, "process", lambda url: ("LONGlecture1", chunks))
    monkeypatch.setattr(services.search_agent, "index_chunks", lambda vid, ch: len(ch) == 150)
    # No Postgres in these tests: no transcript/result/notes reuse between runs.
    monkeypatch.setattr(services, "store", None)
    notes_fake = FakeClaude(structured_delay=0.01)
    notes_agent = mr.NotesAgent(client=notes_fake, model="m")
    monkeypatch.setattr(services, "get_notes_agent", lambda: notes_agent)
    content = StreamingContentAgent()
    content._client = FakeClaude()
    monkeypatch.setattr(services, "get_streaming_content_agent", lambda: content)
    return {"chunks": chunks, "notes_fake": notes_fake, "content": content}


async def _run(fn, job_id, kind, *args):
    r = AsyncRedis.from_url(REDIS_URL)
    bus = JobEventBus(r)
    await bus.create(job_id, kind, {})
    await fn(bus, job_id, *args)
    events = await bus.history(job_id)
    await r.aclose()
    return events


@needs_redis
def test_student_long_lecture_maps_then_reduces(long_lecture):
    events = asyncio.run(_run(pipeline.run_student, "m1", "student", "https://youtu.be/LONGlecture1"))
    types = [e.type for e in events]
    assert types.index("transcript_fetched") < types.index("mapping") < types.index("notes_ready")
    assert types.index("notes_ready") < types.index("summary_delta")
    mapped = [e.data for e in events if e.type == "section_mapped"]
    assert [m["done"] for m in mapped] == [1, 2, 3, 4, 5, 6]  # in order, none after notes_ready
    assert types.index("notes_ready") > max(i for i, t in enumerate(types) if t == "section_mapped")
    done = events[-1]
    assert done.type == "done"
    assert done.data["timings"]["map"]["sections"] == 6
    assert done.data["timings"]["usage"]["map"]["attempts"] == 6
    # Search still indexes the full transcript, not the notes.
    assert done.data["result"]["indexed"] is True
    # Both reduce calls read notes, not the raw transcript.
    for call in long_lecture["content"]._client.calls:
        assert mr.DIGEST_NOTE in call["system"][-1]["text"]


@needs_redis
def test_short_lecture_skips_the_map(long_lecture, monkeypatch):
    short = _lecture(20)
    monkeypatch.setattr(services.transcript_agent, "process", lambda url: ("SHORTlectur", short))
    monkeypatch.setattr(services.search_agent, "index_chunks", lambda vid, ch: True)
    events = asyncio.run(_run(pipeline.run_student, "m2", "student", "https://youtu.be/SHORTlectur"))
    assert not {"mapping", "section_mapped", "notes_ready"} & {e.type for e in events}
    assert long_lecture["notes_fake"].calls == []
    assert events[-1].type == "done" and "map" not in events[-1].data["timings"]


@needs_redis
def test_stop_during_the_map_cancels_the_job(long_lecture, monkeypatch):
    slow = mr.NotesAgent(client=FakeClaude(structured_delay=0.2), model="m")
    monkeypatch.setattr(services, "get_notes_agent", lambda: slow)

    async def run():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create("m3", "student", {})
        task = asyncio.create_task(pipeline.run_student(bus, "m3", "https://youtu.be/LONGlecture1"))
        while "mapping" not in [e.type for e in await bus.history("m3")]:
            await asyncio.sleep(0.05)
        await bus.request_cancel("m3")
        await task
        events = await bus.history("m3")
        await r.aclose()
        return events

    events = asyncio.run(run())
    assert events[-1].type == "cancelled"
    assert "summary_delta" not in [e.type for e in events]


@needs_redis
def test_faculty_reads_notes_for_a_lecture_over_its_budget(long_lecture, monkeypatch):
    seen = {}

    class Faculty:
        prompt_version = "faculty-test"

        def generate_report(self, chunks, video_id):
            seen["chunks"] = chunks
            return {"overall_score": 7}

    monkeypatch.setattr(services, "get_faculty_agent", lambda: Faculty())
    events = asyncio.run(_run(pipeline.run_faculty, "m4", "faculty", "https://youtu.be/LONGlecture1"))
    assert events[-1].type == "done"
    assert seen["chunks"][0].text.startswith(mr.DIGEST_NOTE)
    assert seen["chunks"][-1].end == long_lecture["chunks"][-1].end  # whole lecture, not the first 40 min


@needs_redis
def test_provost_maps_only_the_long_lectures(long_lecture, monkeypatch):
    short = _lecture(20)
    by_url = {"https://youtu.be/LONGlecture1": ("LONGlecture1", long_lecture["chunks"]),
              "https://youtu.be/SHORTlectur": ("SHORTlectur", short)}
    monkeypatch.setattr(services.transcript_agent, "process", lambda url: by_url[url])
    seen = {}

    class Provost:
        def generate_curriculum_map(self, lectures, objectives):
            seen["lectures"] = lectures
            return {"overall_coverage_score": 6}

    monkeypatch.setattr(services, "get_provost_agent", lambda: Provost())
    events = asyncio.run(
        _run(pipeline.run_provost, "m5", "provost", list(by_url), "1) x")
    )
    mapping = [e.data for e in events if e.type == "mapping"]
    assert len(mapping) == 1 and mapping[0]["lecture_index"] == 0
    long_l, short_l = seen["lectures"]
    assert long_l["chunks"][0]["text"].startswith(mr.DIGEST_NOTE)
    assert short_l["chunks"][0]["text"] == short[0].text  # under budget: raw transcript
    assert events[-1].type == "done"
