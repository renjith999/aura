
import pytest

import memory_retriever


def test_retrieve_memories_combines_keyword_and_semantic_results(monkeypatch):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [
            {"id": "mem-1", "content": "Aura uses Python"},
            {"id": "mem-2", "content": "Aura uses FastAPI"},
        ],
    )
    monkeypatch.setattr(
        memory_retriever,
        "search_memories",
        lambda query: [
            {"id": "mem-1", "content": "Aura uses Python", "match_count": 2}
        ],
    )
    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        lambda query, top_k: [
            {"id": "mem-2", "content": "Aura uses FastAPI", "similarity": 0.99},
            {"id": "mem-1", "content": "Aura uses Python", "similarity": 0.2},
        ],
    )

    results = memory_retriever.retrieve_memories("Which technology powers Aura?")

    assert len(results) == 2
    assert results[0]["id"] == "mem-2"
    assert results[1]["id"] == "mem-1"
    assert results[0]["score"] > results[1]["score"]


def test_retrieve_memories_returns_empty_for_blank_query():
    assert memory_retriever.retrieve_memories("   ") == []


def test_retrieve_memories_returns_empty_when_no_memories(monkeypatch):
    monkeypatch.setattr(memory_retriever, "load_memories", lambda: [])
    assert memory_retriever.retrieve_memories("Aura") == []


def test_retrieve_memories_rejects_negative_weights():
    with pytest.raises(ValueError, match="negative"):
        memory_retriever.retrieve_memories(
            "Aura",
            keyword_weight=-0.1,
            semantic_weight=1.0,
        )


def test_retrieve_memories_rejects_zero_total_weight():
    with pytest.raises(ValueError, match="greater than zero"):
        memory_retriever.retrieve_memories(
            "Aura",
            keyword_weight=0,
            semantic_weight=0,
        )


def test_retrieve_memories_respects_top_k(monkeypatch):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [
            {"id": "mem-1", "content": "Python"},
            {"id": "mem-2", "content": "FastAPI"},
            {"id": "mem-3", "content": "JavaScript"},
        ],
    )
    monkeypatch.setattr(memory_retriever, "search_memories", lambda query: [])
    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        lambda query, top_k: [
            {"id": "mem-1", "content": "Python", "similarity": 0.9},
            {"id": "mem-2", "content": "FastAPI", "similarity": 0.8},
            {"id": "mem-3", "content": "JavaScript", "similarity": 0.7},
        ][:top_k],
    )

    results = memory_retriever.retrieve_memories("technology", top_k=2)

    assert len(results) == 2

def test_retrieve_memories_filters_results_below_min_score(monkeypatch):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [
            {"id": "mem-1", "content": "Python"},
            {"id": "mem-2", "content": "FastAPI"},
        ],
    )
    monkeypatch.setattr(memory_retriever, "search_memories", lambda query: [])
    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        lambda query, top_k: [
            {"id": "mem-1", "content": "Python", "similarity": 0.9},
            {"id": "mem-2", "content": "FastAPI", "similarity": 0.1},
        ],
    )

    results = memory_retriever.retrieve_memories(
        "Which technology?",
        min_score=0.5,
    )

    assert [item["id"] for item in results] == ["mem-1"]
    assert results[0]["score"] >= 0.5


def test_retrieve_memories_returns_empty_when_all_scores_below_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [{"id": "mem-1", "content": "Python"}],
    )
    monkeypatch.setattr(memory_retriever, "search_memories", lambda query: [])
    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        lambda query, top_k: [
            {"id": "mem-1", "content": "Python", "similarity": 0.1}
        ],
    )

    results = memory_retriever.retrieve_memories(
        "Favorite food?",
        min_score=0.5,
    )

    assert results == []


def test_retrieve_memories_skips_semantic_search_when_weight_is_zero(
    monkeypatch,
):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [{"id": "mem-1", "content": "Aura uses Python"}],
    )
    monkeypatch.setattr(
        memory_retriever,
        "search_memories",
        lambda query: [
            {"id": "mem-1", "content": "Aura uses Python", "match_count": 1}
        ],
    )

    def unexpected_semantic_search(*args, **kwargs):
        pytest.fail("semantic search should be skipped when its weight is zero")

    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        unexpected_semantic_search,
    )

    results = memory_retriever.retrieve_memories(
        "Aura Python",
        keyword_weight=1,
        semantic_weight=0,
    )

    assert [item["id"] for item in results] == ["mem-1"]
    assert results[0]["score"] == 1


def test_retrieve_memories_skips_keyword_search_when_weight_is_zero(
    monkeypatch,
):
    monkeypatch.setattr(
        memory_retriever,
        "load_memories",
        lambda: [{"id": "mem-1", "content": "Aura uses Python"}],
    )
    monkeypatch.setattr(
        memory_retriever,
        "semantic_search",
        lambda query, top_k: [
            {"id": "mem-1", "content": "Aura uses Python", "similarity": 0.8}
        ],
    )

    def unexpected_keyword_search(*args, **kwargs):
        pytest.fail("keyword search should be skipped when its weight is zero")

    monkeypatch.setattr(
        memory_retriever,
        "search_memories",
        unexpected_keyword_search,
    )

    results = memory_retriever.retrieve_memories(
        "Aura Python",
        keyword_weight=0,
        semantic_weight=1,
    )

    assert [item["id"] for item in results] == ["mem-1"]
    assert results[0]["score"] == 0.8