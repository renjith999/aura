# ADR 0001: Durable enrichment jobs, overrides, and attempt audit

- **Status:** Accepted (implemented in the current backend)
- **Date:** 2026-11
- **Scope:** Memory enrichment reliability, manual metadata corrections, and per-attempt usage/cost records

## Context

Memory enrichment calls an external provider and may be delayed, refused, incomplete, invalid, or interrupted by a worker restart. The original user text must remain unchanged, retries must not lose manually corrected metadata, and provider usage/cost evidence should survive later configuration changes and memory deletion.

## Decisions

1. Persist one current enrichment generation per memory in PostgreSQL, with a lifecycle state, attempt counter, source-content hash, retry time, lease, and completion time.
2. Use a database polling worker started by each FastAPI process. Claim rows atomically so multiple API instances and direct request background tasks coordinate through the same durable record.
3. Limit each generation to three application-level attempts, with jittered waits around five and thirty seconds, a 40-second provider timeout, and 90-second processing leases. Disable SDK automatic retries so the persisted attempt count bounds the provider calls.
4. Hash source content and check the hash before and after provider work. Discard results for content that changed during the call; never replace `memories.content` with AI output.
5. Store manual metadata in a separate JSON override row keyed by field. Return effective metadata and explicit `manual_fields` from the API, leaving AI values and original memory content distinct.
6. Create a durable audit row for each worker claim. Retain response/request identifiers, model and prompt/schema versions, provider usage details, outcome, and a decimal cost estimate with its applied pricing rates/version snapshot. Keep memory text out of attempt records. Set the memory reference to null on memory deletion so usage history remains.
7. Treat cost as an estimate from explicitly configured deployment rates; do not ship guessed or hardcoded provider pricing and do not represent estimates as actual invoices.

## Consequences

- A database outage prevents job claiming and progress, but persisted jobs remain recoverable when the database returns.
- Every API instance runs a poller. Atomic claims prevent duplicate ownership, though an external provider request may be repeated after a worker crashes and its lease expires; such attempts are marked `unknown` when recoverable.
- Manual values survive content re-enrichment because they are overlaid independently. Clients receive effective values and should use `manual_fields` rather than recreate override precedence.
- Token and cost records are auditable per attempt, including retries, but the current API does not expose usage reports and no actual billing reconciliation is performed.
- Retaining detached attempt rows requires a retention policy to be considered separately if usage-history retention requirements change.

## Alternatives considered

- **In-process task queue only:** rejected because queued work would be lost on process restart and multiple API instances would not coordinate.
- **Redis-backed job queue:** not selected; PostgreSQL already owns the lifecycle and supports transactional claiming without adding a runtime dependency. Redis remains unused by the current API.
- **Store manual edits directly in AI columns:** rejected because later retries/re-enrichment could overwrite corrections and clients could not distinguish their source.
- **Store content in attempt history:** rejected to minimize duplicated sensitive user data; a SHA-256 hash provides stale-source validation without persisting the text.
- **Hardcode provider prices:** rejected because rates can change and vary by model/configuration; each attempt instead snapshots configured rates.

## References

- [Architecture](../architecture.md)
- [Database schema](../database.md)
- [API guide](../../apps/api/README.md)
- [Operations and configuration](../operations.md)
