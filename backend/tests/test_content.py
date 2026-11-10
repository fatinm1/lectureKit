import json
import pytest
from agents.content_agent import ContentAgent, ContentAgentError
from models.schemas import TranscriptChunk
from utils.youtube import extract_youtube_video_id, InvalidYouTubeUrlError

def agent():
    return ContentAgent.__new__(ContentAgent)

@pytest.mark.parametrize("raw", ['{"x": 1}', '```json\n{"x": 1}\n```', 'Here is the result: {"x": 1} done'])
def test_json_wrappers(raw):
    assert agent()._parse_json_response(raw) == {"x": 1}

def test_malformed_output_repaired_once():
    a = agent()
    calls = []
    a._call_claude = lambda prompt: calls.append(prompt) or '{"x":1}'
    assert a._parse_json_with_retry("broken", transcript="source") == {"x": 1}
    assert len(calls) == 1

def test_invalid_schema_is_not_returned_as_success():
    a = agent()
    a._call_claude = lambda prompt: '{"outline": []}'
    with pytest.raises(ContentAgentError, match="schema"):
        a.process([TranscriptChunk(text="source", start=0, end=2, chunk_index=0, word_count=1)])

def test_non_youtube_domain_rejected():
    with pytest.raises(InvalidYouTubeUrlError):
        extract_youtube_video_id("https://example.com/watch?v=jNQXAC9IVRw")
