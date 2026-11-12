import pytest
from pydantic import ValidationError

from app.prompts.memory_enrichment import v1, v1_1, v1_2, v1_3
from app.prompts.memory_enrichment.registry import (
    CURRENT_PROMPT_VERSION,
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1


def build_enrichment(tags: list[str]) -> MemoryEnrichmentV1:
    return MemoryEnrichmentV1(
        summary="Test summary",
        category=None,
        memory_type=None,
        tags=tags,
        entities=[],
        importance=None,
    )


@pytest.mark.parametrize(
    ("input_tags", "expected"),
    [
        (
            ["React Native", "REACT NATIVE", "react-native"],
            ["react-native"],
        ),
        (
            [" FastAPI ", "Node.js", "Python"],
            ["fastapi", "node-js", "python"],
        ),
        (
            ["AI   Engineering", "AI_Engineering", "AI---Engineering"],
            ["ai-engineering"],
        ),
        (
            ["தமிழ் மொழி", "தமிழ்-மொழி"],
            ["தமிழ்-மொழி"],
        ),
        (
            ["---", "!!!", "   "],
            [],
        ),
    ],
)
def test_normalize_tags(input_tags: list[str], expected: list[str]) -> None:
    result = build_enrichment(input_tags)

    assert result.tags == expected


def test_empty_tags_are_allowed() -> None:
    result = build_enrichment([])

    assert result.tags == []


def test_tag_count_cannot_exceed_ten() -> None:
    tags = [f"tag-{index}" for index in range(11)]

    with pytest.raises(ValidationError):
        build_enrichment(tags)


def test_ten_tags_are_allowed() -> None:
    tags = [f"tag-{index}" for index in range(10)]

    result = build_enrichment(tags)

    assert len(result.tags) == 10


def test_current_prompt_version_is_v1_3() -> None:
    assert CURRENT_PROMPT_VERSION == "1.3.0"
    assert get_memory_enrichment_prompt().version == "1.3.0"


@pytest.mark.parametrize(
    "prompt_module",
    [v1, v1_1, v1_2, v1_3],
)
def test_previous_and_current_prompt_versions_remain_available(
    prompt_module,
) -> None:
    prompt = get_memory_enrichment_prompt(prompt_module.PROMPT_VERSION)

    assert prompt.version == prompt_module.PROMPT_VERSION
    assert prompt.instructions == prompt_module.INSTRUCTIONS


def test_v1_3_preserves_summary_and_categorization_rules() -> None:
    instructions = v1_3.INSTRUCTIONS

    assert "Preserve negation and uncertainty." in instructions
    assert "Do not turn intentions or plans into completed actions." in instructions
    assert "Determine category and memory_type independently." in instructions
    assert "Use project when the memory primarily concerns a specific" in instructions


def test_v1_3_contains_tag_generation_rules() -> None:
    instructions = v1_3.INSTRUCTIONS

    assert "lowercase kebab-case" in instructions
    assert "Never generate more than 10 tags." in instructions
    assert "Return an empty array when no useful tags can be identified." in instructions
    assert "Avoid generic tags" in instructions