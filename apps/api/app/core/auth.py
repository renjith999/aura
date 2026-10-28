from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.core.security import hash_access_token, utc_now
from app.repositories.auth_repository import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db_session)]


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()

    active_session = AuthRepository(session).get_active_session(
        hash_access_token(credentials.credentials), utc_now()
    )
    if active_session is None:
        raise _authentication_error()
    return active_session.user_id


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
