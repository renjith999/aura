# Aura API

The supported Aura API is the Python + FastAPI application in `app/`. The TypeScript/Fastify bootstrap in `src/` is legacy reference code and is not used to run the backend.

## Requirements

- Python 3.13
- uv

## Run locally

From the repository root, install dependencies:

```bash
uv sync --project apps/api --group dev
```

Then run the API from its application directory:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

Or, after installing the JavaScript workspace dependencies, run it through pnpm from the repository root:

```bash
pnpm --filter @aura/api dev
```

The health check is available at `GET /health`. Swagger UI is available at `/docs`.

## Python checks

Run these from `apps/api/`:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```