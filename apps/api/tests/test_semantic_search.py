import semantic_search


def test_semantic_search_returns_relevant_memories(tmp_path, monkeypatch):
    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: [
            {
                "id": "mem-python",
                "content": "The Aura backend uses Python and FastAPI.",
                "category": "technology",
            },
            {
                "id": "mem-food",
                "content": "My favorite food is biryani.",
                "category": "personal",
            },
        ],
    )

    results = semantic_search.semantic_search(
        "Which technologies power Aura?",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0]["id"] == "mem-python"
    assert results[0]["similarity"] > results[1]["similarity"]


def test_semantic_search_returns_empty_for_blank_query():
    assert semantic_search.semantic_search("   ") == []


def test_semantic_search_returns_empty_for_no_memories(
    monkeypatch,
):
    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: [],
    )

    assert semantic_search.semantic_search("What is Aura?") == []


def test_semantic_search_respects_top_k(monkeypatch):
    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: [
            {"id": "mem-1", "content": "Aura uses Python."},
            {"id": "mem-2", "content": "Aura uses FastAPI."},
            {"id": "mem-3", "content": "Aura stores memories."},
        ],
    )

    results = semantic_search.semantic_search(
        "What technology does Aura use?",
        top_k=2,
    )

    assert len(results) == 2


def test_memory_embeddings_are_cached(monkeypatch):
    import semantic_search

    memories = [{"id": "mem-1", "content": "Aura uses Python and FastAPI"}]

    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: memories,
    )
    monkeypatch.setattr(
        semantic_search,
        "_cached_memories",
        None,
    )
    monkeypatch.setattr(
        semantic_search,
        "_cached_embeddings",
        None,
    )

    original_encode = semantic_search.model.encode
    memory_encoding_calls = 0

    def tracked_encode(sentences, **kwargs):
        nonlocal memory_encoding_calls

        if isinstance(sentences, list):
            memory_encoding_calls += 1

        return original_encode(sentences, **kwargs)

    monkeypatch.setattr(
        semantic_search.model,
        "encode",
        tracked_encode,
    )

    semantic_search.semantic_search("What technology does Aura use?")
    semantic_search.semantic_search("Which framework does Aura use?")

    assert memory_encoding_calls == 1


def test_memory_embeddings_refresh_when_content_changes(monkeypatch):
    import semantic_search

    memories = [{"id": "mem-1", "content": "Aura uses Python"}]

    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: memories,
    )
    monkeypatch.setattr(
        semantic_search,
        "_cached_memories",
        None,
    )
    monkeypatch.setattr(
        semantic_search,
        "_cached_embeddings",
        None,
    )

    original_encode = semantic_search.model.encode
    memory_encoding_calls = 0

    def tracked_encode(sentences, **kwargs):
        nonlocal memory_encoding_calls

        if isinstance(sentences, list):
            memory_encoding_calls += 1

        return original_encode(sentences, **kwargs)

    monkeypatch.setattr(
        semantic_search.model,
        "encode",
        tracked_encode,
    )

    semantic_search.semantic_search("What language does Aura use?")

    memories[0]["content"] = "Aura uses JavaScript"

    semantic_search.semantic_search("What language does Aura use?")

    assert memory_encoding_calls == 2
