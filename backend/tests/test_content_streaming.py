import threading

import pytest

from agents.content_agent import ContentAgentError
from agents.content_streaming import ContentCancelled, SectionStreamParser, StreamingContentAgent
from models.schemas import TranscriptChunk
from fake_claude import SUMMARY_TEXT, FakeClaude


def _feed_all(pieces):
    p = SectionStreamParser()
    out = []
    for piece in pieces:
        out += p.feed(piece)
    out += p.close()
    return p, out


def test_parser_splits_sections():
    p, out = _feed_all([SUMMARY_TEXT])
    assert p.text["summary_90s"].startswith("Gradient descent")
    assert p.text["summary_5min"].endswith("tiny network.")
    assert p.text["summary_full"].startswith("First, derivatives")
    assert [s for s, _ in out] == ["summary_90s", "summary_5min", "summary_full"]


@pytest.mark.parametrize("size", range(1, 21))
def test_parser_handles_markers_split_across_pieces(size):
    whole, _ = _feed_all([SUMMARY_TEXT])
    split, _ = _feed_all([SUMMARY_TEXT[i : i + size] for i in range(0, len(SUMMARY_TEXT), size)])
    assert split.text == whole.text


def test_parser_keeps_literal_double_at_and_drops_preamble():
    p, _ = _feed_all(["Sure!\n", "@@SUMMARY_90S@@\nemail me @@ home ", "@", "@x"])
    assert p.text["summary_90s"] == "email me @@ home @@x"


def _chunks():
    return [
        TranscriptChunk(text=f"text {i}", start=i * 60.0, end=i * 60.0 + 59, chunk_index=i, word_count=2)
        for i in range(3)
    ]


def _agent(fake):
    agent = StreamingContentAgent()
    agent._client = fake
    return agent


def test_both_calls_share_a_cacheable_system_prompt():
    fake = FakeClaude()
    agent = _agent(fake)
    warm = threading.Event()
    deltas = []
    agent.stream_summaries(_chunks(), lambda s, t: deltas.append((s, t)), cache_warm=warm)
    agent.generate_structured(_chunks(), cache_warm=warm)
    a, b = fake.calls
    assert a["system"] == b["system"]
    assert a["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "text 0" in a["system"][-1]["text"]
    assert len(deltas) > 3  # streamed in pieces, not one blob


def test_structured_call_waits_for_cache_then_reads_it():
    fake = FakeClaude(summary_delay=0.05)
    agent = _agent(fake)
    warm = threading.Event()
    results = {}

    t = threading.Thread(
        target=lambda: results.__setitem__("s", agent.stream_summaries(_chunks(), lambda *_: None, cache_warm=warm))
    )
    t.start()
    results["c"] = agent.generate_structured(_chunks(), cache_warm=warm)
    t.join()
    assert fake.started["structured"] > fake.started["summaries"]
    assert results["c"].usage.cache_read_input_tokens == 5000
    assert results["s"].usage.cache_creation_input_tokens == 5000
    assert len(results["c"].flashcards) == 10 and results["c"].outline[1].title == "Chain rule"


def test_stop_closes_the_stream_early():
    fake = FakeClaude(summary_delay=0.01)
    agent = _agent(fake)
    seen = []

    def on_delta(section, text):
        seen.append(text)

    with pytest.raises(ContentCancelled):
        agent.stream_summaries(_chunks(), on_delta, should_stop=lambda: len(seen) >= 3)
    assert fake.closed_early["summaries"] is True


def test_stream_error_becomes_content_agent_error():
    agent = _agent(FakeClaude(fail={"summaries"}))
    with pytest.raises(ContentAgentError):
        agent.stream_summaries(_chunks(), lambda *_: None)
