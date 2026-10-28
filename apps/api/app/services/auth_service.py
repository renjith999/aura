from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_access_token,
    hash_password,
    utc_now,
    verify_password,
)
from app.models.user import User
from app.repositories.auth_repository import AuthRepository


class AccountExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, session: Session, token_ttl_seconds: int) -> None:
        self.repository = AuthRepository(session)
        self.token_ttl_seconds = token_ttl_seconds

    def register(self, email: str, password: str) -> tuple[User, str]:
        if self.repository.get_user_by_email(email) is not None:
            raise AccountExistsError
        user = self.repository.create_user(email, hash_password(password))
        return self._issue_session(user)

    def login(self, email: str, password: str) -> tuple[User, str]:
        user = self.repository.get_user_by_email(email)
        if user is None:
            hash_password(password)
            raise InvalidCredentialsError
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        return self._issue_session(user)

    def logout(self, token: str) -> None:
        self.repository.delete_session(hash_access_token(token))

    def _issue_session(self, user: User) -> tuple[User, str]:
        token = create_access_token()
        expires_at = utc_now() + timedelta(seconds=self.token_ttl_seconds)
        self.repository.create_session(hash_access_token(token), user.id, expires_at)
        return user, token
