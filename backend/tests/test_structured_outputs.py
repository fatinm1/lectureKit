"""Forced tool calls, Pydantic validation, the corrective retry, the legacy fallback and path counting."""

from __future__ import annotations

import copy
import json
import threading

import pytest

import agents.structured_call as sc
from agents.content_streaming import STUDY_TOOL, StreamingContentAgent
from agents.faculty_agent import FACULTY_TOOL, FacultyAgent
from agents.provost_agent import PROVOST_TOOL, ProvostAgent
from fake_claude import STRUCTURED, FakeClaude
from models.schemas import TranscriptChunk
from models.structured import CurriculumMap, FacultyReport, StudyStructure, tool_input_schema


@pytest.fixture()
def paths(monkeypatch):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(sc, "record_path", lambda agent, path: seen.append((agent, path)))
    return seen


def _chunks(n=3, length=60.0):
    return [
        TranscriptChunk(text=f"chunk {i}", start=i * length, end=i * length + length - 1, chunk_index=i, word_count=2)
        for i in range(n)
    ]


def _agent(fake):
    a = StreamingContentAgent()
    a._client = fake
    return a


def _bad_structured(**overrides):
    payload = copy.deepcopy(STRUCTURED)
    payload.update(overrides)
    return payload


# ---------- schema generation ----------


def test_tool_schemas_are_self_contained():
    for model in (StudyStructure, FacultyReport, CurriculumMap):
        schema = tool_input_schema(model)
        text = json.dumps(schema)
        assert "$ref" not in text and "$defs" not in text
        assert schema["type"] == "object" and schema["required"]
    study = tool_input_schema(StudyStructure)
    assert study["properties"]["flashcards"]["minItems"] == 10 == study["properties"]["flashcards"]["maxItems"]
    status = tool_input_schema(CurriculumMap)["properties"]["objectives_analysis"]["items"]["properties"]["coverage_status"]
    assert set(status["enum"]) == {"covered", "partial", "missing"}


# ---------- validators catch what JSON Schema can't ----------


def test_timestamps_past_the_lecture_are_rejected():
    payload = _bad_structured()
    payload["flashcards"][3]["source_timestamp"] = 9999
    with pytest.raises(Exception, match="past the end of the lecture"):
        StudyStructure.model_validate(payload, context={"max_timestamp": 179})


def test_outline_must_be_chronological():
    payload = _bad_structured()
    payload["outline"].reverse()
    with pytest.raises(Exception, match="chronological"):
        StudyStructure.model_validate(payload, context={"max_timestamp": 179})


def _curriculum(**overrides):
    m = {
        "overall_coverage_score": 7,
        "executive_summary": "ok",
        "objectives_analysis": [
            {"objective": "A", "coverage_status": "covered", "coverage_score": 8, "evidence": "L1 3:00",
             "lectures_covering": [1], "gaps": ""},
            {"objective": "B", "coverage_status": "missing", "coverage_score": 1, "evidence": "",
             "lectures_covering": [], "gaps": "not taught"},
        ],
        "curriculum_strengths": ["x"],
        "critical_gaps": [{"gap": "B", "impact": "i", "recommendation": "r"}],
        "coverage_distribution": {"fully_covered": 1, "partially_covered": 0, "not_covered": 1},
        "recommendations": [{"priority": p, "recommendation": "r", "rationale": "w"} for p in range(1, 6)],
    }
    m.update(overrides)
    return m


def test_curriculum_counts_and_lecture_numbers_are_checked():
    CurriculumMap.model_validate(_curriculum(), context={"lecture_count": 2})
    # A miscounted distribution is corrected, not rejected: the server derives it.
    m = CurriculumMap.model_validate(
        _curriculum(coverage_distribution={"fully_covered": 2, "partially_covered": 0, "not_covered": 0})
    )
    assert m.coverage_distribution.model_dump() == {"fully_covered": 1, "partially_covered": 0, "not_covered": 1}
    no_dist = _curriculum()
    del no_dist["coverage_distribution"]
    assert CurriculumMap.model_validate(no_dist).coverage_distribution.not_covered == 1
    assert "coverage_distribution" not in PROVOST_TOOL["input_schema"]["properties"]
    bad = _curriculum()
    bad["objectives_analysis"][0]["lectures_covering"] = [3]
    with pytest.raises(Exception, match="only lectures 1..2"):
        CurriculumMap.model_validate(bad, context={"lecture_count": 2})


# ---------- the call paths ----------


def test_first_try_path(paths):
    fake = FakeClaude()
    s = _agent(fake).generate_structured(_chunks())
    assert s.path == "tool" and s.attempts == 1 and len(s.flashcards) == 10
    assert paths == [("student", "tool")]
    call = fake.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_study_kit"}
    assert call["tools"] == [STUDY_TOOL]


