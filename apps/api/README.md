# Aura API

The supported backend is the Python + FastAPI application in `app/`. The TypeScript/Fastify bootstrap in `src/` is legacy reference code and is not used to run the API.

## Quick start

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), and PostgreSQL 16 or newer. From the repository root:

```bash
cp apps/api/.env.example apps/api/.env
docker compose up -d postgres
uv sync --project apps/api --group dev
cd apps/api
uv run alembic upgrade head
uv run python -m app
```

The API listens on `http://localhost:8000` by default. The local web client can be started separately with `pnpm --filter @aura/web dev`, or both apps can be started from the repository root with `pnpm dev` after `pnpm install`.

- Health check: `GET /health`
- Interactive API reference: `/docs`
- OpenAPI schema: `/openapi.json`

The interactive reference is generated from the FastAPI routes and schemas. Use it to inspect the live contract while developing.

## API endpoints

### Health

`GET /health` is public and does not require a database account or bearer token.

```json
{ "status": "ok" }
```

### Authentication

Passwords must be 12–1024 characters. Registration normalizes email to lowercase and returns a bearer token, so a separate login is not needed immediately after registering.

| Method | Path             | Behavior                                               |
| ------ | ---------------- | ------------------------------------------------------ |
| `POST` | `/auth/register` | Create an account and session; returns `201`           |
| `POST` | `/auth/login`    | Verify credentials and create a session; returns `200` |
| `POST` | `/auth/logout`   | Revoke the current bearer token; returns `204`         |

Register request:

```json
{ "email": "you@example.com", "password": "a-long-unique-passphrase" }
```

Register and login both return this shape (with generated values):

```json
{
  "access_token": "<access-token>",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "<user-id>", "email": "you@example.com" }
}
```

Send the token as `Authorization: Bearer <access-token>` to memory endpoints. Tokens expire after `ACCESS_TOKEN_TTL_SECONDS` (default `86400`); logging out revokes the token immediately.

### Memories

All memory endpoints require a valid bearer token. Reads and writes are scoped to the signed-in user. Unknown IDs and IDs owned by another user both return `404`.

| Method   | Path                    | Behavior                                      |
| -------- | ----------------------- | --------------------------------------------- |
| `POST`   | `/memories`             | Create a memory; returns `201`                |
| `GET`    | `/memories`             | List and filter the signed-in user's memories |
| `GET`    | `/memories/{memory_id}` | Retrieve one owned memory                     |
| `PATCH`  | `/memories/{memory_id}` | Update one or more memory fields              |
| `DELETE` | `/memories/{memory_id}` | Delete one owned memory; returns `204`        |

Create request:

```json
{
  "title": "Project note",
  "content": "Remember this exactly.",
  "category": "work",
  "is_favorite": false
}
```

`title` is required and limited to 200 characters. `content` is required. Both must contain a non-whitespace character. `category` defaults to `uncategorized` and is limited to 100 characters; `is_favorite` defaults to `false`.

Create, retrieve, and update responses use this shape:

```json
{
  "id": "<memory-id>",
  "title": "Project note",
  "content": "Remember this exactly.",
  "category": "work",
  "is_favorite": false,
  "user_id": "<user-id>",
  "created_at": "2026-01-01T12:00:00Z",
  "updated_at": "2026-01-01T12:00:00Z"
}
```

`PATCH` accepts any non-empty subset of `title`, `content`, `category`, and `is_favorite`. An empty patch or blank text value is invalid.

`GET /memories` supports these optional query parameters:

| Parameter     | Meaning                                          | Limits/default            |
| ------------- | ------------------------------------------------ | ------------------------- |
| `query`       | Case-insensitive text match in title and content | Up to 2000 characters     |
| `category`    | Exact category match                             | 1–100 characters          |
| `is_favorite` | Filter by favorite status                        | `true` or `false`         |
| `limit`       | Maximum number of results                        | 1–200; default `100`      |
| `offset`      | Number of rows to skip                           | 0 or greater; default `0` |

Results are ordered by newest creation time, then by ID for stable ordering. For example:

```bash
curl 'http://localhost:8000/memories?query=project&category=work&is_favorite=false&limit=20&offset=0' \
  -H 'Authorization: Bearer <access-token>'
```

### Chat

`POST /chat` accepts `{"message":"..."}` (up to `CHAT_MAX_INPUT_CHARACTERS` characters, 4000 by default) and returns `{"response":"..."}`. It requires a valid `Authorization: Bearer <access-token>` header and `OPENAI_API_KEY`; missing or invalid authentication returns `401`, and a missing key returns `503` with code `unavailable`. Each user can make 10 requests per rolling 60-second window by default. The limit is stored as one usage-window row per user in PostgreSQL, so it is shared across API workers and survives restarts. When exceeded, the API returns `429` with code `rate_limited` and a `Retry-After` header. Configure the per-user request count and window with `CHAT_RATE_LIMIT_PER_MINUTE` and `CHAT_RATE_LIMIT_WINDOW_SECONDS`. Provider calls are capped at 1000 output tokens by default (`CHAT_MAX_OUTPUT_TOKENS`). Provider failures return `502` with code `upstream_error`.

