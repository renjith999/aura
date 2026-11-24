from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from openai import OpenAIError
from pydantic import SecretStr

from app.core.config import settings
from app.prompts.memory_enrichment.registry import (
    CURRENT_PROMPT_VERSION,
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.memory_enrichment_service import (
    MemoryEnrichmentIncompleteError,
    MemoryEnrichmentProviderError,
    MemoryEnrichmentRefusalError,
    MemoryEnrichmentService,
    MemoryEnrichmentValidationError,
)


def create_test_service():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock()),
    )
    return MemoryEnrichmentService(client=client)


def test_default_client_uses_approved_timeout_and_application_retries(
    monkeypatch,
):
    dummy_api_key = "sk-test-dummy-enrichment-key"
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(dummy_api_key))
    constructor = Mock()
    monkeypatch.setattr(
        "app.services.memory_enrichment_service.AsyncOpenAI",
        constructor,
    )
    MemoryEnrichmentService()

    constructor.assert_called_once_with(
        api_key=dummy_api_key,
        timeout=40.0,
        max_retries=0,
    )
    passed_api_key = constructor.call_args.kwargs["api_key"]
    assert not isinstance(passed_api_key, SecretStr)
    assert str(settings.openai_api_key) not in passed_api_key


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
    usage=None,
    response_id="resp-test-id",
    model="gpt-5-mini-2026-01-01",
):
    return SimpleNamespace(
        id=response_id,
        model=model,
        status=status,
        output_text=output_text,
        output=output or [],
        usage=usage,
    )


@pytest.mark.asyncio
async def test_enrich_returns_validated_memory_enrichment():
    service = create_test_service()
    expected = create_enrichment()

    response = create_response(
        output_text=expected.model_dump_json(),
    )

    service.client.responses.create.return_value = response

    result = await service.enrich("I am building Aura using Python and FastAPI.")

    assert result == expected
    service.client.responses.create.assert_awaited_once()

    call_args = service.client.responses.create.await_args
    assert call_args.kwargs["model"] == "gpt-5-mini"
    assert call_args.kwargs["input"] == ("I am building Aura using Python and FastAPI.")

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
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
            input_tokens_details=SimpleNamespace(
                cached_tokens=0,
                cache_write_tokens=0,
            ),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentRefusalError) as error:
        await service.enrich("Some memory content")
    assert error.value.attempt.usage.total_tokens == 13


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
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=1,
            total_tokens=11,
            input_tokens_details=SimpleNamespace(
                cached_tokens=0,
                cache_write_tokens=0,
            ),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentValidationError) as error:
        await service.enrich("Some memory content")
    assert error.value.attempt.usage.total_tokens == 11


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

    provider_error = OpenAIError("Simulated OpenAI failure")
    provider_error.request_id = "req-provider-error"
    service.client.responses.create.side_effect = provider_error

    with pytest.raises(MemoryEnrichmentProviderError) as error:
        await service.enrich("Some memory content")
    assert error.value.attempt.request_id == "req-provider-error"
    assert error.value.attempt.usage is None


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_api_key_in_error_or_logs(caplog):
    dummy_api_key = "sk-test-dummy-enrichment-key"
    service = create_test_service()
    service.client.responses.create.side_effect = OpenAIError(
        f"Provider error containing {dummy_api_key}"
    )

    with pytest.raises(MemoryEnrichmentProviderError) as error:
        await service.enrich("Some memory content")

    assert dummy_api_key not in str(error.value)
    assert dummy_api_key not in caplog.text


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
    ) as error:
        await service.enrich("Some memory content")

    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_incomplete_response_is_checked_before_json_validation():
    service = create_test_service()

    response = create_response(
        status="incomplete",
        output_text="This is deliberately invalid JSON",
        usage=SimpleNamespace(
            input_tokens=42,
            output_tokens=8,
            total_tokens=50,
            input_tokens_details=SimpleNamespace(
                cached_tokens=2,
                cache_write_tokens=0,
            ),
            output_tokens_details=SimpleNamespace(reasoning_tokens=1),
        ),
    )

    service.client.responses.create.return_value = response

    with pytest.raises(MemoryEnrichmentIncompleteError) as error:
        await service.enrich("Some memory content")
    assert error.value.attempt.usage.input_tokens == 42
    assert error.value.attempt.usage.output_tokens == 8
    assert error.value.attempt.response_id == "resp-test-id"
    assert error.value.attempt.provider_status == "incomplete"


@pytest.mark.asyncio
async def test_usage_and_success_request_id_are_captured_from_raw_response():
    service = create_test_service()
    expected = create_enrichment()
    response = create_response(
        output_text=expected.model_dump_json(),
        usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=40,
            total_tokens=160,
            input_tokens_details=SimpleNamespace(
                cached_tokens=20,
                cache_write_tokens=5,
            ),
            output_tokens_details=SimpleNamespace(reasoning_tokens=7),
        ),
    )
    raw_response = SimpleNamespace(
        parse=Mock(return_value=response),
        headers={"x-request-id": "req-test-id"},
    )
    service.client.responses.with_raw_response = SimpleNamespace(
        create=AsyncMock(return_value=raw_response)
    )

    result = await service.enrich_with_metadata("Original memory text")

    assert result.enrichment == expected
    assert result.attempt.response_id == "resp-test-id"
    assert result.attempt.request_id == "req-test-id"
    assert result.attempt.response_model == "gpt-5-mini-2026-01-01"
    assert result.attempt.usage.input_tokens == 120
    assert result.attempt.usage.output_tokens == 40
    assert result.attempt.usage.total_tokens == 160
    assert result.attempt.usage.cached_input_tokens == 20
    assert result.attempt.usage.cache_write_input_tokens == 5
    assert result.attempt.usage.reasoning_output_tokens == 7


@pytest.mark.asyncio
async def test_missing_response_usage_is_preserved_as_unavailable():
    service = create_test_service()
    expected = create_enrichment()
    service.client.responses.create.return_value = create_response(
        output_text=expected.model_dump_json(),
    )

    result = await service.enrich_with_metadata("Original memory text")

    assert result.attempt.usage is None


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
