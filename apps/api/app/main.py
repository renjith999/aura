from fastapi import FastAPI

from app.api.routes.chat import router as chat_router

app = FastAPI()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat_router)
