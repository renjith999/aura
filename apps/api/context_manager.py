
import tiktoken

encoding = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(encoding.encode(text))


def build_context(
    system_instructions: str,
    question: str,
    recent_messages: list[str],
    memories: list[str],
    context_limit: int = 10_000,
    answer_budget: int = 2_000,
) -> dict:
    """Build a token-budgeted context without making an API call."""

    if context_limit < 0 or answer_budget < 0:
        raise ValueError("Token budgets cannot be negative")

    sections = {
        "system_instructions": system_instructions,
        "question": question,
    }

    for name, value in sections.items():
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")

    for name, items in {
        "recent_messages": recent_messages,
        "memories": memories,
    }.items():
        if not all(isinstance(item, str) for item in items):
            raise TypeError(f"Every item in {name} must be a string")

    fixed_tokens = (
        count_tokens(system_instructions)
        + count_tokens(question)
        + answer_budget
    )

    available = context_limit - fixed_tokens
    if available < 0:
        raise ValueError(
            "System instructions and question exceed the input budget"
        )

    selected_memories = []
    selected_messages = []

    # Reserve space for memories first.
    for memory in memories:
        cost = count_tokens(memory)
        if cost <= available:
            selected_memories.append(memory)
            available -= cost

    # Keep the newest messages that fit.
    for message in reversed(recent_messages):
        cost = count_tokens(message)
        if cost > available:
            break
        selected_messages.append(message)
        available -= cost

    selected_messages.reverse()

    return {
        "system_instructions": system_instructions,
        "question": question,
        "memories": selected_memories,
        "recent_messages": selected_messages,
        "input_tokens_estimate": context_limit - answer_budget - available,
        "remaining_history_budget": available,
        "answer_budget": answer_budget,
    }


if __name__ == "__main__":
    context = build_context(
        system_instructions="You are Aura, a helpful personal assistant.",
        question="Which laptop did I buy?",
        recent_messages=[
            "I am building Aura with Python.",
            "I bought a Lenovo LOQ laptop.",
            "I am learning token budgeting.",
        ],
        memories=[
            "The user owns a Lenovo LOQ laptop.",
            "Aura uses a Python and FastAPI backend.",
        ],
    )

    print("Built context:")
    for key, value in context.items():
        print(f"{key}: {value}")
