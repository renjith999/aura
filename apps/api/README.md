# Aura API

Python API service for Aura.

## Run locally

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

The health check is available at `GET /health`.
