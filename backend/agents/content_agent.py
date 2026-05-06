"""
Purpose: Agent 2 — Content Agent (chunks → outline, summaries, flashcards).

Part 3: Production implementation using the Anthropic SDK directly (no LangChain).

Responsibilities:
- Accept a list of TranscriptChunk objects (Agent 1 output)
- Build a single timestamped transcript string for context
- Make one Claude call that returns ALL study materials in a single JSON payload
- Parse JSON with one repair retry when malformed

Data flow:
FastAPI `/process` → TranscriptAgent → ContentAgent → API response → frontend.

Data flow: Consumes Transcript Agent output; returns outline/summaries/cards.
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Sequence

import anthropic

from models.schemas import ContentAgentResult, TranscriptChunk


class ContentAgentError(Exception):
    """Raised for any ContentAgent failure with a clear descriptive message."""


class ContentAgent:
    """
    Agent 2 — generates outline, summaries, and flashcards from transcript chunks.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 4000,
    ) -> None:
        """
        Create a ContentAgent with a single shared Anthropic client.

        Args:
            model: Claude model identifier.
            max_tokens: Maximum tokens for Claude output.

        Steps:
            1. Read ANTHROPIC_API_KEY from env and fail early if missing.
            2. Create a single Anthropic client instance for reuse across requests.
        """
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            raise ContentAgentError(
                "Missing ANTHROPIC_API_KEY. Set it in backend/.env and restart the server."
            )

        self._client = anthropic.Anthropic(api_key=api_key)
        # Step: Prefer explicit arg; otherwise allow env override; otherwise use a safe default.
        # Note: Some older model IDs are deprecated and may return NotFoundError.
        self._model = (model or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
        self._max_tokens = max_tokens

    def process(self, chunks: Sequence[TranscriptChunk]) -> ContentAgentResult:
        """
        Generate study materials from transcript chunks in one Claude call.

        Args:
            chunks: TranscriptChunk list produced by TranscriptAgent.

        Returns:
            ContentAgentResult with outline, summaries, and exactly 10 flashcards.

        Steps:
            1. Build timestamped transcript context from chunks.
            2. Call Claude once to generate the full JSON payload.
            3. Parse JSON, and if malformed, retry once with a repair prompt.
        """
        if not chunks:
            raise ContentAgentError("ContentAgent received no transcript chunks.")

        transcript = self._format_timestamped_transcript(chunks)
        prompt = self._build_generation_prompt(transcript)

        raw_text = self._call_claude(prompt)
        parsed = self._parse_json_with_retry(raw_text, transcript=transcript)

        try:
            return ContentAgentResult.model_validate(parsed)
        except Exception as exc:
            raise ContentAgentError(
                "Claude returned JSON but it did not match the expected schema."
            ) from exc

    def _format_timestamped_transcript(self, chunks: Sequence[TranscriptChunk]) -> str:
        """
        Format chunks into a single string with timestamp markers.

        Format:
            [timestamp: Xs] chunk_text

        Args:
            chunks: TranscriptChunk list.

        Returns:
            Single transcript string for prompting.
        """
        lines: List[str] = []
        for chunk in chunks:
            # Step: Use chunk.start to anchor chronological references.
            lines.append(f"[timestamp: {chunk.start:.2f}s] {chunk.text}")
        return "\n".join(lines)

    def _build_generation_prompt(self, transcript: str) -> str:
        """
        Build the Claude prompt that requests strict JSON output.

        Args:
            transcript: Timestamped transcript string.

        Returns:
            Prompt string.
        """
        return (
            "You are a study-material generation engine.\n"
            "You will be given a lecture transcript with timestamps.\n\n"
            "CRITICAL OUTPUT RULES:\n"
            "- Respond with ONLY valid JSON.\n"
            "- No markdown, no backticks, no explanations, no preamble.\n\n"
            "Transcript (timestamped):\n"
            f"{transcript}\n\n"
            "Return JSON with EXACTLY this structure:\n"
            "{\n"
            '  \"outline\": [\n'
            "    {\n"
            '      \"timestamp\": 0.0,\n'
            '      \"title\": \"Topic title here\",\n'
            '      \"description\": \"One sentence description\"\n'
            "    }\n"
            "  ],\n"
            '  \"summary_90s\": \"2 to 3 sentence summary of the single most important idea\",\n'
            '  \"summary_5min\": \"3 to 4 paragraph summary covering all main topics\",\n'
            '  \"summary_full\": \"Comprehensive paragraph by paragraph summary of the entire lecture\",\n'
            '  \"flashcards\": [\n'
            "    {\n"
            '      \"question\": \"Question testing understanding not just recall\",\n'
            '      \"answer\": \"2 to 4 sentence answer\",\n'
            '      \"source_timestamp\": 0.0\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Requirements:\n"
            "- outline: 5 to 8 main topics, chronological order, each has timestamp (seconds), title, and 1-sentence description.\n"
            "- summary_90s: 2 to 3 sentences only AND under 100 words.\n"
            "- summary_5min: 3 to 4 full paragraphs AND between 200 and 600 words.\n"
            "- summary_full: one paragraph per major topic, comprehensive AND at least 450 words.\n"
            "- flashcards: EXACTLY 10. Questions test understanding/application. Answers 2 to 4 sentences. Spread across lecture.\n"
            "- Each flashcard source_timestamp must point to where it appears in the transcript. If timestamps are sparse, choose diverse timestamps within the covered ranges.\n"
            "- Before returning the final JSON, verify your own word counts satisfy the constraints.\n"
        )

    def _call_claude(self, prompt: str) -> str:
        """
        Execute a single Claude API call and return the text output.

        Args:
            prompt: User prompt content.

        Returns:
            Plain text content from Claude.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            # Step: If a model has been deprecated/retired, Anthropic returns a NotFoundError.
            # We retry once with a known-current default to keep the pipeline reliable.
            if type(exc).__name__ == "NotFoundError" and self._model != "claude-sonnet-4-6":
                try:
                    response = self._client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=self._max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                except Exception as exc2:
                    raise ContentAgentError(
                        f"Claude API call failed: {type(exc2).__name__}"
                    ) from exc2
            else:
                raise ContentAgentError(f"Claude API call failed: {type(exc).__name__}") from exc

        # Step: Anthropic returns a list of content blocks; concatenate text blocks defensively.
        parts: List[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)

        return "\n".join(parts).strip()

    def _parse_json_with_retry(self, raw_text: str, *, transcript: str) -> dict:
        """
        Parse Claude JSON, with one repair retry if malformed.

        Steps:
            1. Strip common markdown fences/backticks.
            2. Attempt json.loads.
            3. If it fails, ask Claude once to output corrected JSON only.
            4. If it fails again, raise ContentAgentError with raw response.
        """
        try:
            return self._parse_json_response(raw_text)
        except Exception:
            repair_prompt = self._build_repair_prompt(transcript=transcript, bad_output=raw_text)
            repaired_text = self._call_claude(repair_prompt)
            try:
                return self._parse_json_response(repaired_text)
            except Exception as exc:
                raise ContentAgentError(
                    "Claude returned malformed JSON after one repair retry. Raw response:\n"
                    + raw_text
                ) from exc

    def _parse_json_response(self, text: str) -> dict:
        """
        Parse JSON from Claude response with multiple fallback strategies.

        Claude sometimes wraps JSON in markdown fences, adds preamble text,
        or includes trailing explanation. This handles all those cases.
        """
        raw = text or ""

        # Strategy 1: Aggressive markdown fence removal then parse
        cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw)
        cleaned = cleaned.replace("```", "")
        cleaned = cleaned.strip().strip("` \n\t")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Find the outermost JSON object by locating first { and last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass

        # Strategy 3: Try original text (no cleaning) then parse
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ContentAgentError(
            "Could not parse JSON after all strategies. "
            f"First 300 chars of response: {raw[:300]}"
        )

    def _build_repair_prompt(self, *, transcript: str, bad_output: str) -> str:
        """
        Build a minimal prompt asking Claude to fix JSON formatting only.
        """
        return (
            "You previously attempted to return JSON but it was invalid.\n"
            "Return ONLY valid JSON (no markdown, no backticks, no commentary).\n\n"
            "Transcript (timestamped):\n"
            f"{transcript}\n\n"
            "Invalid JSON output:\n"
            f"{bad_output}\n\n"
            "Return corrected JSON now."
        )


def run_content_agent_placeholder() -> None:
    """
    Placeholder for Claude-powered content generation.

    Inputs/outputs: Defined in Part 3+; no-op in Part 1.
    """
    # Step: Reserved for LangChain + Claude invocation.
    return None
