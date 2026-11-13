
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.core.config import settings
from app.prompts.memory_enrichment.registry import (
    get_memory_enrichment_prompt,
)
from app.schemas.memory_enrichment import MemoryEnrichmentV1


MEMORY_ENRICHMENT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class EnrichmentResult:
    enrichment: MemoryEnrichmentV1
    schema_version: str
    prompt_version: str
    model: str


class MemoryEnrichmentError(Exception):
    """Base exception for memory enrichment failures."""


class MemoryEnrichmentRefusalError(MemoryEnrichmentError):
    """Raised when the model refuses to enrich the memory."""


class MemoryEnrichmentIncompleteError(MemoryEnrichmentError):
    """Raised when the model does not complete its response."""


class MemoryEnrichmentValidationError(MemoryEnrichmentError):
    """Raised when the response fails application validation."""


class MemoryEnrichmentProviderError(MemoryEnrichmentError):
    """Raised when the OpenAI request fails."""


class MemoryEnrichmentService:
    MODEL = "gpt-5-mini"

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client: Any = client or AsyncOpenAI(
            api_key=settings.openai_api_key
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

        try:
            response = await self.client.responses.create(
                model=self.MODEL,
                instructions=prompt.instructions,
                input=content,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "memory_enrichment_v1",
                        "strict": True,
                        "schema": MemoryEnrichmentV1.model_json_schema(),
                    }
                },
            )
        except OpenAIError as exc:
            raise MemoryEnrichmentProviderError(
                "OpenAI enrichment request failed."
            ) from exc

        if response.status == "incomplete":
            raise MemoryEnrichmentIncompleteError(
                "OpenAI returned an incomplete enrichment response."
            )

        if response.status != "completed":
            raise MemoryEnrichmentProviderError(
                f"OpenAI response did not complete. Status: {response.status}"
            )

        if self._has_refusal(response):
            raise MemoryEnrichmentRefusalError(
                "OpenAI refused to enrich this memory."
            )

        try:
            enrichment = MemoryEnrichmentV1.model_validate_json(
                response.output_text
            )
        except ValidationError as exc:
            raise MemoryEnrichmentValidationError(
                "OpenAI returned enrichment that failed validation."
            ) from exc

        return EnrichmentResult(
            enrichment=enrichment,
            schema_version=MEMORY_ENRICHMENT_SCHEMA_VERSION,
            prompt_version=prompt.version,
            model=self.MODEL,
        )

    @staticmethod
    def _has_refusal(response: Any) -> bool:
        for output_item in getattr(response, "output", []):
            for content_item in getattr(output_item, "content", []):
                if getattr(content_item, "type", None) == "refusal":
                    return True

        return False
