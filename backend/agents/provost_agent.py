from __future__ import annotations

import json
import os
import re
from typing import Any

import anthropic


class ProvostAgentError(Exception):
    pass


class ProvostAgent:
    def __init__(self) -> None:
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            raise ProvostAgentError("Missing ANTHROPIC_API_KEY")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()

    def generate_curriculum_map(self, lectures: list[dict[str, Any]], learning_objectives: str) -> dict:
        combined_transcript = self._format_lectures(lectures)
        prompt = self._build_prompt(combined_transcript, learning_objectives)

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

    def _format_lectures(self, lectures: list[dict[str, Any]]) -> str:
        sections: list[str] = []
        for i, lecture in enumerate(lectures):
            sections.append(f"=== LECTURE {i + 1}: {lecture.get('video_id', '')} ===")
            chunks = lecture.get("chunks", []) or []
            total_words = 0
            max_words_per_lecture = 4000
            for chunk in chunks:
                start = float((chunk.get("start", 0) or 0) if isinstance(chunk, dict) else 0)
                minutes = int(start // 60)
                seconds = int(start % 60)
                text = (chunk.get("text", "") if isinstance(chunk, dict) else "") or ""
                words = len(str(text).split())
                if total_words + words > max_words_per_lecture:
                    break
                sections.append(f"[{minutes:02d}:{seconds:02d}] {text}")
                total_words += words
        return "\n".join(sections)

    def _build_prompt(self, transcript: str, learning_objectives: str) -> str:
        return f"""IMPORTANT: Respond entirely in English regardless of the language of the transcripts.

You are an expert curriculum analyst helping a provost understand whether a course is delivering on its stated learning objectives. Analyze the provided lecture transcripts and compare them against the stated learning objectives.

LEARNING OBJECTIVES:
{learning_objectives}

LECTURE TRANSCRIPTS:
{transcript}

Respond ONLY with valid JSON — no markdown fences, no preamble. Use this exact structure:

{{
  "overall_coverage_score": <integer 1-10>,
  "executive_summary": "<3-4 sentence summary for a provost>",
  "objectives_analysis": [
    {{
      "objective": "<the learning objective text>",
      "coverage_status": "<covered|partial|missing>",
      "coverage_score": <integer 1-10>,
      "evidence": "<specific evidence from the lectures with timestamps>",
      "lectures_covering": [<lecture numbers as integers>],
      "gaps": "<what is missing or underdeveloped>"
    }}
  ],
  "curriculum_strengths": [
    "<strength 1>",
    "<strength 2>",
    "<strength 3>"
  ],
  "critical_gaps": [
    {{
      "gap": "<description of the gap>",
      "impact": "<why this matters for student outcomes>",
      "recommendation": "<specific actionable recommendation>"
    }}
  ],
  "coverage_distribution": {{
    "fully_covered": <integer count>,
    "partially_covered": <integer count>,
    "not_covered": <integer count>
  }},
  "recommendations": [
    {{
      "priority": <integer 1-5>,
      "recommendation": "<specific actionable recommendation>",
      "rationale": "<why this matters>"
    }}
  ]
}}

Rules:
- objectives_analysis must have one entry per learning objective provided
- coverage_status must be exactly 'covered', 'partial', or 'missing'
- evidence must cite specific timestamps and lecture numbers
- recommendations must have exactly 5 items ordered by priority
- Be analytical and specific — this is for institutional decision-making"""

    def _parse_json_response(self, text: str) -> dict:
        cleaned = re.sub(r"```[a-zA-Z]*\r?\n?", "", text or "").replace("```", "").strip()
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
        raise ProvostAgentError(
            f"Could not parse provost report JSON. First 200 chars: {(text or '')[:200]}"
        )

