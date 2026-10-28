from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError

from app.core.auth import DbSession, bearer_scheme, get_current_user_id
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import AuthResponse, Credentials, UserResponse
from app.services.auth_service import (
    AccountExistsError,
    AuthService,
    InvalidCredentialsError,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]
CurrentUser = Annotated[str, Depends(get_current_user_id)]


def _response(user: User, token: str) -> AuthResponse:
    return AuthResponse(
        access_token=token,
        expires_in=settings.access_token_ttl_seconds,
        user=UserResponse(id=user.id, email=user.email),
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
def register(data: Credentials, session: DbSession) -> AuthResponse:
    service = AuthService(session, settings.access_token_ttl_seconds)
    try:
        user, token = service.register(str(data.email), data.password)
    except AccountExistsError as exc:
        raise HTTPException(
            status_code=409, detail="An account already exists."
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="An account already exists."
        ) from exc
    return _response(user, token)


@router.post("/login", response_model=AuthResponse)
def login(data: Credentials, session: DbSession) -> AuthResponse:
    service = AuthService(session, settings.access_token_ttl_seconds)
    try:
        user, token = service.login(str(data.email), data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return _response(user, token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: CredentialsDependency,
    _user_id: CurrentUser,
    session: DbSession,
) -> Response:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    AuthService(session, settings.access_token_ttl_seconds).logout(
        credentials.credentials
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
