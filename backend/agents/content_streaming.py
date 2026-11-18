"""
Purpose: Streaming variant of the Content Agent (Agent 2) for background jobs.

The original ContentAgent makes one ~70 s Claude call that returns everything as one JSON
object, so nothing can be shown until the very end. This agent splits the work in two calls
that run in parallel:

1. Summaries (streamed, plain text). All three summaries are written in one response,
   separated by section markers, and forwarded piece by piece as Claude writes them. The
   student starts reading the 90-second summary a few seconds after the transcript is ready.
2. Outline + flashcards (structured JSON). Smaller output than before, so it finishes sooner.

Prompt caching: the structured call marks the transcript block `cache_control: ephemeral`, so
its corrective retry (and the legacy fallback) re-read the transcript at the cached rate. The
summaries call deliberately sends no tools: sharing one tools+system prefix between the two
calls looked cheaper, but in production a tools list on the summaries call made Claude skip the
@@SECTION@@ markers. The two calls now start in parallel instead of the structured call waiting.

Cancellation: both calls stream, and both check `should_stop()` between pieces. Leaving the
`with client.messages.stream(...)` block closes the connection, which stops generation (and
billing) on Anthropic's side.

The blocking `/process` endpoint keeps using ContentAgent.process unchanged.
"""

from __future__ import annotations

import usage
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from agents.content_agent import ContentAgent, ContentAgentError
from agents.structured_call import StructuredCallCancelled, StructuredOutputError, call_structured, make_tool
from models.schemas import Flashcard, OutlineItem, TranscriptChunk
from models.structured import StudyStructure

logger = logging.getLogger("lecturekit.content")

SECTIONS: Tuple[str, ...] = ("summary_90s", "summary_5min", "summary_full")
_MARKERS: Dict[str, str] = {
    "@@SUMMARY_90S@@": "summary_90s",
    "@@SUMMARY_5MIN@@": "summary_5min",
    "@@SUMMARY_FULL@@": "summary_full",
}
_MAX_MARKER_LEN = max(len(m) for m in _MARKERS)

# Only the structured call carries this tool. (An earlier version also sent it to the summaries
# call with tool_choice "none" so both calls shared one cache prefix; in production that made
# Claude drop the @@SECTION@@ markers, so the summaries call stays tool-free.)
STUDY_TOOL = make_tool(
    "record_study_kit",
    "Record the outline and flashcards for the lecture.",
    StudyStructure,
)

# How long the structured call waits for the summaries call to warm the prompt cache.
CACHE_WARM_TIMEOUT_S = 8.0


class ContentCancelled(Exception):
    """Raised when should_stop() asked the agent to stop."""


