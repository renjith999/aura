from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserSession


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def create_user(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        self.session.flush()
        return user

    def create_session(
        self, token_hash: str, user_id: str, expires_at: datetime
    ) -> None:
        self.session.add(
            UserSession(token_hash=token_hash, user_id=user_id, expires_at=expires_at)
        )
        self.session.commit()

    def get_active_session(self, token_hash: str, now: datetime) -> UserSession | None:
        return self.session.scalar(
            select(UserSession).where(
                UserSession.token_hash == token_hash,
                UserSession.expires_at > now,
            )
        )

    def delete_session(self, token_hash: str) -> None:
        session = self.session.get(UserSession, token_hash)
        if session is not None:
            self.session.delete(session)
            self.session.commit()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
