"""
Purpose: "Ask the lecture" — answer a student's question from the lecture itself, with citations.

Retrieval-augmented and grounded:
1. Retrieve the lecture's most relevant transcript chunks (pgvector / ChromaDB, same index as
   /search) and number them [1]..[n], each with its time range.
2. Stream Claude's answer. It may only use those sources and must cite them inline as [n]. If
   the sources don't cover the question it says so instead of answering from general knowledge.
3. Check the citations against what was actually retrieved. A citation to a source that doesn't
   exist is dropped from the list the UI turns into timestamp links, and the answer is flagged
   `grounded: false` if nothing valid is cited.

Costs stay small: only ~5 chunks (~2,500 words) are sent, history is capped at the last few
turns, answers are capped at 700 tokens, and `ANTHROPIC_ASK_MODEL` can point this at a
cheaper model. First-turn answers are cached per (lecture, normalized question).
"""

from __future__ import annotations

import usage as usage_mod
import hashlib
import json
import inspect
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Generator, List, Optional, Sequence

MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 3
MAX_HISTORY_ANSWER_CHARS = 1500
N_SOURCES = 5
MAX_ANSWER_TOKENS = 700

_CITATION = re.compile(r"\[(\d{1,2})(?:\s*,\s*(\d{1,2}))*\]")
_NUMBERS = re.compile(r"\d{1,2}")

# The model is never told it has "excerpts", "passages" or "sources": a name it's given is a name
# it repeats ("the excerpts don't cover…"), and telling it not to say the word didn't stop that
# (caught by the evals). It's told it has the lecture itself, in numbered parts.
ASK_SYSTEM = (
    "You answer a student's questions about one university lecture. You're given what the "
    "lecturer said, split into numbered parts with their time ranges. Rules:\n"
    "- After every claim, put the number of the part it comes from in square brackets, e.g. "
    "\"Gradient descent follows the negative gradient [2].\" Use [1][3] or [1, 3] for several.\n"
    "- Answer only from what the lecturer said. If the lecture doesn't answer the question, say "
    "plainly that the lecture doesn't cover it, and mention what it does cover if useful. Never "
    "fill gaps from general knowledge.\n"
    "- The student only sees the lecture, not the numbered parts. Refer to \"the lecture\" or "
    "\"the lecturer\"; never mention parts, excerpts, passages, sources, the transcript or what "
    "you were given.\n"
    "- Be concise: 2-6 sentences unless the student asks for more. Plain prose, no headings.\n"
    "- Respond in English."
)


@dataclass
class Source:
    n: int
    start: float
    end: float
    text: str
    relevance: float

    def public(self) -> dict:
        """What the client gets: enough to show and seek, not the full chunk."""
        snippet = self.text if len(self.text) <= 280 else self.text[:277].rstrip() + "…"
        return {"n": self.n, "start": self.start, "end": self.end, "snippet": snippet, "relevance": round(self.relevance, 4)}


@dataclass
class AskResult:
    answer: str
    citations: List[int]
    grounded: bool
    usage: dict = field(default_factory=dict)


def normalize_question(q: str) -> str:
    return " ".join(q.lower().split()).rstrip("?!. ")


def extract_citations(answer: str, valid: Sequence[int]) -> List[int]:
    """Cited source numbers, in first-mention order, keeping only ones that were retrieved."""
    allowed = set(valid)
    seen: List[int] = []
    for m in _CITATION.finditer(answer):
        for num in _NUMBERS.findall(m.group(0)):
            n = int(num)
            if n in allowed and n not in seen:
                seen.append(n)
    return seen


def _fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


class AskAgent:
    def __init__(self, client: Any = None, model: Optional[str] = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip())
        self.client = client
        self.model = (model or os.getenv("ANTHROPIC_ASK_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

    @property
    def prompt_version(self) -> str:
        material = "\n".join([self.model, ASK_SYSTEM, str(N_SOURCES), str(MAX_ANSWER_TOKENS), inspect.getsource(self._user_message)])
        return "ask-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _user_message(question: str, sources: Sequence[Source]) -> str:
        blocks = "\n\n".join(f"[{s.n}] ({_fmt(s.start)}–{_fmt(s.end)})\n{s.text}" for s in sources)
        return f"The lecture, in numbered parts:\n\n{blocks}\n\nStudent's question: {question}"

    def _messages(self, question: str, sources: Sequence[Source], history: Sequence[dict]) -> list:
        """
        Earlier turns go in as plain Q/A text (their excerpts aren't resent, which keeps follow-ups
        cheap); the current turn carries this question's freshly retrieved excerpts.
        """
        msgs: list = []
        for turn in list(history)[-MAX_HISTORY_TURNS:]:
            q = str(turn.get("question", ""))[:MAX_QUESTION_CHARS]
            a = str(turn.get("answer", ""))[:MAX_HISTORY_ANSWER_CHARS]
            if q and a:
                msgs.append({"role": "user", "content": q})
                msgs.append({"role": "assistant", "content": a})
        msgs.append({"role": "user", "content": self._user_message(question, sources)})
        return msgs

    def answer_stream(
        self, question: str, sources: Sequence[Source], history: Sequence[dict] = ()
    ) -> Generator[str, None, AskResult]:
        """
        Yield the answer as Claude writes it; the generator's return value is the AskResult.
        Closing the generator early (client went away) leaves the `with` block, which closes
        the connection to Anthropic and stops generation.
        """
        t0 = time.perf_counter()
        parts: List[str] = []
        first: Optional[float] = None
        with self.client.messages.stream(
            model=self.model,
            max_tokens=MAX_ANSWER_TOKENS,
            system=ASK_SYSTEM,
            messages=self._messages(question, sources, history),
        ) as stream:
            for piece in stream.text_stream:
                if first is None:
                    first = time.perf_counter() - t0
                parts.append(piece)
                yield piece
            message = stream.get_final_message()
        usage_mod.report("ask", message)

        answer = "".join(parts).strip()
        citations = extract_citations(answer, [s.n for s in sources])
        u = getattr(message, "usage", None)
        usage: dict = {
            f: int(getattr(u, f, 0) or 0)
            for f in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        }
        usage["seconds"] = round(time.perf_counter() - t0, 3)
        if first is not None:
            usage["first_token_s"] = round(first, 3)
        return AskResult(answer=answer, citations=citations, grounded=bool(citations), usage=usage)


def sources_from_hits(hits: Sequence[Any]) -> List[Source]:
    """Search hits → numbered sources, in lecture order (easier to read, and to cite)."""
    ordered = sorted(hits, key=lambda h: float(h.start))
    return [
        Source(n=i + 1, start=float(h.start), end=float(h.end), text=str(h.text), relevance=float(h.relevance_score))
        for i, h in enumerate(ordered)
    ]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


__all__ = [
    "AskAgent",
    "AskResult",
    "Source",
    "extract_citations",
    "normalize_question",
    "sources_from_hits",
    "sse",
    "MAX_QUESTION_CHARS",
    "N_SOURCES",
]
