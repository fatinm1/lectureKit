"""
Purpose: Translation helper for bilingual Study Dashboard (Part 6).

Responsibilities:
- Accept a JSON-serializable content object and a target language
- Use the Anthropic Claude API to translate text fields in one call
- Return ONLY valid JSON with the exact same structure as the input
- Do not translate timestamps / numeric fields
- Retry once if JSON is malformed

Data flow:
frontend language selector -> POST /translate -> TranslateAgent -> translated JSON -> UI state (cached per language)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

import anthropic


class TranslateAgentError(Exception):
    """Raised for any TranslateAgent failure with a clear descriptive message."""


class TranslateAgent:
    """
    Translate structured study materials to a target language.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 16000,
    ) -> None:
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            raise TranslateAgentError(
                "Missing ANTHROPIC_API_KEY. Set it in backend/.env and restart the server."
            )

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = (model or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
        self._max_tokens = max_tokens

    def translate(self, *, content: Dict[str, Any], target_language: str) -> Dict[str, Any]:
        """
        Translate the given content object into the target language.
        """
        if not target_language or not target_language.strip():
            raise TranslateAgentError("target_language must be a non-empty string.")

        target = target_language.strip()

        # Attempt 1: single-call translation (fast path).
        try:
            prompt = self._build_prompt(content=content, target_language=target)
            raw = self._call_claude(prompt)
            return self._parse_json_with_retry(raw, content=content, target_language=target)
        except Exception:
            # Attempt 2 (fallback): split into two calls to reduce output size and avoid truncation.
            return self._translate_split(content=content, target_language=target)

    def _translate_split(self, *, content: Dict[str, Any], target_language: str) -> Dict[str, Any]:
        """
        Fallback strategy: translate (outline+flashcards) and (summaries) separately, then merge.
        """
        content_part1: Dict[str, Any] = {
            "outline": content.get("outline"),
            "flashcards": content.get("flashcards"),
        }
        content_part2: Dict[str, Any] = {
            "summary_90s": content.get("summary_90s"),
            "summary_5min": content.get("summary_5min"),
            "summary_full": content.get("summary_full"),
        }

        prompt1 = self._build_prompt(content=content_part1, target_language=target_language)
        raw1 = self._call_claude(prompt1)
        res1 = self._parse_json_with_retry(raw1, content=content_part1, target_language=target_language)

        prompt2 = self._build_prompt(content=content_part2, target_language=target_language)
        raw2 = self._call_claude(prompt2)
        res2 = self._parse_json_with_retry(raw2, content=content_part2, target_language=target_language)

        merged: Dict[str, Any] = {}
        merged.update(res1 if isinstance(res1, dict) else {})
        merged.update(res2 if isinstance(res2, dict) else {})
        return merged

    def _build_prompt(self, *, content: Dict[str, Any], target_language: str) -> str:
        payload = json.dumps(content, ensure_ascii=False)
        return (
            f"Translate the following study materials to {target_language}.\n"
            "Return ONLY valid JSON with the exact same structure as the input.\n"
            "Do not translate timestamps or numeric fields (e.g. timestamp, source_timestamp, start, end, chunk_index, word_count, relevance_score).\n"
            "Do not add any explanation.\n"
            "Do not translate proper nouns like names of people or programming languages.\n\n"
            f"{payload}"
        )

    def _call_claude(self, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            if type(exc).__name__ == "NotFoundError" and self._model != "claude-sonnet-4-6":
                response = self._client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=self._max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                raise TranslateAgentError(f"Claude API call failed: {type(exc).__name__}") from exc

        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()

    def _parse_json_with_retry(
        self, raw_text: str, *, content: Dict[str, Any], target_language: str
    ) -> Dict[str, Any]:
        try:
            return self._parse_json_response(raw_text)
        except Exception:
            repair_prompt = (
                f"You returned invalid JSON. Fix it.\n"
                f"Return ONLY valid JSON with the same structure.\n"
                f"Target language: {target_language}\n\n"
                f"INPUT JSON:\n{json.dumps(content, ensure_ascii=False)}\n\n"
                f"INVALID OUTPUT:\n{raw_text}\n"
            )
            repaired = self._call_claude(repair_prompt)
            try:
                return self._parse_json_response(repaired)
            except Exception as exc:
                raise TranslateAgentError(
                    "Claude returned malformed JSON after one repair retry. Raw response:\n" + raw_text
                ) from exc

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from Claude response with multiple fallback strategies.

        Claude sometimes wraps JSON in markdown fences, adds preamble text,
        or includes trailing explanation. This handles all those cases.
        """
        raw = text or ""

        # Strategy 1: Aggressive markdown fence removal then parse
        cleaned = re.sub(r"```[a-zA-Z]*\n?", "", raw)
        cleaned = cleaned.replace("```", "")
        cleaned = cleaned.strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            raise TranslateAgentError("Claude returned JSON but not an object.")
        except json.JSONDecodeError:
            pass

        # Strategy 2: Find the outermost JSON object by locating first { and last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
                raise TranslateAgentError("Claude returned JSON but not an object.")
            except json.JSONDecodeError:
                pass

        # Strategy 3: Try original text (no cleaning) then parse
        try:
            parsed = json.loads(raw.strip())
            if isinstance(parsed, dict):
                return parsed
            raise TranslateAgentError("Claude returned JSON but not an object.")
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
                raise TranslateAgentError("Claude returned JSON but not an object.")
            except json.JSONDecodeError:
                pass

        raise TranslateAgentError(
            "Could not parse JSON after all strategies. "
            f"First 300 chars of response: {raw[:300]}"
        )

