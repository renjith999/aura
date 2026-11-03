// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});
