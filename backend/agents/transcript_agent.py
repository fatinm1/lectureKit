"""
Purpose: Agent 1 — Transcript Agent (YouTube URL → cleaned, timestamped chunks).

Part 2: Production implementation.

Responsibilities:
- Accept a YouTube URL as input
- Extract the video ID from common URL formats
- Fetch full transcript via `youtube-transcript-api`
- Clean transcript text (remove filler, whitespace/newlines, strip HTML tags)
- Chunk into ~500-word segments with sentence-aware boundaries
- Preserve start/end timestamps per chunk (seconds)
- Return a list of `TranscriptChunk` objects for downstream agents

Data flow: FastAPI `/process` orchestrator → this agent → downstream agents.
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass
from typing import Sequence
from xml.etree.ElementTree import ParseError

import requests
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from models.schemas import TranscriptChunk
from utils.youtube import InvalidYouTubeUrlError, extract_youtube_video_id


class TranscriptAgentError(Exception):
    """Base class for TranscriptAgent failures."""


class TranscriptFetchTimeoutError(TranscriptAgentError):
    """Raised when transcript retrieval exceeds the configured timeout."""


class TranscriptUnavailableError(TranscriptAgentError):
    """Raised when a transcript cannot be retrieved (disabled/missing/unavailable)."""


@dataclass(frozen=True)
class _WordTime:
    """Internal helper mapping a word token to an approximate timestamp (seconds)."""

    token: str
    time_s: float


_FILLER_WORDS = (
    "um",
    "uh",
    "you know",
    "like",
    "basically",
    "actually",
    "literally",
)


class TranscriptAgent:
    """
    Agent 1 — transcript extraction + cleaning + chunking.

    Public API:
        process(youtube_url: str) -> tuple[str, list[TranscriptChunk]]
    """

    def __init__(
        self,
        *,
        target_words_per_chunk: int = 500,
        max_words_over_target: int = 120,
        fetch_timeout_s: float = 20.0,
    ) -> None:
        """
        Configure chunking and network timeout behavior.

        Args:
            target_words_per_chunk: Desired chunk size in words.
            max_words_over_target: How far beyond target we’ll search for a sentence boundary.
            fetch_timeout_s: Max seconds allowed for transcript retrieval.

        Steps:
            1. Store configuration for deterministic chunking behavior.
        """
        self._target_words_per_chunk = target_words_per_chunk
        self._max_words_over_target = max_words_over_target
        self._fetch_timeout_s = fetch_timeout_s

    def process(self, youtube_url: str) -> tuple[str, list[TranscriptChunk]]:
        """
        Process a YouTube URL into cleaned, timestamped transcript chunks.

        Args:
            youtube_url: Any supported YouTube URL format.

        Returns:
            (video_id, chunks) where chunks are ordered by time and indexed from 0.

        Steps:
            1. Extract video ID from URL.
            2. Fetch transcript entries with a hard timeout guard.
            3. Clean and normalize transcript text.
            4. Convert transcript into a word-level time series.
            5. Chunk words into sentence-aware ~500-word segments.

        Raises:
            InvalidYouTubeUrlError: If video ID cannot be extracted.
            TranscriptFetchTimeoutError: If transcript fetch times out.
            TranscriptUnavailableError: If transcript is missing/disabled/unavailable.
            TranscriptAgentError: For other unexpected failures.
        """
        # Step: Extract canonical ID early; downstream tooling requires the 11-char ID.
        video_id = extract_youtube_video_id(youtube_url)

        # Step: Fetch transcript with a timeout so network stalls don’t hang the API.
        entries = self._fetch_transcript_entries(video_id)

        # Step: Convert to word-level tokens with approximate per-word timestamps.
        word_times = self._entries_to_word_times(entries)

        # Step: Chunk tokens into ~500 word blocks without cutting mid-sentence when possible.
        chunks = self._chunk_word_times(word_times)

        return video_id, chunks

    def _fetch_transcript_entries(self, video_id: str) -> list[dict]:
        """
        Retrieve transcript entries from youtube-transcript-api.

        Args:
            video_id: 11-character YouTube ID.

        Returns:
            List of transcript entries (dicts with `text`, `start`, `duration`).

        Steps:
            1. Run the library call in a thread.
            2. Enforce a hard timeout at the future boundary.
            3. Re-map library exceptions into domain errors with descriptive messages.
        """
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(YouTubeTranscriptApi.get_transcript, video_id)
                return future.result(timeout=self._fetch_timeout_s)
        except concurrent.futures.TimeoutError as exc:
            raise TranscriptFetchTimeoutError(
                f"Network timeout while fetching transcript (>{self._fetch_timeout_s:.0f}s)"
            ) from exc
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            raise TranscriptUnavailableError(
                "No transcript available for this video (transcripts disabled or not found)"
            ) from exc
        except VideoUnavailable as exc:
            raise TranscriptUnavailableError(
                "Video is private, unavailable, or cannot be accessed"
            ) from exc
        except CouldNotRetrieveTranscript as exc:
            # Step: Catch-all for other transcript retrieval failures from the library.
            raise TranscriptUnavailableError(
                "Unable to retrieve transcript for this video"
            ) from exc
        except ParseError as exc:
            # Step: YouTube sometimes returns empty/blocked pages that the library can’t parse as XML.
            # Step: Fallback to yt-dlp captions extraction before declaring failure.
            return self._fetch_transcript_entries_with_ytdlp(video_id, cause=exc)
        except Exception as exc:
            raise TranscriptAgentError(
                f"Unexpected error while fetching transcript ({type(exc).__name__})"
            ) from exc

    def _fetch_transcript_entries_with_ytdlp(self, video_id: str, *, cause: Exception) -> list[dict]:
        """
        Fallback transcript fetcher using yt-dlp when youtube-transcript-api cannot parse.

        Args:
            video_id: 11-character YouTube ID.
            cause: The exception that triggered fallback (for diagnostics).

        Returns:
            Transcript entries as dicts with `text`, `start`, `duration`.

        Steps:
            1. Use yt-dlp to extract available subtitles/automatic captions metadata.
            2. Choose a language (prefer English; otherwise first available).
            3. Choose a subtitle format (prefer VTT).
            4. Download the subtitle URL with requests and parse into cue entries.

        Raises:
            TranscriptUnavailableError: If captions cannot be extracted or parsed.
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = {
            # Step: Metadata only — we download subtitles ourselves from the returned URLs.
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except DownloadError as exc:
            raise TranscriptUnavailableError(
                "Unable to retrieve transcript via yt-dlp fallback (video may be unavailable)"
            ) from exc
        except Exception as exc:
            raise TranscriptUnavailableError(
                "Unable to retrieve transcript via yt-dlp fallback"
            ) from exc

        subtitles = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}

        # Step: Prefer human subtitles; fall back to automatic captions.
        captions_source = subtitles if subtitles else auto
        if not captions_source:
            raise TranscriptUnavailableError(
                "No transcript available for this video (no subtitles or automatic captions found)"
            ) from cause

        # Step: Prefer English if available; otherwise pick the first language key.
        lang = "en" if "en" in captions_source else next(iter(captions_source.keys()))
        formats = captions_source.get(lang) or []
        if not formats:
            raise TranscriptUnavailableError(
                "No transcript available for this video (captions metadata missing formats)"
            ) from cause

        # Step: Prefer VTT; otherwise take the first format.
        chosen = None
        for f in formats:
            if f.get("ext") == "vtt":
                chosen = f
                break
        if chosen is None:
            chosen = formats[0]

        sub_url = chosen.get("url")
        ext = chosen.get("ext") or ""
        if not sub_url:
            raise TranscriptUnavailableError(
                "Unable to retrieve transcript via yt-dlp fallback (missing subtitle URL)"
            ) from cause

        try:
            resp = requests.get(sub_url, timeout=self._fetch_timeout_s)
            resp.raise_for_status()
            data = resp.text
        except requests.Timeout as exc:
            raise TranscriptFetchTimeoutError(
                f"Network timeout while fetching transcript (>{self._fetch_timeout_s:.0f}s)"
            ) from exc
        except Exception as exc:
            raise TranscriptUnavailableError(
                "Unable to download transcript captions via yt-dlp fallback"
            ) from exc

        if ext == "vtt" or data.lstrip().startswith("WEBVTT"):
            entries = self._parse_vtt_to_entries(data)
        else:
            # Step: Keep implementation tight — VTT is the most common. If needed, we can extend later.
            raise TranscriptUnavailableError(
                f"yt-dlp fallback returned unsupported caption format '{ext}' (expected vtt)"
            ) from cause

        if not entries:
            raise TranscriptUnavailableError(
                "Transcript captions were downloaded but contained no usable cues"
            ) from cause

        return entries

    def _parse_vtt_to_entries(self, vtt_text: str) -> list[dict]:
        """
        Parse a VTT subtitle file into transcript entries.

        Args:
            vtt_text: WEBVTT file content.

        Returns:
            List of dict entries matching youtube-transcript-api shape: {text, start, duration}.

        Steps:
            1. Scan for cue timing lines: `HH:MM:SS.mmm --> HH:MM:SS.mmm`.
            2. Collect cue payload lines until blank separator.
            3. Emit each cue as one transcript entry with start/duration.
        """
        lines = [ln.rstrip("\n") for ln in vtt_text.splitlines()]
        entries: list[dict] = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Step: Skip headers and empty lines.
            if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
                i += 1
                continue

            # Step: Cue timing line.
            if "-->" in line:
                start_str, rest = [p.strip() for p in line.split("-->", 1)]
                end_str = rest.split()[0].strip()

                start_s = self._parse_vtt_timestamp_seconds(start_str)
                end_s = self._parse_vtt_timestamp_seconds(end_str)
                duration_s = max(0.0, end_s - start_s)

                i += 1
                cue_text_lines: list[str] = []
                while i < len(lines) and lines[i].strip():
                    cue_text_lines.append(lines[i].strip())
                    i += 1

                cue_text = " ".join(cue_text_lines).strip()
                cue_text = self._clean_text(cue_text)
                if cue_text:
                    entries.append({"text": cue_text, "start": start_s, "duration": duration_s})

                continue

            # Step: Some VTTs include numeric cue identifiers; skip them.
            i += 1

        return entries

    def _parse_vtt_timestamp_seconds(self, ts: str) -> float:
        """
        Convert a VTT timestamp into seconds.

        Args:
            ts: Timestamp like `MM:SS.mmm` or `HH:MM:SS.mmm`.

        Returns:
            Seconds as float.
        """
        parts = ts.split(":")
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return (minutes * 60) + seconds
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return (hours * 3600) + (minutes * 60) + seconds
        # Step: Defensive fallback — treat malformed timestamps as 0.
        return 0.0

    def _entries_to_word_times(self, entries: Sequence[dict]) -> list[_WordTime]:
        """
        Clean transcript entries and expand them into word-level tokens with timestamps.

        Args:
            entries: Transcript list; each dict contains `text`, `start`, `duration`.

        Returns:
            List of `_WordTime` where each word token has an approximate `time_s`.

        Steps:
            1. Clean each entry’s text (filler removal, whitespace normalization, HTML stripping).
            2. Split into words (simple whitespace tokenization).
            3. Assign each word a timestamp by evenly spacing across the entry’s duration.
        """
        word_times: list[_WordTime] = []

        for entry in entries:
            # Step: Read raw fields defensively; library returns these keys but we guard anyway.
            raw_text = str(entry.get("text", ""))
            start_s = float(entry.get("start", 0.0))
            duration_s = float(entry.get("duration", 0.0))

            cleaned = self._clean_text(raw_text)
            if not cleaned:
                # Step: Skip empty segments after cleaning (e.g., only filler words).
                continue

            words = cleaned.split()
            if not words:
                continue

            # Step: Avoid divide-by-zero; treat zero-duration segments as instant stamps at `start`.
            denom = max(len(words), 1)
            step = duration_s / denom if duration_s > 0 else 0.0

            for idx, token in enumerate(words):
                word_times.append(_WordTime(token=token, time_s=start_s + (idx * step)))

        return word_times

    def _chunk_word_times(self, word_times: Sequence[_WordTime]) -> list[TranscriptChunk]:
        """
        Chunk a word-time sequence into ~target sized segments with sentence-aware boundaries.

        Args:
            word_times: Ordered words with approximate timestamps.

        Returns:
            List of TranscriptChunk objects.

        Steps:
            1. Advance a sliding pointer over words.
            2. Prefer chunk boundaries on sentence endings near the target size.
            3. Fall back to hard cut at target if no boundary exists in the search window.
            4. Emit start/end timestamps using first/last word time in each chunk.
        """
        if not word_times:
            return []

        chunks: list[TranscriptChunk] = []
        i = 0
        chunk_index = 0

        while i < len(word_times):
            target_end = min(i + self._target_words_per_chunk, len(word_times))
            search_end = min(target_end + self._max_words_over_target, len(word_times))

            # Step: Find a sentence boundary at/after target, otherwise look backward.
            boundary = self._find_sentence_boundary(word_times, i, target_end, search_end)
            if boundary is None:
                boundary = target_end

            # Step: Defensive guard — always make progress.
            boundary = max(boundary, i + 1)

            chunk_words = [wt.token for wt in word_times[i:boundary]]
            start_s = float(word_times[i].time_s)
            end_s = float(word_times[boundary - 1].time_s)

            chunks.append(
                TranscriptChunk(
                    text=" ".join(chunk_words).strip(),
                    start=start_s,
                    end=end_s,
                    chunk_index=chunk_index,
                    word_count=len(chunk_words),
                )
            )

            i = boundary
            chunk_index += 1

        return chunks

    def _find_sentence_boundary(
        self,
        word_times: Sequence[_WordTime],
        start_idx: int,
        target_end: int,
        search_end: int,
    ) -> int | None:
        """
        Find a sentence boundary for chunk termination.

        Strategy:
        - First search forward from `target_end` to `search_end` for a sentence end.
        - If none found, search backward from `target_end` down to `start_idx + min_tail_words`.
        """
        # Step: Avoid extremely tiny chunks by requiring at least some tail content.
        min_tail_words = 140
        min_idx = min(start_idx + min_tail_words, target_end)

        for j in range(target_end, search_end):
            if self._is_sentence_end(word_times[j - 1].token):
                return j

        for j in range(target_end, min_idx, -1):
            if self._is_sentence_end(word_times[j - 1].token):
                return j

        return None

    def _clean_text(self, text: str) -> str:
        """
        Normalize transcript text to a clean, model-ready surface.

        Cleaning rules:
        - Remove filler words: um, uh, you know, like, basically, actually, literally
        - Strip HTML tags
        - Collapse newlines/whitespace
        - Collapse immediate duplicate sentences/phrases (common caption artifact)
        """
        # Step: Strip HTML tags if present.
        without_html = re.sub(r"<[^>]+>", " ", text)

        # Step: Remove filler words/phrases as standalone tokens (case-insensitive).
        cleaned = without_html
        for filler in _FILLER_WORDS:
            pattern = r"\b" + re.escape(filler) + r"\b"
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

        # Step: Normalize whitespace/newlines.
        cleaned = cleaned.replace("\n", " ").replace("\r", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Step: Remove consecutive duplicate sentences (e.g. the same caption line repeated).
        cleaned = self._dedupe_consecutive_sentences(cleaned)
        # Step: Remove consecutive duplicate phrases within a sentence (e.g. phrase repeated 2-3 times).
        cleaned = self._dedupe_consecutive_phrases(cleaned)

        return cleaned.strip()

    def _dedupe_consecutive_sentences(self, text: str) -> str:
        """
        Collapse immediate duplicate sentences.

        Example:
            "We do X. We do X. Then Y." -> "We do X. Then Y."
        """
        if not text:
            return text

        # Step: Split into sentence-like parts while keeping punctuation boundaries.
        parts = re.split(r"(?<=[.!?])\s+", text)
        out: list[str] = []
        prev_norm: str | None = None
        for p in parts:
            s = p.strip()
            if not s:
                continue
            norm = re.sub(r"\s+", " ", s).strip().lower()
            if prev_norm is not None and norm == prev_norm:
                continue
            out.append(s)
            prev_norm = norm
        return " ".join(out)

    def _dedupe_consecutive_phrases(self, text: str) -> str:
        """
        Remove immediate repeated word-phrases inside a line.

        This targets yt-dlp/VTT artifacts where a phrase repeats back-to-back:
            "this is important this is important this is important" -> "this is important"
        """
        if not text:
            return text

        words = text.split()
        if len(words) < 6:
            return text

        out: list[str] = []
        i = 0
        # Step: Consider phrases between 3 and 12 words, preferring longer matches first.
        min_n = 3
        max_n = 12

        while i < len(words):
            matched = False

            # Step: Try to find the longest immediate repetition starting at i.
            for n in range(min(max_n, len(words) - i), min_n - 1, -1):
                a = words[i : i + n]
                j = i + n
                repeat_count = 0
                while j + n <= len(words) and words[j : j + n] == a:
                    repeat_count += 1
                    j += n

                if repeat_count > 0:
                    # Keep only one instance of the phrase, skip the immediate repeats.
                    out.extend(a)
                    i = j
                    matched = True
                    break

            if not matched:
                out.append(words[i])
                i += 1

        return " ".join(out)

    def _is_sentence_end(self, token: str) -> bool:
        """
        Detect sentence boundaries at the word level.

        Steps:
            1. Strip closing quotes/brackets.
            2. Check trailing punctuation for `.`, `?`, or `!`.
        """
        stripped = token.rstrip(")]}\"'”’")
        return stripped.endswith((".", "?", "!"))


def run_transcript_agent_placeholder() -> None:
    """Backward-compatible placeholder kept for older imports; not used in Part 2."""
    return None
