
import pytest
from pydantic import ValidationError

from app.prompts.memory_enrichment.registry import (
    CURRENT_PROMPT_VERSION,
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1


@pytest.mark.parametrize(
    ("category", "memory_type"),
    [
        ("project", "decision"),
        ("learning", "goal"),
        ("finance", "fact"),
        ("health", "preference"),
        ("work", "achievement"),
        ("personal", "event"),
        ("other", "instruction"),
    ],
)
def test_enrichment_accepts_valid_category_and_memory_type(
    category,
    memory_type,
):
    result = MemoryEnrichmentV1(
        summary="Example memory.",
        category=category,
        memory_type=memory_type,
        tags=[],
        entities=[],
        importance=3,
    )

    assert result.category.value == category
    assert result.memory_type.value == memory_type


@pytest.mark.parametrize(
    "category",
    ["technology", "business", "unknown", ""],
)
def test_enrichment_rejects_invalid_category(category):
    with pytest.raises(ValidationError):
        MemoryEnrichmentV1(
            summary="Example memory.",
            category=category,
            memory_type="fact",
            tags=[],
            entities=[],
            importance=3,
        )


@pytest.mark.parametrize(
    "memory_type",
    ["task", "plan", "status", "unknown", ""],
)
def test_enrichment_rejects_invalid_memory_type(memory_type):
    with pytest.raises(ValidationError):
        MemoryEnrichmentV1(
            summary="Example memory.",
            category="project",
            memory_type=memory_type,
            tags=[],
            entities=[],
            importance=3,
        )


def test_enrichment_accepts_unknown_category_as_other():
    result = MemoryEnrichmentV1(
        summary="Example memory.",
        category="other",
        memory_type="fact",
        tags=[],
        entities=[],
        importance=2,
    )

    assert result.category.value == "other"


def test_enrichment_accepts_null_category_when_ambiguous():
    result = MemoryEnrichmentV1(
        summary="Example memory.",
        category=None,
        memory_type="fact",
        tags=[],
        entities=[],
        importance=2,
    )

    assert result.category is None


def test_enrichment_accepts_null_memory_type_when_ambiguous():
    result = MemoryEnrichmentV1(
        summary="Example memory.",
        category="project",
        memory_type=None,
        tags=[],
        entities=[],
        importance=2,
    )

    assert result.memory_type is None


def test_current_prompt_version_is_1_3_0():
    assert CURRENT_PROMPT_VERSION == "1.3.0"
    assert get_memory_enrichment_prompt().version == "1.3.0"


def test_previous_prompt_versions_remain_available():
    assert get_memory_enrichment_prompt("1.0.0").version == "1.0.0"
    assert get_memory_enrichment_prompt("1.1.0").version == "1.1.0"


def test_current_prompt_contains_category_rules():
    prompt = get_memory_enrichment_prompt()
    instructions = prompt.instructions.lower()

    expected_rules = [
        "category represents the primary subject area",
        "memory type represents the kind of information",
        "determine category and memory_type independently",
        "use project when the memory primarily concerns",
        "use other when the subject or information type is identifiable",
        "use null when the category or memory type cannot be determined",
        "do not assign multiple categories or memory types",
    ]

    for rule in expected_rules:
        assert rule in instructions
