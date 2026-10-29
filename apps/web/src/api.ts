export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface Memory {
  id: string;
  title: string;
  content: string;
  category: string;
  is_favorite: boolean;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryInput {
  title: string;
  content: string;
  category: string;
  is_favorite: boolean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const apiOrigin = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${apiOrigin}${path}`, { ...options, headers });
  } catch {
    throw new ApiError('Aura could not reach the server. Check that the API is running.', 0);
  }

  if (response.status === 204) return undefined as T;

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail: unknown }).detail
        : undefined;
    const message = Array.isArray(detail)
      ? detail
          .map((item) =>
            typeof item === 'object' && item !== null && 'msg' in item
              ? String(item.msg)
              : 'Invalid input.',
          )
          .join(' ')
      : typeof detail === 'string'
        ? detail
        : `The request failed (${response.status}).`;
    throw new ApiError(message, response.status);
  }

  return body as T;
}

export function register(email: string, password: string) {
  return request<AuthResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string) {
  return request<AuthResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function logout(token: string) {
  return request<void>('/auth/logout', { method: 'POST' }, token);
}

export function listMemories(
  token: string,
  filters: { query: string; category: string; favoritesOnly: boolean },
) {
  const params = new URLSearchParams();
  if (filters.query) params.set('query', filters.query);
  if (filters.category) params.set('category', filters.category);
  if (filters.favoritesOnly) params.set('is_favorite', 'true');
  const suffix = params.size ? `?${params.toString()}` : '';
  return request<Memory[]>(`/memories${suffix}`, {}, token);
}

export function createMemory(token: string, data: MemoryInput) {
  return request<Memory>(
    '/memories',
    {
      method: 'POST',
      body: JSON.stringify(data),
    },
    token,
  );
}

export function updateMemory(token: string, id: string, data: Partial<MemoryInput>) {
  return request<Memory>(
    `/memories/${encodeURIComponent(id)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
    },
    token,
  );
}

export function deleteMemory(token: string, id: string) {
  return request<void>(`/memories/${encodeURIComponent(id)}`, { method: 'DELETE' }, token);
}
