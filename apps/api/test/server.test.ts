import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildServer } from '../src/server';

describe('health endpoint', () => {
  let app: FastifyInstance;

  beforeEach(() => {
    app = buildServer({ logger: false });
  });

  afterEach(async () => {
    await app.close();
  });

  it('returns an ok status and an ISO timestamp', async () => {
    const response = await app.inject({ method: 'GET', url: '/health' });
    const body = response.json();

    expect(response.statusCode).toBe(200);
    expect(body.status).toBe('ok');
    expect(Number.isNaN(Date.parse(body.timestamp))).toBe(false);
  });

  it('returns not found for an unsupported route', async () => {
    const response = await app.inject({ method: 'GET', url: '/missing' });

    expect(response.statusCode).toBe(404);
  });
});
