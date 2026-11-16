# Aura Web

The React + Vite client for Aura's Phase 1 memory app.

## Run locally

Start the FastAPI service and apply its database migrations first. From the repository root:

```bash
pnpm install
pnpm --filter @aura/web dev
```

The client uses `http://localhost:8000` by default. To use another API origin, copy `.env.example` to `.env.local`, set `VITE_API_URL`, and set the API's `WEB_ORIGIN` to the Vite origin. The web client keeps the bearer token in tab-scoped session storage and clears it after sign-out or when the API rejects it.

Memory cards show the effective summary, enriched category, tags, and enrichment status. Use **Details** to view the exact original memory separately from its effective enrichment metadata, including memory type, entities, importance, and which fields have manual corrections. The client reads enrichment from `GET /memories/{memory_id}/enrichment`; it does not edit metadata. Pending and processing statuses refresh every 2.5 seconds, and polling stops when enrichment reaches a terminal state. Missing enrichment is shown as unavailable while memory-list, enrichment-request, and deletion errors remain separate.

## Manual verification

1. Open `http://localhost:5173` and create an account with a valid email and a password of at least 12 characters.
2. Create a memory with a title, exact text, and a manual category; confirm it appears in the list.
3. Search by text, filter by category and favorites, favorite/unfavorite a memory, edit it, then delete it.
4. Reload the page and confirm the signed-in session and stored memories remain available in the tab.
5. Sign out, sign in again, and confirm a second account cannot see the first account's memories.
6. Stop the API or use an expired session and confirm the page shows a useful error or returns to sign-in.
7. Check a memory with pending enrichment, wait for its status to update, then open Details and confirm the original text, effective metadata, and any manual correction labels are shown separately.
