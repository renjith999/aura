import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.openai_service import OpenAIService
from app.services.tool_executor import ToolExecutionError


def create_test_service():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock()),
    )
    return OpenAIService(client=client)


@pytest.mark.asyncio
async def test_generate_response_with_tools_returns_normal_response():
    service = create_test_service()

    response = SimpleNamespace(
        output=[],
        output_text="Hello from Aura!",
    )

    with patch.object(
        service.client.responses,
        "create",
        new_callable=AsyncMock,
        return_value=response,
    ) as mock_create:
        result = await service.generate_response_with_tools("Hello")

    assert result == "Hello from Aura!"
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_with_tools_executes_function_call():
    service = create_test_service()

    tool_call = SimpleNamespace(
        type="function_call",
        name="search_memories",
        arguments=json.dumps({"query": "What do I remember?"}),
        call_id="call_test_123",
    )

    first_response = SimpleNamespace(
        id="resp_test_123",
        output=[tool_call],
        output_text="",
    )

    final_response = SimpleNamespace(
        output=[],
        output_text="Aura found your memories.",
    )

    with (
        patch.object(
            service.client.responses,
            "create",
            new_callable=AsyncMock,
            side_effect=[first_response, final_response],
        ) as mock_create,
        patch(
            "app.services.openai_service.execute_tool",
            return_value={
                "ok": True,
                "data": [{"content": "Aura uses Python."}],
                "error": None,
            },
        ) as mock_execute,
    ):
        result = await service.generate_response_with_tools("What do I remember?")

    assert result == "Aura found your memories."
    mock_execute.assert_called_once_with(
        "search_memories",
        {"query": "What do I remember?"},
    )
    assert mock_create.await_count == 2

    second_call = mock_create.await_args_list[1]
    assert second_call.kwargs["previous_response_id"] == "resp_test_123"

    submitted_output = second_call.kwargs["input"][0]
    assert submitted_output["type"] == "function_call_output"
    assert submitted_output["call_id"] == "call_test_123"
    assert json.loads(submitted_output["output"])["ok"] is True


@pytest.mark.asyncio
async def test_malformed_tool_arguments_return_controlled_error():
    service = create_test_service()

    tool_call = SimpleNamespace(
        type="function_call",
        name="search_memories",
        arguments="{invalid json",
        call_id="call_bad_json",
    )

    first_response = SimpleNamespace(
        id="resp_bad_json",
        output=[tool_call],
        output_text="",
    )

    final_response = SimpleNamespace(
        output=[],
        output_text="I couldn't search the memories this time.",
    )

    with patch.object(
        service.client.responses,
        "create",
        new_callable=AsyncMock,
        side_effect=[first_response, final_response],
    ) as mock_create:
        result = await service.generate_response_with_tools("What do I remember?")

    assert result == "I couldn't search the memories this time."
    assert mock_create.await_count == 2

    submitted_output = mock_create.await_args_list[1].kwargs["input"][0]
    tool_result = json.loads(submitted_output["output"])

    assert tool_result["ok"] is False
    assert tool_result["error"] == (
        "Invalid tool arguments. Please provide valid JSON."
    )


@pytest.mark.asyncio
async def test_tool_calling_stops_after_three_iterations():
    service = create_test_service()

    tool_call = SimpleNamespace(
        type="function_call",
        name="search_memories",
        arguments=json.dumps({"query": "Find a memory"}),
        call_id="call_loop",
    )

    repeated_response = SimpleNamespace(
        id="resp_loop",
        output=[tool_call],
        output_text="",
    )

    with (
        patch.object(
            service.client.responses,
            "create",
            new_callable=AsyncMock,
            return_value=repeated_response,
        ) as mock_create,
        patch(
            "app.services.openai_service.execute_tool",
            return_value={"ok": True, "data": [], "error": None},
        ),
    ):
        with pytest.raises(
            ToolExecutionError,
            match="Tool-calling limit reached.",
        ):
            await service.generate_response_with_tools("Find a memory")

    assert mock_create.await_count == 3
