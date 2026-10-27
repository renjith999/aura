# Aura

Aura is an AI unified recall assistant: a private place to collect, search, and retrieve the context that matters to you.

## Backend direction

The supported backend is Python + FastAPI in `apps/api/app`. The TypeScript/Fastify bootstrap in `apps/api/src` is legacy code from the earlier Phase 0 baseline. It is retained for reference and is not a supported runtime or startup path.

## Repository layout

```text
apps/
  api/app/          Python + FastAPI backend (authoritative)
  api/src/          Legacy TypeScript/Fastify code (reference only)
  web/              React + Vite client shell
packages/
  contracts/        Shared TypeScript contracts used by the web workspace
```

## Prerequisites

- Python 3.13
- uv
- Node.js 22 or newer and pnpm 9 (`corepack enable` is recommended)

## Quick start

1. Copy `apps/api/.env.example` to `apps/api/.env` and set any local values you need.
2. Install Python dependencies: `uv sync --project apps/api --group dev`.
3. Install JavaScript workspace dependencies: `pnpm install`.
4. Start the supported API and web development servers: `pnpm dev`.

The FastAPI service runs at `http://localhost:8000`. Its health endpoint is `http://localhost:8000/health`, and Swagger UI is at `http://localhost:8000/docs`. To start only one app, run `pnpm --filter @aura/api dev` or `pnpm --filter @aura/web dev`.

## Useful commands

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Run the FastAPI backend and web client in watch mode |
| `pnpm --filter @aura/api dev` | Run only the FastAPI backend |
| `pnpm --filter @aura/web dev` | Run only the web client |
| From `apps/api/`: `uv run pytest` | Run Python tests |
| From `apps/api/`: `uv run ruff check .` | Lint Python code |
| `pnpm build` | Build JavaScript workspaces |
| `pnpm lint` | Lint JavaScript workspaces |

See [the architecture notes](docs/architecture.md) for the current backend direction and [the contribution guide](CONTRIBUTING.md) for repository conventions.