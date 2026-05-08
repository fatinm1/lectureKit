from __future__ import annotations

import json
import os
import re
from typing import Sequence

import anthropic

from models.schemas import TranscriptChunk


class FacultyAgentError(Exception):
    pass


class FacultyAgent:
    def __init__(self) -> None:
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            raise FacultyAgentError("Missing ANTHROPIC_API_KEY")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

    def generate_report(self, chunks: Sequence[TranscriptChunk], video_id: str) -> dict:
        transcript_text = self._format_transcript(chunks)
        prompt = self._build_prompt(transcript_text=transcript_text, video_id=video_id)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        raw = "\n".join(parts).strip()
        return self._parse_json_response(raw)

    def _format_transcript(self, chunks: Sequence[TranscriptChunk]) -> str:
        lines: list[str] = []
        total_words = 0
        max_words = 6000

        for chunk in chunks:
            start = float(getattr(chunk, "start", 0.0) or 0.0)
            minutes = int(start // 60)
            seconds = int(start % 60)
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            text = (getattr(chunk, "text", "") or "").strip()
            words = len(text.split())

            if total_words + words > max_words:
                break

            lines.append(f"{timestamp} {text}")
            total_words += words

        return "\n".join(lines)

    def _build_prompt(self, *, transcript_text: str, video_id: str) -> str:
        return f"""You are an expert pedagogical reviewer analyzing a lecture transcript for a faculty member. This report is PRIVATE and only for the faculty member — it is not surveillance. Be constructive, specific, and actionable.

IMPORTANT: Respond entirely in English regardless of the language of the transcript.

Analyze this lecture transcript and produce a structured audit report in JSON format.

VIDEO_ID: {video_id}

TRANSCRIPT:
{transcript_text}

Respond ONLY with valid JSON — no markdown fences, no preamble. Use this exact structure:

{{
  "overall_score": <integer 1-10>,
  "top_priority_fix": {{
    "title": "<single most important change>",
    "description": "<specific actionable description>",
    "timestamp": <seconds as float>,
    "suggested_rewrite": "<exact suggested replacement text>"
  }},
  "pedagogical": {{
    "score": <integer 1-10>,
    "summary": "<2-3 sentence assessment>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "issues": [
      {{
        "description": "<issue description>",
        "timestamp": <seconds as float>,
        "suggested_rewrite": "<specific suggested fix>"
      }}
    ]
  }},
  "accessibility": {{
    "score": <integer 1-10>,
    "summary": "<2-3 sentence assessment>",
    "strengths": ["<strength 1>"],
    "issues": [
      {{
        "description": "<issue description>",
        "timestamp": <seconds as float>,
        "suggested_rewrite": "<specific suggested fix>"
      }}
    ]
  }},
  "equity": {{
    "score": <integer 1-10>,
    "summary": "<2-3 sentence assessment>",
    "strengths": ["<strength 1>"],
    "issues": [
      {{
        "description": "<issue description>",
        "timestamp": <seconds as float>,
        "suggested_rewrite": "<specific suggested fix>"
      }}
    ]
  }},
  "clarity": {{
    "score": <integer 1-10>,
    "summary": "<2-3 sentence assessment>",
    "strengths": ["<strength 1>"],
    "issues": [
      {{
        "description": "<issue description>",
        "timestamp": <seconds as float>,
        "suggested_rewrite": "<specific suggested fix>"
      }}
    ]
  }},
  "prioritized_fixes": [
    {{
      "priority": <integer 1-5>,
      "category": "<pedagogical|accessibility|equity|clarity>",
      "title": "<short title>",
      "description": "<specific actionable fix>",
      "timestamp": <seconds as float>,
      "suggested_rewrite": "<exact suggested replacement text>"
    }}
  ]
}}

Rules:
- All timestamps must reference real moments in the transcript
- suggested_rewrite must be specific and usable, not vague advice
- prioritized_fixes must have exactly 5 items ordered by impact
- top_priority_fix is the single most impactful change the faculty member could make
- Be honest but constructive — this is to help the faculty member improve"""

    def _parse_json_response(self, text: str) -> dict:
        cleaned = re.sub(r"```[a-zA-Z]*\r?\n?", "", text or "")
        cleaned = cleaned.replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise FacultyAgentError(
            f"Could not parse faculty report JSON. First 200 chars: {(text or '')[:200]}"
        )

