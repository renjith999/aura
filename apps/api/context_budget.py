
def calculate_context_budget(
    context_limit: int,
    system_tokens: int,
    question_tokens: int,
    memory_tokens: int,
    answer_tokens: int,
) -> dict:
    """Calculate how many tokens remain for conversation history."""

    values = {
        "context_limit": context_limit,
        "system_tokens": system_tokens,
        "question_tokens": question_tokens,
        "memory_tokens": memory_tokens,
        "answer_tokens": answer_tokens,
    }

    for name, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} cannot be negative")

    reserved_tokens = (
        system_tokens
        + question_tokens
        + memory_tokens
        + answer_tokens
    )

    history_budget = context_limit - reserved_tokens

    return {
        "context_limit": context_limit,
        "reserved_tokens": reserved_tokens,
        "history_budget": max(0, history_budget),
        "over_budget_by": max(0, -history_budget),
        "fits": history_budget >= 0,
    }


if __name__ == "__main__":
    result = calculate_context_budget(
        context_limit=10_000,
        system_tokens=1_000,
        question_tokens=500,
        memory_tokens=7_000,
        answer_tokens=2_000,
    )

    for name, value in result.items():
        print(f"{name}: {value}")
