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
| `OPENAI_PRICING_VERSION`                                                                                                                                                                                                       | `unconfigured`           | Version label copied into each enrichment attempt record |
| `OPENAI_MODEL_PRICING`                                                                                                                                                                                                         | `{}`                    | JSON model-to-rate map; unset rates leave cost estimates unavailable |
| `ACCESS_TOKEN_TTL_SECONDS`                                                                                                                                                                                                     | `86400`                 | Must be 1–2592000                               |
| `CHAT_RATE_LIMIT_PER_MINUTE`                                                                                                                                                                                                   | `10`                    | Requests allowed per user during the window     |
| `CHAT_RATE_LIMIT_WINDOW_SECONDS`                                                                                                                                                                                               | `60`                    | Rolling usage window in seconds                 |
| `CHAT_MAX_INPUT_CHARACTERS`                                                                                                                                                                                                    | `4000`                  | Maximum characters per chat message             |
| `CHAT_MAX_OUTPUT_TOKENS`                                                                                                                                                                                                       | `1000`                  | Maximum provider output tokens per chat request |
| `WEB_ORIGIN`                                                                                                                                                                                                                   | `http://localhost:5173` | HTTP(S) browser origin allowed by CORS          |
| Production requires `ENVIRONMENT=production` and an explicitly configured server database URL; SQLite is rejected. The OpenAI key and database URL are held as redacted secret settings. Invalid settings fail during startup. |

## Architecture

Routes in `app/api/routes/` handle HTTP input, authentication dependencies, status codes, and response schemas. Authentication and memory routes delegate to services in `app/services/`; services apply application rules and call SQLAlchemy repositories in `app/repositories/`. Models in `app/models/` map to PostgreSQL tables. Request and response models live in `app/schemas/`. Database engine and session creation are in `app/core/database.py`; settings and bearer-token validation are in `app/core/`.

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
| `GET`    | `/memories/{memory_id}/enrichment` | Retrieve enrichment status and retry details                                     |
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
The memory API stores the submitted text as-is and uses deterministic case-insensitive keyword matching across title and content. It does not currently use embeddings, semantic search, or RAG. See [the architecture notes](../../docs/architecture.md) for the system diagram, storage choices, and open operational decisions.

## Memory enrichment worker

Apply migrations before starting the API so the enrichment status and lease columns are
available:

```bash
cd apps/api
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

The polling worker starts automatically in the FastAPI lifespan; it does not need a
separate command. It polls `memory_enrichments` every second for pending jobs, due
retries, and expired processing leases. Each API process may run a worker because the
database claim is atomic. A job has at most three application-level attempts, with
jittered delays around 5 seconds and 30 seconds. The OpenAI request timeout is 40
seconds, and SDK-level automatic retries are disabled so the persisted attempt count
remains the retry limit. Refusals and invalid enrichment output fail without retry;
transient provider and network errors can be retried.

Each atomic worker claim creates a row in `memory_enrichment_attempts`. The row is
updated with the Responses API response/request IDs, returned model, status, token
usage and outcome when available. Refused, incomplete and invalid responses retain
reported usage. Provider failures without usage keep token and cost fields null. A
worker crash can leave an attempt as `unknown`; recovery never overwrites that row,
and a retry receives a separate record. Usage rows contain no memory text and remain
for billing aggregates after memory deletion, with their memory reference cleared.

Estimated cost is calculated with Decimal arithmetic from the returned model and
deployment configuration. `OPENAI_MODEL_PRICING` is a JSON object keyed by model;
each value has `input_per_million` and `output_per_million`, and may specify
`cached_input_per_million` and `cache_write_input_per_million`. Values are decimal
USD rates. `OPENAI_PRICING_VERSION` labels the configuration snapshot. The applied
rates and version are copied to each attempt for historical explanation. Configure
rates from the organization's approved price source, keyed by the exact returned
Responses API model name; this repository intentionally does not set provider prices.
Missing models, missing rates for reported cached
tokens, or invalid/missing usage produce a null estimate without failing enrichment.
These are estimates based on usage, not actual billed amounts. No usage reporting API
or frontend display is added by this task.

New memories and content edits queue enrichment without changing the original content.
Use `GET /memories/{memory_id}/enrichment` to read `pending`, `processing`,
`completed`, or `failed`, along with `attempt_count`, `last_error`, and
`next_retry_at`, plus the effective enrichment metadata and `manual_fields`.
Authenticated clients can use `PATCH /memories/{memory_id}/enrichment` to correct
summary, category, memory type, tags, entities, and importance. These corrections are
stored separately from AI-generated values and remain effective across retries and
content-triggered re-enrichment until cleared with `clear_overrides`. A `null` scalar
is an explicit manual clear; empty tag/entity arrays clear those values. To return a
field to its AI-generated value, name it in `clear_overrides`. Corrections never
change the original memory content. Existing enrichment rows are migrated as
completed.

## Python checks

Run from `apps/api/`:

```bash
uv run pytest
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run alembic upgrade head
```

## Integration and regression tests

The normal API suite uses isolated SQLite databases and does not need the local
development database. To include the PostgreSQL-only migration and parallel worker
claim tests, set `AURA62_POSTGRES_TEST_URL` to a disposable PostgreSQL database whose
name ends in `_aura62_test`. The tests create and remove uniquely named schemas in
that database; never point this variable at the development database.

```powershell
$env:AURA62_POSTGRES_TEST_URL = "postgresql+psycopg://<user>:<password>@<host>:5432/aura_aura62_test"
uv run pytest tests/test_postgres_enrichment_contract.py
uv run pytest
```

The PostgreSQL migration scenario upgrades through Alembic head from the revision
before AURA-61, checks the existing-row generation backfill, usage constraints,
foreign-key deletion behavior and downgrade. The concurrency scenario uses two
independent PostgreSQL sessions competing to claim one pending job. Both tests skip
when the disposable database URL is not configured.
