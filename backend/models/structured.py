"""
Purpose: Pydantic models for every structured Claude output, used two ways:

1. Their JSON Schema becomes the `input_schema` of a forced tool call, so Claude returns
   arguments that already have the right shape instead of free text we have to repair.
2. Their validators check what a schema can't: timestamps inside the lecture, coverage
   counts that add up, "covered" objectives that cite a lecture. A failed check is sent back
   to Claude once with the exact error, so it can correct itself.

Field names match frontend/types/lecture.ts, so the UI doesn't change.

Validation context (passed to model_validate(context=...)):
- max_timestamp: lecture duration in seconds; timestamps past it are rejected
- lecture_count:  number of lectures in a Provost run; lecture numbers must be 1..N
"""

from __future__ import annotations

from typing import Any, List, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from models.schemas import Flashcard, OutlineItem

TIMESTAMP_SLACK_S = 5.0  # chunk boundaries are estimated, so allow a little past the end


def _check_timestamp(value: float, info: ValidationInfo, label: str) -> float:
    ctx = info.context or {}
    max_ts = ctx.get("max_timestamp")
    if value < 0:
        raise ValueError(f"{label} must be >= 0 seconds")
    if max_ts is not None and value > float(max_ts) + TIMESTAMP_SLACK_S:
        raise ValueError(f"{label} {value:.0f}s is past the end of the lecture ({float(max_ts):.0f}s)")
    return value


# ---------- Student: outline + flashcards ----------


class StudyStructure(BaseModel):
    """Outline and flashcards for one lecture (summaries are streamed separately)."""

    outline: List[OutlineItem] = Field(
        ..., min_length=3, max_length=12, description="5 to 8 main topics in chronological order."
    )
    flashcards: List[Flashcard] = Field(
        ..., min_length=10, max_length=10, description="Exactly 10 flashcards spread across the lecture."
    )

    @model_validator(mode="after")
    def _timestamps(self, info: ValidationInfo) -> "StudyStructure":
        for i, item in enumerate(self.outline):
            _check_timestamp(item.timestamp, info, f"outline[{i}].timestamp")
        for i, card in enumerate(self.flashcards):
            _check_timestamp(card.source_timestamp, info, f"flashcards[{i}].source_timestamp")
        stamps = [o.timestamp for o in self.outline]
        if stamps != sorted(stamps):
            raise ValueError("outline must be in chronological order (timestamps ascending)")
        return self


# ---------- Faculty audit ----------


class FacultyIssue(BaseModel):
    description: str = Field(..., min_length=1)
    timestamp: float
    suggested_rewrite: str = Field(..., min_length=1)

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float, info: ValidationInfo) -> float:
        return _check_timestamp(v, info, "issue.timestamp")


class FacultyCategory(BaseModel):
    score: int = Field(..., ge=1, le=10)
    summary: str = Field(..., min_length=1, description="2-3 sentence assessment")
    strengths: List[str]
    issues: List[FacultyIssue]


class TopPriorityFix(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    timestamp: float
    suggested_rewrite: str = Field(..., min_length=1)

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float, info: ValidationInfo) -> float:
        return _check_timestamp(v, info, "top_priority_fix.timestamp")


class PrioritizedFix(BaseModel):
    priority: int = Field(..., ge=1, le=5)
    category: Literal["pedagogical", "accessibility", "equity", "clarity"]
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    timestamp: float
    suggested_rewrite: str = Field(..., min_length=1)

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float, info: ValidationInfo) -> float:
        return _check_timestamp(v, info, "prioritized_fixes.timestamp")


class FacultyReport(BaseModel):
    overall_score: int = Field(..., ge=1, le=10)
    top_priority_fix: TopPriorityFix
    pedagogical: FacultyCategory
    accessibility: FacultyCategory
    equity: FacultyCategory
    clarity: FacultyCategory
    prioritized_fixes: List[PrioritizedFix] = Field(..., min_length=5, max_length=5)

    @model_validator(mode="after")
    def _ordered(self) -> "FacultyReport":
        priorities = [f.priority for f in self.prioritized_fixes]
        if priorities != sorted(priorities):
            raise ValueError("prioritized_fixes must be ordered by priority (1 first)")
        return self


# ---------- Provost curriculum map ----------


class ObjectiveAnalysis(BaseModel):
    objective: str = Field(..., min_length=1)
    coverage_status: Literal["covered", "partial", "missing"]
    coverage_score: int = Field(..., ge=1, le=10)
    evidence: str
    lectures_covering: List[int]
    gaps: str

    @field_validator("lectures_covering")
    @classmethod
    def _lectures_exist(cls, v: List[int], info: ValidationInfo) -> List[int]:
        n = (info.context or {}).get("lecture_count")
        if n is not None:
            bad = [x for x in v if x < 1 or x > int(n)]
            if bad:
                raise ValueError(f"lectures_covering has lecture numbers {bad}, but only lectures 1..{n} exist")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "ObjectiveAnalysis":
        if self.coverage_status in ("covered", "partial") and not self.lectures_covering:
            raise ValueError(f"objective '{self.objective[:40]}' is {self.coverage_status} but cites no lecture")
        if self.coverage_status == "missing" and self.lectures_covering:
            raise ValueError(f"objective '{self.objective[:40]}' is missing but cites lectures")
        return self


class CriticalGap(BaseModel):
    gap: str
    impact: str
    recommendation: str


class CoverageDistribution(BaseModel):
    fully_covered: int = Field(..., ge=0)
    partially_covered: int = Field(..., ge=0)
    not_covered: int = Field(..., ge=0)


class ProvostRecommendation(BaseModel):
    priority: int = Field(..., ge=1, le=5)
    recommendation: str
    rationale: str


class CurriculumMap(BaseModel):
    overall_coverage_score: int = Field(..., ge=1, le=10)
    executive_summary: str = Field(..., min_length=1)
    objectives_analysis: List[ObjectiveAnalysis] = Field(..., min_length=1)
    curriculum_strengths: List[str]
    critical_gaps: List[CriticalGap]
    coverage_distribution: CoverageDistribution
    recommendations: List[ProvostRecommendation] = Field(..., min_length=5, max_length=5)

    @model_validator(mode="after")
    def _counts_match(self) -> "CurriculumMap":
        by_status = {"covered": 0, "partial": 0, "missing": 0}
        for o in self.objectives_analysis:
            by_status[o.coverage_status] += 1
        d = self.coverage_distribution
        actual = (d.fully_covered, d.partially_covered, d.not_covered)
        expected = (by_status["covered"], by_status["partial"], by_status["missing"])
        if actual != expected:
            raise ValueError(
                f"coverage_distribution {actual} does not match objectives_analysis statuses {expected} "
                "(fully_covered, partially_covered, not_covered)"
            )
        return self


def tool_input_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """
    JSON Schema for a tool's input_schema, with every $ref inlined (one self-contained
    object) and Pydantic's cosmetic `title` keys dropped.
    """
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                merged = {**resolve(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)

