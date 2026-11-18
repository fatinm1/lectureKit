"""
The eval harness: scoring functions, each suite against the real app (fakes behind it), the new
read-only endpoints it relies on, and the CLI end to end.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

import main
import services
from agents.ask_agent import AskAgent
from evals import metrics, run
from fake_claude import FakeClaude

LECTURE = {
    "id": "nn",
    "video_id": "aircAruvnKk",
    "youtube_url": "https://www.youtube.com/watch?v=aircAruvnKk",
    "retrieval": [
        {"q": "what is a bias", "gold": [680, 854]},
        {"q": "sigmoid", "gold": [510, 680]},
        {"q": "relu", "gold": [1023, 100000]},
    ],
    "ask": [
        {"q": "what is a bias?", "answerable": True, "gold": [0, 100]},
        {"q": "how does backprop work?", "answerable": False},
    ],
}

KIT = {
    "outline": [{"timestamp": t, "title": "t", "description": "d"} for t in (4, 300, 700, 1050)],
    "flashcards": [{"question": f"Q{i}?", "answer": "a", "source_timestamp": 60.0 * i * 2} for i in range(10)],
    "summary_90s": "word " * 60,
    "summary_5min": "word " * 400,
    "summary_full": "word " * 700,
}


# ---------- scoring ----------


def test_retrieval_ranks_and_summary():
    results = [{"start": 600, "end": 660}, {"start": 660, "end": 720}, {"start": 0, "end": 60}]
    assert metrics.first_hit_rank(results, [680, 854]) == 2  # 660-720 overlaps 680-854
    assert metrics.first_hit_rank(results, [2000, 2100]) is None
    s = metrics.retrieval_summary([1, 2, None, 4])
    assert s == {"n": 4, "hit@1": 0.25, "hit@3": 0.5, "hit@5": 0.75, "mrr": round((1 + 0.5 + 0.25) / 4, 4)}


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("The lecture doesn't cover backpropagation.", True),
        ("This lecture does not go into how the gradient is computed.", True),
        ("Backprop isn't covered here; it's left for the next video.", True),
        ("A bias shifts the threshold [1].", False),
        ("It does not matter which neuron fires first [2].", False),
    ],
)
def test_not_covered_detection(answer, expected):
    assert metrics.says_not_covered(answer) is expected


def test_score_ask_answerable_and_unanswerable():
    sources = [{"n": 1, "start": 0, "end": 59}, {"n": 2, "start": 700, "end": 760}]
    good = metrics.score_ask({"answerable": True, "gold": [680, 854]}, sources, {"answer": "x [2]", "citations": [2, 1]})
    assert good["pass"] and good["citation_precision"] == 0.5
    bad = metrics.score_ask({"answerable": True, "gold": [680, 854]}, sources, {"answer": "x [1]", "citations": [1]})
    assert not bad["pass"]
    refuse = metrics.score_ask({"answerable": False}, sources, {"answer": "The lecture doesn't cover it.", "citations": []})
    assert refuse["pass"]


def test_study_kit_checks_pass_and_fail():
    ok = metrics.check_study_kit(KIT, duration_s=1150)
    assert all(c["pass"] for c in ok), [c for c in ok if not c["pass"]]
    broken = dict(KIT, outline=KIT["outline"][:2], summary_90s="word " * 300)
    failed = {c["check"] for c in metrics.check_study_kit(broken, duration_s=1150) if not c["pass"]}
    assert {"outline has 3-12 topics", "90-second summary under 110 words", "outline reaches the last third"} <= failed


# ---------- suites against the real app ----------


@pytest.fixture()
def app(monkeypatch):
    chunks = [(i * 120.0, i * 120.0 + 119) for i in range(10)]

    def search(video_id, query, n_results):
        # "bias": the right chunk (720-839) comes second, like the production failure the evals
        # catch; "sigmoid": right first (480-599); "relu": nothing near 1023s in the top 3.
        order = {"what is a bias": [3, 6], "sigmoid": [4], "relu": [0, 1, 2]}.get(query, [0])
        idxs = order + [i for i in range(10) if i not in order]
        return [
            SimpleNamespace(start=chunks[i][0], end=chunks[i][1], text=f"chunk {i}", relevance_score=0.5, chunk_index=i)
            for i in idxs[:n_results]
        ]

    monkeypatch.setattr(services.search_agent, "search", search)
    fake = FakeClaude(summary_delay=0)
    fake.ask_text = "A bias shifts the threshold [1]."
    monkeypatch.setattr(services, "get_ask_agent", lambda: AskAgent(client=fake, model="m"))

    class Store:
        def get_lecture(self, vid):
            return {"video_id": vid, "youtube_url": "u", "duration_s": 1150.0, "chunk_count": 10} if vid == "aircAruvnKk" else None

        def has_embeddings(self, vid):
            return True

        def get_result(self, *a):
            return SimpleNamespace(payload=KIT, usage=None)

    monkeypatch.setattr(services, "store", Store())
    monkeypatch.setattr(services, "cache", services.Cache(Store(), None))
    return SimpleNamespace(client=TestClient(main.app), fake=fake)


def test_search_honours_n_results(app):
    r = app.client.post("/search", json={"youtube_url": LECTURE["youtube_url"], "query": "relu", "n_results": 5})
    assert len(r.json()["results"]) == 5
    assert len(app.client.post("/search", json={"youtube_url": LECTURE["youtube_url"], "query": "relu"}).json()["results"]) == 3
    assert app.client.post("/search", json={"youtube_url": LECTURE["youtube_url"], "query": "x", "n_results": 11}).status_code == 422


def test_lecture_endpoint_is_read_only(app):
    info = app.client.get("/lectures/aircAruvnKk").json()
    assert info["duration_s"] == 1150.0 and info["indexed"] is True and info["study_kit"]["outline"]
    assert app.client.get("/lectures/nope").status_code == 404


def test_retrieval_suite(app):
    out = run.run_retrieval(app.client, [LECTURE])
    assert [r["rank"] for r in out["rows"]] == [2, 1, None]  # relu: right chunk is 9th, outside the top 5
    s = out["summary"]
    assert s["hit@1"] == round(1 / 3, 4) and s["hit@3"] == round(2 / 3, 4) and s["hit@5"] == round(2 / 3, 4)


def test_content_suite(app):
    out = run.run_content(app.client, [LECTURE])
    assert out["summary"]["pass_rate"] == 1.0


def test_ask_suite(app):
    out = run.run_ask(app.client, [LECTURE])
    s = out["summary"]
    assert s["n"] == 2 and s["answerable_correct_citation"] == 1.0
    # The fake always answers with a citation, so "doesn't cover" is never said: the
    # unanswerable question fails, which is exactly what the suite should report.
    assert s["unanswerable_admits_not_covered"] == 0.0


def test_cli_end_to_end_writes_reports(tmp_path, app, monkeypatch):
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps({"version": 9, "lectures": [LECTURE]}))
    out_md, out_json = tmp_path / "r.md", tmp_path / "r.json"
    # Route the CLI's httpx client into the app.
    transport = httpx.MockTransport(lambda req: _forward(app.client, req))
    report = run.main(
        ["--api", "http://test", "--suites", "retrieval,content,ask", "--dataset", str(ds), "--out", str(out_md), "--json", str(out_json)],
        transport=transport,
    )
    assert report["dataset_version"] == 9 and set(report) >= {"retrieval", "content", "ask"}
    md = out_md.read_text()
    assert "## Retrieval" in md and "hit@1" in md and "Not ranked first" in md and "## Ask the lecture" in md
    assert json.loads(out_json.read_text())["retrieval"]["summary"]["n"] == 3
    assert "rank 2" in md  # misses are listed with where the right chunk landed


def _forward(client: TestClient, req: httpx.Request) -> httpx.Response:
    r = client.request(req.method, req.url.path, content=req.content, headers={"content-type": req.headers.get("content-type", "")})
    return httpx.Response(r.status_code, content=r.content, headers=r.headers)


def test_unknown_suite_is_rejected():
    with pytest.raises(SystemExit):
        run.main(["--suites", "vibes"])


@pytest.mark.parametrize(
    "answer,leaks",
    [
        ("These topics aren't addressed in the excerpts.", True),  # seen in production, run 2
        ("The excerpts focus on foundational concepts.", True),
        ("Based on the provided context, a bias shifts the threshold.", True),
        ("The transcript doesn't mention quicksort.", True),
        ("The lecture doesn't cover quicksort. It focuses on problem definitions [1].", False),
        ("The lecturer explains that a bias shifts the threshold [2].", False),
    ],
)
def test_internal_wording_detection(answer, leaks):
    assert metrics.leaks_internal_wording(answer) is leaks


def test_ask_summary_reports_wording_leaks():
    rows = [
        {"answerable": False, "score": metrics.score_ask({"answerable": False}, [], {"answer": "The excerpts don't cover it.", "citations": []})},
        {"answerable": False, "score": metrics.score_ask({"answerable": False}, [], {"answer": "The lecture doesn't cover it.", "citations": []})},
    ]
    assert metrics.ask_summary(rows)["leaks_internal_wording"] == 0.5
