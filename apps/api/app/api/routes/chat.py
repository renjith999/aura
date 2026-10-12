from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.openai_service import OpenAIService

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def get_openai_service() -> OpenAIService:
    return OpenAIService()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    openai_service: Annotated[OpenAIService, Depends(get_openai_service)],
) -> dict[str, str]:
    try:
        response = await openai_service.generate_response(request.message)
        return {"response": response}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to generate an AI response.",
        ) from exc
