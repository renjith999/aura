from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, data: MemoryCreate, user_id: str) -> Memory:
        memory = Memory(**data.model_dump(), user_id=user_id)
        self.session.add(memory)
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

    def update(self, memory: Memory, data: MemoryUpdate) -> Memory:
        from app.models.memory import utc_now

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(memory, field, value)
        memory.updated_at = utc_now()
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def delete(self, memory: Memory) -> None:
        self.session.delete(memory)
        self.session.commit()
