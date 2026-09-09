# Contributing to Aura

## Prerequisites

- Node.js 22 or newer
- pnpm 9 or newer (`corepack enable` is recommended)
- Docker Desktop for local PostgreSQL and Redis

## Working agreement

- Keep app-specific code in `apps/` and reusable types or validation in
  `packages/`.
- Do not commit `.env` files, credentials, database dumps, or generated output.
- Add tests for behavior changes and run `pnpm typecheck && pnpm lint && pnpm
test` before opening a pull request.
- Keep changes small and use conventional, imperative commit messages.

## Environment

Copy `.env.example` to `.env`. The checked-in values are suitable only for
local development.
