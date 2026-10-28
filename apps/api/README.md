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

## Memory API

The memory API stores exact user text in PostgreSQL. Apply schema migrations before using it:

```bash
cd apps/api
uv run alembic upgrade head
```

Memory routes require an authenticated user identity. Authentication is supplied by the account story (AURA-33); tests inject a controlled user while that integration is in progress. The API supports:

| Method   | Path                    | Behavior                                                                                  |
| -------- | ----------------------- | ----------------------------------------------------------------------------------------- |
| `POST`   | `/memories`             | Create a memory; returns `201`                                                            |
| `GET`    | `/memories`             | List memories; optional `query`, `category`, `is_favorite`, `limit`, and `offset` filters |
| `GET`    | `/memories/{memory_id}` | Retrieve one owned memory                                                                 |
| `PATCH`  | `/memories/{memory_id}` | Update title, content, category, or favorite status                                       |
| `DELETE` | `/memories/{memory_id}` | Delete one owned memory; returns `204`                                                    |

Example create request (after authentication is connected):

```bash
curl -X POST http://localhost:8000/memories \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access-token>' \
  -d '{"title":"Project note","content":"Remember this exactly.","category":"work","is_favorite":false}'
```

List/search example: `GET /memories?query=project&category=work&is_favorite=false`. Search is a deterministic case-insensitive text match across title and content; results are ordered by newest creation time, then stable ID. Unknown and non-owned IDs return the same `404` response.

## Python checks

Run these from `apps/api/`:

```bash
uv run pytest
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run alembic upgrade head
```
