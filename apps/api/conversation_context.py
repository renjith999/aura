
import tiktoken

encoding = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(encoding.encode(text))


def build_context(messages: list[str], history_budget: int) -> dict:
    """Keep the newest messages that fit within the token budget."""
    if history_budget < 0:
        raise ValueError("history_budget cannot be negative")

    recent_messages = []
    used_tokens = 0

    # Process newest messages first, then restore chronological order.
    for message in reversed(messages):
        message_tokens = count_tokens(message)

        if used_tokens + message_tokens > history_budget:
            break

        recent_messages.append(message)
        used_tokens += message_tokens

    recent_messages.reverse()

    return {
        "recent_messages": recent_messages,
        "used_tokens": used_tokens,
        "omitted_messages": len(messages) - len(recent_messages),
    }


if __name__ == "__main__":
    messages = [
        "I want to build Aura.",
        "I chose Python for the backend.",
        "I installed FastAPI.",
        "I learned about tokens.",
        "I counted tokens using tiktoken.",
        "I learned about context budgets.",
    ]

    result = build_context(messages, history_budget=20)

    print("Recent messages:")
    for message in result["recent_messages"]:
        print("-", message)

    print("\nTokens used:", result["used_tokens"])
    print("Messages omitted:", result["omitted_messages"])
