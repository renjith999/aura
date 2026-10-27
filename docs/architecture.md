# Aura architecture

## Backend direction

The authoritative API runtime is Python + FastAPI in `apps/api/app`. The TypeScript/Fastify bootstrap in `apps/api/src` belongs to the earlier Phase 0 baseline. It remains as legacy reference code and is not a supported backend or startup path.

## Current boundaries

- **Web (`apps/web`)** owns browser rendering and user interaction.
- **API (`apps/api/app`)** owns HTTP handling and backend application behavior. FastAPI publishes the interactive OpenAPI documentation at `/docs`.
- **Contracts (`packages/contracts`)** contains shared TypeScript contracts for the web workspace. Python request and response models belong with the FastAPI application and should be aligned with these contracts as API endpoints are formalized.
- **Configuration** comes from environment variables; local values belong in ignored `.env` files, based on the checked-in examples.

## Local development shape

```text
Browser → React/Vite web client → Python/FastAPI API
                                  ├─ health endpoint
                                  ├─ chat route
                                  └─ memory search route
```

Use `pnpm dev` to start the supported FastAPI and web development servers, or start either workspace separately. The API listens on port 8000 by default. The legacy Fastify bootstrap is not part of this runtime shape.

## Delivery notes

- Python 3.13 is the backend runtime for Phase 1.
- The FastAPI service is still being verified and its API, persistence, and service boundaries remain active Phase 1 work.
- PostgreSQL, Redis, authentication, and later AI capabilities must be described as implemented only after the corresponding work lands; do not infer them from the original Phase 0 architecture.
- Keep secrets out of the repository and use environment configuration for local development.