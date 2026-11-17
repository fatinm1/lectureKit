from agents.search_agent import SearchAgent
from models.schemas import TranscriptChunk


def _chunks():
    texts = [
        "gradient descent updates weights using the gradient of the loss",
        "backpropagation applies the chain rule through the computation graph",
        "the course logistics include homework deadlines and office hours",
    ]
    return [
        TranscriptChunk(text=t, start=i * 60.0, end=i * 60.0 + 59, chunk_index=i, word_count=len(t.split()))
        for i, t in enumerate(texts)
    ]


def test_index_and_search_ranks_relevant_chunk_first(tmp_path):
    agent = SearchAgent(persist_dir=tmp_path)
    assert agent.index_chunks("abcDEF12345", _chunks())
    hits = agent.search("abcDEF12345", "chain rule backpropagation", n_results=3)
    assert hits[0].chunk_index == 1
    assert all(0.0 <= h.relevance_score <= 1.0 for h in hits)
    # Scores are cosine similarity, so they must be strictly ordered by relevance.
    assert hits[0].relevance_score > hits[-1].relevance_score


def test_new_collections_use_cosine_space(tmp_path):
    agent = SearchAgent(persist_dir=tmp_path)
    agent.index_chunks("abcDEF12345", _chunks())
    col = agent.client.get_collection(agent._sanitize_collection_name("abcDEF12345"))
    assert (col.metadata or {}).get("hnsw:space") == "cosine"


def test_reindex_is_skipped(tmp_path):
    agent = SearchAgent(persist_dir=tmp_path)
    agent.index_chunks("abcDEF12345", _chunks())
    agent.index_chunks("abcDEF12345", _chunks())
    col = agent.client.get_collection(agent._sanitize_collection_name("abcDEF12345"))
    assert col.count() == 3


def test_ids_with_leading_dash_are_valid_collection_names(tmp_path):
    agent = SearchAgent(persist_dir=tmp_path)
    assert agent.index_chunks("-bcDEF1234_", _chunks())
    assert agent.search("-bcDEF1234_", "homework deadlines")[0].chunk_index == 2
