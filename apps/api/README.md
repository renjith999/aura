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
uv run python -m app
```

Or, after installing the JavaScript workspace dependencies, run it through pnpm from the repository root:

```bash
pnpm --filter @aura/api dev
```

The health check is available at `GET /health`. Swagger UI is available at `/docs`.

## Architecture

The FastAPI route modules in `app/api/routes/` handle HTTP inputs, authentication dependencies, status codes, and response schemas. They delegate application behavior to services in `app/services/`. Services apply user-scoped rules and call repositories in `app/repositories/` for persistence. Repositories contain SQLAlchemy queries and writes against models in `app/models/`.

Database engine and session creation are isolated in `app/core/database.py`; environment-backed application settings are defined in `app/core/config.py`. Routes receive a database session through `get_db_session`, and service-level behavior can be exercised directly without an HTTP client.

## Memory API

The memory API stores exact user text in PostgreSQL. Apply schema migrations before using it:

```bash
cd apps/api
uv run alembic upgrade head
```

Create an account and sign in through `/auth/register` and `/auth/login`. Passwords are stored as salted PBKDF2-SHA256 hashes. Sign-in returns a random opaque bearer token; only its SHA-256 hash is stored in PostgreSQL. Tokens expire after `ACCESS_TOKEN_TTL_SECONDS` (default `86400`); `POST /auth/logout` revokes the current token. Clients send the token in the `Authorization: Bearer <access-token>` header. No signing secret is needed because tokens are random and validated against the database.

For the local React client, `WEB_ORIGIN` sets the allowed browser origin and defaults to `http://localhost:5173`. The client API URL can be set with `VITE_API_URL`.

The memory routes require a valid bearer token and scope each read, update, and delete to the signed-in user. The API supports:

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

Register example:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"a-long-unique-passphrase"}'
```

List/search example: `GET /memories?query=project&category=work&is_favorite=false`. Search is a deterministic case-insensitive text match across title and content; results are ordered by newest creation time, then stable ID. Unknown and non-owned IDs return the same `404` response.

## Runtime configuration and errors

Settings are loaded from environment variables or `apps/api/.env`; values in the environment take precedence. `apps/api/.env.example` lists the supported settings. `API_PORT` must be from 1 to 65535, `ACCESS_TOKEN_TTL_SECONDS` must be from 1 to 2592000, `WEB_ORIGIN` must be an HTTP(S) origin, and `DATABASE_URL` must be a valid SQLAlchemy URL. `OPENAI_API_KEY` is optional when the chat endpoint is not used; `/chat` returns `503` with a configuration error when the key is unset. `LOG_LEVEL` accepts DEBUG, INFO, WARNING, ERROR, or CRITICAL.

Development keeps the existing local database default. Production must set `ENVIRONMENT=production` and provide `DATABASE_URL` explicitly; SQLite is rejected in production. Invalid settings fail during application startup. The OpenAI key and database URL are held as redacted secret settings.

API errors use a stable JSON shape while preserving the `detail` field used by the web client. For example, validation errors return `{"detail":"Request validation failed.","code":"validation_error"}`, missing records return `{"detail":"Memory not found.","code":"not_found"}`, and unexpected failures return `{"detail":"An unexpected error occurred.","code":"internal_error"}`. Responses include an `X-Request-ID` header for support and log correlation.

Request logs include the request ID, method, path, status, and duration. Unexpected errors add the exception type. Request bodies, query strings, authorization headers, credentials, and note contents are not logged.
## Python checks

Run these from `apps/api/`:

```bash
uv run pytest
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run alembic upgrade head
```
