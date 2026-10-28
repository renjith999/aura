from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryService:
    def __init__(self, session: Session) -> None:
        self.repository = MemoryRepository(session)

    def create(self, data: MemoryCreate, user_id: str) -> Memory:
        return self.repository.create(data, user_id)

    def list_for_user(self, user_id: str, **filters: object) -> list[Memory]:
        return self.repository.list_for_user(user_id, **filters)

    def get_for_user(self, memory_id: str, user_id: str) -> Memory | None:
        return self.repository.get_for_user(memory_id, user_id)

    def update_for_user(
        self,
        memory_id: str,
        user_id: str,
        data: MemoryUpdate,
    ) -> Memory | None:
        memory = self.repository.get_for_user(memory_id, user_id)
        if memory is None:
            return None
        return self.repository.update(memory, data)

    def delete_for_user(self, memory_id: str, user_id: str) -> bool:
        memory = self.repository.get_for_user(memory_id, user_id)
        if memory is None:
            return False
        self.repository.delete(memory)
        return True
