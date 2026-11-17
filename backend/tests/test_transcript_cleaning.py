from agents.transcript_agent import (
    USER_FRIENDLY_MSG_LIVESTREAM,
    USER_FRIENDLY_MSG_NO_TRANSCRIPT,
    USER_FRIENDLY_MSG_PRIVATE,
    USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC,
    TranscriptAgent,
    user_friendly_transcript_failure_message,
)


def test_meaningful_words_survive_cleaning():
    agent = TranscriptAgent()
    text = "Um so this looks like a tree. Do you know why? It actually is, uh, literally a graph."
    cleaned = agent._clean_text(text)
    assert "looks like a tree" in cleaned
    assert "Do you know why" in cleaned
    assert "actually" in cleaned and "literally" in cleaned
    assert "Um" not in cleaned and " uh" not in cleaned


def test_html_and_whitespace_are_stripped():
    agent = TranscriptAgent()
    assert agent._clean_text("<i>hello</i>\n\n   world") == "hello world"


def test_livestream_message_requires_real_livestream_wording():
    assert user_friendly_transcript_failure_message("This video is a live stream") == USER_FRIENDLY_MSG_LIVESTREAM
    assert user_friendly_transcript_failure_message("Premiere starts soon") == USER_FRIENDLY_MSG_LIVESTREAM
    # Previously any substring "live" (delivered, alive, oliver) was misread as a livestream.
    assert (
        user_friendly_transcript_failure_message("Payload delivered but empty")
        == USER_FRIENDLY_MSG_TRANSCRIPT_GENERIC
    )
    assert user_friendly_transcript_failure_message("Video unavailable") == USER_FRIENDLY_MSG_PRIVATE
    assert user_friendly_transcript_failure_message("No transcript found") == USER_FRIENDLY_MSG_NO_TRANSCRIPT


def test_chunking_keeps_order_and_timestamps():
    agent = TranscriptAgent(target_words_per_chunk=50, max_words_over_target=10)
    entries = [
        {"text": f"Sentence number {i} is here.", "start": float(i * 3), "duration": 3.0}
        for i in range(60)
    ]
    chunks = agent._chunk_word_times(agent._entries_to_word_times(entries))
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for a, b in zip(chunks, chunks[1:]):
        assert a.start <= a.end <= b.start
    assert sum(c.word_count for c in chunks) == 60 * 5
