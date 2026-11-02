from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory_service import MemoryService


def test_memory_service_uses_repository_without_http(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory-service.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            service = MemoryService(session)
            created = service.create(
                MemoryCreate(title="Service note", content="Saved directly."),
                user_id="user-1",
            )

            assert service.get_for_user(created.id, "user-1") == created
            assert service.list_for_user("user-1") == [created]
            assert service.get_for_user(created.id, "user-2") is None

            updated = service.update_for_user(
                created.id,
                "user-1",
                MemoryUpdate(title="Updated service note"),
            )
            assert updated is not None
            assert updated.title == "Updated service note"

            assert service.delete_for_user(created.id, "user-2") is False
            assert service.delete_for_user(created.id, "user-1") is True
            assert service.get_for_user(created.id, "user-1") is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
