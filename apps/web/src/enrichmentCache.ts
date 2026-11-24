import { ApiError, getMemoryEnrichment, type MemoryEnrichment } from './api';

export type EnrichmentLookup = MemoryEnrichment | null;
type EnrichmentFetcher = (token: string, memoryId: string) => Promise<MemoryEnrichment>;

interface QueuedRequest {
  token: string;
  memoryId: string;
  generation: number;
  version: number;
  resolve: (value: EnrichmentLookup) => void;
  reject: (reason: unknown) => void;
}

export class EnrichmentRequestCancelled extends Error {
  constructor() {
    super('The enrichment request is no longer needed.');
    this.name = 'EnrichmentRequestCancelled';
  }
}

/** Per-memory cache with in-flight deduplication and bounded request concurrency. */
export class MemoryEnrichmentCache {
  private readonly cache = new Map<string, EnrichmentLookup>();
  private readonly inFlight = new Map<string, Promise<EnrichmentLookup>>();
  private readonly versions = new Map<string, number>();
  private readonly queue: QueuedRequest[] = [];
  private activeRequests = 0;
  private generation = 0;

  constructor(
    private readonly fetcher: EnrichmentFetcher = getMemoryEnrichment,
    private readonly maxConcurrency = 5,
  ) {}

  get(token: string, memoryId: string): Promise<EnrichmentLookup> {
    if (this.cache.has(memoryId)) {
      return Promise.resolve(this.cache.get(memoryId) ?? null);
    }
    const existing = this.inFlight.get(memoryId);
    if (existing) return existing;

    const generation = this.generation;
    const version = this.versions.get(memoryId) ?? 0;
    const promise = new Promise<EnrichmentLookup>((resolve, reject) => {
      this.queue.push({ token, memoryId, generation, version, resolve, reject });
      this.pump();
    });
    this.inFlight.set(memoryId, promise);
    return promise;
  }

  refresh(token: string, memoryId: string): Promise<EnrichmentLookup> {
    this.invalidate(memoryId);
    return this.get(token, memoryId);
  }

  invalidate(memoryId: string): void {
    this.versions.set(memoryId, (this.versions.get(memoryId) ?? 0) + 1);
    this.cache.delete(memoryId);
    this.inFlight.delete(memoryId);
    this.cancelQueued(memoryId);
  }

  clear(): void {
    this.generation += 1;
    this.cache.clear();
    this.inFlight.clear();
    this.versions.clear();
    for (const request of this.queue.splice(0)) {
      request.reject(new EnrichmentRequestCancelled());
    }
  }

  private cancelQueued(memoryId: string): void {
    for (let index = this.queue.length - 1; index >= 0; index -= 1) {
      const request = this.queue[index];
      if (request?.memoryId === memoryId) {
        this.queue.splice(index, 1);
        request.reject(new EnrichmentRequestCancelled());
      }
    }
  }

  private pump(): void {
    while (this.activeRequests < this.maxConcurrency && this.queue.length > 0) {
      const request = this.queue.shift();
      if (!request) return;
      if (
        request.generation !== this.generation ||
        request.version !== (this.versions.get(request.memoryId) ?? 0)
      ) {
        request.reject(new EnrichmentRequestCancelled());
        continue;
      }

      this.activeRequests += 1;
      void this.fetch(request)
        .then(request.resolve, request.reject)
        .finally(() => {
          this.activeRequests -= 1;
          this.pump();
        });
    }
  }

  private async fetch(request: QueuedRequest): Promise<EnrichmentLookup> {
    try {
      const enrichment = await this.fetcher(request.token, request.memoryId);
      if (
        request.generation !== this.generation ||
        request.version !== (this.versions.get(request.memoryId) ?? 0)
      ) {
        throw new EnrichmentRequestCancelled();
      }
      this.cache.set(request.memoryId, enrichment);
      return enrichment;
    } catch (error) {
      if (
        request.generation !== this.generation ||
        request.version !== (this.versions.get(request.memoryId) ?? 0)
      ) {
        throw new EnrichmentRequestCancelled();
      }
      if (
        error instanceof ApiError &&
        error.status === 404 &&
        error.message === 'Memory enrichment status not found.'
      ) {
        this.cache.set(request.memoryId, null);
        return null;
      }
      throw error;
    } finally {
      const active = this.inFlight.get(request.memoryId);
      if (
        active &&
        request.generation === this.generation &&
        request.version === (this.versions.get(request.memoryId) ?? 0)
      ) {
        this.inFlight.delete(request.memoryId);
      }
    }
  }
}
