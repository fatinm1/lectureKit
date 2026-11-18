"""
Accounts, library and share links, against real Postgres + Redis (skipped without them).
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from redis.asyncio import Redis as AsyncRedis

import accounts_routes
import main
import services
from db.store import Store
from jobs.events import JobEventBus

DB_URL = os.getenv("TEST_DATABASE_URL", "")
REDIS_URL = os.getenv("TEST_REDIS_URL", "")

pytestmark = pytest.mark.skipif(not (DB_URL and REDIS_URL), reason="TEST_DATABASE_URL / TEST_REDIS_URL not set")

STUDENT = {
    "video_id": "aircAruvnKk",
    "youtube_url": "https://www.youtube.com/watch?v=aircAruvnKk",
    "chunk_count": 7,
    "outline": [{"timestamp": 4, "title": "Handwritten digits", "description": "d"}],
    "summary_90s": "A neural network is a layered function.",
    "summary_5min": "…",
    "summary_full": "…",
    "flashcards": [],
    "indexed": True,
}
FACULTY = {"video_id": "UzxYlbK2c7E", "youtube_url": "https://youtu.be/UzxYlbK2c7E", "report": {"overall_score": 7}}
PROVOST = {"lecture_count": 2, "failed_urls": [], "video_ids": ["a", "b"], "curriculum_map": {"overall_coverage_score": 5}}


@pytest.fixture(scope="module")
def store():
    s = Store(DB_URL)
    yield s
    s.close()


@pytest.fixture()
def api(store, monkeypatch):
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE users, lectures, jobs CASCADE")
    redis.Redis.from_url(REDIS_URL).flushdb()
    monkeypatch.setattr(services, "store", store)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("RUN_WORKER_IN_PROCESS", "false")
    titles = {"aircAruvnKk": "But what is a neural network?", "UzxYlbK2c7E": "Lecture 1 | Machine Learning"}
    monkeypatch.setattr(accounts_routes, "_youtube_title", lambda vid: titles.get(vid))
    with TestClient(main.app) as client:
        yield client


def _finished_job(job_id: str, kind: str, result: dict, status: str = "done") -> None:
    async def go():
        r = AsyncRedis.from_url(REDIS_URL)
        bus = JobEventBus(r)
        await bus.create(job_id, kind, {})
        if status == "done":
            await bus.set_result(job_id, result)
        await bus.emit(job_id, status, {"result": result} if status == "done" else {})
        await r.aclose()

    asyncio.run(go())


def _signup(client, email="fatin@example.com", password="correct horse"):
    r = client.post("/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- auth ----------


def test_signup_login_me_logout(api, store):
    h = _signup(api, "Fatin@Example.com ")
    assert api.get("/auth/me", headers=h).json()["user"]["email"] == "fatin@example.com"

    with psycopg.connect(DB_URL) as conn:
        pw_hash, = conn.execute("SELECT password_hash FROM users").fetchone()
        stored_tokens = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
    assert pw_hash.startswith("$argon2id$") and "correct horse" not in pw_hash
    assert h["Authorization"][7:] not in stored_tokens  # only the hash is stored

    login = api.post("/auth/login", json={"email": "FATIN@example.com", "password": "correct horse"})
    assert login.status_code == 200
    h2 = {"Authorization": f"Bearer {login.json()['token']}"}
    assert api.post("/auth/logout", headers=h2).status_code == 204
    assert api.get("/auth/me", headers=h2).status_code == 401
    assert api.get("/auth/me", headers=h).status_code == 200  # other session unaffected


def test_signup_validation_and_duplicates(api):
    assert api.post("/auth/signup", json={"email": "nope", "password": "longenough"}).status_code == 422
    assert api.post("/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422
    _signup(api, "a@b.co")
    dup = api.post("/auth/signup", json={"email": "A@B.co", "password": "anotherpass"})
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]


def test_wrong_password_and_unknown_email_look_the_same(api):
    _signup(api)
    wrong = api.post("/auth/login", json={"email": "fatin@example.com", "password": "wrong password"})
    unknown = api.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Email or password is incorrect."}


def test_password_change_ends_other_sessions(api):
    h = _signup(api)
    other = {"Authorization": "Bearer " + api.post("/auth/login", json={"email": "fatin@example.com", "password": "correct horse"}).json()["token"]}
    bad = api.post("/auth/password", headers=h, json={"current_password": "nope", "new_password": "brand new pass"})
    assert bad.status_code == 403
    ok = api.post("/auth/password", headers=h, json={"current_password": "correct horse", "new_password": "brand new pass"})
    assert ok.status_code == 204
    assert api.get("/auth/me", headers=h).status_code == 200  # this device stays signed in
    assert api.get("/auth/me", headers=other).status_code == 401  # every other session ends
    assert api.post("/auth/login", json={"email": "fatin@example.com", "password": "brand new pass"}).status_code == 200


def test_delete_account_removes_library_and_share_links(api):
    h = _signup(api)
    _finished_job("job-delete-1", "student", STUDENT)
    item = api.post("/library", headers=h, json={"job_id": "job-delete-1"}).json()
    token = api.post(f"/library/{item['id']}/share", headers=h).json()["share_token"]
    assert api.request("DELETE", "/auth/account", headers=h, json={"password": "wrong"}).status_code == 403
    assert api.request("DELETE", "/auth/account", headers=h, json={"password": "correct horse"}).status_code == 204
    assert api.get("/auth/me", headers=h).status_code == 401
    assert api.get(f"/shared/{token}").status_code == 404


def test_login_is_rate_limited_per_ip(api, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_HOUR", "3")
    body = {"email": "x@y.co", "password": "whatever1"}
    codes = [api.post("/auth/login", json=body, headers={"X-Real-IP": "7.7.7.7"}).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_daily_budget_never_blocks_sign_in(api, monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.000001")
    services.cache.record_spend("student", {"output_tokens": 10_000})
    assert api.post("/auth/signup", json={"email": "c@d.co", "password": "longenough"}).status_code == 201


# ---------- library ----------


def test_saving_finished_runs_of_each_kind(api):
    h = _signup(api)
    _finished_job("job-s-0000000", "student", STUDENT)
    _finished_job("job-f-0000000", "faculty", FACULTY)
    _finished_job("job-p-0000000", "provost", PROVOST)
    titles = [api.post("/library", headers=h, json={"job_id": j}).json()["title"] for j in ("job-s-0000000", "job-f-0000000", "job-p-0000000")]
    assert titles == [
        "But what is a neural network?",
        "Audit · Lecture 1 | Machine Learning",
        "Curriculum map · 2 lectures",
    ]
    items = api.get("/library", headers=h).json()["items"]
    assert [i["kind"] for i in items] == ["provost", "faculty", "student"]  # newest first
    assert all("payload" not in i for i in items)  # the list stays light
    full = api.get(f"/library/{items[2]['id']}", headers=h).json()
    assert full["payload"]["summary_90s"] == STUDENT["summary_90s"]


def test_saving_is_idempotent_and_title_falls_back(api, monkeypatch):
    monkeypatch.setattr(accounts_routes, "_youtube_title", lambda vid: None)  # YouTube unreachable
    h = _signup(api)
    _finished_job("job-s-0000000", "student", STUDENT)
    a = api.post("/library", headers=h, json={"job_id": "job-s-0000000"}).json()
    b = api.post("/library", headers=h, json={"job_id": "job-s-0000000"}).json()
    assert a["id"] == b["id"] and len(api.get("/library", headers=h).json()["items"]) == 1
    assert a["title"] == "Handwritten digits"  # first outline topic


def test_only_finished_unexpired_runs_can_be_saved(api):
    h = _signup(api)
    _finished_job("job-x-0000000", "student", STUDENT, status="failed")
    assert api.post("/library", headers=h, json={"job_id": "job-x-0000000"}).status_code == 409
    assert api.post("/library", headers=h, json={"job_id": "job-never-existed"}).status_code == 404
    assert api.post("/library", json={"job_id": "job-x-0000000"}).status_code == 401


def test_users_cannot_see_or_touch_each_others_items(api):
    alice = _signup(api, "alice@example.com")
    bob = _signup(api, "bob@example.com")
    _finished_job("job-a-0000000", "student", STUDENT)
    item = api.post("/library", headers=alice, json={"job_id": "job-a-0000000"}).json()
    assert api.get("/library", headers=bob).json()["items"] == []
    for method, path, body in (
        ("GET", f"/library/{item['id']}", None),
        ("PATCH", f"/library/{item['id']}", {"title": "mine now"}),
        ("POST", f"/library/{item['id']}/share", None),
        ("DELETE", f"/library/{item['id']}", None),
    ):
        assert api.request(method, path, headers=bob, json=body).status_code == 404, (method, path)
    assert api.get(f"/library/{item['id']}", headers=alice).json()["title"] == STUDENT_TITLE


STUDENT_TITLE = "But what is a neural network?"


def test_rename_and_delete(api):
    h = _signup(api)
    _finished_job("job-s-0000000", "student", STUDENT)
    item = api.post("/library", headers=h, json={"job_id": "job-s-0000000"}).json()
    assert api.patch(f"/library/{item['id']}", headers=h, json={"title": "  NN basics  "}).json()["title"] == "NN basics"
    assert api.patch(f"/library/{item['id']}", headers=h, json={"title": "   "}).status_code == 422
    assert api.delete(f"/library/{item['id']}", headers=h).status_code == 204
    assert api.delete(f"/library/{item['id']}", headers=h).status_code == 404


# ---------- sharing ----------


def test_share_links_are_read_only_stable_and_revocable(api):
    h = _signup(api)
    _finished_job("job-f-0000000", "faculty", FACULTY)
    item = api.post("/library", headers=h, json={"job_id": "job-f-0000000"}).json()
    assert item["shared"] is False and api.get("/shared/anything").status_code == 404

    first = api.post(f"/library/{item['id']}/share", headers=h).json()
    again = api.post(f"/library/{item['id']}/share", headers=h).json()
    token = first["share_token"]
    assert first["shared"] and len(token) >= 20 and again["share_token"] == token  # same link

    shared = api.get(f"/shared/{token}")  # no auth needed
    assert shared.status_code == 200 and shared.headers["x-robots-tag"] == "noindex"
    body = shared.json()
    assert body["kind"] == "faculty" and body["payload"]["report"]["overall_score"] == 7
    assert "user" not in body and "email" not in str(body)  # nothing about the owner

    assert api.delete(f"/library/{item['id']}/share", headers=h).json()["shared"] is False
    assert api.get(f"/shared/{token}").status_code == 404
    new = api.post(f"/library/{item['id']}/share", headers=h).json()["share_token"]
    assert new != token  # re-sharing makes a new link; the revoked one stays dead


def test_accounts_need_the_database(api, monkeypatch):
    monkeypatch.setattr(services, "store", None)
    r = api.post("/auth/signup", json={"email": "e@f.co", "password": "longenough"})
    assert r.status_code == 503


def test_browser_preflight_allows_every_library_method(api):
    """TestClient skips CORS, so check the preflight a browser sends (PATCH was missing once)."""
    for method in ("GET", "POST", "PATCH", "DELETE"):
        r = api.options(
            "/library/abc",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert r.status_code == 200, method
        assert method in r.headers["access-control-allow-methods"], method
        assert "authorization" in r.headers["access-control-allow-headers"].lower()
