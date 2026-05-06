"""
Purpose: Agent 3 — Search Agent (chunk embeddings → ChromaDB semantic search).

Part 4: Local embeddings + persistent vector search.

Key decisions (per requirements):
- Embeddings run locally using `sentence-transformers` with `all-MiniLM-L6-v2`
- Vectors are stored in ChromaDB using a persistent directory: `backend/chroma_db`
- Each YouTube video gets its own ChromaDB collection named by `video_id`
- If a collection already exists, we reuse it and skip re-indexing
- Search returns the top 3 most relevant chunks with timestamps

Data flow: Consumes Transcript Agent chunks; serves `/search` or dashboard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import chromadb
from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

from models.schemas import TranscriptChunk


class SearchAgentError(Exception):
    """Raised for any SearchAgent failure with a clear descriptive message."""


@dataclass(frozen=True)
class SearchHit:
    """
    Internal search hit returned by the SearchAgent.

    Note: API layer converts this to a Pydantic `SearchResult`.
    """

    text: str
    start: float
    end: float
    chunk_index: int
    relevance_score: float


class SearchAgent:
    """
    Agent 3 — embed transcript chunks and perform semantic search.
    """

    def __init__(
        self,
        *,
        model_name: str = "all-MiniLM-L6-v2",
        persist_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize embedding model and persistent Chroma client.

        Args:
            model_name: SentenceTransformers model name.
            persist_dir: Persistent directory for ChromaDB.
        """
        self.model = SentenceTransformer(model_name)

        # Step: Allow deploy platforms (e.g. Railway) to mount a persistent volume and
        # configure Chroma's storage path via env var, while keeping a safe local default.
        env_dir = (os.getenv("CHROMA_DB_PATH") or "").strip()
        resolved_dir = persist_dir if persist_dir is not None else (env_dir or "./chroma_db")

        self._persist_dir = Path(resolved_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self._persist_dir))

    def index_chunks(self, video_id: str, chunks: Sequence[TranscriptChunk]) -> bool:
        """
        Index transcript chunks into ChromaDB for a given video.

        Requirements:
        - Use `video_id` as collection name.
        - If collection already exists, skip re-indexing and return True.
        - Store each chunk with metadata: start, end, chunk_index, word_count.

        Returns:
            True if indexing is available for this video (either reused or newly indexed).
        """
        if not video_id.strip():
            raise SearchAgentError("video_id is required for indexing.")
        if not chunks:
            raise SearchAgentError("No chunks provided for indexing.")

        if self._collection_exists(video_id):
            return True

        collection = self.client.get_or_create_collection(name=video_id)

        texts = [c.text for c in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

        ids = [f"{video_id}:{c.chunk_index}" for c in chunks]
        metadatas: List[Dict[str, Any]] = [
            {
                "start": float(c.start),
                "end": float(c.end),
                "chunk_index": int(c.chunk_index),
                "word_count": int(c.word_count),
            }
            for c in chunks
        ]

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )
        return True

    def search(self, video_id: str, query: str, n_results: int = 3) -> List[SearchHit]:
        """
        Search a previously indexed video collection for the query.

        Args:
            video_id: YouTube video ID whose collection should be searched.
            query: Natural-language question/query.
            n_results: Number of results to return (defaults to 3).

        Returns:
            List of SearchHit with relevance_score normalized to [0,1].

        Raises:
            SearchAgentError: if the collection does not exist or query is empty.
        """
        if not video_id.strip():
            raise SearchAgentError("video_id is required for searching.")
        if not query or not query.strip():
            raise SearchAgentError("query must be a non-empty string.")
        if n_results <= 0:
            raise SearchAgentError("n_results must be >= 1.")

        if not self._collection_exists(video_id):
            raise SearchAgentError("Collection not found for video_id (video not processed yet).")

        collection = self.client.get_collection(name=video_id)
        q_embedding = self.model.encode([query.strip()], show_progress_bar=False, normalize_embeddings=True)[0]

        res = collection.query(
            query_embeddings=[q_embedding.tolist()],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        documents = (res.get("documents") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]

        hits: List[SearchHit] = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            # Step: Convert distance to a bounded relevance score.
            # For normalized embeddings, distance is typically cosine distance.
            # We map any non-negative distance into (0,1] via 1/(1+d), then clamp to [0,1].
            d = float(dist) if dist is not None else 0.0
            score = 1.0 / (1.0 + max(d, 0.0))
            score = max(0.0, min(1.0, score))

            hits.append(
                SearchHit(
                    text=str(doc),
                    start=float(meta.get("start", 0.0)),
                    end=float(meta.get("end", 0.0)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    relevance_score=score,
                )
            )

        return hits

    def _collection_exists(self, name: str) -> bool:
        """
        Check if a ChromaDB collection exists.
        """
        try:
            self.client.get_collection(name=name)
            return True
        except Exception:
            return False


def run_search_agent_placeholder() -> None:
    """
    Placeholder for embedding + vector retrieval.

    Inputs/outputs: Defined in a later part; no-op in Part 1.
    """
    # Step: Reserved for embeddings + ChromaDB wiring.
    return None
