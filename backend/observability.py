"""
Purpose: Structured logs, request IDs and (optional) Sentry.

- Logs are one JSON object per line (`LOG_FORMAT=json`, the default) so Railway's log search can
  filter on fields like @level:error or @request_id:… . `LOG_FORMAT=text` gives plain lines for
  local work.
- Every HTTP request gets an ID: the caller's `X-Request-ID`, else Railway's
  `X-Railway-Request-Id`, else a new one. It's echoed back as `X-Request-ID`, attached to every
  log line written while handling the request, and logged once per request with method, path,
  status, duration and client IP.
- Sentry starts only when `SENTRY_DSN` is set; without it nothing is imported or sent. Request
  bodies and cookies are never sent (`send_default_pii=False`).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            out["request_id"] = rid
        # Anything passed with `extra={...}` becomes a top-level field.
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    """Idempotent: replaces the root handler, and routes uvicorn's loggers through it."""
    fmt = (os.getenv("LOG_FORMAT") or "json").lower()
    level = (os.getenv("LOG_LEVEL") or "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.addFilter(_RequestIdFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # The request log below replaces uvicorn's access log (it has the request ID and timing).
    logging.getLogger("uvicorn.access").disabled = True


def client_ip(scope: dict) -> str:
    """
    Railway's edge sets X-Real-IP to the client's address. X-Forwarded-For is not used: a
    client can put anything in it, which would let one person spread across many rate-limit
    buckets.
    """
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
    real = headers.get("x-real-ip", "").strip()
    if real:
        return real
    client = scope.get("client")
    return client[0] if client else "unknown"


class RequestContextMiddleware:
    """Pure ASGI (doesn't buffer streaming responses like SSE)."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.log = logging.getLogger("lecturekit.http")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        rid = (headers.get("x-request-id") or headers.get("x-railway-request-id") or uuid.uuid4().hex[:16])[:64]
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode("latin-1"))]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path != "/health":  # Railway's health probe would drown everything else
                self.log.info(
                    "%s %s %s",
                    scope.get("method"),
                    path,
                    status["code"],
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status["code"],
                        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                        "client_ip": client_ip(scope),
                    },
                )
            request_id_var.reset(token)


def setup_sentry() -> bool:
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("SENTRY_ENVIRONMENT") or "development",
        release=(os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:12] or None,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
        send_default_pii=False,
    )
    return True
