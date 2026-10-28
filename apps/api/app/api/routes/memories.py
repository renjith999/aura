from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserId
from app.core.database import get_db_session
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["Memories"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    data: MemoryCreate,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    memory = MemoryService(session).create(data, user_id)
    return MemoryResponse.model_validate(memory)


@router.get("", response_model=list[MemoryResponse])
def list_memories(
    session: DbSession,
    user_id: CurrentUserId,
    query: str | None = Query(default=None, max_length=2000),
    category: str | None = Query(default=None, min_length=1, max_length=100),
    is_favorite: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[MemoryResponse]:
    memories = MemoryService(session).list_for_user(
        user_id,
        query=query,
        category=category,
        is_favorite=is_favorite,
        limit=limit,
        offset=offset,
    )
    return [MemoryResponse.model_validate(memory) for memory in memories]


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: str,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    memory = MemoryService(session).get_for_user(memory_id, user_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return MemoryResponse.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    data: MemoryUpdate,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryResponse:
    memory = MemoryService(session).update_for_user(memory_id, user_id, data)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return MemoryResponse.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    session: DbSession,
    user_id: CurrentUserId,
) -> Response:
    deleted = MemoryService(session).delete_for_user(memory_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
