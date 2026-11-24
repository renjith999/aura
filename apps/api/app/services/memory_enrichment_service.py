from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import ValidationError

from app.core.config import settings
from app.prompts.memory_enrichment.registry import (
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1
from app.services.enrichment_cost import UsageCounts

MEMORY_ENRICHMENT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class EnrichmentAttemptData:
    response_model: str | None
    provider_status: str | None
    response_id: str | None
    request_id: str | None
    usage: UsageCounts | None
    response_received_at: datetime | None


@dataclass(frozen=True)
class EnrichmentResult:
    enrichment: MemoryEnrichmentV1
    schema_version: str
    prompt_version: str
    model: str
    attempt: EnrichmentAttemptData


class MemoryEnrichmentError(Exception):
    """Base exception for memory enrichment failures."""

    def __init__(
        self,
        message: str,
        attempt: EnrichmentAttemptData | None = None,
    ) -> None:
        super().__init__(message)
        self.attempt = attempt


class MemoryEnrichmentRefusalError(MemoryEnrichmentError):
    """Raised when the model refuses to enrich the memory."""


class MemoryEnrichmentIncompleteError(MemoryEnrichmentError):
    """Raised when the model does not complete its response."""


class MemoryEnrichmentValidationError(MemoryEnrichmentError):
    """Raised when the response fails application validation."""


class MemoryEnrichmentProviderError(MemoryEnrichmentError):
    """Raised when the OpenAI request fails."""

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        attempt: EnrichmentAttemptData | None = None,
    ) -> None:
        super().__init__(message, attempt=attempt)
        self.retryable = retryable


class MemoryEnrichmentService:
    MODEL = "gpt-5-mini"

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client: Any = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=40.0,
            max_retries=0,
        )

    async def enrich(
        self,
        content: str,
        prompt_version: str | None = None,
    ) -> MemoryEnrichmentV1:
        result = await self.enrich_with_metadata(content, prompt_version)
        return result.enrichment

    async def enrich_with_metadata(
        self,
        content: str,
        prompt_version: str | None = None,
    ) -> EnrichmentResult:
        if not content or not content.strip():
            raise ValueError("Memory content must not be empty.")

        prompt = get_memory_enrichment_prompt(prompt_version)

        request_kwargs = {
            "model": self.MODEL,
            "instructions": prompt.instructions,
            "input": content,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "memory_enrichment_v1",
                    "strict": True,
                    "schema": MemoryEnrichmentV1.model_json_schema(),
                }
            },
        }

        request_id = None
        try:
            responses = self.client.responses
            if hasattr(responses, "with_raw_response"):
                raw_response = await responses.with_raw_response.create(
                    **request_kwargs
                )
                response = raw_response.parse()
                request_id = raw_response.headers.get("x-request-id")
            else:
                # Retain compatibility with small custom/test clients.
                response = await responses.create(**request_kwargs)
                request_id = getattr(response, "_request_id", None)
        except OpenAIError as exc:
            attempt = EnrichmentAttemptData(
                response_model=None,
                provider_status=None,
                response_id=None,
                request_id=getattr(exc, "request_id", None),
                usage=None,
                response_received_at=None,
            )
            raise MemoryEnrichmentProviderError(
                "OpenAI enrichment request failed.",
                retryable=self._is_retryable_provider_error(exc),
                attempt=attempt,
            ) from exc

        attempt = self._extract_attempt_data(
            response,
            request_id=request_id,
        )

        if response.status == "incomplete":
            raise MemoryEnrichmentIncompleteError(
                "OpenAI returned an incomplete enrichment response.",
                attempt=attempt,
            )

        if response.status != "completed":
            raise MemoryEnrichmentProviderError(
                f"OpenAI response did not complete. Status: {response.status}",
                retryable=True,
                attempt=attempt,
            )

        if self._has_refusal(response):
            raise MemoryEnrichmentRefusalError(
                "OpenAI refused to enrich this memory.",
                attempt=attempt,
            )

        try:
            enrichment = MemoryEnrichmentV1.model_validate_json(response.output_text)
        except ValidationError as exc:
            raise MemoryEnrichmentValidationError(
                "OpenAI returned enrichment that failed validation.",
                attempt=attempt,
            ) from exc

        return EnrichmentResult(
            enrichment=enrichment,
            schema_version=MEMORY_ENRICHMENT_SCHEMA_VERSION,
            prompt_version=prompt.version,
            model=self.MODEL,
            attempt=attempt,
        )

    @classmethod
    def _extract_attempt_data(
        cls,
        response: Any,
        request_id: str | None,
    ) -> EnrichmentAttemptData:
        usage_object = getattr(response, "usage", None)
        usage = None
        if usage_object is not None:
            input_details = getattr(usage_object, "input_tokens_details", None)
            output_details = getattr(usage_object, "output_tokens_details", None)
            usage = UsageCounts(
                input_tokens=cls._valid_token_count(
                    getattr(usage_object, "input_tokens", None)
                ),
                output_tokens=cls._valid_token_count(
                    getattr(usage_object, "output_tokens", None)
                ),
                total_tokens=cls._valid_token_count(
                    getattr(usage_object, "total_tokens", None)
                ),
                cached_input_tokens=cls._valid_token_count(
                    getattr(input_details, "cached_tokens", None)
                ),
                cache_write_input_tokens=cls._valid_token_count(
                    getattr(input_details, "cache_write_tokens", None)
                ),
                reasoning_output_tokens=cls._valid_token_count(
                    getattr(output_details, "reasoning_tokens", None)
                ),
            )
        model = getattr(response, "model", None)
        response_id = getattr(response, "id", None)
        status = getattr(response, "status", None)
        return EnrichmentAttemptData(
            response_model=model if isinstance(model, str) else None,
            provider_status=status if isinstance(status, str) else None,
            response_id=response_id if isinstance(response_id, str) else None,
            request_id=request_id,
            usage=usage,
            response_received_at=datetime.now(UTC),
        )

    @staticmethod
    def _valid_token_count(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _has_refusal(response: Any) -> bool:
        for output_item in getattr(response, "output", []):
            for content_item in getattr(output_item, "content", []):
                if getattr(content_item, "type", None) == "refusal":
                    return True

        return False

    @staticmethod
    def _is_retryable_provider_error(error: OpenAIError) -> bool:
        if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError)):
            return True

        if isinstance(error, APIStatusError):
            return error.status_code in {408, 409, 429} or error.status_code >= 500

        # SDK errors without a status code are treated as transient, but remain
        # bounded by the application-level attempt limit.
        return getattr(error, "status_code", None) is None
