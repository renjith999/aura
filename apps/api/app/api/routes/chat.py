import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.core.auth import CurrentUserId, DbSession
from app.core.config import settings
from app.core.security import utc_now
from app.repositories.chat_usage_repository import ChatUsageRepository
from app.services.openai_service import OpenAIService

router = APIRouter()
logger = logging.getLogger("aura.api")


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=settings.chat_max_input_characters,
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value


class ChatRateLimitError(BaseModel):
    detail: str
    code: Literal["rate_limited"]


def get_openai_service() -> OpenAIService:
    if not settings.openai_api_key.get_secret_value():
        raise HTTPException(status_code=503, detail="Chat is not configured.")
    return OpenAIService()


@router.post(
    "/chat",
    responses={
        429: {
            "model": ChatRateLimitError,
            "description": "The authenticated user exceeded the chat request limit.",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until the per-user usage window resets.",
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        }
    },
)
async def chat(
    current_user_id: CurrentUserId,
    session: DbSession,
    request: Request,
    payload: ChatRequest,
    openai_service: Annotated[OpenAIService, Depends(get_openai_service)],
) -> dict[str, str]:
    retry_after = ChatUsageRepository(session).consume_request(
        user_id=current_user_id,
        now=utc_now(),
        limit=settings.chat_rate_limit_per_minute,
        window_seconds=settings.chat_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Chat usage limit reached. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        response = await openai_service.generate_response(payload.message)
        return {"response": response}
    except Exception as exc:
        logger.error(
            "chat_upstream_error request_id=%s exception_type=%s",
            getattr(request.state, "request_id", "unknown"),
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Unable to generate an AI response.",
        ) from exc