def test_invalid_then_corrected_uses_one_retry_with_the_errors(paths):
    nine_cards = _bad_structured(flashcards=STRUCTURED["flashcards"][:9])
    fake = FakeClaude(tool_inputs=[nine_cards, STRUCTURED])
    s = _agent(fake).generate_structured(_chunks())
    assert s.path == "tool_retry" and s.attempts == 2
    assert paths == [("student", "tool_retry")]
    retry_messages = fake.calls[1]["messages"]
    assert retry_messages[1]["role"] == "assistant" and retry_messages[1]["content"][0]["type"] == "tool_use"
    result = retry_messages[2]["content"][0]
    assert result["type"] == "tool_result" and result["is_error"] is True
    assert "flashcards" in result["content"] and "10" in result["content"]
    # Usage is summed over both attempts.
    assert s.usage.output_tokens == 600


def test_two_invalid_tool_calls_fall_back_to_the_legacy_parser(paths):
    late = _bad_structured()
    late["outline"][0]["timestamp"] = 5000
    fake = FakeClaude(tool_inputs=[late, late], legacy_text="```json\n" + json.dumps(STRUCTURED) + "\n```")
    s = _agent(fake).generate_structured(_chunks())
    assert s.path == "legacy_fallback"
    assert paths == [("student", "legacy_fallback")]
    legacy_call = fake.calls[2]
    assert "tools" not in legacy_call  # plain text call; reads the cached transcript


def test_everything_failing_raises_and_is_counted(paths):
    from agents.content_agent import ContentAgentError

    late = _bad_structured()
    late["outline"][0]["timestamp"] = 5000
    fake = FakeClaude(tool_inputs=[late, late], legacy_text=json.dumps(late))
    with pytest.raises(ContentAgentError, match="failed validation"):
        _agent(fake).generate_structured(_chunks())
    assert paths == [("student", "failed")]


def test_stop_cancels_the_structured_call():
    from agents.content_streaming import ContentCancelled

    fake = FakeClaude(structured_delay=0.02)
    with pytest.raises(ContentCancelled):
        _agent(fake).generate_structured(_chunks(), should_stop=lambda: len(fake.calls) >= 1)
    assert fake.closed_early.get("structured") is True


def test_retry_reuses_the_cached_transcript_prefix():
    nine_cards = copy.deepcopy(STRUCTURED)
    nine_cards["flashcards"] = nine_cards["flashcards"][:9]
    fake = FakeClaude(tool_inputs=[nine_cards, STRUCTURED])
    _agent(fake).generate_structured(_chunks())
    first, retry = fake.calls
    # Same tools + system on both turns, transcript block cached -> the retry pays the cached rate.
    assert first["tools"] == retry["tools"] and first["system"] == retry["system"]
    assert first["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_prompt_version_changes_with_the_tool_schema(monkeypatch):
    agent = _agent(FakeClaude())
    before = agent.prompt_version
    import agents.content_streaming as cs

    monkeypatch.setitem(cs.STUDY_TOOL, "description", "changed")
    assert agent.prompt_version != before


# ---------- faculty + provost agents ----------


def _faculty_report():
    cat = {"score": 7, "summary": "s", "strengths": ["a"], "issues": [{"description": "d", "timestamp": 30, "suggested_rewrite": "r"}]}
    return {
        "overall_score": 7,
        "top_priority_fix": {"title": "t", "description": "d", "timestamp": 10, "suggested_rewrite": "r"},
        "pedagogical": cat, "accessibility": cat, "equity": cat, "clarity": cat,
        "prioritized_fixes": [
            {"priority": p, "category": "clarity", "title": "t", "description": "d", "timestamp": 20, "suggested_rewrite": "r"}
            for p in range(1, 6)
        ],
    }


def test_faculty_agent_retries_bad_category_then_succeeds(paths, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bad = _faculty_report()
    bad["prioritized_fixes"][0]["category"] = "vibes"
    agent = FacultyAgent()
    agent.client = FakeClaude(tool_inputs=[bad, _faculty_report()])
    report = agent.generate_report(_chunks(), "jNQXAC9IVRw")
    assert report["prioritized_fixes"][0]["category"] == "clarity"
    assert paths == [("faculty", "tool_retry")]
    assert agent.client.calls[0]["tools"] == [FACULTY_TOOL]


def test_provost_agent_validates_against_lecture_count(paths, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bad = _curriculum()
    bad["objectives_analysis"][0]["lectures_covering"] = [7]  # only 2 lectures exist
    agent = ProvostAgent()
    agent.client = FakeClaude(tool_inputs=[bad, _curriculum()])
    lectures = [{"video_id": "a", "chunks": [c.model_dump() for c in _chunks()]} for _ in range(2)]
    out = agent.generate_curriculum_map(lectures, "A\nB")
    assert out["coverage_distribution"]["not_covered"] == 1
    assert paths == [("provost", "tool_retry")]
    assert "only lectures 1..2" in agent.client.calls[1]["messages"][2]["content"][0]["content"]
    assert agent.client.calls[0]["tools"] == [PROVOST_TOOL]
