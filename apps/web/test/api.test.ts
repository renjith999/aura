import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  createMemory,
  deleteMemory,
  getMemoryEnrichment,
  listMemories,
} from '../src/api';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('API client', () => {
  it('encodes memory filters and sends the bearer token', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await listMemories('secret-token', {
      query: 'garden & notes',
      category: 'Ideas & plans',
      favoritesOnly: true,
    });

    const [input, init] = fetchMock.mock.calls[0]!;
    const url = new URL(String(input));
    const headers = new Headers(init?.headers);

    expect(url.pathname).toBe('/memories');
    expect(url.searchParams.get('query')).toBe('garden & notes');
    expect(url.searchParams.get('category')).toBe('Ideas & plans');
    expect(url.searchParams.get('is_favorite')).toBe('true');
    expect(headers.get('Authorization')).toBe('Bearer secret-token');
  });

  it('sends JSON for creates and reports API validation errors', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [{ msg: 'title is required' }] }, 422));

    await expect(
      createMemory('secret-token', {
        title: '',
        content: 'Remember this',
        category: 'personal',
        is_favorite: false,
      }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      message: 'title is required',
      status: 422,
    });

    const [input, init] = fetchMock.mock.calls[0]!;
    const headers = new Headers(init?.headers);

    expect(String(input)).toBe('http://localhost:8000/memories');
    expect(headers.get('Authorization')).toBe('Bearer secret-token');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(JSON.parse(String(init?.body))).toEqual({
      title: '',
      content: 'Remember this',
      category: 'personal',
      is_favorite: false,
    });
  });

  it('returns undefined for 204 responses and encodes memory IDs', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(deleteMemory('secret-token', 'idea/one')).resolves.toBeUndefined();
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://localhost:8000/memories/idea%2Fone');
  });

  it('turns network failures into a user-facing ApiError', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network unavailable'));

    await expect(
      listMemories('secret-token', { query: '', category: '', favoritesOnly: false }),
    ).rejects.toEqual(
      new ApiError('Aura could not reach the server. Check that the API is running.', 0),
    );
  });

  it('loads effective enrichment metadata with the bearer token', async () => {
    const response = {
      memory_id: 'memory/one',
      status: 'completed',
      attempt_count: 1,
      last_error: null,
      next_retry_at: null,
      completed_at: '2026-11-16T10:00:00Z',
      summary: 'Effective summary',
      category: 'work',
      memory_type: 'decision',
      tags: ['planning'],
      entities: [{ name: 'Aura', entity_type: 'product' }],
      importance: 4,
      manual_fields: ['summary'],
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(response));

    await expect(getMemoryEnrichment('secret-token', 'memory/one')).resolves.toEqual(response);

    const [input, init] = fetchMock.mock.calls[0]!;
    expect(String(input)).toBe('http://localhost:8000/memories/memory%2Fone/enrichment');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer secret-token');
  });

  it('preserves enrichment 404 responses as ApiErrors for the cache to interpret', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Memory enrichment status not found.' }, 404),
    );

    await expect(getMemoryEnrichment('secret-token', 'memory-1')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      message: 'Memory enrichment status not found.',
    });
  });
});