## Errors and request IDs

Errors have a stable JSON shape and retain the `detail` field:

```json
{ "detail": "Request validation failed.", "code": "validation_error" }
```

| HTTP status                                                                                                                                                                                                                                                      | Code               | Typical cause                                        |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ---------------------------------------------------- |
| `401`                                                                                                                                                                                                                                                            | `unauthorized`     | Missing, invalid, expired, or revoked bearer token   |
| `404`                                                                                                                                                                                                                                                            | `not_found`        | Resource does not exist or is not owned by this user |
| `409`                                                                                                                                                                                                                                                            | `conflict`         | An account already exists                            |
| `422`                                                                                                                                                                                                                                                            | `validation_error` | Invalid request body or query parameter              |
| `429`                                                                                                                                                                                                                                                            | `rate_limited`     | Per-user chat request limit exceeded                 |
| `500`                                                                                                                                                                                                                                                            | `internal_error`   | Unexpected server failure                            |
| `502`                                                                                                                                                                                                                                                            | `upstream_error`   | Chat provider failure                                |
| `503`                                                                                                                                                                                                                                                            | `unavailable`      | Chat is not configured                               |
| Every response includes `X-Request-ID`. Request logs include the ID, method, path, status, and duration; unexpected errors also include the exception type. Request bodies, query strings, authorization headers, credentials, and note contents are not logged. |

## Runtime configuration

Settings are loaded from environment variables or `apps/api/.env`; environment variables take precedence. The checked-in `apps/api/.env.example` is the local template.

| Setting                                                                                                                                                                                                                        | Default                 | Notes                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- | ----------------------------------------------- |
| `APP_NAME`                                                                                                                                                                                                                     | `Aura API`              | FastAPI title                                   |
| `APP_VERSION`                                                                                                                                                                                                                  | `0.1.0`                 | API version shown in docs                       |
| `ENVIRONMENT`                                                                                                                                                                                                                  | `development`           | `development`, `test`, or `production`          |
| `API_PORT`                                                                                                                                                                                                                     | `8000`                  | Must be 1–65535                                 |
| `LOG_LEVEL`                                                                                                                                                                                                                    | `INFO`                  | DEBUG, INFO, WARNING, ERROR, or CRITICAL        |
| `DATABASE_URL`                                                                                                                                                                                                                 | Local PostgreSQL URL    | Must be a valid SQLAlchemy URL                  |
| `OPENAI_API_KEY`                                                                                                                                                                                                               | Empty                   | Optional unless `/chat` is used                 |
| `ACCESS_TOKEN_TTL_SECONDS`                                                                                                                                                                                                     | `86400`                 | Must be 1–2592000                               |
| `CHAT_RATE_LIMIT_PER_MINUTE`                                                                                                                                                                                                   | `10`                    | Requests allowed per user during the window     |
| `CHAT_RATE_LIMIT_WINDOW_SECONDS`                                                                                                                                                                                               | `60`                    | Rolling usage window in seconds                 |
| `CHAT_MAX_INPUT_CHARACTERS`                                                                                                                                                                                                    | `4000`                  | Maximum characters per chat message             |
| `CHAT_MAX_OUTPUT_TOKENS`                                                                                                                                                                                                       | `1000`                  | Maximum provider output tokens per chat request |
| `WEB_ORIGIN`                                                                                                                                                                                                                   | `http://localhost:5173` | HTTP(S) browser origin allowed by CORS          |
| Production requires `ENVIRONMENT=production` and an explicitly configured server database URL; SQLite is rejected. The OpenAI key and database URL are held as redacted secret settings. Invalid settings fail during startup. |

## Architecture

Routes in `app/api/routes/` handle HTTP input, authentication dependencies, status codes, and response schemas. Authentication and memory routes delegate to services in `app/services/`; services apply application rules and call SQLAlchemy repositories in `app/repositories/`. Models in `app/models/` map to PostgreSQL tables. Request and response models live in `app/schemas/`. Database engine and session creation are in `app/core/database.py`; settings and bearer-token validation are in `app/core/`.

The memory API stores the submitted text as-is and uses deterministic case-insensitive keyword matching across title and content. It does not currently use embeddings, semantic search, or RAG. See [the architecture notes](../../docs/architecture.md) for the system diagram, storage choices, and open operational decisions.

## Python checks

Run from `apps/api/`:

```bash
uv run pytest
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run alembic upgrade head
```
