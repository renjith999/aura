from dataclasses import dataclass
from decimal import Decimal

from app.core.config import OpenAIModelPricing

TOKENS_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class UsageCounts:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None


@dataclass(frozen=True)
class CostEstimate:
    amount: Decimal | None
    currency: str
    pricing_version: str
    input_per_million: Decimal | None
    output_per_million: Decimal | None
    cached_input_per_million: Decimal | None
    cache_write_input_per_million: Decimal | None


def calculate_cost_estimate(
    model: str,
    usage: UsageCounts | None,
    pricing: dict[str, OpenAIModelPricing],
    pricing_version: str,
) -> CostEstimate:
    """Estimate cost from reported tokens and an explicit pricing snapshot."""
    rates = pricing.get(model)
    if rates is None:
        return CostEstimate(None, "USD", pricing_version, None, None, None, None)

    amount: Decimal | None = None
    if usage is not None:
        required_counts = (
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
        optional_counts = (
            usage.cached_input_tokens,
            usage.cache_write_input_tokens,
            usage.reasoning_output_tokens,
        )
        counts_are_valid = all(
            value is None or value >= 0 for value in required_counts + optional_counts
        ) and all(value is not None for value in required_counts)
        cached = usage.cached_input_tokens or 0
        cache_write = usage.cache_write_input_tokens or 0
        input_details_known = (
            usage.cached_input_tokens is not None
            or rates.cached_input_per_million is None
        ) and (
            usage.cache_write_input_tokens is not None
            or rates.cache_write_input_per_million is None
        )
        subsets_fit = (
            usage.input_tokens is not None
            and cached + cache_write <= usage.input_tokens
        )
        total_is_consistent = (
            usage.total_tokens is not None
            and usage.input_tokens is not None
            and usage.output_tokens is not None
            and usage.total_tokens >= usage.input_tokens
            and usage.total_tokens == usage.input_tokens + usage.output_tokens
        )
        rates_cover_usage = (
            cached == 0 or rates.cached_input_per_million is not None
        ) and (cache_write == 0 or rates.cache_write_input_per_million is not None)

        if (
            counts_are_valid
            and input_details_known
            and subsets_fit
            and total_is_consistent
            and rates_cover_usage
        ):
            uncached = usage.input_tokens - cached - cache_write
            amount = (
                Decimal(uncached) * rates.input_per_million
                + Decimal(usage.output_tokens) * rates.output_per_million
                + Decimal(cached) * (rates.cached_input_per_million or Decimal(0))
                + Decimal(cache_write)
                * (rates.cache_write_input_per_million or Decimal(0))
            ) / TOKENS_PER_MILLION

    return CostEstimate(
        amount=amount,
        currency="USD",
        pricing_version=pricing_version,
        input_per_million=rates.input_per_million,
        output_per_million=rates.output_per_million,
        cached_input_per_million=rates.cached_input_per_million,
        cache_write_input_per_million=rates.cache_write_input_per_million,
    )
