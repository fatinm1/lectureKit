"""
Purpose: Postgres (+ pgvector) storage for LectureKit.

One database holds everything that used to be scattered or lost on redeploy:

- lectures            one row per YouTube video
- transcript_chunks   timestamped chunks + their 384-d embedding (pgvector), so search
                      survives redeploys and a transcript is fetched from YouTube once
- results             generated study kits / faculty reports, keyed by
                      (video_id, kind, language, prompt_version). A popular lecture is
                      generated once and served to everyone; changing a prompt changes
                      prompt_version, so stale results are simply never looked up again.
- jobs                one row per background job: cache hit or not, timings, token usage.
                      This is where the cache-hit-rate and Claude-spend-saved metrics come from.

Why pgvector instead of a separate vector DB: one database, transactional writes of
chunks + embeddings together, and SQL joins. Search is always scoped to one lecture
(at most a few hundred chunks), so it uses an exact scan behind the primary-key index
rather than an approximate HNSW index, which would also need care to stay correct
under the `WHERE video_id = ...` filter.

All methods are synchronous (psycopg 3 + a small connection pool); the async job pipeline
calls them through asyncio.to_thread like the other agents.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from models.schemas import TranscriptChunk

logger = logging.getLogger("lecturekit.db")

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))  # all-MiniLM-L6-v2

SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS lectures (
    video_id     text PRIMARY KEY,
    youtube_url  text,
    duration_s   double precision,
    chunk_count  integer,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
    video_id     text NOT NULL REFERENCES lectures(video_id) ON DELETE CASCADE,
    chunk_index  integer NOT NULL,
    text         text NOT NULL,
    start_s      double precision NOT NULL,
    end_s        double precision NOT NULL,
    word_count   integer NOT NULL,
    embedding    vector({EMBEDDING_DIM}),
    PRIMARY KEY (video_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS results (
    video_id        text NOT NULL REFERENCES lectures(video_id) ON DELETE CASCADE,
    kind            text NOT NULL,
    language        text NOT NULL,
    prompt_version  text NOT NULL,
    payload         jsonb NOT NULL,
    usage           jsonb,
    hits            integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (video_id, kind, language, prompt_version)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      text PRIMARY KEY,
    kind        text NOT NULL,
    video_id    text,
    status      text NOT NULL,
    cache_hit   boolean NOT NULL DEFAULT false,
    timings     jsonb,
    usage       jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON jobs (created_at DESC);

-- Accounts (db/accounts.py). Passwords are argon2id hashes; sessions store only a SHA-256 of
-- the bearer token, so a database leak doesn't hand out live sessions.
CREATE TABLE IF NOT EXISTS users (
    id             text PRIMARY KEY,
    email          text NOT NULL UNIQUE,
    password_hash  text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  text PRIMARY KEY,
    user_id     text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

-- A snapshot of each saved result, so a library item never changes or disappears when the
-- result cache moves to a new prompt version. share_token is null unless the owner shared it.
CREATE TABLE IF NOT EXISTS library_items (
    id           text PRIMARY KEY,
    user_id      text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id       text,
    kind         text NOT NULL,
    video_id     text,
    title        text NOT NULL,
    payload      jsonb NOT NULL,
    share_token  text UNIQUE,
    shared_at    timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);
CREATE INDEX IF NOT EXISTS library_user_created_idx ON library_items (user_id, created_at DESC);
"""


@dataclass(frozen=True)
class StoredHit:
    chunk: TranscriptChunk
    distance: float  # cosine distance, 0 = identical


@dataclass(frozen=True)
class StoredResult:
    payload: dict[str, Any]
    usage: Optional[dict[str, Any]]


