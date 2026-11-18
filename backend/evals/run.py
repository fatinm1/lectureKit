"""
LectureKit evals: run a fixed question set against a live API and report the numbers.

    cd backend
    pip install httpx
    python -m evals.run                                   # retrieval + study kit (free)
    python -m evals.run --suites retrieval,content,ask    # + "Ask the lecture" (costs a little)
    python -m evals.run --api http://localhost:8000 --out report.md --json report.json

Suites
- retrieval  Search quality on labeled questions: hit@1, hit@3, hit@5, MRR. Free: embeddings only.
- content    Structural checks on each lecture's cached study kit (outline order and coverage,
             flashcards, summary lengths). Free: reads the cache, never generates.
- ask        "Ask the lecture": answerable questions must cite the gold moment; unanswerable ones
             must say the lecture doesn't cover them. Costs about $0.01 per new question on Sonnet;
             first questions are cached, so re-running the same set is free.

Cost is reported from /metrics before and after, so a run states what it spent. The server's
daily budget and rate limits still apply.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from evals.metrics import ask_summary, check_study_kit, first_hit_rank, retrieval_summary, score_ask

DEFAULT_API = "https://lecturekit-production.up.railway.app"
DATASET = Path(__file__).with_name("dataset.json")
ALL_SUITES = ("retrieval", "content", "ask")


def _spent(client: httpx.Client) -> Optional[float]:
    try:
        return float(client.get("/metrics").json()["estimated_usd"]["spent"])
    except Exception:
        return None


def run_retrieval(client: httpx.Client, lectures: list[dict], k: int = 5) -> dict[str, Any]:
    rows = []
    for lec in lectures:
        for item in lec.get("retrieval", []):
            r = client.post("/search", json={"youtube_url": lec["youtube_url"], "query": item["q"], "n_results": k})
            if r.status_code != 200:
                rows.append({"lecture": lec["id"], "q": item["q"], "rank": None, "error": f"HTTP {r.status_code}"})
                continue
            results = r.json()["results"]
            rows.append(
                {
                    "lecture": lec["id"],
                    "q": item["q"],
                    "gold": item["gold"],
                    "rank": first_hit_rank(results, item["gold"]),
                    "top": [[round(x["start"]), round(x["end"])] for x in results[:3]],
                }
            )
    per_lecture = {
        lec["id"]: retrieval_summary([r["rank"] for r in rows if r["lecture"] == lec["id"]]) for lec in lectures
    }
    return {"summary": retrieval_summary([r["rank"] for r in rows]), "per_lecture": per_lecture, "rows": rows}


def run_content(client: httpx.Client, lectures: list[dict]) -> dict[str, Any]:
    out = []
    for lec in lectures:
        r = client.get(f"/lectures/{lec['video_id']}")
        if r.status_code != 200:
            out.append({"lecture": lec["id"], "error": f"HTTP {r.status_code}", "checks": []})
            continue
        info = r.json()
        kit = info.get("study_kit")
        if not kit:
            out.append({"lecture": lec["id"], "error": "no cached study kit (run it in Student mode once)", "checks": []})
            continue
        out.append({"lecture": lec["id"], "checks": check_study_kit(kit, info.get("duration_s"))})
    checks = [c for row in out for c in row["checks"]]
    passed = sum(1 for c in checks if c["pass"])
    return {"summary": {"checks": len(checks), "passed": passed, "pass_rate": round(passed / len(checks), 4) if checks else None}, "rows": out}


def _sse(lines: Iterable[str]) -> Iterable[tuple[str, dict]]:
    event, data = "message", ""
    for line in lines:
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data += line[6:]
        elif line == "" and data:
            yield event, json.loads(data)
            event, data = "message", ""


def run_ask(client: httpx.Client, lectures: list[dict]) -> dict[str, Any]:
    rows = []
    for lec in lectures:
        for item in lec.get("ask", []):
            t0 = time.perf_counter()
            first: Optional[float] = None
            sources: list = []
            done: Optional[dict] = None
            error: Optional[str] = None
            with client.stream("POST", "/ask", json={"youtube_url": lec["youtube_url"], "question": item["q"]}) as r:
                if r.status_code != 200:
                    error = f"HTTP {r.status_code}: {r.read().decode()[:120]}"
                else:
                    for event, data in _sse(r.iter_lines()):
                        if event == "sources":
                            sources = data["sources"]
                        elif event == "delta" and first is None:
                            first = time.perf_counter() - t0
                        elif event == "done":
                            done = data
                        elif event == "error":
                            error = data.get("message", "error")
            row: dict[str, Any] = {"lecture": lec["id"], "q": item["q"], "answerable": bool(item.get("answerable"))}
            if done is None:
                row.update({"error": error or "no answer", "score": {"pass": False, "cited": 0, "said_not_covered": False, "citation_precision": 0.0}})
            else:
                row.update(
                    {
                        "score": score_ask(item, sources, done),
                        "cached": done.get("cached", False),
                        "first_token_s": round(first, 2) if first is not None else None,
                        "answer": done["answer"][:300],
                    }
                )
            rows.append(row)
    return {"summary": ask_summary(rows), "rows": rows}


def to_markdown(report: dict[str, Any]) -> str:
    md = [f"# LectureKit evals\n\nAPI: `{report['api']}` · {report['at']} · dataset v{report['dataset_version']}\n"]
    if report.get("spent_usd") is not None:
        md.append(f"Estimated Claude spend for this run: **${report['spent_usd']:.4f}**\n")
    if "retrieval" in report:
        s = report["retrieval"]["summary"]
        md.append("## Retrieval\n")
        md.append("| | n | hit@1 | hit@3 | hit@5 | MRR |\n|---|---|---|---|---|---|")
        md.append(f"| **all** | {s['n']} | {s['hit@1']:.2f} | {s['hit@3']:.2f} | {s['hit@5']:.2f} | {s['mrr']:.2f} |")
        for lec, t in report["retrieval"]["per_lecture"].items():
            if t.get("n"):
                md.append(f"| {lec} | {t['n']} | {t['hit@1']:.2f} | {t['hit@3']:.2f} | {t['hit@5']:.2f} | {t['mrr']:.2f} |")
        misses = [r for r in report["retrieval"]["rows"] if r.get("rank") != 1]
        if misses:
            md.append("\nNot ranked first:\n")
            for r in misses:
                where = f"rank {r['rank']}" if r.get("rank") else (r.get("error") or "not in top 5")
                md.append(f"- *{r['q']}* ({r['lecture']}): {where}; gold {r.get('gold')}, top 3 {r.get('top')}")
        md.append("")
    if "content" in report:
        s = report["content"]["summary"]
        md.append(f"## Study kit checks\n\n{s['passed']}/{s['checks']} passed\n")
        for row in report["content"]["rows"]:
            if row.get("error"):
                md.append(f"- **{row['lecture']}**: {row['error']}")
            for c in row["checks"]:
                if not c["pass"]:
                    md.append(f"- **{row['lecture']}** ✗ {c['check']} ({c['detail']})")
        md.append("")
    if "ask" in report:
        s = report["ask"]["summary"]
        md.append("## Ask the lecture\n")
        md.append(f"- Answerable questions citing the right moment: **{_pct(s['answerable_correct_citation'])}**")
        md.append(f"- Citation precision (cited excerpts inside the gold range): **{_pct(s['citation_precision'])}**")
        md.append(f"- Unanswerable questions where it says the lecture doesn't cover it: **{_pct(s['unanswerable_admits_not_covered'])}**")
        md.append(f"- Answerable questions wrongly called \"not covered\": **{_pct(s['false_not_covered_on_answerable'])}**\n")
        for r in report["ask"]["rows"]:
            mark = "✓" if r["score"]["pass"] else "✗"
            tail = r.get("error") or (r.get("answer") or "")[:140].replace("\n", " ")
            md.append(f"- {mark} *{r['q']}* ({'answerable' if r['answerable'] else 'not in lecture'}): {tail}")
        md.append("")
    return "\n".join(md)


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def main(argv: Optional[list[str]] = None, transport: Optional[httpx.BaseTransport] = None) -> dict[str, Any]:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--suites", default="retrieval,content", help=f"comma-separated: {','.join(ALL_SUITES)}")
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--out", help="write the markdown report here")
    p.add_argument("--json", dest="json_out", help="write the full JSON report here")
    args = p.parse_args(argv)

    suites = [s.strip() for s in args.suites.split(",") if s.strip()]
    unknown = set(suites) - set(ALL_SUITES)
    if unknown:
        p.error(f"unknown suite(s): {', '.join(sorted(unknown))}")
    data = json.loads(Path(args.dataset).read_text())

    with httpx.Client(base_url=args.api.rstrip("/"), timeout=120, transport=transport) as client:
        before = _spent(client)
        report: dict[str, Any] = {
            "api": args.api,
            "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "dataset_version": data.get("version"),
        }
        if "retrieval" in suites:
            report["retrieval"] = run_retrieval(client, data["lectures"])
        if "content" in suites:
            report["content"] = run_content(client, data["lectures"])
        if "ask" in suites:
            report["ask"] = run_ask(client, data["lectures"])
        after = _spent(client)
        report["spent_usd"] = round(after - before, 4) if before is not None and after is not None else None

    md = to_markdown(report)
    print(md)
    if args.out:
        Path(args.out).write_text(md)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
    sys.exit(0)
