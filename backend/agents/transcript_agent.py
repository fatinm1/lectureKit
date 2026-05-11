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
import json
import logging
import os
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

logger = logging.getLogger(__name__)


class TranscriptAgentError(Exception):
    """Base class for TranscriptAgent failures."""


class TranscriptFetchTimeoutError(TranscriptAgentError):
    """Raised when transcript retrieval exceeds the configured timeout."""


class TranscriptUnavailableError(TranscriptAgentError):
    """Raised when a transcript cannot be retrieved (disabled/missing/unavailable)."""


class _SupadataRawError(Exception):
    """
    Internal: raw Supadata/API diagnostic text before user-friendly mapping.

    Used so is_terminal_error() can match upstream wording (e.g. live stream, private).
    """

    __slots__ = ("raw_text",)

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        super().__init__(raw_text)


USER_FRIENDLY_MSG_LIVESTREAM = (
    "This video is a live stream or premiere. LectureKit requires a recorded lecture with captions available."
)
USER_FRIENDLY_MSG_PRIVATE = (
    "This video is private or unavailable. Please use a public YouTube lecture URL."
)
USER_FRIENDLY_MSG_NO_TRANSCRIPT = (
    "No transcript found for this video. Make sure the video has captions enabled and is a recorded lecture, "
    "not a livestream."
)
USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC = (
    "Could not retrieve transcript for this video. Please try a different public YouTube lecture URL."
)

TERMINAL_ERROR_KEYWORDS = (
    "live stream",
    "livestream",
    "premiere",
    "is live",
    "private",
    "unavailable",
    "does not exist",
    "invalid youtube video id",
    "sign in",
    "age-restricted",
    "members only",
    "video unavailable",
    "not available",
)


def is_terminal_error(message: str) -> bool:
    msg_lower = message.lower()
    return any(keyword in msg_lower for keyword in TERMINAL_ERROR_KEYWORDS)


