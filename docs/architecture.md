# Aura architecture — Phase 0

## Purpose

Phase 0 provides a safe, repeatable base for product development. It deliberately
does not decide ingestion sources, retrieval strategy, provider selection, or UI
workflows.

## Boundaries

- **Web (`@aura/web`)** owns browser rendering and user interaction.
- **API (`@aura/api`)** owns HTTP transport, authentication, orchestration, and
  access control. Clients must not connect directly to backing services.
- **Contracts (`@aura/contracts`)** owns public request/response schemas and
  shared domain types. It must not import either application.
- **PostgreSQL** is the durable source of truth; **Redis** is reserved for
  ephemeral caching, jobs, and rate limiting.

## Initial deployment shape

```
Browser → web → API → PostgreSQL
                       ↘ Redis
```

The web and API are independently deployable. Environment variables configure
their connection, and secrets remain in the deployment platform rather than the
repository.

## Phase 0 exit criteria

- A new contributor can boot the web app, API, PostgreSQL, and Redis locally.
- The API exposes a dependency-free health endpoint.
- Shared API contracts are imported by both application boundaries.
- CI type-checks, lints, tests, and builds every workspace.
- No credentials or production infrastructure assumptions are committed.
