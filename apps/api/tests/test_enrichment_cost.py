from decimal import Decimal

from app.core.config import OpenAIModelPricing
from app.services.enrichment_cost import UsageCounts, calculate_cost_estimate


def test_cost_estimate_uses_model_specific_decimal_rates():
    pricing = {
        "model-a": OpenAIModelPricing(
            input_per_million=Decimal("1.25"),
            output_per_million=Decimal("4.50"),
        ),
        "model-b": OpenAIModelPricing(
            input_per_million=Decimal("2.00"),
            output_per_million=Decimal("8.00"),
        ),
    }
    usage = UsageCounts(input_tokens=1_000, output_tokens=200, total_tokens=1_200)

    first = calculate_cost_estimate("model-a", usage, pricing, "test-pricing-v1")
    second = calculate_cost_estimate("model-b", usage, pricing, "test-pricing-v1")

    assert first.amount == Decimal("0.00215")
    assert second.amount == Decimal("0.0036")
    assert first.pricing_version == "test-pricing-v1"


def test_cost_estimate_prices_cached_and_cache_write_tokens_separately():
    rates = OpenAIModelPricing(
        input_per_million=Decimal("10"),
        output_per_million=Decimal("20"),
        cached_input_per_million=Decimal("2"),
        cache_write_input_per_million=Decimal("12"),
    )
    usage = UsageCounts(
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cached_input_tokens=30,
        cache_write_input_tokens=20,
        reasoning_output_tokens=10,
    )

    result = calculate_cost_estimate("model-a", usage, {"model-a": rates}, "v2")

    assert result.amount == Decimal("0.0018")


def test_missing_or_uncertain_usage_never_becomes_zero_cost():
    rates = OpenAIModelPricing(
        input_per_million=Decimal("1"),
        output_per_million=Decimal("2"),
        cached_input_per_million=Decimal("0.5"),
    )

    no_usage = calculate_cost_estimate("model-a", None, {"model-a": rates}, "v1")
    incomplete_usage = calculate_cost_estimate(
        "model-a",
        UsageCounts(input_tokens=100, output_tokens=None, total_tokens=None),
        {"model-a": rates},
        "v1",
    )
    unknown_model = calculate_cost_estimate(
        "model-b",
        UsageCounts(input_tokens=100, output_tokens=10, total_tokens=110),
        {"model-a": rates},
        "v1",
    )

    assert no_usage.amount is None
    assert incomplete_usage.amount is None
    assert unknown_model.amount is None


def test_missing_cached_rate_or_invalid_counts_leave_estimate_unknown():
    rates = OpenAIModelPricing(
        input_per_million=Decimal("1"), output_per_million=Decimal("2")
    )
    cached_without_rate = calculate_cost_estimate(
        "model-a",
        UsageCounts(
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            cached_input_tokens=10,
            cache_write_input_tokens=0,
        ),
        {"model-a": rates},
        "v1",
    )
    invalid_counts = calculate_cost_estimate(
        "model-a",
        UsageCounts(input_tokens=100, output_tokens=10, total_tokens=100),
        {"model-a": rates},
        "v1",
    )

    assert cached_without_rate.amount is None
    assert invalid_counts.amount is None
