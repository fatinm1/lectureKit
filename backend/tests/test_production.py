"""
Production basics: per-IP rate limits, the daily budget, usage accounting from every Claude call,
JSON logs with request IDs, and Sentry being strictly opt-in.
"""

from __future__ import annotations

import io
import json
import logging
import os
from types import SimpleNamespace

import pytest
import redis
from fastapi.testclient import TestClient

import main
import observability
import services
import usage
from agents.ask_agent import AskAgent
from agents.faculty_agent import FacultyAgent
from db.cache import Cache, usd
from fake_claude import FakeClaude
from limits import RateLimiter, _seconds_to_utc_midnight

REDIS_URL = os.getenv("TEST_REDIS_URL", "")
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _redis():
    if not REDIS_URL:
        pytest.skip("TEST_REDIS_URL not set")
    r = redis.Redis.from_url(REDIS_URL)
    try:
        r.ping()
    except redis.RedisError:
        pytest.skip("Redis not reachable")
    r.flushdb()
    return r


@pytest.fixture()
def wired(monkeypatch):
    """App with a real Redis cache, the usage sink attached, and cheap stand-ins for the AI work."""
    r = _redis()
    cache = Cache(None, r)
    monkeypatch.setattr(services, "cache", cache)
    usage.set_sink(cache.record_spend)
    hits = [SimpleNamespace(start=0.0, end=59.0, text="Gradient descent.", relevance_score=0.9, chunk_index=0)]
    monkeypatch.setattr(services.search_agent, "search", lambda **_kw: hits)
    fake = FakeClaude(summary_delay=0)
    monkeypatch.setattr(services, "get_ask_agent", lambda: AskAgent(client=fake, model="m"))
    yield SimpleNamespace(client=TestClient(main.app), cache=cache, redis=r, fake=fake)
    usage.set_sink(None)


def _ask(client, ip="1.1.1.1", headers=None):
    return client.post(
        "/ask", json={"youtube_url": URL, "question": "q"}, headers={"X-Real-IP": ip, **(headers or {})}
    )


# ---------- rate limits ----------


def test_rate_limiter_window_and_reset():
    rl = RateLimiter(window_s=3600)
    t = 7200.0 + 10
    assert [rl.hit("k", 2, now=t)[0] for _ in range(3)] == [True, True, False]
    assert rl.hit("k", 2, now=t)[1] == 3600 - 10 + 1  # retry after the window ends
    assert rl.hit("k", 2, now=t + 3600)[0] is True  # next hour, fresh window
    assert rl.hit("other", 2, now=t)[0] is True  # keys are independent


def test_ask_is_limited_per_ip_with_retry_after(wired, monkeypatch):
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "2")
    assert [_ask(wired.client).status_code for _ in range(2)] == [200, 200]
    blocked = _ask(wired.client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "limit of 2 questions an hour" in blocked.json()["detail"]
    assert _ask(wired.client, ip="2.2.2.2").status_code == 200  # another visitor is unaffected
    assert len(wired.fake.calls) == 1  # repeats were cached; the blocked one never got that far


def test_forged_forwarded_for_does_not_get_a_fresh_bucket(wired, monkeypatch):
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "1")
    assert _ask(wired.client).status_code == 200
    spoof = _ask(wired.client, headers={"X-Forwarded-For": "9.9.9.9"})
    assert spoof.status_code == 429


def test_runs_and_questions_have_separate_limits(wired, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "5")
    bad = {}  # 422 from validation, but still counted against the limit
    h = {"X-Real-IP": "3.3.3.3"}
    assert wired.client.post("/translate", json=bad, headers=h).status_code == 422
    assert wired.client.post("/faculty", json=bad, headers=h).status_code == 429
    assert _ask(wired.client, ip="3.3.3.3").status_code == 200


