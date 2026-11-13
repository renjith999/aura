import pytest
from pydantic import ValidationError

from app.prompts.memory_enrichment.registry import get_memory_enrichment_prompt
from app.schemas.memory_enrichment import MemoryEnrichmentV1


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_importance_accepts_each_score_in_the_existing_range(score):
    result = MemoryEnrichmentV1(
        summary=None,
        category=None,
        memory_type=None,
        tags=[],
        entities=[],
        importance=score,
    )
    assert result.importance == score


def test_importance_accepts_null_when_value_cannot_be_determined():
    result = MemoryEnrichmentV1(
        summary=None,
        category=None,
        memory_type=None,
        tags=[],
        entities=[],
        importance=None,
    )
    assert result.importance is None


@pytest.mark.parametrize("score", [0, 6, 2.5, "high"])
def test_importance_rejects_values_outside_existing_integer_range(score):
    with pytest.raises(ValidationError):
        MemoryEnrichmentV1(
            summary=None,
            category=None,
            memory_type=None,
            tags=[],
            entities=[],
            importance=score,
        )


def test_current_prompt_documents_approved_importance_rubric():
    instructions = get_memory_enrichment_prompt().instructions.lower()
    assert "importance scoring rules" in instructions
    assert "long-term usefulness for future assistance" in instructions
    assert "confidence in the memory's accuracy" in instructions
    assert "do not use recency alone" in instructions
    for anchor in (
        "1: little future use",
        "2: some context may help later",
        "3: useful personal, work, learning, or project context",
        "4: strong ongoing value",
        "5: critical to retain",
        "use null when the memory does not provide enough information",
        "preserve the original memory content unchanged",
    ):
        assert anchor in instructions
