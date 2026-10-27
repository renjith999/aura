import pytest

import memory_store


def test_save_memory_creates_a_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    memory = memory_store.save_memory(
        "The Aura backend uses Python and FastAPI.",
        "Technology",
    )

    assert memory["id"].startswith("mem-")
    assert memory["category"] == "technology"
    assert memory["source"] == "user"
    assert memory["created_at"]
    assert memory["updated_at"]
    assert memory_store.load_memories() == [memory]


def test_save_memory_prevents_exact_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    first = memory_store.save_memory(
        "Aura uses Python",
        "technology",
    )

    second = memory_store.save_memory(
        "  AURA   USES PYTHON  ",
        "technology",
    )

    assert first["id"] == second["id"]
    assert len(memory_store.load_memories()) == 1


def test_search_memories_finds_matching_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    memory_store.save_memory(
        "The Aura backend uses Python and FastAPI.",
        "technology",
    )

    results = memory_store.search_memories("Aura Python")

    assert len(results) == 1
    assert results[0]["content"] == ("The Aura backend uses Python and FastAPI.")
    assert results[0]["match_count"] == 2
    assert results[0]["matched_words"] == ["aura", "python"]


def test_update_memory_preserves_id_and_creation_time(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    original = memory_store.save_memory(
        "Aura uses Python",
        "technology",
    )

    updated = memory_store.update_memory(
        original["id"],
        "Aura uses Python and FastAPI",
    )

    assert updated["id"] == original["id"]
    assert updated["created_at"] == original["created_at"]
    assert updated["updated_at"]
    assert updated["content"] == "Aura uses Python and FastAPI"


def test_update_memory_rejects_empty_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    memory_store.save_memory("Aura uses Python", "technology")

    with pytest.raises(ValueError, match="Memory content cannot be empty"):
        memory_store.update_memory("mem-001", "   ")


def test_find_similar_memories_detects_related_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    memory_store.save_memory(
        "The Aura backend uses Python and FastAPI.",
        "technology",
    )

    results = memory_store.find_similar_memories(
        "I am learning Python for my Aura project"
    )

    assert len(results) == 1
    assert results[0]["memory"]["id"].startswith("mem-")
    assert results[0]["matched_words"] == ["aura", "python"]


def test_review_new_memory_requests_review_for_similar_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    memory_store.save_memory(
        "The Aura backend uses Python and FastAPI.",
        "technology",
    )

    result = memory_store.review_new_memory("I am learning Python for my Aura project")

    assert result["action"] == "review"
    assert len(result["matches"]) == 1


def test_resolve_memory_rejects_unknown_decision():
    with pytest.raises(ValueError, match="decision must be"):
        memory_store.resolve_memory(
            "Aura uses Python",
            "unknown",
        )


def test_resolve_memory_update_preserves_id_and_changes_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    original = memory_store.save_memory(
        "Aura uses Python",
        "technology",
    )

    updated = memory_store.resolve_memory(
        content="Aura uses Python and FastAPI",
        decision="update",
        memory_id=original["id"],
        category="technology",
    )

    assert updated["id"] == original["id"]
    assert updated["content"] == "Aura uses Python and FastAPI"
    assert len(memory_store.load_memories()) == 1


def test_update_memory_rejects_empty_category_without_changing_record(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    original = memory_store.save_memory(
        "Aura uses Python",
        "technology",
    )

    with pytest.raises(ValueError, match="Memory category cannot be empty"):
        memory_store.update_memory(
            original["id"],
            "Aura uses Python and FastAPI",
            new_category="   ",
        )

    stored = memory_store.load_memories()[0]
    assert stored["content"] == original["content"]
    assert stored["category"] == original["category"]


def test_update_memory_rejects_unknown_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    with pytest.raises(ValueError, match="Memory not found: mem-does-not-exist"):
        memory_store.update_memory(
            "mem-does-not-exist",
            "New content",
        )


def test_update_memory_rejects_duplicate_content_without_changing_records(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    original = memory_store.save_memory("Aura uses Python", "technology")
    duplicate = memory_store.save_memory("Aura uses Rust", "technology")

    with pytest.raises(
        ValueError,
        match=f"Memory content already exists: {original['id']}",
    ):
        memory_store.update_memory(
            duplicate["id"],
            "  AURA   USES PYTHON  ",
        )

    assert memory_store.load_memories() == [original, duplicate]


def test_update_memory_rejects_duplicate_content(tmp_path, monkeypatch):
    monkeypatch.setattr(
        memory_store,
        "MEMORY_FILE",
        tmp_path / "memories.json",
    )

    first = memory_store.save_memory(
        "Aura uses Python",
        "technology",
    )
    second = memory_store.save_memory(
        "Aura uses FastAPI",
        "technology",
    )

    with pytest.raises(
        ValueError,
        match=f"Memory content already exists: {first['id']}",
    ):
        memory_store.update_memory(
            second["id"],
            "  AURA   USES PYTHON ",
        )

    stored = memory_store.load_memories()

    assert len(stored) == 2
    assert stored[0]["content"] == "Aura uses Python"
    assert stored[1]["id"] == second["id"]
    assert stored[1]["content"] == "Aura uses FastAPI"