def test_limited_responses_still_carry_cors_headers(wired, monkeypatch):
    monkeypatch.setenv("ASK_RATE_LIMIT_PER_HOUR", "0")
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.000001")
    wired.cache.record_spend("ask", {"output_tokens": 1000})
    r = wired.client.post(
        "/ask",
        json={"youtube_url": URL, "question": "q"},
        headers={"Origin": "http://localhost:3000", "X-Real-IP": "4.4.4.4"},
    )
    assert r.status_code == 503
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------- daily budget ----------


def test_daily_budget_blocks_new_ai_work_until_midnight(wired, monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.05")
    assert _ask(wired.client).status_code == 200  # tiny spend, under budget
    wired.cache.record_spend("student", {"input_tokens": 10_000, "output_tokens": 2_000})  # $0.06
    r = _ask(wired.client)
    assert r.status_code == 503 and "today's AI budget" in r.json()["detail"]
    assert 0 < int(r.headers["retry-after"]) <= 86401
    assert wired.client.get("/health").status_code == 200  # reads are never blocked
    m = wired.client.get("/metrics").json()["estimated_usd"]
    assert m["today"] >= 0.06 and m["daily_budget"] == 0.05


def test_seconds_to_midnight():
    assert _seconds_to_utc_midnight(now=86400 * 5 + 86000) == 401


# ---------- usage from every Claude call ----------


def test_every_attempt_is_counted_per_agent(wired):
    agent = FacultyAgent.__new__(FacultyAgent)  # skip the API-key check
    agent.client = FakeClaude(tool_inputs=[{"not": "valid"}, {"still": "not"}])
    agent.model = "m"
    with pytest.raises(Exception):
        agent.generate_report([], "vid")  # both tool calls rejected, legacy fallback fails too
    c = wired.cache.counters()
    # Rejected calls are billed, so both attempts are counted, under "faculty".
    assert c["agent_faculty_output_tokens"] == 2 * 300
    assert c["spent_output_tokens"] == 2 * 300
    m = wired.client.get("/metrics").json()["estimated_usd"]
    assert m["by_agent"]["faculty"] == usd(
        {"input_tokens": 80, "output_tokens": 600, "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 5000}
    )


def test_ask_usage_is_counted_once(wired):
    _ask(wired.client)
    c = wired.cache.counters()
    assert c["agent_ask_output_tokens"] == 300 and c["spent_output_tokens"] == 300


def test_a_broken_sink_never_breaks_the_call():
    def boom(agent, counts):
        raise RuntimeError("redis on fire")

    usage.set_sink(boom)
    try:
        usage.report("x", SimpleNamespace(usage=SimpleNamespace(input_tokens=5)))  # no exception
    finally:
        usage.set_sink(None)


# ---------- logs, request IDs, Sentry ----------


def test_json_logs_carry_the_request_id(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    observability.setup_logging()
    buf = io.StringIO()
    logging.getLogger().handlers[0].stream = buf
    try:
        r = TestClient(main.app).get("/metrics", headers={"X-Request-ID": "abc123", "X-Real-IP": "5.5.5.5"})
        assert r.headers["x-request-id"] == "abc123"
        lines = [json.loads(line) for line in buf.getvalue().splitlines() if line.startswith("{")]
        req = [l for l in lines if l.get("logger") == "lecturekit.http"][-1]
        assert req["request_id"] == "abc123" and req["path"] == "/metrics" and req["status"] == 200
        assert req["client_ip"] == "5.5.5.5" and req["duration_ms"] >= 0 and req["level"] == "info"
    finally:
        monkeypatch.setenv("LOG_FORMAT", "text")
        observability.setup_logging()


def test_request_id_is_generated_when_missing():
    r = TestClient(main.app).get("/health")
    assert len(r.headers["x-request-id"]) == 16


def test_sentry_is_off_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.setup_sentry() is False


def test_sentry_starts_with_a_dsn_and_never_sends_pii(monkeypatch):
    import sentry_sdk

    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/1")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    assert observability.setup_sentry() is True
    assert seen["send_default_pii"] is False and seen["release"] == "abcdef123456"
    assert seen["traces_sample_rate"] == 0.0
