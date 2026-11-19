from threading import Event

from fastapi.testclient import TestClient

from app.main import app


def test_application_worker_starts_and_stops_with_lifespan(monkeypatch):
    started = Event()
    stopped = Event()

    async def held_worker():
        started.set()
        try:
            import asyncio

            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr("app.main.run_memory_enrichment_worker", held_worker)

    with TestClient(app):
        assert started.wait(timeout=2)

    assert stopped.wait(timeout=2)
