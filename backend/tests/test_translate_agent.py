import pytest

import agents.translate_agent as ta


class _Block:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


def _agent_with(responses):
    agent = ta.TranslateAgent()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)

    agent._client.messages.create = create  # type: ignore[method-assign]
    return agent, calls


def test_api_error_is_not_retried_with_split():
    agent, calls = _agent_with([RuntimeError("401 auth")])
    with pytest.raises(ta.TranslateAgentError):
        agent.translate(content={"summary_90s": "hi"}, target_language="Spanish")
    assert len(calls) == 1


def test_truncated_output_falls_back_to_split():
    content = {"outline": [], "flashcards": [], "summary_90s": "hi", "summary_5min": "a", "summary_full": "b"}
    agent, calls = _agent_with(
        [
            '{"outline": [',  # truncated
            '{"outline": [',  # repair also fails
            '{"outline": [], "flashcards": [], "search_results": null}',
            '{"summary_90s": "hola", "summary_5min": "a", "summary_full": "b"}',
        ]
    )
    out = agent.translate(content=content, target_language="Spanish")
    assert out["summary_90s"] == "hola"
    assert len(calls) == 4
