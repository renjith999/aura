import { describe, expect, it, vi } from 'vitest';
import { ApiError, type MemoryEnrichment } from '../src/api';
import { MemoryEnrichmentCache } from '../src/enrichmentCache';

function enrichment(memoryId: string, status: MemoryEnrichment['status'] = 'completed') {
  return {
    memory_id: memoryId,
    status,
    attempt_count: 1,
    last_error: null,
    next_retry_at: null,
    completed_at: null,
    summary: `Summary for ${memoryId}`,
    category: null,
    memory_type: null,
    tags: [],
    entities: [],
    importance: null,
    manual_fields: [],
  } satisfies MemoryEnrichment;
}

describe('MemoryEnrichmentCache', () => {
  it('deduplicates in-flight requests, limits concurrency, and caches by memory ID', async () => {
    let active = 0;
    let maxActive = 0;
    const fetcher = vi.fn(async (_token: string, memoryId: string) => {
      active += 1;
      maxActive = Math.max(active, maxActive);
      await new Promise((resolve) => setTimeout(resolve, 0));
      active -= 1;
      return enrichment(memoryId);
    });
    const cache = new MemoryEnrichmentCache(fetcher, 2);

    const duplicateA = cache.get('token', 'memory-0');
    const duplicateB = cache.get('token', 'memory-0');
    const results = await Promise.all([
      duplicateA,
      duplicateB,
      ...Array.from({ length: 8 }, (_, index) => cache.get('token', `memory-${index + 1}`)),
    ]);

    expect(fetcher).toHaveBeenCalledTimes(9);
    expect(maxActive).toBeLessThanOrEqual(2);
    expect(results[0]).toEqual(results[1]);
    await expect(cache.get('different-token', 'memory-0')).resolves.toEqual(results[0]);
    expect(fetcher).toHaveBeenCalledTimes(9);
  });

  it('caches a missing-enrichment 404 as unavailable', async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValue(new ApiError('Memory enrichment status not found.', 404));
    const cache = new MemoryEnrichmentCache(fetcher);

    await expect(cache.get('token', 'legacy-memory')).resolves.toBeNull();
    await expect(cache.get('token', 'legacy-memory')).resolves.toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not treat a deleted memory 404 as a missing enrichment record', async () => {
    const cache = new MemoryEnrichmentCache(
      vi.fn().mockRejectedValue(new ApiError('Memory not found.', 404)),
    );

    await expect(cache.get('token', 'deleted-memory')).rejects.toMatchObject({
      status: 404,
      message: 'Memory not found.',
    });
  });

  it('invalidates a memory result and fetches the updated enrichment', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(enrichment('memory-1'))
      .mockResolvedValueOnce({ ...enrichment('memory-1'), summary: 'Updated summary' });
    const cache = new MemoryEnrichmentCache(fetcher);

    await expect(cache.get('token', 'memory-1')).resolves.toMatchObject({
      summary: 'Summary for memory-1',
    });
    cache.invalidate('memory-1');
    await expect(cache.get('token', 'memory-1')).resolves.toMatchObject({
      summary: 'Updated summary',
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
