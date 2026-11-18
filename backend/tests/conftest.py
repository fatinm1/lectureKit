"""
Shared test fixtures.

Nothing here touches the network: the embedding model is replaced by a tiny
deterministic hash embedder, and Claude / transcript fetching are mocked per test.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import sys
from pathlib import Path

import numpy as np

# Tests make many AI-route calls; keep the demo budget from returning 429.
os.environ["AI_REQUESTS_PER_MINUTE"] = "10000"
os.environ["AI_MAX_CONCURRENT"] = "100"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class FakeEmbedder:
    """Bag-of-words hashing embedder: same words -> similar vectors. No downloads."""

    dim = 384

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def encode(self, texts, show_progress_bar=False, normalize_embeddings=True):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in str(text).lower().split():
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
            norm = np.linalg.norm(out[i])
            if normalize_embeddings and norm > 0:
                out[i] /= norm
        return out


# Patch at import time (before any test module imports `services`, which builds a
# SearchAgent at import) so no test ever downloads the real embedding model.
import sentence_transformers  # noqa: E402

sentence_transformers.SentenceTransformer = FakeEmbedder  # type: ignore[assignment]
import agents.search_agent as _sa  # noqa: E402

_sa.SentenceTransformer = FakeEmbedder  # type: ignore[assignment]
os.environ.setdefault("CHROMA_DB_PATH", tempfile.mkdtemp(prefix="lk-chroma-"))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
# Limits are off by default in tests (they share one client IP and one Redis); the tests in
# test_production.py turn them on explicitly.
os.environ.setdefault("RATE_LIMIT_PER_HOUR", "0")
os.environ.setdefault("ASK_RATE_LIMIT_PER_HOUR", "0")
os.environ.setdefault("LOG_FORMAT", "text")
