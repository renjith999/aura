
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from memory_retriever import retrieve_memories

router = APIRouter(prefix="/memories", tags=["Memories"])


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.25, ge=0.0, le=1.0)


@router.post("/search")
def search_memories_endpoint(
    request: MemorySearchRequest,
) -> dict:
    if not request.query.strip():
        raise HTTPException(
            status_code=422,
            detail="Query must not be blank.",
        )

    try:
        results = retrieve_memories(
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
        )
        return {
            "query": request.query,
            "count": len(results),
            "results": results,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