class Store:
    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 5) -> None:
        self.dsn = dsn
        # The vector type must exist before connections register it, so migrate first
        # on a plain connection, then open the pool.
        self.migrate()
        self.pool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"autocommit": True},
            configure=register_vector,
            open=True,
        )

    @classmethod
    def from_env(cls) -> Optional["Store"]:
        """A Store if DATABASE_URL is set and reachable, otherwise None (features degrade, app still runs)."""
        dsn = (os.getenv("DATABASE_URL") or "").strip()
        if not dsn:
            logger.info("DATABASE_URL not set: no result cache, search uses local ChromaDB")
            return None
        try:
            store = cls(dsn)
            logger.info("Postgres connected: result cache + pgvector search enabled")
            return store
        except Exception as exc:
            logger.error("DATABASE_URL is set but Postgres is unusable (%s); running without it", exc)
            print(f"Warning: Postgres unavailable, running without cache: {type(exc).__name__}")
            return None

    def migrate(self) -> None:
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.pool.close()

    # ---------- lectures + transcripts ----------

    def get_transcript(self, video_id: str) -> Optional[List[TranscriptChunk]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT chunk_index, text, start_s, end_s, word_count FROM transcript_chunks "
                "WHERE video_id = %s ORDER BY chunk_index",
                (video_id,),
            ).fetchall()
        if not rows:
            return None
        return [
            TranscriptChunk(chunk_index=r[0], text=r[1], start=r[2], end=r[3], word_count=r[4]) for r in rows
        ]

    def save_transcript(self, video_id: str, youtube_url: str, chunks: Sequence[TranscriptChunk]) -> None:
        if not chunks:
            return
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO lectures (video_id, youtube_url, duration_s, chunk_count) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (video_id) DO UPDATE SET duration_s = EXCLUDED.duration_s, "
                "chunk_count = EXCLUDED.chunk_count",
                (video_id, youtube_url, float(chunks[-1].end), len(chunks)),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO transcript_chunks (video_id, chunk_index, text, start_s, end_s, word_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (video_id, chunk_index) DO UPDATE SET text = EXCLUDED.text, "
                    "start_s = EXCLUDED.start_s, end_s = EXCLUDED.end_s, word_count = EXCLUDED.word_count",
                    [(video_id, c.chunk_index, c.text, c.start, c.end, c.word_count) for c in chunks],
                )

    # ---------- embeddings + search ----------

    def has_embeddings(self, video_id: str) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT count(*) FILTER (WHERE embedding IS NOT NULL), count(*) "
                "FROM transcript_chunks WHERE video_id = %s",
                (video_id,),
            ).fetchone()
        return bool(row and row[1] > 0 and row[0] == row[1])

    def save_embeddings(self, video_id: str, chunk_indexes: Sequence[int], embeddings: Iterable[Any]) -> None:
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                "UPDATE transcript_chunks SET embedding = %s WHERE video_id = %s AND chunk_index = %s",
                [
                    (np.asarray(e, dtype=np.float32), video_id, int(i))
                    for i, e in zip(chunk_indexes, embeddings)
                ],
            )

    def search(self, video_id: str, query_embedding: Any, n: int) -> List[StoredHit]:
        q = np.asarray(query_embedding, dtype=np.float32)
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT chunk_index, text, start_s, end_s, word_count, embedding <=> %s AS distance "
                "FROM transcript_chunks WHERE video_id = %s AND embedding IS NOT NULL "
                "ORDER BY distance LIMIT %s",
                (q, video_id, n),
            ).fetchall()
        return [
            StoredHit(
                chunk=TranscriptChunk(chunk_index=r[0], text=r[1], start=r[2], end=r[3], word_count=r[4]),
                distance=float(r[5]),
            )
            for r in rows
        ]

    # ---------- generated results ----------

    def get_result(self, video_id: str, kind: str, language: str, prompt_version: str) -> Optional[StoredResult]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "UPDATE results SET hits = hits + 1 "
                "WHERE video_id = %s AND kind = %s AND language = %s AND prompt_version = %s "
                "RETURNING payload, usage",
                (video_id, kind, language, prompt_version),
            ).fetchone()
        if not row:
            return None
        return StoredResult(payload=row[0], usage=row[1])

    def save_result(
        self,
        video_id: str,
        kind: str,
        language: str,
        prompt_version: str,
        payload: dict[str, Any],
        usage: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO results (video_id, kind, language, prompt_version, payload, usage) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (video_id, kind, language, prompt_version) "
                "DO UPDATE SET payload = EXCLUDED.payload, usage = EXCLUDED.usage, created_at = now()",
                (video_id, kind, language, prompt_version, Jsonb(payload), Jsonb(usage) if usage else None),
            )

    # ---------- job log + metrics ----------

    def record_job(
        self,
        job_id: str,
        kind: str,
        video_id: Optional[str],
        status: str,
        *,
        cache_hit: bool = False,
        timings: Optional[dict[str, Any]] = None,
        usage: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, kind, video_id, status, cache_hit, timings, usage) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (job_id) DO UPDATE SET status = EXCLUDED.status, cache_hit = EXCLUDED.cache_hit, "
                "timings = EXCLUDED.timings, usage = EXCLUDED.usage",
                (
                    job_id,
                    kind,
                    video_id,
                    status,
                    cache_hit,
                    Jsonb(timings) if timings else None,
                    Jsonb(usage) if usage else None,
                ),
            )

    def job_metrics(self) -> dict[str, Any]:
        """Aggregate stats over finished jobs: counts, hit rate, typical latency for hits vs misses."""
        # Row factory on the cursor, not the connection: pooled connections are shared.
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT
                  count(*)                                          AS jobs,
                  count(*) FILTER (WHERE cache_hit)                 AS cache_hits,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY (timings->>'total_s')::float)
                    FILTER (WHERE cache_hit)                        AS median_total_s_hit,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY (timings->>'total_s')::float)
                    FILTER (WHERE NOT cache_hit)                    AS median_total_s_miss,
                  (SELECT count(*) FROM lectures)                   AS lectures,
                  (SELECT count(*) FROM results)                    AS cached_results
                FROM jobs WHERE status = 'done'
                """
            ).fetchone()
        out = dict(row or {})
        jobs = out.get("jobs") or 0
        out["cache_hit_rate"] = round((out.get("cache_hits") or 0) / jobs, 4) if jobs else None
        return out


