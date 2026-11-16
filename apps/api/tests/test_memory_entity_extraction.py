import pytest
from pydantic import ValidationError

from app.prompts.memory_enrichment import v1_3, v1_4
from app.prompts.memory_enrichment.registry import get_memory_enrichment_prompt
from app.schemas.memory_enrichment import EntityType, MemoryEnrichmentV1, MemoryEntity


def test_entity_schema_preserves_existing_eight_types():
    assert {item.value for item in EntityType} == {
        "person",
        "organization",
        "technology",
        "product",
        "location",
        "certification",
        "role",
        "other",
    }


@pytest.mark.parametrize("entity_type", [item.value for item in EntityType])
def test_memory_entity_accepts_each_existing_type(entity_type):
    entity = MemoryEntity(name="  Example Entity  ", entity_type=entity_type)

    assert entity.name == "Example Entity"
    assert entity.entity_type.value == entity_type


@pytest.mark.parametrize("entity_type", ["company", "tool", "unknown", ""])
def test_memory_entity_rejects_types_outside_existing_taxonomy(entity_type):
    with pytest.raises(ValidationError):
        MemoryEntity(name="Example", entity_type=entity_type)


def test_memory_entity_rejects_blank_names_and_extra_fields():
    with pytest.raises(ValidationError):
        MemoryEntity(name="  ", entity_type="person")

    with pytest.raises(ValidationError):
        MemoryEntity(name="Example", entity_type="person", confidence=0.9)


def test_enrichment_entity_limit_and_deduplication_are_unchanged():
    entity = {"name": "Microsoft", "entity_type": "organization"}
    result = MemoryEnrichmentV1(
        summary="Example.", category=None, memory_type=None, tags=[],
        entities=[entity, {"name": "microsoft", "entity_type": "organization"}],
        importance=None,
    )
    assert len(result.entities) == 1

    with pytest.raises(ValidationError):
        MemoryEnrichmentV1(
            summary="Example.", category=None, memory_type=None, tags=[],
            entities=[{"name": f"Entity {i}", "entity_type": "other"} for i in range(21)],
            importance=None,
        )


def test_v1_4_adds_grounded_entity_rules_without_changing_v1_3():
    current = get_memory_enrichment_prompt("1.4.0")
    assert current.version == "1.4.0"
    assert v1_4.INSTRUCTIONS.startswith(v1_3.INSTRUCTIONS)
    instructions = current.instructions.lower()
    for rule in (
        "explicitly mentioned or unambiguously identified",
        "person, organization, technology, product, location, certification, role, other",
        "preserve each entity's meaningful spelling and capitalization",
        "do not guess a person's identity",
        "remove duplicate entities",
        "empty array when no reliable entities",
        "no more than 20 entities",
        "do not invent relationships",
    ):
        assert rule in instructions


@pytest.mark.parametrize(
    "rule",
    [
        "category represents the primary subject area",
        "memory type represents the kind of information",
        "determine category and memory_type independently",
        "keep the summary within 500 characters",
        "format every tag in lowercase kebab-case",
    ],
)
def test_v1_4_preserves_v1_3_categorization_summary_and_tag_rules(rule):
    assert rule in v1_4.INSTRUCTIONS.lower()
