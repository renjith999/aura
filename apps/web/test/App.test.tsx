// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const authResponse = {
  access_token: 'session-token',
  token_type: 'bearer',
  expires_in: 3600,
  user: { id: 'user-1', email: 'renji@example.com' },
};

const memoryFixture = {
  id: 'memory-1',
  title: 'Morning walk',
  content: 'The original note stays exactly as it was written.',
  category: 'personal',
  is_favorite: false,
  user_id: 'user-1',
  created_at: '2026-11-03T10:00:00.000Z',
  updated_at: '2026-11-03T10:00:00.000Z',
};

function enrichmentFixture(
  memoryId: string,
  status: 'pending' | 'processing' | 'completed' | 'failed' = 'completed',
) {
  return {
    memory_id: memoryId,
    status,
    attempt_count: status === 'pending' ? 0 : 1,
    last_error: status === 'failed' ? 'ProviderError' : null,
    next_retry_at: status === 'failed' ? '2026-11-16T12:30:00Z' : null,
    completed_at: status === 'completed' ? '2026-11-16T10:00:00Z' : null,
    summary: 'A manually refined note about a morning walk.',
    category: 'work',
    memory_type: 'preference',
    tags: ['routine', 'wellbeing', 'outdoors'],
    entities: [{ name: 'River Park', entity_type: 'location' }],
    importance: 4,
    manual_fields: ['summary', 'category'],
  };
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe('Aura web app', () => {
  it('signs in, stores the session, and loads the memory dashboard', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/auth/login')) return jsonResponse(authResponse);
      if (url.includes('/memories')) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'renji@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct horse' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Welcome back.')).toBeTruthy();
    expect(screen.getByText('Your collection')).toBeTruthy();
    expect(sessionStorage.getItem('aura.access-token')).toBe('session-token');
    expect(sessionStorage.getItem('aura.account-email')).toBe('renji@example.com');

    const memoryRequests = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/memories'),
    );
    expect(memoryRequests.length).toBeGreaterThan(0);
    expect(new Headers(memoryRequests[0]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer session-token',
    );
  });

  it('creates a memory and refreshes the collection', async () => {
    const existingMemory = {
      id: 'memory-1',
      title: 'Morning walk',
      content: 'Walk by the river',
      category: 'personal',
      is_favorite: false,
      user_id: 'user-1',
      created_at: '2026-11-03T10:00:00.000Z',
      updated_at: '2026-11-03T10:00:00.000Z',
    };
    const createdMemory = {
      ...existingMemory,
      id: 'memory-2',
      title: 'Weekend plan',
      content: 'Visit the botanical garden',
      category: 'Ideas',
      is_favorite: true,
    };
    let created = false;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/memories') && init?.method === 'POST') {
        created = true;
        return jsonResponse(createdMemory);
      }
      if (url.includes('/enrichment')) {
        return jsonResponse(enrichmentFixture(decodeURIComponent(url.split('/').at(-2) ?? '')));
      }
      if (url.includes('/memories')) {
        return jsonResponse(created ? [existingMemory, createdMemory] : [existingMemory]);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Morning walk')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Add a memory' }));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Weekend plan' } });
    fireEvent.change(screen.getByLabelText('Memory'), {
      target: { value: 'Visit the botanical garden' },
    });
    fireEvent.change(screen.getByPlaceholderText('e.g. Work, Ideas, Personal'), {
      target: { value: '  Ideas  ' },
    });
    fireEvent.click(screen.getByLabelText('Keep this one in my favorites'));
    fireEvent.click(screen.getByRole('button', { name: 'Save memory' }));

    expect(await screen.findByText('Memory saved.')).toBeTruthy();
    expect(await screen.findByText('Weekend plan')).toBeTruthy();
    await waitFor(() => expect(created).toBe(true));

    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      title: 'Weekend plan',
      content: 'Visit the botanical garden',
      category: 'Ideas',
      is_favorite: true,
    });
  });

  it('shows effective metadata, provenance, and original content in the detail dialog', async () => {
    const enrichment = enrichmentFixture(memoryFixture.id);
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) return jsonResponse(enrichment);
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);

    expect(await screen.findByText('A manually refined note about a morning walk.')).toBeTruthy();
    expect(screen.getByText('Saved: personal')).toBeTruthy();
    expect(screen.getByText('Manual category: Work')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'View details for Morning walk' }));

    expect(screen.getByRole('dialog', { name: 'Morning walk' })).toBeTruthy();
    expect(screen.getByText('Original memory')).toBeTruthy();
    expect(screen.getByText(memoryFixture.content)).toBeTruthy();
    expect(screen.getByText('Enriched metadata')).toBeTruthy();
    expect(screen.getByText('Preference')).toBeTruthy();
    expect(screen.getByText('4 out of 5')).toBeTruthy();
    expect(screen.getByText('River Park · Location')).toBeTruthy();
    expect(screen.getAllByText('Manually corrected').length).toBe(2);
    expect(screen.getAllByText('AI-generated').length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('Edit metadata')).toBeNull();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it.each([
    ['pending', 'Waiting', 'Enrichment is queued for processing.'],
    ['processing', 'Processing', 'Aura is analyzing this memory.'],
    ['completed', 'Enriched', 'Enrichment is complete.'],
    ['failed', 'Enrichment failed', 'Another attempt is scheduled for'],
  ] as const)('renders %s enrichment state', async (status, badge, detailText) => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) return jsonResponse(enrichmentFixture(memoryFixture.id, status));
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText(badge)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'View details for Morning walk' }));
    expect(await screen.findByText(new RegExp(detailText))).toBeTruthy();
  });

  it('polls pending enrichment and stops after a terminal result', async () => {
    let enrichmentCalls = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) {
        enrichmentCalls += 1;
        return jsonResponse(
          enrichmentFixture(memoryFixture.id, enrichmentCalls === 1 ? 'pending' : 'completed'),
        );
      }
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Waiting')).toBeTruthy();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2600));
    });
    expect(await screen.findByText('Enriched')).toBeTruthy();
    expect(enrichmentCalls).toBe(2);
  });

  it('invalidates cached enrichment after editing original memory content', async () => {
    let savedMemory = memoryFixture;
    let enrichmentCalls = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) {
        enrichmentCalls += 1;
        return jsonResponse({
          ...enrichmentFixture(savedMemory.id),
          summary: enrichmentCalls === 1 ? 'Before the edit.' : 'After the edit.',
        });
      }
      if (url.endsWith('/memories/memory-1') && init?.method === 'PATCH') {
        savedMemory = { ...savedMemory, content: JSON.parse(String(init.body)).content };
        return jsonResponse(savedMemory);
      }
      if (url.endsWith('/memories')) return jsonResponse([savedMemory]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Before the edit.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Edit Morning walk' }));
    fireEvent.change(screen.getByLabelText('Memory'), {
      target: { value: 'Updated original wording.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Memory updated.')).toBeTruthy();
    expect(await screen.findByText('After the edit.')).toBeTruthy();
    expect(savedMemory.content).toBe('Updated original wording.');
    expect(enrichmentCalls).toBe(2);
  });

  it('shows unavailable enrichment for a 404 without failing the memory list', async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) {
        return jsonResponse({ detail: 'Memory enrichment status not found.' }, 404);
      }
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Enrichment is not available.')).toBeTruthy();
    expect(screen.getByText('Morning walk')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders null and empty metadata as safe, provenance-aware values', async () => {
    const partial = {
      ...enrichmentFixture(memoryFixture.id),
      summary: null,
      category: null,
      memory_type: null,
      tags: [],
      entities: [],
      importance: null,
      manual_fields: ['summary', 'tags'],
    };
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) return jsonResponse(partial);
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Enriched')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'View details for Morning walk' }));

    expect(screen.getAllByText('Cleared manually')).toHaveLength(2);
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
  });

  it('shows an enrichment skeleton while its request is in flight', async () => {
    let resolveEnrichment!: (response: Response) => void;
    const enrichmentResponse = new Promise<Response>((resolve) => {
      resolveEnrichment = resolve;
    });
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) return enrichmentResponse;
      if (url.endsWith('/memories')) return Promise.resolve(jsonResponse([memoryFixture]));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByRole('status', { name: 'Loading enrichment' })).toBeTruthy();
    resolveEnrichment(jsonResponse(enrichmentFixture(memoryFixture.id)));
    expect(await screen.findByText('Enriched')).toBeTruthy();
  });

  it('refreshes the list when the enrichment 404 indicates a concurrent deletion', async () => {
    let listCalls = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) {
        return jsonResponse({ detail: 'Memory not found.' }, 404);
      }
      if (url.endsWith('/memories')) {
        listCalls += 1;
        return jsonResponse(listCalls <= 2 ? [memoryFixture] : []);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByText('Your first memory is waiting.')).toBeTruthy();
    expect(screen.queryByText('Enrichment could not be loaded.')).toBeNull();
  });

  it('offers a retry when enrichment cannot be fetched', async () => {
    let enrichmentCalls = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith('/enrichment')) {
        enrichmentCalls += 1;
        return enrichmentCalls === 1
          ? jsonResponse({ detail: 'Unavailable.' }, 503)
          : jsonResponse(enrichmentFixture(memoryFixture.id));
      }
      if (url.endsWith('/memories')) return jsonResponse([memoryFixture]);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    sessionStorage.setItem('aura.access-token', 'session-token');
    sessionStorage.setItem('aura.account-email', 'renji@example.com');

    render(<App />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Enriched')).toBeTruthy();
    expect(enrichmentCalls).toBe(2);
  });
});
