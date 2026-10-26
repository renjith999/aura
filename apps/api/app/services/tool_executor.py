from inspect import signature
from typing import Any, TypedDict

from memory_retriever import retrieve_memories


class ToolExecutionError(Exception):
    """Raised when an approved tool fails during execution."""


class ToolResult(TypedDict):
    ok: bool
    data: Any
    error: str | None


def search_memories_tool(
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search Aura's stored memories."""
    if not query.strip():
        raise ValueError("Query must not be blank.")

    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")

    return retrieve_memories(
        query=query,
        top_k=top_k,
        min_score=0.25,
    )


TOOL_REGISTRY = {
    "search_memories": search_memories_tool,
}

SEARCH_MEMORIES_SCHEMA = {
    "type": "function",
    "name": "search_memories",
    "description": "Search Aura's stored memories to answer a question.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question to search memories for.",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results, from 1 to 20.",
            },
        },
        "required": ["query", "top_k"],
        "additionalProperties": False,
    },
    "strict": True,
}


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """Execute an approved tool and return a structured result."""
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return {
            "ok": False,
            "data": None,
            "error": "Unsupported tool.",
        }

    try:
        signature(tool).bind(**arguments)
    except TypeError:
        return {
            "ok": False,
            "data": None,
            "error": "Invalid tool arguments.",
        }

    try:
        data = tool(**arguments)
        return {
            "ok": True,
            "data": data,
            "error": None,
        }
    except ValueError:
        return {
            "ok": False,
            "data": None,
            "error": "Invalid tool arguments.",
        }
    except Exception as exc:
        raise ToolExecutionError(
            "Tool execution failed."
        ) from exc
