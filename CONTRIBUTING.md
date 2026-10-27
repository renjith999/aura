# Contributing to Aura

## Prerequisites

- Python 3.13 and uv for the FastAPI backend
- Node.js 22 or newer and pnpm 9 for the web and shared TypeScript workspaces

## Setup

Follow the repository [quick start](README.md#quick-start). The Python backend is the authoritative API. The TypeScript/Fastify code under `apps/api/src` is retained as legacy reference and is not a supported runtime.

## Working agreement

- Keep backend application code in `apps/api/app`, web code in `apps/web`, and reusable TypeScript contracts in `packages/`.
- Do not commit `.env` files, credentials, database dumps, or generated output.
- Add tests for behavior changes. Run the relevant Python and web checks before opening a pull request; record any checks that cannot run and why.
- Keep changes small and use conventional, imperative commit messages.

## Environment

Copy `apps/api/.env.example` to `apps/api/.env`. The checked-in values are suitable only for local development.