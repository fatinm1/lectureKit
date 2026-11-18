"""
Pure scoring functions for the evals (no network, no I/O), so they're unit-tested on their own.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence


def overlaps(start: float, end: float, gold: Sequence[float]) -> bool:
    """A chunk [start, end] counts as a hit if it overlaps the gold range at all."""
    return start < gold[1] and end > gold[0]


def first_hit_rank(results: Sequence[dict[str, Any]], gold: Sequence[float]) -> Optional[int]:
    """1-based rank of the first result overlapping the gold range, or None."""
    for i, r in enumerate(results, start=1):
        if overlaps(float(r["start"]), float(r["end"]), gold):
            return i
    return None


def retrieval_summary(ranks: Sequence[Optional[int]]) -> dict[str, float]:
    n = len(ranks)
    if n == 0:
        return {"n": 0}

    def hit_at(k: int) -> float:
        return round(sum(1 for r in ranks if r is not None and r <= k) / n, 4)

    mrr = round(sum(1.0 / r for r in ranks if r is not None) / n, 4)
    return {"n": n, "hit@1": hit_at(1), "hit@3": hit_at(3), "hit@5": hit_at(5), "mrr": mrr}


# Phrases an answer uses when it says the lecture doesn't cover something.
_NOT_COVERED = re.compile(
    r"\b(does ?n[o']?t|did ?n[o']?t|does not|did not|is ?n[o']?t|is not|are ?n[o']?t)\b[^.]{0,40}\b"
    r"(cover|covered|discuss|discussed|address|addressed|explain|explained|mention|mentioned|include|included|go into)\b"
    r"|\bnot (covered|discussed|addressed|explained|mentioned)\b"
    r"|\bno (information|mention|discussion)\b"
    r"|\bleft for (the|a) (next|later|future)\b",
    re.IGNORECASE,
)


# Words that reveal the retrieval plumbing to a student who only sees "the lecture".
_INTERNAL = re.compile(
    r"\b(excerpts?|passages?|transcripts?|snippets?|the (provided|given) (text|context|material|parts?)|"
    r"the sources?|numbered parts?|context provided)\b",
    re.IGNORECASE,
)


def leaks_internal_wording(answer: str) -> bool:
    return bool(_INTERNAL.search(answer or ""))


def says_not_covered(answer: str) -> bool:
    return bool(_NOT_COVERED.search(answer or ""))


def score_ask(item: dict[str, Any], sources: Sequence[dict[str, Any]], done: dict[str, Any]) -> dict[str, Any]:
    """
    Answerable: pass if at least one valid citation lands in the gold range.
      citation_precision = cited sources overlapping gold / cited sources.
    Unanswerable: pass if the answer says the lecture doesn't cover it.
    """
    by_n = {int(s["n"]): s for s in sources}
    cited = [by_n[n] for n in done.get("citations", []) if n in by_n]
    answer = str(done.get("answer", ""))
    leak = leaks_internal_wording(answer)
    if item.get("answerable"):
        gold = item["gold"]
        good = [s for s in cited if overlaps(float(s["start"]), float(s["end"]), gold)]
        return {
            "pass": bool(good),
            "citation_precision": round(len(good) / len(cited), 4) if cited else 0.0,
            "cited": len(cited),
            "said_not_covered": says_not_covered(answer),
            "leaks_internal_wording": leak,
        }
    return {
        "pass": says_not_covered(answer),
        "cited": len(cited),
        "said_not_covered": says_not_covered(answer),
        "leaks_internal_wording": leak,
    }


def ask_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    ans = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]

    def rate(rs: list, key: str = "pass") -> Optional[float]:
        return round(sum(1 for r in rs if r["score"][key]) / len(rs), 4) if rs else None

    precision = [r["score"]["citation_precision"] for r in ans if r["score"]["cited"]]
    return {
        "n": len(rows),
        "answerable_correct_citation": rate(ans),
        "citation_precision": round(sum(precision) / len(precision), 4) if precision else None,
        "unanswerable_admits_not_covered": rate(unans),
        "false_not_covered_on_answerable": rate(ans, "said_not_covered"),
        "leaks_internal_wording": rate(rows, "leaks_internal_wording"),
    }


def _words(text: str) -> int:
    return len((text or "").split())


def check_study_kit(kit: dict[str, Any], duration_s: Optional[float]) -> list[dict[str, Any]]:
    """Structural checks on a study kit. Each: {check, pass, detail}."""
    out: list[dict[str, Any]] = []

    def add(check: str, ok: bool, detail: str) -> None:
        out.append({"check": check, "pass": bool(ok), "detail": detail})

    outline = kit.get("outline") or []
    ts = [float(o.get("timestamp", 0)) for o in outline]
    add("outline has 3-12 topics", 3 <= len(outline) <= 12, f"{len(outline)} topics")
    add("outline in time order", ts == sorted(ts), "sorted" if ts == sorted(ts) else f"{ts}")
    if duration_s:
        inside = all(0 <= t <= duration_s for t in ts)
        add("outline timestamps inside the lecture", inside, f"max {max(ts, default=0):.0f}s of {duration_s:.0f}s")
        reach = (max(ts) / duration_s) if ts else 0
        add("outline reaches the last third", reach >= 0.66, f"last topic at {reach:.0%} of the lecture")
        start = (min(ts) / duration_s) if ts else 1
        add("outline starts in the first 10%", start <= 0.10, f"first topic at {start:.0%}")

    cards = kit.get("flashcards") or []
    qs = [" ".join(str(c.get("question", "")).lower().split()) for c in cards]
    add("10 flashcards", len(cards) == 10, f"{len(cards)} cards")
    add("no duplicate flashcards", len(set(qs)) == len(qs), f"{len(qs) - len(set(qs))} duplicates")
    card_ts = [float(c["source_timestamp"]) for c in cards if c.get("source_timestamp") is not None]
    if duration_s and card_ts:
        spread = (max(card_ts) - min(card_ts)) / duration_s
        add("flashcards span half the lecture", spread >= 0.5, f"span {spread:.0%}")

    s90, s5, sfull = (_words(kit.get(k, "")) for k in ("summary_90s", "summary_5min", "summary_full"))
    add("90-second summary under 110 words", 0 < s90 <= 110, f"{s90} words")
    add("5-minute summary 200-650 words", 200 <= s5 <= 650, f"{s5} words")
    add("full summary at least 450 words", sfull >= 450, f"{sfull} words")
    add("full summary longer than 5-minute", sfull > s5, f"{sfull} vs {s5} words")
    return out
