import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services.openai_service import OpenAIService

router = APIRouter()
logger = logging.getLogger("aura.api")


class ChatRequest(BaseModel):
    message: str


def get_openai_service() -> OpenAIService:
    if not settings.openai_api_key.get_secret_value():
        raise HTTPException(status_code=503, detail="Chat is not configured.")
    return OpenAIService()


@router.post("/chat")
async def chat(
    request: Request,
    payload: ChatRequest,
    openai_service: Annotated[OpenAIService, Depends(get_openai_service)],
) -> dict[str, str]:
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
