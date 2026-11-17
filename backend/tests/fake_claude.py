"""
A fake Anthropic client whose `messages.stream(...)` behaves like the real SDK's:
a context manager with `.text_stream` and `.get_final_message()`. It records every call
and whether each stream was closed early, so tests can check caching and cancellation.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from types import SimpleNamespace

SUMMARY_TEXT = (
    "@@SUMMARY_90S@@\nGradient descent minimizes loss by following the negative gradient.\n"
    "@@SUMMARY_5MIN@@\nThe lecture covers derivatives, the chain rule and backpropagation.\n\n"
    "It then trains a tiny network.\n"
    "@@SUMMARY_FULL@@\nFirst, derivatives. Second, the chain rule. Third, backprop through a graph."
)

STRUCTURED = {
    "outline": [
        {"timestamp": 0, "title": "Derivatives", "description": "What a derivative measures."},
        {"timestamp": 30, "title": "Chain rule", "description": "Composing derivatives."},
        {"timestamp": 60, "title": "Backpropagation", "description": "Chain rule through a graph."},
    ],
    "flashcards": [
        {"question": f"Q{i}?", "answer": "Because of the chain rule.", "source_timestamp": i * 10}
        for i in range(10)
    ],
}


def _pieces(text: str, size: int):
    return [text[i : i + size] for i in range(0, len(text), size)]


class _Stream:
    def __init__(self, client, kind, pieces, delay, usage, content=None):
        self.client, self.kind, self.pieces, self.delay, self.usage = client, kind, pieces, delay, usage
        self.content = content  # final message content blocks (tool_use for forced tool calls)
        self.closed_early = False
        self.yielded = 0

    def __enter__(self):
        self.client.started[self.kind] = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.closed_early = self.yielded < len(self.pieces)
        self.client.closed_early[self.kind] = self.closed_early
        return False

    @property
    def text_stream(self):
        if self.kind in self.client.fail:
            raise RuntimeError(f"boom in {self.kind}")
        for p in self.pieces:
            time.sleep(self.delay)
            self.yielded += 1
            yield p

    def __iter__(self):
        # Iterating a real MessageStream yields events; one per piece is enough here.
        return iter(self.text_stream)

    def get_final_message(self):
        content = self.content if self.content is not None else []
        return SimpleNamespace(usage=SimpleNamespace(**self.usage), content=content, stop_reason="tool_use")


def tool_use(name, payload, id_="toolu_1"):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=copy.deepcopy(payload))


class FakeClaude:
    """
    messages.stream() routing:
    - tool_choice {"type": "tool"}  → a forced tool call; returns the next entry of
      `tool_inputs` (default: a valid STRUCTURED payload) as a tool_use block
    - user text containing @@SUMMARY_90S@@ → streamed summaries text
    - anything else (legacy text-JSON prompts) → `legacy_text`
    """

    def __init__(
        self,
        *,
        summary_delay=0.01,
        structured_delay=0.01,
        piece_size=7,
        fail=(),
        tool_inputs=None,
        legacy_text=None,
    ):
        self.tool_inputs = list(tool_inputs) if tool_inputs is not None else None
        self.legacy_text = legacy_text if legacy_text is not None else json.dumps(STRUCTURED)
        self.calls: list[dict] = []
        self.started: dict[str, float] = {}
        self.closed_early: dict[str, bool] = {}
        self.summary_delay = summary_delay
        self.structured_delay = structured_delay
        self.piece_size = piece_size
        self.fail = set(fail)
        self._lock = threading.Lock()
        self.messages = SimpleNamespace(stream=self._stream, create=self._create)

    def _stream(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
            first = len(self.calls) == 1
        first_msg = kwargs["messages"][0]["content"]
        user = first_msg if isinstance(first_msg, str) else json.dumps(first_msg)
        forced = (kwargs.get("tool_choice") or {}).get("type") == "tool"
        if forced:
            kind = "structured"
        elif "@@SUMMARY_90S@@" in user:
            kind = "summaries"
        else:
            kind = "legacy"
        usage = {
            "input_tokens": 40,
            "output_tokens": 300,
            # Whoever calls first writes the cache; the other reads it.
            "cache_creation_input_tokens": 5000 if first else 0,
            "cache_read_input_tokens": 0 if first else 5000,
        }
        if kind == "summaries":
            return _Stream(self, kind, _pieces(SUMMARY_TEXT, self.piece_size), self.summary_delay, usage)
        if kind == "legacy":
            return _Stream(self, kind, _pieces(self.legacy_text, 40), self.structured_delay, usage)
        name = kwargs["tool_choice"]["name"]
        with self._lock:
            payload = self.tool_inputs.pop(0) if self.tool_inputs else STRUCTURED
        content = [tool_use(name, payload, id_=f"toolu_{len(self.calls)}")]
        return _Stream(self, kind, _pieces(json.dumps(payload), 40), self.structured_delay, usage, content=content)

    def _create(self, **kwargs):  # used by the JSON repair path
        raise RuntimeError("repair should not be needed in these tests")
