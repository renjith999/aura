
def summarize_conversation(messages: list[str]) -> str:
    """
    A rule-based demo that selects important messages.
    This is not an AI-generated summary yet.
    """
    keywords = [
        "aura",
        "python",
        "fastapi",
        "openai",
        "memory",
        "voice",
        "decision",
        "plan",
        "prefer",
        "important",
    ]

    important_messages = []

    for message in messages:
        if any(keyword in message.lower() for keyword in keywords):
            important_messages.append(message)

    if not important_messages:
        return "No key information identified."

    return "Key information from the conversation:\n- " + "\n- ".join(
        important_messages
    )


if __name__ == "__main__":
    messages = [
        "I'm building Aura using Python and FastAPI.",
        "I installed the OpenAI SDK.",
        "I learned about token budgets.",
        "I want to add long-term memory and voice features.",
        "I had tea this morning.",
        "I prefer keeping the backend in Python.",
    ]

    summary = summarize_conversation(messages)
    print(summary)
