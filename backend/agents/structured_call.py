"""
Purpose: Get a validated, typed object out of Claude with a forced tool call.

    Claude ──tool_use(input=…)──▶ Pydantic validate ──ok──▶ done            path = "tool"
                                        │ fail
                                        ▼
    tool_result(is_error, "<exact validation errors>") ──▶ Claude ──▶ validate ──ok──▶ "tool_retry"
                                                                          │ fail
                                                                          ▼
                                      legacy text prompt + 4-strategy JSON parser ──▶ "legacy_fallback"
                                                                          │ fail
                                                                          ▼
                                                               StructuredOutputError  "failed"

- `tool_choice` forces the named tool, so the reply is always a tool_use block whose `input`
  already follows the JSON Schema generated from the Pydantic model. No markdown fences,
  preamble, or truncated text to repair.
- Validation errors go back as an `is_error` tool_result, so the retry is a correction in
  context rather than a fresh roll of the dice.
- The old text-JSON path stays as a last resort, and every outcome is counted (see
  `record_path`), which is how the parse-failure rate is measured.
- Calls stream so `should_stop()` (the Stop button) can abort mid-generation.
"""

from __future__ import annotations

import usage as usage_mod
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from models.structured import tool_input_schema

logger = logging.getLogger("lecturekit.structured")

T = TypeVar("T", bound=BaseModel)

PATHS = ("tool", "tool_retry", "legacy_fallback", "failed")


class StructuredOutputError(Exception):
    """Claude's output could not be validated by any path."""


class StructuredCallCancelled(Exception):
    """should_stop() returned True mid-call."""


def _noop_record(agent: str, path: str) -> None:
    return None


# Set by services.py to increment Redis counters; a no-op in tests and without Redis.
record_path: Callable[[str, str], None] = _noop_record


def make_tool(name: str, description: str, model_cls: type[BaseModel]) -> dict[str, Any]:
    return {"name": name, "description": description, "input_schema": tool_input_schema(model_cls)}


def format_validation_error(exc: ValidationError, limit: int = 12) -> str:
    """Compact, model-readable list of what's wrong: one line per error with its JSON path."""
    lines = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        lines.append(f"- {loc}: {err.get('msg')}")
    extra = len(exc.errors()) - limit
    if extra > 0:
        lines.append(f"- … and {extra} more")
    return "\n".join(lines)


@dataclass
class StructuredResult(Generic[T]):
    value: T
    path: str
    usage: dict[str, Any] = field(default_factory=dict)  # summed over every attempt


def _add_usage(total: dict[str, Any], message: Any, seconds: float, first_token_s: Optional[float]) -> None:
    u = getattr(message, "usage", None)
    for f in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        total[f] = int(total.get(f, 0)) + int(getattr(u, f, 0) or 0)
    total["seconds"] = round(float(total.get("seconds", 0.0)) + seconds, 3)
    total["attempts"] = int(total.get("attempts", 0)) + 1
    if first_token_s is not None and "first_token_s" not in total:
        total["first_token_s"] = round(first_token_s, 3)


def _stream_message(client: Any, should_stop: Callable[[], bool], **kwargs: Any) -> tuple[Any, float, Optional[float]]:
    t0 = time.perf_counter()
    first: Optional[float] = None
    with client.messages.stream(**kwargs) as stream:
        for _event in stream:
            if first is None:
                first = time.perf_counter() - t0
            if should_stop():
                raise StructuredCallCancelled()
        message = stream.get_final_message()
    return message, time.perf_counter() - t0, first


def _tool_use_block(message: Any, tool_name: str) -> Any:
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return block
    return None


def call_structured(
    client: Any,
    *,
    agent: str,
    model: str,
    system: Any,
    user: str,
    tools: Sequence[dict[str, Any]],
    tool_name: str,
    model_cls: type[T],
    max_tokens: int,
    context: Optional[dict[str, Any]] = None,
    should_stop: Callable[[], bool] = lambda: False,
    legacy_fallback: Optional[Callable[[], dict[str, Any]]] = None,
) -> StructuredResult[T]:
    """
    Force `tool_name`, validate its input with `model_cls`, retry once with the validation
    errors, then fall back to `legacy_fallback()` (old text prompt + parser) if given.

    `tools` is the full tool list for the request (it is part of the prompt-cache prefix, so
    callers that share a cached prefix must pass the same list everywhere).
    """
    usage: dict[str, Any] = {}
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    base = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=list(tools),
        tool_choice={"type": "tool", "name": tool_name},
    )
    last_error = "no tool call returned"

    for attempt in (1, 2):
        try:
            message, seconds, first = _stream_message(client, should_stop, messages=messages, **base)
        except StructuredCallCancelled:
            raise
        except Exception as exc:
            raise StructuredOutputError(f"Claude call failed: {type(exc).__name__}: {exc}") from exc
        _add_usage(usage, message, seconds, first)
        usage_mod.report(agent, message)  # every attempt is billed, valid or not

        block = _tool_use_block(message, tool_name)
        if block is None:
            last_error = f"stop_reason={getattr(message, 'stop_reason', None)!r} with no {tool_name} call"
            break  # nothing to correct in context; go to the fallback

        try:
            value = model_cls.model_validate(block.input, context=context or {})
        except ValidationError as exc:
            last_error = format_validation_error(exc)
            logger.warning("%s: attempt %d failed validation:\n%s", agent, attempt, last_error)
            if attempt == 2:
                break
            messages = messages + [
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": (
                                "Your output failed validation:\n"
                                f"{last_error}\n"
                                f"Call {tool_name} again with all fields, fixing every error above."
                            ),
                        }
                    ],
                },
            ]
            continue

        path = "tool" if attempt == 1 else "tool_retry"
        record_path(agent, path)
        return StructuredResult(value=value, path=path, usage=usage)

    if legacy_fallback is not None:
        try:
            raw = legacy_fallback()
            value = model_cls.model_validate(raw, context=context or {})
            record_path(agent, "legacy_fallback")
            return StructuredResult(value=value, path="legacy_fallback", usage=usage)
        except StructuredCallCancelled:
            raise
        except Exception as exc:
            last_error = f"{last_error}\nlegacy fallback: {type(exc).__name__}: {exc}"

    record_path(agent, "failed")
    raise StructuredOutputError(f"{agent}: Claude's output failed validation.\n{last_error}")