class SectionStreamParser:
    """
    Incrementally split a text stream into sections delimited by @@MARKER@@ lines.

    Text before the first marker is dropped (models sometimes start with a stray newline).
    A marker can arrive split across several pieces, so text that might be the start of a
    marker is held back until the next piece decides it.
    """

    def __init__(self) -> None:
        self._buf = ""
        self.section: Optional[str] = None
        self.text: Dict[str, str] = {s: "" for s in SECTIONS}

    def feed(self, piece: str) -> List[Tuple[str, str]]:
        self._buf += piece
        out: List[Tuple[str, str]] = []
        while True:
            idx = self._buf.find("@@")
            if idx == -1:
                # A trailing "@" may be the first half of a marker's "@@": hold it back.
                keep = 1 if self._buf.endswith("@") else 0
                emit, self._buf = self._buf[: len(self._buf) - keep], self._buf[len(self._buf) - keep :]
                self._emit(emit, out)
                return out

            # Emit everything before a possible marker.
            self._emit(self._buf[:idx], out)
            self._buf = self._buf[idx:]

            matched = next((m for m in _MARKERS if self._buf.startswith(m)), None)
            if matched:
                self.section = _MARKERS[matched]
                self._buf = self._buf[len(matched) :].lstrip("\n")
                continue

            # Could still become a marker once more text arrives: wait for it.
            if len(self._buf) < _MAX_MARKER_LEN and any(m.startswith(self._buf) for m in _MARKERS):
                return out

            # Not a marker: emit the "@@" literally and keep scanning after it.
            self._emit(self._buf[:2], out)
            self._buf = self._buf[2:]

    def close(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        self._emit(self._buf, out)
        self._buf = ""
        for s in SECTIONS:
            self.text[s] = self.text[s].strip()
        return out

    def _emit(self, text: str, out: List[Tuple[str, str]]) -> None:
        if not text or self.section is None:
            return
        self.text[self.section] += text
        if out and out[-1][0] == self.section:
            out[-1] = (self.section, out[-1][1] + text)
        else:
            out.append((self.section, text))


@dataclass
class CallUsage:
    """Token usage for one Claude call (cache fields show whether the transcript was reused)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    seconds: float = 0.0
    first_token_s: Optional[float] = None

    @classmethod
    def from_message(cls, message, seconds: float, first_token_s: Optional[float]) -> "CallUsage":
        u = getattr(message, "usage", None)
        return cls(
            input_tokens=int(getattr(u, "input_tokens", 0) or 0),
            output_tokens=int(getattr(u, "output_tokens", 0) or 0),
            cache_creation_input_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            seconds=round(seconds, 3),
            first_token_s=None if first_token_s is None else round(first_token_s, 3),
        )


@dataclass
class StructuredContent:
    outline: List[OutlineItem]
    flashcards: List[Flashcard]
    usage: CallUsage = field(default_factory=CallUsage)
    path: str = "tool"  # which structured_call path produced it
    attempts: int = 1


@dataclass
class StreamedSummaries:
    summary_90s: str
    summary_5min: str
    summary_full: str
    usage: CallUsage = field(default_factory=CallUsage)


class StreamingContentAgent(ContentAgent):
    """ContentAgent with a streamed-summaries call and a separate structured call."""

    @property
    def prompt_version(self) -> str:
        """
        Cache key component: a hash of everything that shapes the output (prompts, model,
        output limits). Edit a prompt or switch models and cached study kits stop matching,
        so they are regenerated instead of served stale.
        """
        material = "\n".join(
            [
                self._model,
                repr(self._system_blocks("")),
                self._summaries_instruction(),
                self._structured_instruction(),
                repr(STUDY_TOOL),
                "summaries:4000/structured:6000",
            ]
        )
        return "student-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    # The agent is a shared singleton, so per-job state (the cache-warm signal) is passed in
    # by the caller rather than stored on the instance.

    # ---------- prompts ----------

    def _system_blocks(self, transcript: str, *, cache: bool = False) -> list:
        """
        Instructions + transcript. `cache=True` marks the transcript block for prompt caching; the
        structured call uses it so its corrective retry (and the legacy fallback) re-read the
        transcript at the cached rate instead of paying full price again.
        """
        transcript_block: dict = {"type": "text", "text": f"Lecture transcript (timestamped):\n{transcript}"}
        if cache:
            transcript_block["cache_control"] = {"type": "ephemeral"}
        return [
            {
                "type": "text",
                "text": (
                    "You are a study-material generation engine for university lectures. "
                    "Respond entirely in English regardless of the language of the transcript. "
                    "You will be given a lecture transcript; each line starts with [timestamp: Xs]."
                ),
            },
            transcript_block,
        ]

    @staticmethod
    def _summaries_instruction() -> str:
        return (
            "Write three summaries of this lecture as plain prose (no markdown headings, no bullet lists).\n"
            "Use EXACTLY this layout, with each marker on its own line:\n\n"
            "@@SUMMARY_90S@@\n"
            "<2 to 3 sentences, under 100 words: the single most important idea>\n"
            "@@SUMMARY_5MIN@@\n"
            "<3 to 4 paragraphs, 200 to 600 words, covering all main topics>\n"
            "@@SUMMARY_FULL@@\n"
            "<one paragraph per major topic, comprehensive, at least 450 words>\n\n"
            "Start immediately with @@SUMMARY_90S@@. Write nothing before the first marker or after the last section."
        )

    @staticmethod
    def _structured_instruction() -> str:
        return (
            f"Call {STUDY_TOOL['name']} with the outline and flashcards for this lecture.\n"
            "- outline: 5 to 8 main topics in chronological order; timestamp in seconds where each topic starts.\n"
            "- flashcards: EXACTLY 10, testing understanding/application, not just recall. "
            "Answers are 2 to 4 sentences. Spread them across the whole lecture.\n"
            "- Every timestamp must be a real moment from the transcript's [timestamp: Xs] markers."
        )

    @staticmethod
    def _legacy_structured_instruction() -> str:
        return (
            "Return ONLY valid JSON (no markdown, no backticks, no commentary) with EXACTLY this structure:\n"
            "{\n"
            '  "outline": [{"timestamp": 0.0, "title": "Topic title", "description": "One sentence"}],\n'
            '  "flashcards": [{"question": "...", "answer": "...", "source_timestamp": 0.0}]\n'
            "}\n\n"
            "Requirements:\n"
            "- outline: 5 to 8 main topics in chronological order; timestamp in seconds where the topic starts.\n"
            "- flashcards: EXACTLY 10, testing understanding/application, not just recall. "
            "Answers are 2 to 4 sentences. Spread them across the whole lecture.\n"
            "- Each source_timestamp must point to where that concept appears in the transcript."
        )

    # ---------- calls ----------

    def stream_summaries(
        self,
        chunks: Sequence[TranscriptChunk],
        on_delta: Callable[[str, str], None],
        should_stop: Callable[[], bool] = lambda: False,
        cache_warm: Optional[threading.Event] = None,
    ) -> StreamedSummaries:
        """
        Stream the three summaries. Calls on_delta(section, text) as text arrives, and sets
        `cache_warm` once Claude starts responding (the prompt cache is readable from then on).
        """
        cache_warm = cache_warm or threading.Event()
        if not chunks:
            raise ContentAgentError("ContentAgent received no transcript chunks.")
        transcript = self._format_timestamped_transcript(chunks)
        parser = SectionStreamParser()
        raw: List[str] = []
        t0 = time.perf_counter()
        first_token_s: Optional[float] = None

        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=4000,
                system=self._system_blocks(transcript),
                messages=[{"role": "user", "content": self._summaries_instruction()}],
            ) as stream:
                for piece in stream.text_stream:
                    if first_token_s is None:
                        first_token_s = time.perf_counter() - t0
                        cache_warm.set()
                    if should_stop():
                        raise ContentCancelled()
                    raw.append(piece)
                    for section, text in parser.feed(piece):
                        on_delta(section, text)
                for section, text in parser.close():
                    on_delta(section, text)
                message = stream.get_final_message()
            usage.report("student", message)
        except ContentCancelled:
            raise
        except Exception as exc:
            raise ContentAgentError(f"Claude summary stream failed: {type(exc).__name__}: {exc}") from exc
        finally:
            # Never leave the structured call waiting on a cache that won't come.
            cache_warm.set()

        if not parser.text["summary_90s"]:
            head = "".join(raw)[:300].replace("\n", "\\n")
            logger.warning(
                "Summary stream had no sections (stop_reason=%r, %d chars). Start: %s",
                getattr(message, "stop_reason", None),
                len("".join(raw)),
                head,
            )
            raise ContentAgentError("Claude's summary stream did not contain the expected sections.")
        return StreamedSummaries(
            summary_90s=parser.text["summary_90s"],
            summary_5min=parser.text["summary_5min"],
            summary_full=parser.text["summary_full"],
            usage=CallUsage.from_message(message, time.perf_counter() - t0, first_token_s),
        )

    def generate_structured(
        self,
        chunks: Sequence[TranscriptChunk],
        should_stop: Callable[[], bool] = lambda: False,
        cache_warm: Optional[threading.Event] = None,
    ) -> StructuredContent:
        """
        Outline + flashcards via a forced `record_study_kit` tool call, validated against
        StudyStructure (counts, timestamps inside the lecture, chronological outline), with one
        corrective retry and the old text-JSON path as a last resort. Starts once the summaries
        call has warmed the prompt cache.
        """
        if not chunks:
            raise ContentAgentError("ContentAgent received no transcript chunks.")
        transcript = self._format_timestamped_transcript(chunks)
        if cache_warm is not None:
            deadline = time.perf_counter() + CACHE_WARM_TIMEOUT_S
            while not cache_warm.wait(0.25):
                if should_stop():
                    raise ContentCancelled()
                if time.perf_counter() > deadline:
                    break

        system = self._system_blocks(transcript, cache=True)

        def legacy() -> dict:
            # Last resort: the pre-tool-use prompt, read as text and repaired by the 4-strategy parser.
            parts: List[str] = []
            with self._client.messages.stream(
                model=self._model,
                max_tokens=6000,
                system=system,
                messages=[{"role": "user", "content": self._legacy_structured_instruction()}],
            ) as stream:
                for piece in stream.text_stream:
                    if should_stop():
                        raise StructuredCallCancelled()
                    parts.append(piece)
                usage.report("student", stream.get_final_message())
            return self._parse_json_with_retry("".join(parts), transcript=transcript)

        try:
            result = call_structured(
                self._client,
                agent="student",
                model=self._model,
                system=system,
                user=self._structured_instruction(),
                tools=[STUDY_TOOL],
                tool_name=STUDY_TOOL["name"],
                model_cls=StudyStructure,
                max_tokens=6000,
                context={"max_timestamp": float(chunks[-1].end)},
                should_stop=should_stop,
                legacy_fallback=legacy,
            )
        except StructuredCallCancelled as exc:
            raise ContentCancelled() from exc
        except StructuredOutputError as exc:
            raise ContentAgentError(str(exc)) from exc

        u = result.usage
        return StructuredContent(
            outline=list(result.value.outline),
            flashcards=list(result.value.flashcards),
            usage=CallUsage(
                input_tokens=u.get("input_tokens", 0),
                output_tokens=u.get("output_tokens", 0),
                cache_creation_input_tokens=u.get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=u.get("cache_read_input_tokens", 0),
                seconds=u.get("seconds", 0.0),
                first_token_s=u.get("first_token_s"),
            ),
            path=result.path,
            attempts=int(u.get("attempts", 1)),
        )
