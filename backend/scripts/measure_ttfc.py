#!/usr/bin/env python3
"""
Measure time-to-first-visible-content: blocking POST /process vs background jobs + SSE.

For each URL it runs both flows against a live backend and prints a markdown table:
  - legacy:  the study page can render only when POST /process returns
  - jobs:    the study page renders at `transcript_fetched` (video player), search works at
             `chunks_indexed`, and the full kit lands at `done`

Usage:
  python scripts/measure_ttfc.py --api https://lecturekit-production.up.railway.app \
      https://www.youtube.com/watch?v=VMj-3S1tku0 https://www.youtube.com/watch?v=...

Cost note: every URL makes two real Claude content calls (one per flow).
Run the jobs flow first so it doesn't benefit from a warm search index.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

import httpx


def run_jobs(client: httpx.Client, api: str, url: str) -> dict[str, float]:
    t0 = time.perf_counter()
    r = client.post(f"{api}/jobs", json={"mode": "student", "youtube_url": url})
    r.raise_for_status()
    job_id = r.json()["job_id"]
    marks: dict[str, float] = {"enqueue": time.perf_counter() - t0}
    event = None
    with client.stream("GET", f"{api}/jobs/{job_id}/events", timeout=None) as s:
        for line in s.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                marks.setdefault(event, time.perf_counter() - t0)
                if event == "failed":
                    raise RuntimeError(json.loads(line[6:]).get("message"))
                if event == "done":
                    break
    return marks


def run_legacy(client: httpx.Client, api: str, url: str) -> float:
    t0 = time.perf_counter()
    r = client.post(f"{api}/process", json={"youtube_url": url}, timeout=600)
    r.raise_for_status()
    return time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("urls", nargs="+")
    args = ap.parse_args()
    api = args.api.rstrip("/")

    rows = []
    with httpx.Client(timeout=60) as client:
        for url in args.urls:
            print(f"… {url}", file=sys.stderr)
            jobs = run_jobs(client, api, url)
            legacy = run_legacy(client, api, url)
            rows.append((url, legacy, jobs))

    print("| Lecture | Blocking /process: first content | Jobs: first content (video) | Jobs: search ready | Jobs: full kit |")
    print("|---|---|---|---|---|")
    for url, legacy, jobs in rows:
        print(
            f"| {url} | {legacy:.1f}s | {jobs.get('transcript_fetched', float('nan')):.1f}s "
            f"| {jobs.get('chunks_indexed', float('nan')):.1f}s | {jobs.get('done', float('nan')):.1f}s |"
        )
    if rows:
        legacy_med = statistics.median(r[1] for r in rows)
        first_med = statistics.median(r[2].get("transcript_fetched", 0) for r in rows)
        print(f"\nMedian time to first visible content: {legacy_med:.1f}s → {first_med:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
