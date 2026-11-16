import uvicorn

from app.core.config import settings


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0" if settings.environment == "production" else "127.0.0.1",
        port=settings.api_port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    run()
