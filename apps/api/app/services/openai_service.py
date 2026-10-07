from openai import AsyncOpenAI

from app.core.config import settings


class OpenAIService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_response(self, message: str) -> str:
        response = await self.client.responses.create(
            model="gpt-5-mini",
            input=message,
        )

        return response.output_text
