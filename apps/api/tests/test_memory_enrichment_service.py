
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai import OpenAIError

from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.memory_enrichment_service import (
    MemoryEnrichmentIncompleteError,
    MemoryEnrichmentProviderError,
    MemoryEnrichmentRefusalError,
    MemoryEnrichmentService,
    MemoryEnrichmentValidationError,
)
from app.prompts.memory_enrichment.registry import (
    CURRENT_PROMPT_VERSION,
    get_memory_enrichment_prompt,
)

def create_test_service():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock()),
    )
    return MemoryEnrichmentService(client=client)


def create_enrichment():
    return MemoryEnrichmentV1(
        summary="User is building Aura with Python and FastAPI.",
        category="project",
        memory_type="goal",
        tags=["Aura", "Python"],
        entities=[
            {"name": "Aura", "entity_type": "other"},
            {"name": "FastAPI", "entity_type": "technology"},
        ],
        importance=5,
    )


def create_response(
    status="completed",
    output_text=None,
    output=None,
):
    return SimpleNamespace(
        status=status,
        output_text=output_text,
        output=output or [],
    )


@pytest.mark.asyncio
async def test_enrich_returns_validated_memory_enrichment():
    service = create_test_service()
    expected = create_enrichment()

    response = create_response(
        output_text=expected.model_dump_json(),
    )

    service.client.responses.create.return_value = response

    result = await service.enrich(
        "I am building Aura using Python and FastAPI."
    )

    assert result == expected
    service.client.responses.create.assert_awaited_once()

    call_args = service.client.responses.create.await_args
    assert call_args.kwargs["model"] == "gpt-5-mini"
    assert call_args.kwargs["input"] == (
        "I am building Aura using Python and FastAPI."
    )

    text_format = call_args.kwargs["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "memory_enrichment_v1"
    assert text_format["strict"] is True
    assert text_format["schema"] == MemoryEnrichmentV1.model_json_schema()


@pytest.mark.asyncio
async def test_enrich_rejects_empty_content():
    service = create_test_service()

    with pytest.raises(ValueError, match="must not be empty"):
        await service.enrich("   ")

    service.client.responses.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_handles_model_refusal():
    service = create_test_service()

    refusal = SimpleNamespace(type="refusal")
    message = SimpleNamespace(content=[refusal])

    response = create_response(
        output_text="This is not valid JSON",
        output=[message],
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentRefusalError):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_enrich_handles_incomplete_response():
    service = create_test_service()

    response = create_response(
        status="incomplete",
        output_text='{"summary":',
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentIncompleteError):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_enrich_handles_missing_output_text():
    service = create_test_service()

    response = create_response(
        output_text="",
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentValidationError):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_enrich_handles_invalid_structured_output():
    service = create_test_service()

    response = create_response(
        output_text='{"summary": "Test", "category": "invalid"}',
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentValidationError):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_enrich_handles_openai_error():
    service = create_test_service()

    service.client.responses.create.side_effect = OpenAIError(
        "Simulated OpenAI failure"
    )

    with pytest.raises(MemoryEnrichmentProviderError):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_enrich_handles_unexpected_response_status():
    service = create_test_service()

    response = create_response(
        status="failed",
        output_text="",
    )

    service.client.responses.create.return_value = response

    with pytest.raises(
        MemoryEnrichmentProviderError,
        match="did not complete",
    ):
        await service.enrich("Some memory content")


@pytest.mark.asyncio
async def test_incomplete_response_is_checked_before_json_validation():
    service = create_test_service()

    response = create_response(
        status="incomplete",
        output_text="This is deliberately invalid JSON",
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentIncompleteError):
        await service.enrich("Some memory content")

def test_prompt_registry_returns_current_version_by_default():
    prompt = get_memory_enrichment_prompt()

    assert prompt.version == "1.4.0"
    assert prompt.version == CURRENT_PROMPT_VERSION
    assert prompt.instructions
    assert "memory enrichment assistant" in prompt.instructions


def test_prompt_registry_returns_explicit_version():
    prompt = get_memory_enrichment_prompt("1.0.0")

    assert prompt.version == "1.0.0"


def test_prompt_registry_rejects_unknown_version():
    with pytest.raises(
        ValueError,
        match="Unsupported memory enrichment prompt version",
    ):
        get_memory_enrichment_prompt("99.0.0")


@pytest.mark.asyncio
async def test_enrich_uses_registered_prompt_instructions():
    service = create_test_service()
    expected = create_enrichment()

    service.client.responses.create.return_value = create_response(
        output_text=expected.model_dump_json(),
    )

    await service.enrich("Some memory content")

    call_args = service.client.responses.create.await_args

    prompt = get_memory_enrichment_prompt()

    assert call_args.kwargs["instructions"] == prompt.instructions


@pytest.mark.asyncio
async def test_enrich_accepts_explicit_prompt_version():
    service = create_test_service()
    expected = create_enrichment()

    service.client.responses.create.return_value = create_response(
        output_text=expected.model_dump_json(),
    )

    await service.enrich(
        "Some memory content",
        prompt_version="1.0.0",
    )

    call_args = service.client.responses.create.await_args

    assert call_args.kwargs["instructions"] == (
        get_memory_enrichment_prompt("1.0.0").instructions
    )


@pytest.mark.asyncio
async def test_enrich_rejects_unknown_prompt_version_before_api_call():
    service = create_test_service()

    with pytest.raises(
        ValueError,
        match="Unsupported memory enrichment prompt version",
    ):
        await service.enrich(
            "Some memory content",
            prompt_version="99.0.0",
        )

    service.client.responses.create.assert_not_awaited()
