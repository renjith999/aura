# Aura architecture

## Supported runtime

Phase 1's supported backend is the Python + FastAPI application in `apps/api/app`. The TypeScript/Fastify bootstrap in `apps/api/src` is retained as legacy reference code and is not a supported startup path. FastAPI generates the interactive reference at `/docs` and the schema at `/openapi.json`.

## System shape

```text
Browser → React/Vite web client → Python/FastAPI API
                                  ├─ health route
                                  ├─ auth routes → auth service → auth repository ─┐
                                  ├─ memory routes → memory service → repository ─┼→ PostgreSQL
                                  └─ chat route → OpenAI service                  │
                                     (optional OPENAI_API_KEY)                    ┘
```

## Code boundaries

- **Web (`apps/web`)** renders the browser experience and calls the API.
- **Routes (`apps/api/app/api/routes`)** parse HTTP requests, apply dependencies, and select response status codes and schemas.
- **Schemas (`apps/api/app/schemas`)** validate request bodies and serialize response data.
- **Services (`apps/api/app/services`)** contain application behavior. Auth and memory routes delegate to these services; the chat route delegates provider work to `OpenAIService`.
- **Repositories (`apps/api/app/repositories`)** contain SQLAlchemy queries and writes for user accounts, sessions, and memories.
- **Models (`apps/api/app/models`)** map application data to database tables.
- **Core (`apps/api/app/core`)** owns settings, database sessions, password/token security, and authenticated-user dependencies.
- **Contracts (`packages/contracts`)** contains shared TypeScript types for the JavaScript workspaces. Python's Pydantic schemas define the active API contract and should be reflected in the generated OpenAPI schema.

## Data and security decisions

- PostgreSQL is the supported persistence store. SQLAlchemy uses synchronous sessions supplied to the synchronous route handlers through `get_db_session`; Alembic migrations define schema changes.
- Memories are stored as submitted. Each memory is associated with the authenticated user, and repository queries scope memory reads, updates, and deletes by that user ID.
- Keyword search uses a case-insensitive match against title and content, then orders by creation time and ID. It is deterministic text search; embeddings, semantic search, and RAG are outside Phase 1.
- Passwords are stored as salted PBKDF2-SHA256 hashes. Access tokens are random opaque bearer values; the database stores their SHA-256 hashes, with expiry and revocation. No JWT signing secret is required.
- `OPENAI_API_KEY` is optional for the API to start. The chat route returns a configuration error when it is absent. Chat does not currently require authentication or enforce usage limits; keep it on a trusted network until access control and rate limits are defined.
- Redis is available in the local Compose file but is not used by the current API runtime.

## Runtime and operations

Settings come from environment variables or `apps/api/.env`, based on `apps/api/.env.example`. Environment variables take precedence. Production requires an explicit server database URL and rejects SQLite. `WEB_ORIGIN` controls the allowed browser origin. The API returns an `X-Request-ID` on responses and logs request ID, method, path, status, and duration without request bodies, query strings, credentials, or note contents.

The documented local startup, endpoint examples, configuration table, and error responses are maintained in [the API guide](../apps/api/README.md). Use the live `/docs` page when checking the generated request and response schemas.
