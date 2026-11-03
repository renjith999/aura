import { describe, expect, it } from 'vitest';
import { healthResponseSchema } from '../src/index';

describe('health response contract', () => {
  it('accepts the API health response shape', () => {
    const result = healthResponseSchema.safeParse({
      status: 'ok',
      timestamp: '2026-11-03T12:00:00.000Z',
    });

    expect(result.success).toBe(true);
  });

  it('rejects an unexpected status or a non-datetime timestamp', () => {
    const result = healthResponseSchema.safeParse({
      status: 'healthy',
      timestamp: 'not-a-date',
    });

    expect(result.success).toBe(false);
  });
});
