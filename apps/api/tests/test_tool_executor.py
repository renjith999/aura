from unittest.mock import patch

import pytest

from app.services.tool_executor import (
    SEARCH_MEMORIES_SCHEMA,
    TOOL_REGISTRY,
    ToolExecutionError,
    execute_tool,
)


def test_unknown_tool_is_rejected():
    result = execute_tool("delete_all_memories", {})

    assert result == {
        "ok": False,
        "data": None,
        "error": "Unsupported tool.",
    }


def test_search_tool_rejects_blank_query():
    result = execute_tool(
        "search_memories",
        {"query": "   "},
    )

    assert result == {
        "ok": False,
        "data": None,
        "error": "Invalid tool arguments.",
    }


def test_search_tool_rejects_invalid_top_k():
    for top_k in (0, 21):
        result = execute_tool(
            "search_memories",
            {
                "query": "What technologies power Aura?",
                "top_k": top_k,
            },
        )

        assert result == {
            "ok": False,
            "data": None,
            "error": "Invalid tool arguments.",
        }


@pytest.mark.parametrize("top_k", [1, 20])
def test_search_tool_accepts_top_k_boundaries(top_k):
    with patch(
        "app.services.tool_executor.retrieve_memories",
        return_value=[],
    ) as mock_retrieve:
        result = execute_tool(
            "search_memories",
            {"query": "What do I remember?", "top_k": top_k},
        )

    assert result == {"ok": True, "data": [], "error": None}
    mock_retrieve.assert_called_once_with(
        query="What do I remember?",
        top_k=top_k,
        min_score=0.25,
    )


def test_search_tool_returns_retrieved_memories():
    expected = [
        {
            "id": "mem-test-1",
            "content": "Aura uses Python and FastAPI.",
            "score": 0.9,
        }
    ]

    with patch(
        "app.services.tool_executor.retrieve_memories",
        return_value=expected,
    ) as mock_retrieve:
        result = execute_tool(
            "search_memories",
            {
                "query": "What technologies power Aura?",
                "top_k": 5,
            },
        )

    assert result == {
        "ok": True,
        "data": expected,
        "error": None,
    }
    mock_retrieve.assert_called_once_with(
        query="What technologies power Aura?",
        top_k=5,
        min_score=0.25,
    )


def test_search_tool_wraps_retrieval_error():
    with patch(
        "app.services.tool_executor.retrieve_memories",
        side_effect=RuntimeError("Storage unavailable"),
    ):
        with pytest.raises(
            ToolExecutionError,
            match="Tool execution failed",
        ) as exc_info:
            execute_tool(
                "search_memories",
                {
                    "query": "What technologies power Aura?",
                    "top_k": 5,
                },
            )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "Storage unavailable" not in str(exc_info.value)


def test_search_memories_schema_has_required_arguments():
    assert SEARCH_MEMORIES_SCHEMA["name"] == "search_memories"
    assert SEARCH_MEMORIES_SCHEMA["strict"] is True

    parameters = SEARCH_MEMORIES_SCHEMA["parameters"]
    assert parameters["required"] == ["query", "top_k"]
    assert parameters["additionalProperties"] is False

    properties = parameters["properties"]
    assert properties["query"]["type"] == "string"
    assert properties["top_k"]["type"] == "integer"


def test_schema_name_matches_registered_tool():
    assert SEARCH_MEMORIES_SCHEMA["name"] in TOOL_REGISTRY


def test_unexpected_argument_returns_structured_failure():
    result = execute_tool(
        "search_memories",
        {
            "query": "What do I remember?",
            "unexpected": True,
        },
    )

    assert result == {
        "ok": False,
        "data": None,
        "error": "Invalid tool arguments.",
    }


def test_search_tool_wraps_internal_type_error():
    with patch(
        "app.services.tool_executor.retrieve_memories",
        side_effect=TypeError("Internal implementation error"),
    ):
        with pytest.raises(
            ToolExecutionError,
            match="Tool execution failed.",
        ):
            execute_tool(
                "search_memories",
                {"query": "What do I remember?"},
            )
