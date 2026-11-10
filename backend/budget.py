"""Per-process cost and concurrency guard for public AI demos."""
import os
import threading
import time
from collections import deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class Budget:
    def __init__(self, per_minute: int, concurrent: int):
        self.per_minute = per_minute
        self.concurrent = concurrent
        self.active = 0
        self.started = deque()
        self.lock = threading.Lock()

    def enter(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            while self.started and self.started[0] <= now - 60:
                self.started.popleft()
            if self.active >= self.concurrent or len(self.started) >= self.per_minute:
                return False
            self.active += 1
            self.started.append(now)
            return True

    def leave(self):
        with self.lock:
            self.active = max(0, self.active - 1)


class AIBudgetMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, paths):
        super().__init__(app)
        self.paths = set(paths)
        self.budget = Budget(max(1, int(os.getenv("AI_REQUESTS_PER_MINUTE", "10"))),
                             max(1, int(os.getenv("AI_MAX_CONCURRENT", "2"))))

    async def dispatch(self, request, call_next):
        if request.method != "POST" or request.url.path not in self.paths:
            return await call_next(request)
        if not self.budget.enter():
            return JSONResponse({"detail": "Demo capacity reached. Please try again later."},
                                status_code=429, headers={"Retry-After": "60"})
        try:
            return await call_next(request)
        finally:
            self.budget.leave()
