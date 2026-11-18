"""
"Ask the lecture": citation parsing, the agent's prompt, and the /ask SSE endpoint
(validation, grounding check, caching, follow-ups, client disconnect, errors).
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
import redis
from fastapi.testclient import TestClient

import main
import services
from agents.ask_agent import (
    ASK_SYSTEM,
    MAX_QUESTION_CHARS,
    AskAgent,
    extract_citations,
    normalize_question,
    sources_from_hits,
)
from agents.search_agent import SearchAgentError
from db.cache import Cache
from fake_claude import ASK_TEXT, FakeClaude

URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
REDIS_URL = os.getenv("TEST_REDIS_URL", "")


def _hit(start, text, score=0.5, idx=0):
    return SimpleNamespace(start=start, end=start + 59, text=text, relevance_score=score, chunk_index=idx)


HITS = [  # out of lecture order on purpose: sources are renumbered by time
    _hit(120, "Backpropagation applies the chain rule.", 0.8, 2),
    _hit(0, "Gradient descent follows the negative gradient.", 0.7, 0),
    _hit(60, "The chain rule composes derivatives.", 0.6, 1),
]


# ---------- pure helpers ----------


def test_citations_keep_valid_numbers_in_first_mention_order():
    assert extract_citations("a [2]. b [1, 3]. c [2][9]. d [10]", [1, 2, 3]) == [2, 1, 3]
    assert extract_citations("no sources here", [1, 2]) == []
    assert extract_citations("year [2019] isn't a citation", [1, 2]) == []


def test_sources_are_numbered_in_lecture_order():
    sources = sources_from_hits(HITS)
    assert [(s.n, s.start) for s in sources] == [(1, 0.0), (2, 60.0), (3, 120.0)]
    long = sources_from_hits([_hit(0, "x " * 400)])[0].public()
    assert len(long["snippet"]) <= 280 and long["snippet"].endswith("…")


def test_normalized_questions_share_a_cache_key():
    assert normalize_question("  What is  Backprop? ") == normalize_question("what is backprop")


def test_prompt_numbers_excerpts_with_times_and_keeps_history_short():
    fake = FakeClaude(summary_delay=0)
    agent = AskAgent(client=fake, model="m")
    history = [{"question": f"q{i}", "answer": "a" * 5000} for i in range(6)]
    it = agent.answer_stream("what is backprop?", sources_from_hits(HITS), history)
    list(it)
    call = fake.calls[0]
    assert call["system"] == ASK_SYSTEM and call["max_tokens"] == 700
    msgs = call["messages"]
    assert len(msgs) == 3 * 2 + 1  # last 3 turns only
    assert all(len(m["content"]) <= 1500 for m in msgs[1:-1:2])  # old answers truncated
    last = msgs[-1]["content"]
    assert "[1] (0:00–0:59)" in last and "[3] (2:00–2:59)" in last
    assert last.endswith("Student's question: what is backprop?")


def test_answer_stream_returns_checked_citations():
    agent = AskAgent(client=FakeClaude(summary_delay=0), model="m")
    gen = agent.answer_stream("q", sources_from_hits(HITS))
    pieces = []
    while True:
        try:
            pieces.append(next(gen))
        except StopIteration as stop:
            result = stop.value
            break
    assert "".join(pieces).strip() == ASK_TEXT
    assert result.citations == [1, 2, 3]  # [9] dropped: only 3 sources exist
    assert result.grounded and result.usage["output_tokens"] == 300


# ---------- the endpoint ----------


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture()
def api(monkeypatch):
    searches = []

    def search(video_id, query, n_results):
        searches.append((video_id, query, n_results))
        return HITS

    fake = FakeClaude(summary_delay=0)
    agent = AskAgent(client=fake, model="m")
    monkeypatch.setattr(services.search_agent, "search", search)
    monkeypatch.setattr(services, "get_ask_agent", lambda: agent)
    if REDIS_URL:
        r = redis.Redis.from_url(REDIS_URL)
        r.flushdb()
        monkeypatch.setattr(services, "cache", Cache(None, r))
    else:
        monkeypatch.setattr(services, "cache", Cache(None, None))
    return SimpleNamespace(client=TestClient(main.app), fake=fake, searches=searches)


def test_ask_streams_sources_then_answer_then_done(api):
    r = api.client.post("/ask", json={"youtube_url": URL, "question": "How does backprop work?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r.text)
    kinds = [k for k, _ in events]
    assert kinds[0] == "sources" and kinds[-1] == "done" and kinds.count("delta") > 3
    sources = events[0][1]["sources"]
    assert [s["n"] for s in sources] == [1, 2, 3] and sources[0]["start"] == 0.0
    streamed = "".join(d["text"] for k, d in events if k == "delta")
    done = events[-1][1]
    assert streamed.strip() == done["answer"] == ASK_TEXT
    assert done["citations"] == [1, 2, 3] and done["grounded"] is True and done["cached"] is False
    assert api.searches == [("jNQXAC9IVRw", "How does backprop work?", 5)]


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_same_first_question_is_answered_from_cache(api):
    api.client.post("/ask", json={"youtube_url": URL, "question": "How does backprop work?"})
    second = _events(api.client.post("/ask", json={"youtube_url": URL, "question": "how does BACKPROP work"}).text)
    assert len(api.fake.calls) == 1  # no second Claude call
    assert second[-1][1]["cached"] is True and second[-1][1]["citations"] == [1, 2, 3]
    m = api.client.get("/metrics").json()["ask"]
    assert m["answers"] == 1 and m["cache_hit_rate"] == 0.5 and m["ungrounded_rate"] == 0.0


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_follow_ups_send_history_and_are_never_cached(api):
    body = {
        "youtube_url": URL,
        "question": "And why does that matter?",
        "history": [{"question": "How does backprop work?", "answer": "It applies the chain rule [2]."}],
    }
    api.client.post("/ask", json=body)
    api.client.post("/ask", json=body)
    assert len(api.fake.calls) == 2
    assert api.fake.calls[0]["messages"][0] == {"role": "user", "content": "How does backprop work?"}


def test_an_answer_without_valid_citations_is_flagged_ungrounded(api):
    api.fake.ask_text = "The lecture doesn't cover the history of neural networks."
    done = _events(api.client.post("/ask", json={"youtube_url": URL, "question": "Who invented NNs?"}).text)[-1][1]
    assert done["citations"] == [] and done["grounded"] is False


@pytest.mark.parametrize(
    "body,status",
    [
        ({"youtube_url": URL, "question": "  "}, 422),
        ({"youtube_url": URL, "question": "x" * (MAX_QUESTION_CHARS + 1)}, 422),
        ({"youtube_url": "https://example.com/x", "question": "q"}, 422),
    ],
)
def test_bad_requests_fail_before_streaming(api, body, status):
    r = api.client.post("/ask", json=body)
    assert r.status_code == status and api.fake.calls == []


def test_unprocessed_lecture_is_404(api, monkeypatch):
    def search(**_kw):
        raise SearchAgentError("Video not processed yet: no embeddings for x.")

    monkeypatch.setattr(services.search_agent, "search", search)
    r = api.client.post("/ask", json={"youtube_url": URL, "question": "q"})
    assert r.status_code == 404 and api.fake.calls == []


def test_a_claude_failure_mid_stream_becomes_an_error_event(api):
    api.fake.fail.add("ask")
    events = _events(api.client.post("/ask", json={"youtube_url": URL, "question": "q"}).text)
    assert [k for k, _ in events] == ["sources", "error"]
    assert "try again" in events[-1][1]["message"]


def test_closing_the_stream_early_stops_claude(api):
    api.fake.summary_delay = 0.02
    with api.client.stream("POST", "/ask", json={"youtube_url": URL, "question": "q"}) as r:
        for line in r.iter_lines():
            if line.startswith("event: delta"):
                break  # the student closed the chat mid-answer
    assert api.fake.closed_early.get("ask") is True


def test_prompt_never_names_the_plumbing():
    """The model repeats whatever it's told it has: it must only hear about "the lecture"."""
    import re

    agent = AskAgent(client=FakeClaude(summary_delay=0), model="m")
    msg = agent._user_message("q", sources_from_hits(HITS))
    # The only place these words may appear is the rule telling the model not to use them.
    instructions = ASK_SYSTEM.split("never mention")[0]
    for text in (instructions, msg):
        assert not re.search(r"\b(excerpts?|passages?|sources?)\b", text, re.I), text
