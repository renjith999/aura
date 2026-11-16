from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.models.memory_enrichment import MemoryEnrichment
from app.repositories.memory_enrichment_repository import (
    MemoryEnrichmentRepository,
)
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        data: MemoryCreate,
        user_id: str,
        schema_version: str,
        prompt_version: str,
        model: str,
    ) -> Memory:
        memory = Memory(**data.model_dump(), user_id=user_id)
        self.session.add(memory)
        self.session.flush()
        MemoryEnrichmentRepository(self.session).create_or_reset_pending(
            memory_id=memory.id,
            content=memory.content,
            schema_version=schema_version,
            prompt_version=prompt_version,
            model=model,
        )
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def list_for_user(
        self,
        user_id: str,
        query: str | None = None,
        category: str | None = None,
        is_favorite: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        statement = select(Memory).where(Memory.user_id == user_id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(Memory.title.ilike(pattern), Memory.content.ilike(pattern))
            )
        if category is not None:
            statement = statement.where(Memory.category == category)
        if is_favorite is not None:
            statement = statement.where(Memory.is_favorite == is_favorite)
        statement = statement.order_by(Memory.created_at.desc(), Memory.id.asc())
        statement = statement.limit(limit).offset(offset)
        return list(self.session.scalars(statement))

    def get_for_user(self, memory_id: str, user_id: str) -> Memory | None:
        statement = select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
        )
        return self.session.scalar(statement)


    def update(
        self,
        memory: Memory,
        data: MemoryUpdate,
        schema_version: str | None = None,
        prompt_version: str | None = None,
        model: str | None = None,
    ) -> Memory:
        from app.models.memory import utc_now

        update_data = data.model_dump(exclude_unset=True)

        content_changed = (
            "content" in update_data
            and update_data["content"] != memory.content
        )

        try:
            if content_changed:
                enrichment = self.session.get(
                    MemoryEnrichment,
                    memory.id,
                )

                if enrichment is not None:
                    MemoryEnrichmentRepository(self.session).create_or_reset_pending(
                        memory_id=memory.id,
                        content=update_data["content"],
                        schema_version=schema_version or enrichment.schema_version,
                        prompt_version=prompt_version or enrichment.prompt_version,
                        model=model or enrichment.model,
                    )
                elif (
                    schema_version is not None
                    and prompt_version is not None
                    and model is not None
                ):
                    MemoryEnrichmentRepository(self.session).create_or_reset_pending(
                        memory_id=memory.id,
                        content=update_data["content"],
                        schema_version=schema_version,
                        prompt_version=prompt_version,
                        model=model,
                    )

            for field, value in update_data.items():
                setattr(memory, field, value)

            memory.updated_at = utc_now()

            self.session.commit()
            self.session.refresh(memory)

            return memory

        except Exception:
            self.session.rollback()
            raise


    def delete(self, memory: Memory) -> None:
        self.session.delete(memory)
        self.session.commit()
