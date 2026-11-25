import asyncio
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from app.core.config import settings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the selected embedding provider is not configured."""


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider fails."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingConfigurationError(
            "Local embeddings require the optional dependency. "
            "Install with `uv sync --extra local-embeddings`."
        ) from exc

    return SentenceTransformer(model_name)


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    provider: str
    model: str
    dimensions: int
    input_tokens: int | None = None
    request_id: str | None = None


class EmbeddingService:
    """Create embeddings with the configured remote or local provider."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.provider = settings.embedding_provider
        self._client: Any = client
        self._local_model: Any | None = None

        if self.provider == "openai" and self._client is None:
            api_key = settings.openai_api_key.get_secret_value()
            if not api_key:
                raise EmbeddingConfigurationError(
                    "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai."
                )
            self._client = AsyncOpenAI(
                api_key=api_key,
                timeout=40.0,
                max_retries=0,
            )

    async def embed(self, text: str) -> EmbeddingResult:
        if not text or not text.strip():
            raise ValueError("Embedding input must not be empty.")

        if self.provider == "openai":
            return await self._embed_openai(text)

        try:
            return await asyncio.to_thread(self._embed_local, text)
        except EmbeddingConfigurationError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                "Local sentence-transformers embedding failed.",
                retryable=False,
            ) from exc

    async def _embed_openai(self, text: str) -> EmbeddingResult:
        try:
            response = await self._client.embeddings.create(
                input=text,
                model=settings.openai_embedding_model,
                dimensions=settings.openai_embedding_dimensions,
            )
        except OpenAIError as exc:
            raise EmbeddingProviderError(
                "OpenAI embedding request failed.",
                retryable=self._is_retryable_provider_error(exc),
            ) from exc

        if not response.data:
            raise EmbeddingProviderError(
                "OpenAI returned no embedding data.", retryable=False
            )

        vector = self._validate_vector(
            response.data[0].embedding,
            expected_dimensions=settings.openai_embedding_dimensions,
        )
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
            input_tokens = None

        return EmbeddingResult(
            vector=vector,
            provider="openai",
            model=getattr(response, "model", settings.openai_embedding_model),
            dimensions=len(vector),
            input_tokens=input_tokens,
            request_id=getattr(response, "_request_id", None),
        )

    def _embed_local(self, text: str) -> EmbeddingResult:
        if self._local_model is None:
            self._local_model = _load_sentence_transformer(
                settings.sentence_transformers_model
            )

        encoded = self._local_model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        vector = self._validate_vector(encoded.tolist())
        return EmbeddingResult(
            vector=vector,
            provider="sentence-transformers",
            model=settings.sentence_transformers_model,
            dimensions=len(vector),
        )

    @staticmethod
    def _validate_vector(
        values: Any,
        expected_dimensions: int | None = None,
    ) -> list[float]:
        try:
            vector = [float(value) for value in values]
        except (TypeError, ValueError, OverflowError) as exc:
            raise EmbeddingProviderError(
                "Embedding provider returned an invalid vector.", retryable=False
            ) from exc

        if not vector or (expected_dimensions and len(vector) != expected_dimensions):
            raise EmbeddingProviderError(
                "Embedding provider returned a vector with an unexpected dimension.",
                retryable=False,
            )
        if any(not math.isfinite(value) for value in vector):
            raise EmbeddingProviderError(
                "Embedding provider returned a non-finite vector value.",
                retryable=False,
            )
        return vector

    @staticmethod
    def _is_retryable_provider_error(error: OpenAIError) -> bool:
        if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError)):
            return True
        if isinstance(error, APIStatusError):
            return error.status_code in {408, 409, 429} or error.status_code >= 500
        return getattr(error, "status_code", None) is None