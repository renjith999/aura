import json
from json import JSONDecodeError
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.tool_executor import (
    SEARCH_MEMORIES_SCHEMA,
    ToolExecutionError,
    execute_tool,
)


class OpenAIService:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client: Any = client or AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_response(self, message: str) -> str:
        response = await self.client.responses.create(
            model="gpt-5-mini",
            input=message,
        )

        return response.output_text

    async def generate_response_with_tools(self, message: str) -> str:
        response = await self.client.responses.create(
            model="gpt-5-mini",
            input=message,
            tools=[SEARCH_MEMORIES_SCHEMA],
        )

        for _iteration in range(2):
            tool_calls = [
                item for item in response.output if item.type == "function_call"
            ]

            if not tool_calls:
                return response.output_text

            tool_outputs = []

            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.arguments)
                    result = execute_tool(tool_call.name, arguments)
                except JSONDecodeError:
                    result = {
                        "ok": False,
                        "data": None,
                        "error": "Invalid tool arguments. Please provide valid JSON.",
                    }

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(result),
                    }
                )

            response = await self.client.responses.create(
                model="gpt-5-mini",
                previous_response_id=response.id,
                input=tool_outputs,
                tools=[SEARCH_MEMORIES_SCHEMA],
            )

        raise ToolExecutionError("Tool-calling limit reached.")