def user_friendly_transcript_failure_message(
    detail: str | None = None,
    *more_details: str,
    exc: BaseException | None = None,
) -> str:
    """
    Map internal transcript errors to a small set of user-facing strings.

    Order: livestream / premiere → private / unavailable → missing captions → generic.
    """
    parts: list[str] = []
    if detail and detail.strip():
        parts.append(detail.strip())
    for d in more_details:
        if d and d.strip():
            parts.append(d.strip())
    if exc is not None:
        cur: BaseException | None = exc
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            parts.append(str(cur))
            cur = cur.__cause__

    combined = " ".join(parts).lower()

    if "premiere" in combined or "is live" in combined or "live" in combined:
        return USER_FRIENDLY_MSG_LIVESTREAM
    if (
        "private" in combined
        or "unavailable" in combined
        or "does not exist" in combined
        or "sign in" in combined
        or "age-restricted" in combined
        or "age restricted" in combined
        or "members only" in combined
        or "video unavailable" in combined
        or "not available" in combined
    ):
        return USER_FRIENDLY_MSG_PRIVATE
    if "no transcript" in combined or "subtitles" in combined or "captions" in combined:
        return USER_FRIENDLY_MSG_NO_TRANSCRIPT
    return USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC


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

    def _cookie_file_candidates(self) -> list[str]:
        """Ordered paths for Netscape cookies (Railway may write to /tmp via YOUTUBE_COOKIES_BASE64)."""
        paths: list[str] = []
        for key in ("YTDLP_COOKIE_FILE", "YOUTUBE_COOKIES_PATH", "COOKIES_PATH"):
            raw = (os.getenv(key) or "").strip()
            if raw:
                paths.append(raw)
        paths.extend(("/tmp/cookies.txt", "/data/cookies.txt"))
        return paths

    def _cookie_file_path(self) -> str | None:
        """
        First existing cookies file among env-configured paths and Railway defaults
        (/tmp/cookies.txt, /data/cookies.txt).
        """
        for path in self._cookie_file_candidates():
            if path and os.path.isfile(path):
                return path
        return None

    def _youtube_transcript_proxy_url_candidates(self) -> list[str | None]:
        """
        Ordered proxy URLs for youtube-transcript-api rotation (Webshare, etc.).

        Sources (deduped, first wins): YOUTUBE_PROXY_URL, YOUTUBE_PROXY_URL_LIST
        (comma-separated or JSON array), YOUTUBE_PROXY_URL_1 … YOUTUBE_PROXY_URL_10.
        Empty configuration → [None] (direct connection once).
        """
        urls: list[str] = []
        seen: set[str] = set()

        def add(raw: str) -> None:
            u = raw.strip()
            if not u or u in seen:
                return
            seen.add(u)
            urls.append(u)

        single = (os.getenv("YOUTUBE_PROXY_URL") or "").strip()
        if single:
            add(single)

        raw_list = (os.getenv("YOUTUBE_PROXY_URL_LIST") or "").strip()
        if raw_list:
            try:
                parsed = json.loads(raw_list)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str):
                            add(item)
                elif isinstance(parsed, str):
                    add(parsed)
            except json.JSONDecodeError:
                for part in raw_list.split(","):
                    add(part)

        for i in range(1, 11):
            p = (os.getenv(f"YOUTUBE_PROXY_URL_{i}") or "").strip()
            if p:
                add(p)

        # Always include a final direct attempt as last resort
        urls.append(None)
        return urls

    def _first_configured_proxy_url(self) -> str | None:
        """First non-empty proxy URL for consumers that only support a single proxy (e.g. yt-dlp)."""
        for u in self._youtube_transcript_proxy_url_candidates():
            if u:
                return u
        return None

    def _get_proxy_list(self) -> list[str | None]:
        """Compatibility helper: ordered proxy list; None means no proxy."""
        return self._youtube_transcript_proxy_url_candidates()

    def _fetch_via_supadata(self, video_id: str) -> list[dict]:
        """
        Fetch transcript via Supadata API.
        Primary method for cloud deployments where YouTube blocks direct access.

        Args:
            video_id: YouTube video ID

        Returns:
            List of transcript entries with text, start, duration

        Raises:
            _SupadataRawError: Recoverable upstream failure (caller maps terminal vs fallback).
            TranscriptFetchTimeoutError: If the HTTP request times out.
        """
        api_key = (os.getenv("SUPADATA_API_KEY") or "").strip()
        if not api_key:
            raise _SupadataRawError("Transcript provider API key is not configured")

        url = "https://api.supadata.ai/v1/youtube/transcript"
        params = {"videoId": video_id, "text": "false"}
        headers = {"x-api-key": api_key}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)

            if response.status_code == 404:
                raise _SupadataRawError(response.text[:800] if response.text else "HTTP 404 transcript request")
            if response.status_code == 401:
                raise _SupadataRawError(response.text[:400] if response.text else "HTTP 401 unauthorized")
            if response.status_code != 200:
                body = response.text[:800] if response.text else ""
                raise _SupadataRawError(body or f"HTTP {response.status_code} transcript request")

            try:
                data = response.json()
            except ValueError as exc:
                snippet = (response.text or "")[:400]
                raise _SupadataRawError(f"Non-JSON transcript response: {snippet}") from exc

            content = data.get("content", [])
            if not content:
                raise _SupadataRawError("Transcript response contained no content array entries")

            entries: list[dict] = []
            for segment in content:
                text = (segment.get("text") or "").strip()
                if not text:
                    continue
                entries.append(
                    {
                        "text": text,
                        "start": (segment.get("offset", 0) or 0) / 1000.0,
                        "duration": (segment.get("duration", 5000) or 5000) / 1000.0,
                    }
                )

            if not entries:
                raise _SupadataRawError("Transcript response had no usable text segments after parsing")

            print(f"Supadata succeeded: {len(entries)} segments for video {video_id}")
            return entries

        except _SupadataRawError:
            raise
        except requests.exceptions.Timeout as exc:
            raise TranscriptFetchTimeoutError(USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC) from exc
        except requests.exceptions.RequestException as exc:
            raise _SupadataRawError(str(exc)) from exc
        except Exception as exc:
            raise _SupadataRawError(str(exc)) from exc

    def _transcript_proxies(self) -> dict[str, str] | None:
        """
        Optional HTTP(S) proxies for transcript fetches (youtube-transcript-api, yt-dlp, caption HTTP GET).

        Priority:
        1. First URL from _youtube_transcript_proxy_url_candidates() (YOUTUBE_PROXY_URL + list + numbered vars)
        2. YOUTUBE_TRANSCRIPT_PROXIES — JSON {\"http\":\"...\",\"https\":\"...\"} or one URL string
        3. HTTPS_PROXY / HTTP_PROXY
        """
        first = self._first_configured_proxy_url()
        if first:
            return {"http": first, "https": first}

        raw = (os.getenv("YOUTUBE_TRANSCRIPT_PROXIES") or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed:
                    return {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                pass
            if raw.startswith("http"):
                return {"http": raw, "https": raw}
        https_p = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
        http_p = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
        chosen = https_p or http_p
        if chosen:
            return {"http": chosen, "https": chosen}
        return None

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

        # Fail fast: legitimate YouTube IDs are exactly 11 chars [A-Za-z0-9_-]; no network until this passes.
        if not re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
            raise InvalidYouTubeUrlError(
                "Invalid YouTube video ID. Please use a public YouTube lecture URL with a complete watch or youtu.be link."
            )

        # Step: Fetch transcript with a timeout so network stalls don’t hang the API.
        entries = self._fetch_transcript_entries(video_id)

        # Step: Convert to word-level tokens with approximate per-word timestamps.
        word_times = self._entries_to_word_times(entries)

        # Step: Chunk tokens into ~500 word blocks without cutting mid-sentence when possible.
        chunks = self._chunk_word_times(word_times)

        return video_id, chunks

    def _fetch_transcript_entries(self, video_id: str) -> list[dict]:
        """
        Retrieve transcript entries (datacenter / bot mitigation).

        Order:
        1. youtube-transcript-api get_transcript — try each configured proxy in sequence
           (YOUTUBE_PROXY_URL, YOUTUBE_PROXY_URL_LIST, YOUTUBE_PROXY_URL_1…); optional cookies file.
           With no proxy env vars, tries direct once ([None]).
        2. Same proxy rotation with list_transcripts + fetch.
        3. Caption fallback via metadata + VTT download with optional network configuration.
        4. On total failure, raise TranscriptUnavailableError with a user-facing message (no internal tool names).

        Args:
            video_id: YouTube video ID.

        Returns:
            List of transcript entries (dicts with `text`, `start`, `duration`).
        """
        # Try Supadata first (if configured). They handle bot detection upstream.
        supadata_key = (os.getenv("SUPADATA_API_KEY") or "").strip()
        if supadata_key:
            try:
                print(f"Trying Supadata API for video: {video_id}")
                return self._fetch_via_supadata(video_id)
            except TranscriptFetchTimeoutError:
                print("Supadata timed out, falling back to direct methods")
            except _SupadataRawError as exc:
                raw_error = exc.raw_text
                if is_terminal_error(raw_error):
                    raise TranscriptUnavailableError(
                        user_friendly_transcript_failure_message(detail=raw_error)
                    ) from exc
                logger.warning("Supadata failed with non-terminal error: %s", raw_error[:500])
                print(f"Supadata failed (non-terminal): {raw_error[:100]}...")
            except Exception as exc:
                raw_error = str(exc)
                if is_terminal_error(raw_error):
                    raise TranscriptUnavailableError(
                        user_friendly_transcript_failure_message(detail=raw_error)
                    ) from exc
                logger.warning("Supadata failed with non-terminal error: %s", raw_error[:500])
                print(f"Supadata failed (non-terminal): {raw_error[:100]}...")

        cookies_path = self._cookie_file_path()
        proxy_url_candidates = self._get_proxy_list()

        def _run_with_timeout(fn):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn)
                return future.result(timeout=self._fetch_timeout_s)

        last_exc: BaseException | None = None

        for proxy_url in proxy_url_candidates:
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            try:
                print(f"Trying transcript fetch with proxy: {proxy_url or 'none'}")
                return _run_with_timeout(
                    lambda p=proxies: YouTubeTranscriptApi.get_transcript(
                        video_id,
                        ("en", "en-US", "en-GB", "a.en"),
                        proxies=p,
                        cookies=cookies_path,
                    )
                )
            except concurrent.futures.TimeoutError as exc:
                last_exc = exc
                continue
            except VideoUnavailable as exc:
                raise TranscriptUnavailableError(USER_FRIENDLY_MSG_PRIVATE) from exc
            except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript, ParseError) as exc:
                last_exc = exc
                continue
            except TranscriptUnavailableError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                continue

        for proxy_url in proxy_url_candidates:
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
            try:
                return _run_with_timeout(
                    lambda p=proxies: self._youtube_api_list_transcripts_fetch(video_id, p, cookies_path)
                )
            except concurrent.futures.TimeoutError as exc:
                last_exc = exc
                continue
            except VideoUnavailable as exc:
                raise TranscriptUnavailableError(USER_FRIENDLY_MSG_PRIVATE) from exc
            except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript, ParseError) as exc:
                last_exc = exc
                continue
            except TranscriptUnavailableError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                continue

        # yt-dlp fallback: try per-proxy too (use same proxy for metadata + VTT download)
        for proxy_url in proxy_url_candidates:
            ytdlp_steps = [
                lambda u=proxy_url: self._ytdlp_fetch_transcript_entries(
                    video_id, nocheckcertificate=False, proxy_url=u
                ),
                lambda u=proxy_url: self._ytdlp_fetch_transcript_entries(
                    video_id, nocheckcertificate=True, proxy_url=u
                ),
            ]
            for fn in ytdlp_steps:
                try:
                    return _run_with_timeout(fn)
                except concurrent.futures.TimeoutError as exc:
                    last_exc = exc
                    continue
                except VideoUnavailable as exc:
                    raise TranscriptUnavailableError(USER_FRIENDLY_MSG_PRIVATE) from exc
                except (TranscriptsDisabled, NoTranscriptFound) as exc:
                    last_exc = exc
                    continue
                except (CouldNotRetrieveTranscript, ParseError, TranscriptUnavailableError) as exc:
                    last_exc = exc
                    continue
                except Exception as exc:
                    last_exc = exc
                    continue

        if last_exc is not None:
            if isinstance(last_exc, TranscriptUnavailableError):
                raise TranscriptUnavailableError(str(last_exc)) from last_exc
            if isinstance(last_exc, concurrent.futures.TimeoutError):
                raise TranscriptFetchTimeoutError(USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC) from last_exc
            if isinstance(last_exc, (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript)):
                mapped = user_friendly_transcript_failure_message(exc=last_exc)
                if mapped in (USER_FRIENDLY_MSG_LIVESTREAM, USER_FRIENDLY_MSG_PRIVATE):
                    raise TranscriptUnavailableError(mapped) from last_exc
                raise TranscriptUnavailableError(USER_FRIENDLY_MSG_NO_TRANSCRIPT) from last_exc
            if isinstance(last_exc, ParseError):
                raise TranscriptUnavailableError(user_friendly_transcript_failure_message(exc=last_exc)) from last_exc
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(exc=last_exc)) from last_exc
        raise TranscriptUnavailableError(USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC)

    def _youtube_api_get_transcript(
        self,
        video_id: str,
        proxies: dict[str, str] | None,
        cookies_path: str | None,
    ) -> list[dict]:
        """youtube-transcript-api: get_transcript with optional proxies and Netscape cookies file."""
        return YouTubeTranscriptApi.get_transcript(
            video_id,
            ("en", "en-US", "en-GB"),
            proxies=proxies,
            cookies=cookies_path,
        )

    def _youtube_api_list_transcripts_fetch(
        self,
        video_id: str,
        proxies: dict[str, str] | None,
        cookies_path: str | None,
    ) -> list[dict]:
        """youtube-transcript-api: list_transcripts then find_transcript / first available."""
        kwargs: dict = {}
        if proxies:
            kwargs["proxies"] = proxies
        if cookies_path:
            kwargs["cookies"] = cookies_path
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, **kwargs)
        try:
            transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
        except Exception:
            try:
                transcript = next(iter(transcript_list))
            except StopIteration as exc:
                raise TranscriptUnavailableError(USER_FRIENDLY_MSG_NO_TRANSCRIPT) from exc
        return transcript.fetch()

    def _build_ytdlp_opts(self, *, nocheckcertificate: bool) -> dict:
        """
        yt-dlp options tuned for caption extraction without downloading video.

        Optional env (see README): YOUTUBE_PROXY_URL, YOUTUBE_PO_TOKEN, YOUTUBE_VISITOR_DATA,
        YTDLP_COOKIE_FILE / cookie path vars for a minimal cookies.txt on disk.
        """
        youtube_extras: dict[str, object] = {
            "skip": ["dash", "hls"],
            "player_skip": ["webpage", "configs", "js"],
        }
        po_token = (os.getenv("YOUTUBE_PO_TOKEN") or "").strip()
        if po_token:
            # yt-dlp expects iterable values; format e.g. web.gvs+BASE64... (see yt-dlp PO Token guide).
            youtube_extras["po_token"] = [po_token]
        visitor_data = (os.getenv("YOUTUBE_VISITOR_DATA") or "").strip()
        if visitor_data:
            youtube_extras["visitor_data"] = [visitor_data]

        opts: dict = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {"youtube": youtube_extras},
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        }
        if nocheckcertificate:
            opts["nocheckcertificate"] = True

        proxy_url = self._first_configured_proxy_url()
        if proxy_url:
            opts["proxy"] = proxy_url

        cookie_path = self._cookie_file_path()
        if cookie_path:
            opts["cookiefile"] = cookie_path
            print(f"yt-dlp using cookies from: {cookie_path}")

        return opts

    def _ytdlp_fetch_transcript_entries(
        self, video_id: str, *, nocheckcertificate: bool, proxy_url: str | None = None
    ) -> list[dict]:
        """
        Fetch captions via yt-dlp metadata + HTTP download of VTT URL.

        Raises:
            TranscriptUnavailableError: On failure to obtain usable cues.
        """
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = self._build_ytdlp_opts(nocheckcertificate=nocheckcertificate)
        if proxy_url:
            ydl_opts["proxy"] = proxy_url

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except DownloadError as exc:
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(exc=exc)) from exc
        except Exception as exc:
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(exc=exc)) from exc

        subtitles = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        captions_source = subtitles if subtitles else auto
        if not captions_source:
            raise TranscriptUnavailableError(USER_FRIENDLY_MSG_NO_TRANSCRIPT)

        lang = "en" if "en" in captions_source else next(iter(captions_source.keys()))
        formats = captions_source.get(lang) or []
        if not formats:
            raise TranscriptUnavailableError(USER_FRIENDLY_MSG_NO_TRANSCRIPT)

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
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(detail=ext))

        try:
            resp = requests.get(
                sub_url,
                timeout=self._fetch_timeout_s,
                proxies={"http": proxy_url, "https": proxy_url} if proxy_url else self._transcript_proxies(),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            resp.raise_for_status()
            data = resp.text
        except requests.Timeout as exc:
            raise TranscriptFetchTimeoutError(USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC) from exc
        except Exception as exc:
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(exc=exc)) from exc

        if ext == "vtt" or data.lstrip().startswith("WEBVTT"):
            entries = self._parse_vtt_to_entries(data)
        else:
            raise TranscriptUnavailableError(user_friendly_transcript_failure_message(detail=ext))

        if not entries:
            raise TranscriptUnavailableError(USER_FRIENDLY_MSG_NO_TRANSCRIPT)

        return entries

    def _parse_vtt(self, vtt_content: str) -> list[dict]:
        """Compatibility helper for VTT parsing used by some deployment recipes."""
        return self._parse_vtt_to_entries(vtt_content)

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
