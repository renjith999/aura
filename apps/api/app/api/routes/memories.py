import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserId
from app.core.database import get_db_session
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.memory_enrichment_service import MemoryEnrichmentService
from app.services.memory_service import MemoryService
import hashlib

from app.core.database import SessionLocal
from app.repositories.memory_enrichment_repository import (
    MemoryEnrichmentRepository,
)

router = APIRouter(prefix="/memories", tags=["Memories"])
DbSession = Annotated[Session, Depends(get_db_session)]
logger = logging.getLogger(__name__)


async def enrich_memory_safely(
    memory_id: str,
    content: str,
) -> None:
    """Generate and persist enrichment without affecting the original memory."""

    try:
        source_content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        result = await MemoryEnrichmentService().enrich_with_metadata(content)

        with SessionLocal() as session:
            repository = MemoryEnrichmentRepository(session)

            saved = repository.save_if_memory_unchanged(
                memory_id=memory_id,
                source_content_hash=source_content_hash,
                enrichment=result.enrichment,
                schema_version=result.schema_version,
                prompt_version=result.prompt_version,
                model=result.model,
            )

            if not saved:
                logger.info(
                    "Skipped enrichment persistence for memory %s: "
                    "memory was deleted or its content changed.",
                    memory_id,
                )

    except Exception:
        logger.exception(
            "Memory enrichment failed for memory %s; "
            "original memory was retained.",
            memory_id,
        )

@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    data: MemoryCreate,
    session: DbSession,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
) -> MemoryResponse:
    memory = MemoryService(session).create(data, user_id)
    background_tasks.add_task(
        enrich_memory_safely,
        memory.id,
        memory.content,
    )
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
