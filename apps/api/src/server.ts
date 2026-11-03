// Legacy TypeScript/Fastify bootstrap from Phase 0. Python/FastAPI is authoritative.
import Fastify, { type FastifyServerOptions } from 'fastify';
import type { HealthResponse } from '@aura/contracts';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function buildServer(options: FastifyServerOptions = {}) {
  const app = Fastify({ logger: true, ...options });

  app.get('/health', async (): Promise<HealthResponse> => ({
    status: 'ok',
    timestamp: new Date().toISOString(),
  }));

  return app;
}

async function startServer() {
  const app = buildServer();
  const port = Number(process.env.API_PORT ?? 3000);
  const host = process.env.API_HOST ?? '0.0.0.0';

  try {
    await app.listen({ host, port });
  } catch (error) {
    app.log.error(error);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await startServer();
}
