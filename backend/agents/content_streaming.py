"""
Purpose: Streaming variant of the Content Agent (Agent 2) for background jobs.

The original ContentAgent makes one ~70 s Claude call that returns everything as one JSON
object, so nothing can be shown until the very end. This agent splits the work in two calls
that run in parallel:

1. Summaries (streamed, plain text). All three summaries are written in one response,
   separated by section markers, and forwarded piece by piece as Claude writes them. The
   student starts reading the 90-second summary a few seconds after the transcript is ready.
2. Outline + flashcards (structured JSON). Smaller output than before, so it finishes sooner.

Prompt caching: both calls send the same system prompt (instructions + transcript), marked
`cache_control: ephemeral`. The structured call waits until the summaries call has started
responding (the point at which Anthropic's cache entry becomes readable), so the transcript,
which is most of the input, is billed at the cached rate on the second call instead of twice
at full price. If the summaries call is slow to start, the structured call goes ahead after
a short timeout rather than waiting.

Cancellation: both calls stream, and both check `should_stop()` between pieces. Leaving the
`with client.messages.stream(...)` block closes the connection, which stops generation (and
billing) on Anthropic's side.

The blocking `/process` endpoint keeps using ContentAgent.process unchanged.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from agents.content_agent import ContentAgent, ContentAgentError
from models.schemas import Flashcard, OutlineItem, TranscriptChunk

SECTIONS: Tuple[str, ...] = ("summary_90s", "summary_5min", "summary_full")
_MARKERS: Dict[str, str] = {
    "@@SUMMARY_90S@@": "summary_90s",
    "@@SUMMARY_5MIN@@": "summary_5min",
    "@@SUMMARY_FULL@@": "summary_full",
}
_MAX_MARKER_LEN = max(len(m) for m in _MARKERS)

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


@dataclass
class StreamedSummaries:
    summary_90s: str
    summary_5min: str
    summary_full: str
    usage: CallUsage = field(default_factory=CallUsage)


class StreamingContentAgent(ContentAgent):
    """ContentAgent with a streamed-summaries call and a separate structured call."""

    # The agent is a shared singleton, so per-job state (the cache-warm signal) is passed in
    # by the caller rather than stored on the instance.

    # ---------- prompts ----------

    def _system_blocks(self, transcript: str) -> list:
        """Identical for both calls so the second one reads the first one's cache."""
        return [
            {
                "type": "text",
                "text": (
                    "You are a study-material generation engine for university lectures. "
                    "Respond entirely in English regardless of the language of the transcript. "
                    "You will be given a lecture transcript; each line starts with [timestamp: Xs]."
                ),
            },
            {
                "type": "text",
                "text": f"Lecture transcript (timestamped):\n{transcript}",
                "cache_control": {"type": "ephemeral"},
            },
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
                    for section, text in parser.feed(piece):
                        on_delta(section, text)
                for section, text in parser.close():
                    on_delta(section, text)
                message = stream.get_final_message()
        except ContentCancelled:
            raise
        except Exception as exc:
            raise ContentAgentError(f"Claude summary stream failed: {type(exc).__name__}: {exc}") from exc
        finally:
            # Never leave the structured call waiting on a cache that won't come.
            cache_warm.set()

        if not parser.text["summary_90s"]:
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
        """Outline + flashcards as JSON, after the summaries call has warmed the prompt cache."""
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

        t0 = time.perf_counter()
        first_token_s: Optional[float] = None
        parts: List[str] = []
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=6000,
                system=self._system_blocks(transcript),
                messages=[{"role": "user", "content": self._structured_instruction()}],
            ) as stream:
                for piece in stream.text_stream:
                    if first_token_s is None:
                        first_token_s = time.perf_counter() - t0
                    if should_stop():
                        raise ContentCancelled()
                    parts.append(piece)
                message = stream.get_final_message()
        except ContentCancelled:
            raise
        except Exception as exc:
            raise ContentAgentError(f"Claude structured call failed: {type(exc).__name__}: {exc}") from exc

        parsed = self._parse_json_with_retry("".join(parts), transcript=transcript)
        try:
            outline = [OutlineItem.model_validate(o) for o in parsed.get("outline") or []]
            flashcards = [Flashcard.model_validate(f) for f in parsed.get("flashcards") or []]
        except Exception as exc:
            raise ContentAgentError("Claude returned JSON but it did not match the expected schema.") from exc
        if not outline or not flashcards:
            raise ContentAgentError("Claude returned an empty outline or no flashcards.")
        return StructuredContent(
            outline=outline,
            flashcards=flashcards,
            usage=CallUsage.from_message(message, time.perf_counter() - t0, first_token_s),
        )
