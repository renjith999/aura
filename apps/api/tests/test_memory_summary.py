
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest 
from pydantic import ValidationError

from app.prompts.memory_enrichment.registry import (
    CURRENT_PROMPT_VERSION,
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.memory_enrichment_service import MemoryEnrichmentService


def create_valid_enrichment(summary: str | None) -> MemoryEnrichmentV1:
    return MemoryEnrichmentV1(
        summary=summary,
        category="project",
        memory_type="goal",
        tags=["Aura", "Python"],
        entities=[
            {"name": "Aura", "entity_type": "other"},
            {"name": "Python", "entity_type": "technology"},
        ],
        importance=5,
    )


# ---------------------------------------------------------
# Summary schema validation
# ---------------------------------------------------------


def test_summary_accepts_valid_concise_text():
    result = create_valid_enrichment(
        "Planning to learn React Native next year."
    )

    assert result.summary == "Planning to learn React Native next year."


def test_summary_accepts_null_when_information_is_insufficient():
    result = create_valid_enrichment(None)

    assert result.summary is None


def test_summary_rejects_blank_text():
    with pytest.raises(ValidationError, match="Summary must not be blank"):
        create_valid_enrichment("   ")


def test_summary_rejects_empty_text():
    with pytest.raises(ValidationError, match="Summary must not be blank"):
        create_valid_enrichment("")


def test_summary_accepts_exactly_500_characters():
    summary = "A" * 500

    result = create_valid_enrichment(summary)

    assert result.summary == summary
    assert len(result.summary) == 500


def test_summary_rejects_more_than_500_characters():
    summary = "A" * 501

    with pytest.raises(
        ValidationError,
        match="Summary must be at most 500 characters",
    ):
        create_valid_enrichment(summary)


def test_summary_strips_leading_and_trailing_whitespace():
    result = create_valid_enrichment(
        "  Planning to learn React Native.  "
    )

    assert result.summary == "Planning to learn React Native."


# ---------------------------------------------------------
# Prompt version and summary instructions
# ---------------------------------------------------------


def test_current_prompt_version_is_1_4_0():
    assert CURRENT_PROMPT_VERSION == "1.4.0"


def test_current_prompt_contains_summary_quality_rules():
    prompt = get_memory_enrichment_prompt()

    instructions = prompt.instructions.lower()

    expected_rules = [
        "preserves the most important information",
        "dates, numbers, relationships",
        "preserve negation and uncertainty",
        "do not turn intentions or plans into completed actions",
        "do not add information from external or general knowledge",
        "null when the content is too ambiguous",
        "within 500 characters",
    ]

    for rule in expected_rules:
        assert rule in instructions


def test_previous_prompt_version_remains_available():
    prompt = get_memory_enrichment_prompt("1.0.0")

    assert prompt.version == "1.0.0"


def test_new_prompt_version_is_available():
    prompt = get_memory_enrichment_prompt("1.4.0")

    assert prompt.version == "1.4.0"
    assert prompt.instructions


# ---------------------------------------------------------
# Service integration with current prompt
# ---------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_service_uses_current_summary_prompt():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock()),
    )

    expected = create_valid_enrichment(
        "Plans to learn React Native next year; learning has not started."
    )

    client.responses.create.return_value = SimpleNamespace(
        status="completed",
        output_text=expected.model_dump_json(),
        output=[],
    )

    service = MemoryEnrichmentService(client=client)

    result = await service.enrich(
        "I am planning to learn React Native next year. "
        "I have not started learning it yet."
    )

    assert result.summary == expected.summary

    call_args = client.responses.create.await_args

    current_prompt = get_memory_enrichment_prompt()

    assert call_args.kwargs["instructions"] == current_prompt.instructions
    assert call_args.kwargs["input"] == (
        "I am planning to learn React Native next year. "
        "I have not started learning it yet."
    )
