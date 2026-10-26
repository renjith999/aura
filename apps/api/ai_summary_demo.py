
import asyncio

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

client = AsyncOpenAI()


async def summarize_conversation(messages: list[str]) -> str:
    conversation = "\n".join(
        f"- {message}" for message in messages
    )

    response = await client.responses.create(
        model="gpt-5-mini",
        instructions=(
            "Summarize the conversation for a personal assistant's memory. "
            "Preserve important facts, preferences, decisions, and plans. "
            "Do not invent details. Keep the summary concise."
        ),
        input=conversation,
    )

    return response.output_text


async def main():
    messages = [
        "I'm building Aura using Python and FastAPI.",
        "I installed the OpenAI SDK.",
        "I learned about token budgets.",
        "I want to add long-term memory and voice features.",
        "I prefer keeping the backend in Python.",
    ]

    summary = await summarize_conversation(messages)
    print("AI-generated summary:")
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
