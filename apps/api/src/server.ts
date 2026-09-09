import Fastify from 'fastify';
import type { HealthResponse } from '@aura/contracts';

const app = Fastify({ logger: true });

app.get('/health', async (): Promise<HealthResponse> => ({
  status: 'ok',
  timestamp: new Date().toISOString(),
}));

const port = Number(process.env.API_PORT ?? 3000);
const host = process.env.API_HOST ?? '0.0.0.0';

try {
  await app.listen({ host, port });
} catch (error) {
  app.log.error(error);
  process.exit(1);
}
