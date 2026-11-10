
import pytest
import semantic_search


class FakeTensor:
    """Small stand-in for the tensor behaviour used by cos_sim."""

    def __init__(self, values):
        self.values = values

    def __getitem__(self, index):
        return FakeTensor(self.values[index])

    def tolist(self):
        return self.values


class FakeModel:
    """Deterministic embedding model for unit tests."""

    def __init__(self):
        self.memory_encoding_calls = 0

    @staticmethod
    def _vector(text):
        text = text.lower()

        if any(word in text for word in ("python", "fastapi", "technology",
                                          "technologies", "framework",
                                          "language")):
            return [1.0, 0.0, 0.0, 0.0]

        if "biryani" in text:
            return [0.0, 1.0, 0.0, 0.0]

        if "javascript" in text:
            return [0.0, 0.0, 1.0, 0.0]

        if "memory" in text or "memories" in text:
            return [0.0, 0.0, 0.0, 1.0]

        return [0.0, 0.0, 0.0, 0.0]

    def encode(self, sentences, **kwargs):
        if isinstance(sentences, list):
            self.memory_encoding_calls += 1
            return [self._vector(sentence) for sentence in sentences]

        return self._vector(sentences)


def fake_cos_sim(query_embedding, memory_embeddings):
    scores = [
        sum(a * b for a, b in zip(query_embedding, memory_embedding))
        for memory_embedding in memory_embeddings
    ]

    return FakeTensor([scores])


@pytest.fixture
def fake_model(monkeypatch):
    model = FakeModel()

    monkeypatch.setattr(semantic_search, "model", model)
    monkeypatch.setattr(semantic_search, "cos_sim", fake_cos_sim)
    monkeypatch.setattr(semantic_search, "_cached_memories", None)
    monkeypatch.setattr(semantic_search, "_cached_embeddings", None)

    return model


def test_semantic_search_returns_relevant_memories(
    monkeypatch,
    fake_model,
):
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


def test_semantic_search_returns_empty_for_no_memories(monkeypatch):
    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: [],
    )

    assert semantic_search.semantic_search("What is Aura?") == []


def test_semantic_search_respects_top_k(monkeypatch, fake_model):
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


def test_memory_embeddings_are_cached(monkeypatch, fake_model):
    memories = [
        {"id": "mem-1", "content": "Aura uses Python and FastAPI"}
    ]

    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: memories,
    )

    semantic_search.semantic_search("What technology does Aura use?")
    semantic_search.semantic_search("Which framework does Aura use?")

    assert fake_model.memory_encoding_calls == 1


def test_memory_embeddings_refresh_when_content_changes(
    monkeypatch,
    fake_model,
):
    memories = [{"id": "mem-1", "content": "Aura uses Python"}]

    monkeypatch.setattr(
        semantic_search,
        "load_memories",
        lambda: memories,
    )

    semantic_search.semantic_search("What language does Aura use?")

    memories[0]["content"] = "Aura uses JavaScript"

    semantic_search.semantic_search("What language does Aura use?")

    assert fake_model.memory_encoding_calls == 2
