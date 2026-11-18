"""
Purpose: Map-reduce for lectures too long for one prompt.

Before this, long lectures were silently cut: Faculty read only the first 6,000 words of a
lecture (~40 min), Provost the first 4,000 words of each lecture, and Student sent the whole
transcript in one prompt however long it was. Anything past the cut was never seen.

Map:    split the transcript into ~4,000-word sections (on chunk boundaries) and ask Claude,
        in parallel, for structured notes on each one: a title, a dense summary, timestamped
        key points and defined terms. Forced tool use + Pydantic, like every other call, and
        every timestamp must fall inside its own section.
Reduce: turn the notes back into timestamped pseudo-chunks (`digest_chunks`) and hand them to
        the existing agents unchanged. They format, prompt and validate exactly as before;
        they just read 8 pages of notes instead of 60 pages of speech.

Each mode has its own word budget (what it can read whole). A lecture under the budget takes
the direct path, so short lectures behave exactly as they did. Notes are cached per lecture
(results table, kind "notes"), so Student, Faculty and Provost share one map step.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from agents.structured_call import StructuredCallCancelled, call_structured, make_tool
from models.schemas import TranscriptChunk

logger = logging.getLogger("lecturekit.map_reduce")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


# Word budgets: above these a mode reads notes instead of the raw transcript.
STUDENT_WORD_BUDGET = _env_int("LONG_LECTURE_WORDS", 9000)  # ~60 min of speech
FACULTY_WORD_BUDGET = 6000  # FacultyAgent._format_transcript's cap
PROVOST_WORD_BUDGET = 4000  # ProvostAgent._format_lectures' per-lecture cap

SECTION_WORDS = _env_int("MAP_SECTION_WORDS", 4000)
MAP_CONCURRENCY = _env_int("MAP_CONCURRENCY", 4)

DIGEST_NOTE = (
    "NOTE: this lecture is long, so what follows is a set of timestamped section notes "
    "condensed from the full transcript, not verbatim speech. Timestamps are accurate."
)


# ---------- splitting ----------


def word_count(chunks: Sequence[TranscriptChunk]) -> int:
    return sum(int(c.word_count or len(c.text.split())) for c in chunks)


def needs_map(chunks: Sequence[TranscriptChunk], budget: int) -> bool:
    return word_count(chunks) > budget


def split_sections(chunks: Sequence[TranscriptChunk], target_words: int = SECTION_WORDS) -> List[List[TranscriptChunk]]:
    """
    Greedy split on chunk boundaries into sections of about `target_words`. A short tail
    (under a quarter of the target) is folded into the previous section rather than sent alone.
    """
    sections: List[List[TranscriptChunk]] = []
    current: List[TranscriptChunk] = []
    words = 0
    for c in chunks:
        n = int(c.word_count or len(c.text.split()))
        if current and words + n > target_words:
            sections.append(current)
            current, words = [], 0
        current.append(c)
        words += n
    if current:
        if sections and words < target_words // 4:
            sections[-1].extend(current)
        else:
            sections.append(current)
    return sections


# ---------- the map output ----------


def _in_section(value: float, info: ValidationInfo) -> float:
    ctx = info.context or {}
    lo, hi = ctx.get("section_start"), ctx.get("section_end")
    if lo is not None and hi is not None and not (lo - 1 <= value <= hi + 1):
        raise ValueError(f"timestamp {value:.0f}s is outside this section ({lo:.0f}s–{hi:.0f}s)")
    return value


class KeyPoint(BaseModel):
    timestamp: float = Field(..., ge=0, description="Seconds from the start of the lecture.")
    point: str = Field(..., min_length=1, description="One self-contained idea, claim, example or step.")

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float, info: ValidationInfo) -> float:
        return _in_section(v, info)


class Term(BaseModel):
    term: str = Field(..., min_length=1)
    definition: str = Field(..., min_length=1)
    timestamp: float = Field(..., ge=0)

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float, info: ValidationInfo) -> float:
        return _in_section(v, info)


class SectionNotes(BaseModel):
    title: str = Field(..., min_length=1, description="Short title for what this section covers.")
    summary: str = Field(..., min_length=1, description="Dense 120-200 word summary of the section.")
    key_points: List[KeyPoint] = Field(..., min_length=3, max_length=15)
    terms: List[Term] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _sorted(self) -> "SectionNotes":
        self.key_points.sort(key=lambda k: k.timestamp)
        self.terms.sort(key=lambda t: t.timestamp)
        return self


NOTES_TOOL = make_tool(
    "record_section_notes",
    "Record study notes for one section of a lecture transcript.",
    SectionNotes,
)

NOTES_SYSTEM = (
    "You take notes on one section of a university lecture transcript, so that later steps "
    "can work from your notes instead of the full transcript. Each transcript line starts with "
    "[timestamp: Xs]. Be faithful and specific: keep the lecturer's examples, numbers, "
    "definitions and the order of ideas. Every timestamp you give must be one that appears in "
    "this section. Respond in English."
)


def _section_prompt(section: Sequence[TranscriptChunk], index: int, total: int) -> str:
    lines = "\n".join(f"[timestamp: {c.start:.2f}s] {c.text}" for c in section)
    return (
        f"Section {index + 1} of {total} (from {section[0].start:.0f}s to {section[-1].end:.0f}s).\n\n"
        f"{lines}\n\n"
        f"Call {NOTES_TOOL['name']} with notes for this section: 6-12 key points in order, "
        "and any terms the lecturer defines."
    )


# ---------- notes for a whole lecture ----------


@dataclass
class LectureNotes:
    sections: List[dict]  # SectionNotes.model_dump() + {"start", "end"}
    usage: dict = field(default_factory=dict)

    def payload(self) -> dict:
        return {"sections": self.sections}

    @classmethod
    def from_payload(cls, payload: dict) -> "LectureNotes":
        return cls(sections=list(payload.get("sections") or []))


def _sum_usage(parts: Sequence[dict]) -> dict:
    total: dict[str, Any] = {}
    for u in parts:
        for k, v in u.items():
            if isinstance(v, (int, float)) and k != "first_token_s":
                total[k] = total.get(k, 0) + v
    if "seconds" in total:
        total["seconds"] = round(total["seconds"], 3)
    return total


class NotesAgent:
    """The map step. Stateless apart from the client, so one instance serves every job."""

    def __init__(self, client: Any = None, model: Optional[str] = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip())
        self.client = client
        # The map step is extraction, so it can run on a cheaper model than the rest.
        self.model = (model or os.getenv("ANTHROPIC_MAP_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

    @property
    def prompt_version(self) -> str:
        material = "\n".join(
            [self.model, NOTES_SYSTEM, repr(NOTES_TOOL), str(SECTION_WORDS), inspect.getsource(_section_prompt)]
        )
        return "notes-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    def notes_for(
        self,
        chunks: Sequence[TranscriptChunk],
        should_stop: Callable[[], bool] = lambda: False,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> LectureNotes:
        sections = split_sections(chunks)
        total = len(sections)
        results: List[Optional[dict]] = [None] * total
        usages: List[dict] = []
        failed = threading.Event()
        stop = lambda: should_stop() or failed.is_set()  # noqa: E731  one failure stops the rest

        def one(i: int) -> dict:
            sec = sections[i]
            res = call_structured(
                self.client,
                agent="map",
                model=self.model,
                system=NOTES_SYSTEM,
                user=_section_prompt(sec, i, total),
                tools=[NOTES_TOOL],
                tool_name=NOTES_TOOL["name"],
                model_cls=SectionNotes,
                max_tokens=2000,
                context={"section_start": float(sec[0].start), "section_end": float(sec[-1].end)},
                should_stop=stop,
            )
            usages.append(res.usage)
            return {**res.value.model_dump(), "start": float(sec[0].start), "end": float(sec[-1].end)}

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, MAP_CONCURRENCY)) as pool:
            futures = {pool.submit(one, i): i for i in range(total)}
            try:
                for fut in as_completed(futures):
                    results[futures[fut]] = fut.result()
                    done += 1
                    if on_progress is not None:
                        on_progress(done, total)
            except BaseException:
                failed.set()
                for f in futures:
                    f.cancel()
                raise
        if should_stop():
            raise StructuredCallCancelled()
        return LectureNotes(sections=[r for r in results if r is not None], usage=_sum_usage(usages))


# ---------- reduce input ----------


def digest_chunks(notes: LectureNotes, original: Sequence[TranscriptChunk]) -> List[TranscriptChunk]:
    """
    Notes as TranscriptChunks, in time order, so every downstream agent can read them with its
    usual transcript formatting: a header note, then per section its title + summary, its key
    points and its terms. The last chunk ends where the real lecture ends, so timestamp
    validation (max_timestamp) still allows the whole lecture.
    """
    lecture_end = float(original[-1].end) if original else 0.0
    items: List[tuple[float, str]] = []
    for s in notes.sections:
        start = float(s["start"])
        items.append((start, f"{DIGEST_NOTE if not items else ''} SECTION \"{s['title']}\": {s['summary']}".strip()))
        for kp in s.get("key_points", []):
            items.append((float(kp["timestamp"]), kp["point"]))
        for t in s.get("terms", []):
            items.append((float(t["timestamp"]), f"Definition — {t['term']}: {t['definition']}"))
    items.sort(key=lambda x: x[0])  # stable: a section header stays ahead of its own points

    out: List[TranscriptChunk] = []
    for i, (start, text) in enumerate(items):
        end = items[i + 1][0] if i + 1 < len(items) else lecture_end
        out.append(
            TranscriptChunk(
                text=text, start=start, end=max(end, start), chunk_index=i, word_count=len(text.split())
            )
        )
    return out
