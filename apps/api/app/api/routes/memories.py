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
from app.prompts.memory_enrichment.registry import get_memory_enrichment_prompt
from app.repositories.memory_enrichment_override_repository import (
    MemoryEnrichmentOverrideRepository,
)
from app.repositories.memory_enrichment_repository import (
    MemoryEnrichmentRepository,
)
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.schemas.memory_enrichment import (
    MemoryEnrichmentCorrection,
    MemoryEnrichmentStatusResponse,
)
from app.services.memory_enrichment_service import (
    MEMORY_ENRICHMENT_SCHEMA_VERSION,
    MemoryEnrichmentService,
)
from app.services.memory_enrichment_tasks import process_memory_enrichment
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["Memories"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    data: MemoryCreate,
    session: DbSession,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
) -> MemoryResponse:
    memory = MemoryService(session).create(data, user_id)
    background_tasks.add_task(
        process_memory_enrichment,
        memory.id,
        MemoryEnrichmentService,
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
    background_tasks: BackgroundTasks,
) -> MemoryResponse:
    service = MemoryService(session)
    current = service.get_for_user(memory_id, user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Memory not found.")

    content_changed = data.content is not None and data.content != current.content
    memory = service.update_for_user(memory_id, user_id, data)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    if content_changed:
        background_tasks.add_task(
            process_memory_enrichment,
            memory.id,
            MemoryEnrichmentService,
        )
    return MemoryResponse.model_validate(memory)


@router.get(
    "/{memory_id}/enrichment",
    response_model=MemoryEnrichmentStatusResponse,
)
def get_memory_enrichment_status(
    memory_id: str,
    session: DbSession,
    user_id: CurrentUserId,
) -> MemoryEnrichmentStatusResponse:
    memory = MemoryService(session).get_for_user(memory_id, user_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")

    return _enrichment_response(memory_id, session)


@router.patch(
    "/{memory_id}/enrichment",
    response_model=MemoryEnrichmentStatusResponse,
)
def correct_memory_enrichment(
    memory_id: str,
    data: MemoryEnrichmentCorrection,
    session: DbSession,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
) -> MemoryEnrichmentStatusResponse:
    memory = MemoryService(session).get_for_user(memory_id, user_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found.")

    enrichment_repository = MemoryEnrichmentRepository(session)
    enrichment = enrichment_repository.get_for_memory(memory_id)
    if enrichment is None:
        enrichment_repository.create_or_reset_pending(
            memory_id=memory_id,
            content=memory.content,
            schema_version=MEMORY_ENRICHMENT_SCHEMA_VERSION,
            prompt_version=get_memory_enrichment_prompt().version,
            model=MemoryEnrichmentService.MODEL,
        )

    patch = data.model_dump(
        mode="json",
        exclude_unset=True,
        exclude={"clear_overrides"},
    )
    MemoryEnrichmentOverrideRepository(session).patch_for_memory(
        memory_id,
        patch,
        data.clear_overrides,
    )
    if enrichment is None:
        background_tasks.add_task(
            process_memory_enrichment,
            memory_id,
            MemoryEnrichmentService,
        )
    return _enrichment_response(memory_id, session)


def _enrichment_response(
    memory_id: str,
    session: Session,
) -> MemoryEnrichmentStatusResponse:
    enrichment = MemoryEnrichmentRepository(session).get_for_memory(memory_id)
    if enrichment is None:
        raise HTTPException(
            status_code=404,
            detail="Memory enrichment status not found.",
        )

    override = MemoryEnrichmentOverrideRepository(session).get_for_memory(memory_id)
    values: dict[str, object] = {
        "summary": enrichment.summary,
        "category": enrichment.category,
        "memory_type": enrichment.memory_type,
        "tags": enrichment.tags,
        "entities": enrichment.entities,
        "importance": enrichment.importance,
    }
    overrides = override.overrides if override is not None else {}
    values.update(overrides)
    return MemoryEnrichmentStatusResponse(
        memory_id=memory_id,
        status=enrichment.status,
        attempt_count=enrichment.attempt_count,
        last_error=enrichment.last_error,
        next_retry_at=enrichment.next_retry_at,
        completed_at=enrichment.completed_at,
        **values,
        manual_fields=sorted(overrides),
    )


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
