# Aura

Aura is an AI unified recall assistant: a private place to collect, search, and
retrieve the context that matters to you.

## Repository

This repository is a TypeScript monorepo managed with [pnpm](https://pnpm.io/).
Phase 0 establishes the development foundation; product workflows have not been
implemented yet.

```
apps/
  api/              Fastify service and health endpoint
  web/              React + Vite client shell
packages/
  contracts/        Shared API types and validation schemas
infra/              Local PostgreSQL and Redis services
docs/               Architecture and delivery decisions
```

## Quick start

1. Install Node.js 22+ and pnpm 9+ (or run `corepack enable`).
2. Copy `.env.example` to `.env` and adjust values if needed.
3. Start local dependencies: `docker compose up -d`.
4. Install packages: `pnpm install`.
5. Start the apps: `pnpm dev`.

The web app runs on `http://localhost:5173`; the API health check is available
at `http://localhost:3000/health`.

## Useful commands

| Command             | Purpose                             |
| ------------------- | ----------------------------------- |
| `pnpm dev`          | Run API and web in watch mode       |
| `pnpm build`        | Type-check and build all workspaces |
| `pnpm lint`         | Run ESLint                          |
| `pnpm test`         | Run unit tests                      |
| `pnpm format:check` | Verify formatting                   |

See [the architecture notes](docs/architecture.md) for Phase 0 boundaries and
[the contribution guide](CONTRIBUTING.md) for repository conventions.
