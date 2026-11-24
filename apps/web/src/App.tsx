import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  ApiError,
  createMemory,
  deleteMemory,
  listMemories,
  login,
  logout,
  register,
  updateMemory,
  type EnrichmentField,
  type MemoryEnrichment,
  type Memory,
  type MemoryInput,
} from './api';
import {
  EnrichmentRequestCancelled,
  MemoryEnrichmentCache,
} from './enrichmentCache';

const TOKEN_KEY = 'aura.access-token';
const EMAIL_KEY = 'aura.account-email';

type EditorState = { mode: 'create' } | { mode: 'edit'; memory: Memory } | null;
type EnrichmentView =
  | { state: 'loading' }
  | { state: 'unavailable' }
  | { state: 'error'; message: string }
  | { state: 'ready'; data: MemoryEnrichment };

const ENRICHMENT_POLL_INTERVAL_MS = 2500;

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState(() => sessionStorage.getItem(EMAIL_KEY) ?? '');
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [notice, setNotice] = useState('');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [allMemories, setAllMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [editor, setEditor] = useState<EditorState>(null);
  const [detailsMemory, setDetailsMemory] = useState<Memory | null>(null);
  const [enrichmentById, setEnrichmentById] = useState<Record<string, EnrichmentView>>({});
  const [actionBusy, setActionBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const searchInput = useRef<HTMLInputElement>(null);
  const enrichmentCache = useRef<MemoryEnrichmentCache | null>(null);
  if (!enrichmentCache.current) enrichmentCache.current = new MemoryEnrichmentCache();
  const closeDetails = useCallback(() => setDetailsMemory(null), []);

  const clearSession = useCallback((message = '') => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(EMAIL_KEY);
    setToken(null);
    setEmail('');
    setMemories([]);
    setEnrichmentById({});
    setDetailsMemory(null);
    enrichmentCache.current?.clear();
    setNotice('');
    setAuthError(message);
  }, []);

  useEffect(() => {
    enrichmentCache.current?.clear();
    setEnrichmentById({});
    setDetailsMemory(null);
  }, [token]);

  useEffect(() => {
    const timeout = window.setTimeout(() => setAppliedSearch(search.trim()), 220);
    return () => window.clearTimeout(timeout);
  }, [search]);

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchInput.current?.focus();
      }
    }
    window.addEventListener('keydown', focusSearch);
    return () => window.removeEventListener('keydown', focusSearch);
  }, []);

  useEffect(() => {
    if (!token) return;
    let current = true;
    listMemories(token, { query: '', category: '', favoritesOnly: false })
      .then((items) => {
        if (current) setAllMemories(items);
      })
      .catch((error: unknown) => {
        if (!current) return;
        if (error instanceof ApiError && error.status === 401) {
          clearSession('Your session expired. Sign in again to continue.');
        } else {
          setListError(errorMessage(error));
        }
      });
    return () => {
      current = false;
    };
  }, [token, reloadKey, clearSession]);

  useEffect(() => {
    if (!token) return;
    let current = true;
    setLoading(true);
    setListError('');
    listMemories(token, {
      query: appliedSearch,
      category: categoryFilter,
      favoritesOnly,
    })
      .then((items) => {
        if (current) setMemories(items);
      })
      .catch((error: unknown) => {
        if (!current) return;
        if (error instanceof ApiError && error.status === 401) {
          clearSession('Your session expired. Sign in again to continue.');
          return;
        }
        setListError(errorMessage(error));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [token, appliedSearch, categoryFilter, favoritesOnly, reloadKey, clearSession]);

  const loadEnrichment = useCallback(
    async (memoryId: string, refresh = false, isCurrent: () => boolean = () => true) => {
      if (!token) return null;
      try {
        const cache = enrichmentCache.current!;
        const data = refresh
          ? await cache.refresh(token, memoryId)
          : await cache.get(token, memoryId);
        if (isCurrent()) {
          setEnrichmentById((previous) => ({
            ...previous,
            [memoryId]: data ? { state: 'ready', data } : { state: 'unavailable' },
          }));
        }
        return data;
      } catch (error) {
        if (error instanceof EnrichmentRequestCancelled || !isCurrent()) return null;
        if (error instanceof ApiError && error.status === 401) {
          clearSession('Your session expired. Sign in again to continue.');
        } else if (
          error instanceof ApiError &&
          error.status === 404 &&
          error.message === 'Memory not found.'
        ) {
          enrichmentCache.current!.invalidate(memoryId);
          setEnrichmentById((previous) => {
            const next = { ...previous };
            delete next[memoryId];
            return next;
          });
          setDetailsMemory((current) => (current?.id === memoryId ? null : current));
          setReloadKey((value) => value + 1);
        } else {
          setEnrichmentById((previous) => ({
            ...previous,
            [memoryId]: { state: 'error', message: errorMessage(error) },
          }));
        }
        return null;
      }
    },
    [token, clearSession],
  );

  useEffect(() => {
    if (!token || memories.length === 0) return;
    let current = true;
    const memoryIds = memories.map((memory) => memory.id);

    setEnrichmentById((previous) => {
      const next = { ...previous };
      for (const memoryId of memoryIds) {
        if (!next[memoryId]) next[memoryId] = { state: 'loading' };
      }
      return next;
    });

    void Promise.all(memoryIds.map((memoryId) => loadEnrichment(memoryId, false, () => current)));
    return () => {
      current = false;
    };
  }, [token, memories, loadEnrichment]);

  useEffect(() => {
    if (!token) return;
    const visibleIds = new Set(memories.map((memory) => memory.id));
    if (detailsMemory) visibleIds.add(detailsMemory.id);
    const activeIds = Object.entries(enrichmentById)
      .filter(
        ([memoryId, value]) =>
          visibleIds.has(memoryId) &&
          value.state === 'ready' &&
          (value.data.status === 'pending' || value.data.status === 'processing'),
      )
      .map(([memoryId]) => memoryId);
    if (activeIds.length === 0) return;

    let current = true;
    const timer = window.setTimeout(() => {
      void Promise.all(
        activeIds.map((memoryId) => loadEnrichment(memoryId, true, () => current)),
      );
    }, ENRICHMENT_POLL_INTERVAL_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [token, memories, detailsMemory, enrichmentById, loadEnrichment]);

  async function retryEnrichment(memoryId: string) {
    setEnrichmentById((previous) => ({
      ...previous,
      [memoryId]: { state: 'loading' },
    }));
    await loadEnrichment(memoryId, true);
  }

  const categories = useMemo(
    () =>
      [...new Set(allMemories.map((memory) => memory.category))].sort((a, b) => a.localeCompare(b)),
    [allMemories],
  );

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError('');
    setNotice('');
    const form = new FormData(event.currentTarget);
    const submittedEmail = String(form.get('email') ?? '').trim();
    const password = String(form.get('password') ?? '');
    try {
      const response =
        authMode === 'register'
          ? await register(submittedEmail, password)
          : await login(submittedEmail, password);
      sessionStorage.setItem(TOKEN_KEY, response.access_token);
      sessionStorage.setItem(EMAIL_KEY, response.user.email);
      setToken(response.access_token);
      setEmail(response.user.email);
      setAuthError('');
      setNotice(authMode === 'register' ? 'Your account is ready.' : 'Welcome back.');
      setSearch('');
      setAppliedSearch('');
    } catch (error) {
      setAuthError(errorMessage(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    if (!token) return;
    setActionBusy(true);
    try {
      await logout(token);
      clearSession();
      setNotice('You are signed out.');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession('Your session expired. Sign in again to continue.');
      } else {
        setNotice(errorMessage(error));
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function saveMemory(data: MemoryInput) {
    if (!token) return;
    setActionBusy(true);
    setListError('');
    try {
      if (editor?.mode === 'edit') {
        await updateMemory(token, editor.memory.id, data);
        if (data.content !== editor.memory.content) {
          enrichmentCache.current!.invalidate(editor.memory.id);
          setEnrichmentById((previous) => ({
            ...previous,
            [editor.memory.id]: { state: 'loading' },
          }));
        }
        setNotice('Memory updated.');
      } else {
        await createMemory(token, data);
        setNotice('Memory saved.');
      }
      setEditor(null);
      setReloadKey((value) => value + 1);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession('Your session expired. Sign in again to continue.');
      } else {
        setListError(errorMessage(error));
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function toggleFavorite(memory: Memory) {
    if (!token) return;
    setActionBusy(true);
    setListError('');
    try {
      await updateMemory(token, memory.id, { is_favorite: !memory.is_favorite });
      setNotice(memory.is_favorite ? 'Removed from favorites.' : 'Added to favorites.');
      setReloadKey((value) => value + 1);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession('Your session expired. Sign in again to continue.');
      } else {
        setListError(errorMessage(error));
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function removeMemory(memory: Memory) {
    if (!token || !window.confirm(`Delete “${memory.title}”? This cannot be undone.`)) return;
    setActionBusy(true);
    setListError('');
    try {
      await deleteMemory(token, memory.id);
      enrichmentCache.current!.invalidate(memory.id);
      setEnrichmentById((previous) => {
        const next = { ...previous };
        delete next[memory.id];
        return next;
      });
      if (detailsMemory?.id === memory.id) setDetailsMemory(null);
      setNotice('Memory deleted.');
      setReloadKey((value) => value + 1);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearSession('Your session expired. Sign in again to continue.');
      } else {
        setListError(errorMessage(error));
      }
    } finally {
      setActionBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthScreen
        mode={authMode}
        busy={authBusy}
        error={authError}
        onSubmit={submitAuth}
        onModeChange={(mode) => {
          setAuthMode(mode);
          setAuthError('');
        }}
      />
    );
  }

  const favoriteCount = allMemories.filter((memory) => memory.is_favorite).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="Aura home">
          <span className="brand-mark" aria-hidden="true">
            a
          </span>
          <span>Aura</span>
        </a>
        <div className="sidebar-label">Your space</div>
        <nav aria-label="Main navigation">
          <a className="nav-item active" href="#memories" aria-current="page">
            <span className="nav-icon" aria-hidden="true">
              ▦
            </span>{' '}
            All memories
            <span className="nav-count">{allMemories.length}</span>
          </a>
          <button
            className={`nav-item nav-button ${favoritesOnly ? 'active' : ''}`}
            type="button"
            onClick={() => setFavoritesOnly((value) => !value)}
          >
            <span className="nav-icon heart-icon" aria-hidden="true">
              ♥
            </span>{' '}
            Favorites
            <span className="nav-count">{favoriteCount}</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <div className="privacy-note">
            <span className="privacy-icon" aria-hidden="true">
              ◈
            </span>
            <span>
              <strong>Your memories stay yours.</strong>
              <small>Private to your account</small>
            </span>
          </div>
          <div className="profile-row">
            <span className="avatar" aria-hidden="true">
              {email.slice(0, 1).toUpperCase()}
            </span>
            <span className="profile-copy">
              <strong>{email.split('@')[0]}</strong>
              <small>{email}</small>
            </span>
            <button
              className="icon-button profile-menu"
              type="button"
              onClick={signOut}
              disabled={actionBusy}
              aria-label="Sign out"
            >
              ↗
            </button>
          </div>
        </div>
      </aside>

      <main className="dashboard-main" id="top">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark" aria-hidden="true">
              a
            </span>
            <span>Aura</span>
          </div>
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="crumb-divider">/</span>
            <strong>Memories</strong>
          </div>
          <div className="topbar-actions">
            <span className="user-email">{email}</span>
            <button
              className="button button-quiet signout-button"
              type="button"
              onClick={signOut}
              disabled={actionBusy}
            >
              Sign out
            </button>
          </div>
        </header>

        <section className="page-content" id="memories">
          <div className="welcome-row">
            <div>
              <p className="eyebrow">YOUR PERSONAL LIBRARY</p>
              <h1>
                Your memories,
                <br className="mobile-break" /> all in one place.
              </h1>
              <p className="page-subtitle">A quiet space for the things you want to remember.</p>
            </div>
            <button
              className="button button-primary create-button"
              type="button"
              onClick={() => setEditor({ mode: 'create' })}
            >
              <span aria-hidden="true">＋</span> Add a memory
            </button>
          </div>

          <div className="stats-row" aria-label="Memory overview">
            <div className="stat-card">
              <span className="stat-icon lavender" aria-hidden="true">
                ▦
              </span>
              <span>
                <strong>{allMemories.length}</strong>
                <small>Memories</small>
              </span>
            </div>
            <div className="stat-card">
              <span className="stat-icon peach" aria-hidden="true">
                ♥
              </span>
              <span>
                <strong>{favoriteCount}</strong>
                <small>Favorites</small>
              </span>
            </div>
            <div className="stat-card">
              <span className="stat-icon mint" aria-hidden="true">
                ◷
              </span>
              <span>
                <strong>{categories.length}</strong>
                <small>Categories</small>
              </span>
            </div>
            <div className="quote-card">
              <span className="quote-mark" aria-hidden="true">
                “
              </span>
              <p>
                Small things, remembered well,
                <br />
                become a life.
              </p>
              <span className="quote-credit">YOUR PRIVATE LIBRARY</span>
            </div>
          </div>

          {notice && (
            <div className="notice" role="status">
              <span aria-hidden="true">✓</span>
              {notice}
              <button type="button" aria-label="Dismiss notification" onClick={() => setNotice('')}>
                ×
              </button>
            </div>
          )}
          {listError && (
            <div className="alert alert-error" role="alert">
              <span>{listError}</span>
              <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
                Try again
              </button>
            </div>
          )}

          <div className="section-heading">
            <div>
              <h2>Your collection</h2>
              <p>Everything you’ve saved, right where you left it.</p>
            </div>
            <span className="collection-count">
              {memories.length} {memories.length === 1 ? 'memory' : 'memories'}
            </span>
          </div>

          <div className="toolbar">
            <label className="search-box">
              <span className="search-icon" aria-hidden="true">
                ⌕
              </span>
              <span className="sr-only">Search memories</span>
              <input
                ref={searchInput}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search your memories..."
              />
              <kbd>Ctrl K</kbd>
            </label>
            <label className="filter-select">
              <span className="sr-only">Filter by category</span>
              <span className="filter-icon" aria-hidden="true">
                ▤
              </span>
              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option value="">All categories</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {categoryLabel(category)}
                  </option>
                ))}
              </select>
              <span className="select-chevron" aria-hidden="true">
                ⌄
              </span>
            </label>
            <button
              className={`button button-filter ${favoritesOnly ? 'selected' : ''}`}
              type="button"
              onClick={() => setFavoritesOnly((value) => !value)}
              aria-pressed={favoritesOnly}
            >
              <span aria-hidden="true">♥</span> Favorites
            </button>
          </div>

          {loading ? (
            <div className="loading-state" role="status">
              <span className="spinner" aria-hidden="true" />
              Loading your memories…
            </div>
          ) : memories.length === 0 ? (
            <EmptyState
              hasFilters={Boolean(search || categoryFilter || favoritesOnly)}
              onClear={() => {
                setSearch('');
                setCategoryFilter('');
                setFavoritesOnly(false);
              }}
              onCreate={() => setEditor({ mode: 'create' })}
            />
          ) : (
            <div className="memory-grid">
              {memories.map((memory) => (
                <MemoryCard
                  key={memory.id}
                  memory={memory}
                  enrichment={enrichmentById[memory.id] ?? { state: 'loading' }}
                  busy={actionBusy}
                  onFavorite={() => toggleFavorite(memory)}
                  onEdit={() => setEditor({ mode: 'edit', memory })}
                  onDelete={() => removeMemory(memory)}
                  onDetails={() => setDetailsMemory(memory)}
                  onRetryEnrichment={() => void retryEnrichment(memory.id)}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {editor && (
        <MemoryEditor
          key={editor.mode === 'edit' ? editor.memory.id : 'new'}
          editor={editor}
          busy={actionBusy}
          error={listError}
          onClose={() => {
            setEditor(null);
            setListError('');
          }}
          onSave={saveMemory}
        />
      )}
      {detailsMemory && (
        <MemoryDetails
          key={detailsMemory.id}
          memory={detailsMemory}
          enrichment={enrichmentById[detailsMemory.id] ?? { state: 'loading' }}
          onClose={closeDetails}
          onRetry={() => void retryEnrichment(detailsMemory.id)}
        />
      )}
    </div>
  );
}

function AuthScreen({
  mode,
  busy,
  error,
  onSubmit,
  onModeChange,
}: {
  mode: 'login' | 'register';
  busy: boolean;
  error: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onModeChange: (mode: 'login' | 'register') => void;
}) {
  const isRegister = mode === 'register';
  return (
    <main className="auth-page">
      <div className="auth-topbar">
        <a className="brand" href="#top">
          <span className="brand-mark" aria-hidden="true">
            a
          </span>
          <span>Aura</span>
        </a>
        <span className="auth-top-note">YOUR PRIVATE MEMORY SPACE</span>
      </div>
      <div className="auth-layout">
        <section className="auth-story">
          <div className="auth-orbit orbit-one" />
          <div className="auth-orbit orbit-two" />
          <div className="auth-story-content">
            <span className="story-chip">
              <span className="sparkle" aria-hidden="true">
                ✳
              </span>{' '}
              A LITTLE SPACE FOR WHAT MATTERS
            </span>
            <h1>
              Keep the moments
              <br />
              you don’t want to lose.
            </h1>
            <p>Your thoughts, plans, and small reminders—together in one calm, private place.</p>
            <div className="story-note">
              <span className="note-star" aria-hidden="true">
                ✦
              </span>
              <span>
                Keep the little details close, and find them when you need them.
                <small>Your private memory space</small>
              </span>
            </div>
          </div>
          <span className="auth-art-label">YOUR MIND, WITH ROOM TO BREATHE</span>
        </section>

        <section className="auth-panel" id="top">
          <div className="auth-form-wrap">
            <div className="auth-mobile-mark">
              <span className="brand-mark" aria-hidden="true">
                a
              </span>
            </div>
            <p className="eyebrow">{isRegister ? 'BEGIN YOUR COLLECTION' : 'WELCOME BACK'}</p>
            <h2>{isRegister ? 'Create your account' : 'Sign in to Aura'}</h2>
            <p className="auth-subtitle">
              {isRegister
                ? 'A home for the things you want to remember.'
                : 'Your memories are right where you left them.'}
            </p>

            <div className="auth-tabs" role="tablist" aria-label="Account access">
              <button
                className={!isRegister ? 'active' : ''}
                type="button"
                role="tab"
                aria-selected={!isRegister}
                onClick={() => onModeChange('login')}
              >
                Sign in
              </button>
              <button
                className={isRegister ? 'active' : ''}
                type="button"
                role="tab"
                aria-selected={isRegister}
                onClick={() => onModeChange('register')}
              >
                Create account
              </button>
            </div>

            <form className="auth-form" onSubmit={onSubmit}>
              <label>
                Email address
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                  maxLength={320}
                />
              </label>
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  placeholder={isRegister ? 'At least 12 characters' : 'Enter your password'}
                  required
                  minLength={isRegister ? 12 : 1}
                  maxLength={1024}
                />
              </label>
              {error && (
                <div className="alert alert-error" role="alert">
                  {error}
                </div>
              )}
              <button className="button button-primary auth-submit" type="submit" disabled={busy}>
                {busy ? 'Please wait…' : isRegister ? 'Create my account' : 'Sign in'}
                {!busy && <span aria-hidden="true">→</span>}
              </button>
            </form>
            <div className="auth-assurance">
              <span aria-hidden="true">◇</span> Your memories are private to your account.
            </div>
          </div>
          <footer className="auth-footer">
            <span>Made for remembering.</span>
            <span>© Aura</span>
          </footer>
        </section>
      </div>
    </main>
  );
}

function EmptyState({
  hasFilters,
  onClear,
  onCreate,
}: {
  hasFilters: boolean;
  onClear: () => void;
  onCreate: () => void;
}) {
  return (
    <div className="empty-state">
      <div className="empty-illustration" aria-hidden="true">
        <span className="empty-sun" />
        <span className="empty-card card-back" />
        <span className="empty-card card-front">
          <i />
          <i />
          <i />
        </span>
        <span className="empty-spark">✦</span>
      </div>
      <p className="eyebrow">{hasFilters ? 'NO MATCHES YET' : 'A FRESH START'}</p>
      <h3>{hasFilters ? 'Nothing here fits that search.' : 'Your first memory is waiting.'}</h3>
      <p>
        {hasFilters
          ? 'Try another phrase or clear your filters to see everything.'
          : 'Save a thought, a plan, or a tiny detail you want to keep close.'}
      </p>
      {hasFilters ? (
        <button className="button button-outline" type="button" onClick={onClear}>
          Clear filters
        </button>
      ) : (
        <button className="button button-primary" type="button" onClick={onCreate}>
          ＋ Add your first memory
        </button>
      )}
    </div>
  );
}

function MemoryCard({
  memory,
  enrichment,
  busy,
  onFavorite,
  onEdit,
  onDelete,
  onDetails,
  onRetryEnrichment,
}: {
  memory: Memory;
  enrichment: EnrichmentView;
  busy: boolean;
  onFavorite: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onDetails: () => void;
  onRetryEnrichment: () => void;
}) {
  return (
    <article className="memory-card">
      <div className="memory-card-top">
        <span className={`category-tag category-${categoryTone(memory.category)}`}>
          <i aria-hidden="true" />
          Saved: {categoryLabel(memory.category)}
        </span>
        <button
          className={`favorite-button ${memory.is_favorite ? 'is-favorite' : ''}`}
          type="button"
          onClick={onFavorite}
          disabled={busy}
          aria-label={memory.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
          aria-pressed={memory.is_favorite}
        >
          ♥
        </button>
      </div>
      <h3>{memory.title}</h3>
      <EnrichmentCardPreview enrichment={enrichment} onRetry={onRetryEnrichment} />
      <div className="memory-card-bottom">
        <span className="memory-date">
          <span aria-hidden="true">◷</span>
          {formatDate(memory.updated_at)}
        </span>
        <div className="card-actions">
          <button type="button" onClick={onDetails} aria-label={`View details for ${memory.title}`}>
            Details
          </button>
          <span aria-hidden="true">·</span>
          <button
            type="button"
            onClick={onEdit}
            disabled={busy}
            aria-label={`Edit ${memory.title}`}
          >
            Edit
          </button>
          <span aria-hidden="true">·</span>
          <button
            type="button"
            className="delete-action"
            onClick={onDelete}
            disabled={busy}
            aria-label={`Delete ${memory.title}`}
          >
            Delete
          </button>
        </div>
      </div>
    </article>
  );
}

function EnrichmentCardPreview({
  enrichment,
  onRetry,
}: {
  enrichment: EnrichmentView;
  onRetry: () => void;
}) {
  if (enrichment.state === 'loading') {
    return (
      <div className="enrichment-preview loading" role="status" aria-label="Loading enrichment">
        <span className="enrichment-skeleton" />
      </div>
    );
  }
  if (enrichment.state === 'unavailable') {
    return <p className="enrichment-note">Enrichment is not available.</p>;
  }
  if (enrichment.state === 'error') {
    return (
      <div className="enrichment-error" role="alert">
        <span>Enrichment could not be loaded.</span>
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      </div>
    );
  }

  const { data } = enrichment;
  const summarySource = data.manual_fields.includes('summary') ? 'Manual' : 'AI';
  const categorySource = data.manual_fields.includes('category') ? 'Manual' : 'AI';
  return (
    <div className="enrichment-preview">
      <div className="enrichment-card-status">
        <EnrichmentStatusBadge status={data.status} />
      </div>
      {data.summary ? (
        <p className="enrichment-summary-preview">
          <span>{summarySource} summary</span>
          {data.summary}
        </p>
      ) : (
        <p className="enrichment-note">No summary available.</p>
      )}
      <div className="enrichment-chip-row">
        {data.category && (
          <span className={`enrichment-category category-${categoryTone(data.category)}`}>
            {categorySource} category: {humanize(data.category)}
          </span>
        )}
        {data.tags.slice(0, 2).map((tag) => (
          <span className="metadata-chip" key={tag}>
            {tag}
          </span>
        ))}
        {data.tags.length > 2 && (
          <span className="metadata-chip metadata-chip-more">+{data.tags.length - 2}</span>
        )}
      </div>
    </div>
  );
}

function EnrichmentStatusBadge({ status }: { status: MemoryEnrichment['status'] }) {
  const labels: Record<MemoryEnrichment['status'], string> = {
    pending: 'Waiting',
    processing: 'Processing',
    completed: 'Enriched',
    failed: 'Enrichment failed',
  };
  return (
    <span className={`enrichment-status status-${status}`} aria-label={`Enrichment ${labels[status]}`}>
      <span aria-hidden="true" />
      {labels[status]}
    </span>
  );
}

function MemoryDetails({
  memory,
  enrichment,
  onClose,
  onRetry,
}: {
  memory: Memory;
  enrichment: EnrichmentView;
  onClose: () => void;
  onRetry: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>('button, [href], input, select, textarea')?.focus();

    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }

    document.addEventListener('keydown', handleDialogKeys);
    return () => {
      document.removeEventListener('keydown', handleDialogKeys);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="modal-backdrop details-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="editor-modal details-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-details-title"
        ref={dialogRef}
      >
        <div className="modal-heading">
          <div>
            <p className="eyebrow">MEMORY DETAILS</p>
            <h2 id="memory-details-title">{memory.title}</h2>
          </div>
          <button
            className="icon-button modal-close"
            type="button"
            onClick={onClose}
            aria-label="Close memory details"
            autoFocus
          >
            ×
          </button>
        </div>

        <section className="details-original" aria-labelledby="original-memory-heading">
          <div className="details-section-heading">
            <h3 id="original-memory-heading">Original memory</h3>
            <span>Saved exactly as written</span>
          </div>
          <p className="details-original-content">{memory.content}</p>
          <p className="details-saved-category">
            Saved category: <strong>{categoryLabel(memory.category)}</strong>
          </p>
        </section>

        <section className="details-enrichment" aria-labelledby="enrichment-heading">
          <div className="details-section-heading">
            <h3 id="enrichment-heading">Enriched metadata</h3>
            {enrichment.state === 'ready' && (
              <EnrichmentStatusBadge status={enrichment.data.status} />
            )}
          </div>
          {enrichment.state === 'loading' ? (
            <div className="details-loading" role="status">
              <span className="spinner" aria-hidden="true" />
              Loading enrichment…
            </div>
          ) : enrichment.state === 'unavailable' ? (
            <p className="enrichment-note">Enrichment is not available for this memory.</p>
          ) : enrichment.state === 'error' ? (
            <div className="details-error" role="alert">
              <span>Enrichment could not be loaded. {enrichment.message}</span>
              <button className="button button-outline" type="button" onClick={onRetry}>
                Retry
              </button>
            </div>
          ) : (
            <EnrichmentDetails data={enrichment.data} />
          )}
        </section>
      </section>
    </div>
  );
}

function EnrichmentDetails({ data }: { data: MemoryEnrichment }) {
  const manuallyOverridden = (field: EnrichmentField) => data.manual_fields.includes(field);
  const emptyValue = (field: EnrichmentField) =>
    manuallyOverridden(field) ? 'Cleared manually' : 'Not available';

  return (
    <>
      <div className="details-status-copy" aria-live="polite">
        {data.status === 'pending' && <p>Enrichment is queued for processing.</p>}
        {data.status === 'processing' && <p>Aura is analyzing this memory.</p>}
        {data.status === 'completed' && <p>Enrichment is complete.</p>}
        {data.status === 'failed' && (
          <p>
            Enrichment could not be completed after {data.attempt_count} attempt
            {data.attempt_count === 1 ? '' : 's'}.
            {data.next_retry_at
              ? ` Another attempt is scheduled for ${formatDateTime(data.next_retry_at)}.`
              : ' No retry is scheduled.'}
          </p>
        )}
      </div>

      <dl className="enrichment-details-list">
        <MetadataDetail
          label="Summary"
          field="summary"
          value={data.summary}
          emptyLabel={emptyValue('summary')}
          manual={manuallyOverridden('summary')}
        />
        <MetadataDetail
          label="Enriched category"
          field="category"
          value={data.category ? humanize(data.category) : null}
          emptyLabel={emptyValue('category')}
          manual={manuallyOverridden('category')}
        />
        <MetadataDetail
          label="Memory type"
          field="memory_type"
          value={data.memory_type ? humanize(data.memory_type) : null}
          emptyLabel={emptyValue('memory_type')}
          manual={manuallyOverridden('memory_type')}
        />
        <MetadataDetail
          label="Tags"
          field="tags"
          value={data.tags.length ? data.tags.join(', ') : null}
          emptyLabel={emptyValue('tags')}
          manual={manuallyOverridden('tags')}
        />
        <MetadataDetail
          label="Entities"
          field="entities"
          value={
            data.entities.length
              ? data.entities.map((entity) => `${entity.name} · ${humanize(entity.entity_type)}`).join(', ')
              : null
          }
          emptyLabel={emptyValue('entities')}
          manual={manuallyOverridden('entities')}
        />
        <MetadataDetail
          label="Importance"
          field="importance"
          value={data.importance === null ? null : `${data.importance} out of 5`}
          emptyLabel={emptyValue('importance')}
          manual={manuallyOverridden('importance')}
        />
      </dl>
    </>
  );
}

function MetadataDetail({
  label,
  field,
  value,
  emptyLabel,
  manual,
}: {
  label: string;
  field: EnrichmentField;
  value: string | null;
  emptyLabel: string;
  manual: boolean;
}) {
  return (
    <div className="metadata-detail-row" data-field={field}>
      <dt>{label}</dt>
      <dd>
        <span className={value === null ? 'metadata-empty' : ''}>{value ?? emptyLabel}</span>
        <span className={`metadata-origin ${manual ? 'origin-manual' : 'origin-ai'}`}>
          {manual ? 'Manually corrected' : 'AI-generated'}
        </span>
      </dd>
    </div>
  );
}

function MemoryEditor({
  editor,
  busy,
  error,
  onClose,
  onSave,
}: {
  editor: Exclude<EditorState, null>;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (data: MemoryInput) => void;
}) {
  const memory = editor.mode === 'edit' ? editor.memory : undefined;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    onSave({
      title: String(values.get('title') ?? ''),
      content: String(values.get('content') ?? ''),
      category: String(values.get('category') ?? '').trim() || 'uncategorized',
      is_favorite: values.get('is_favorite') === 'on',
    });
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        className="editor-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-title"
      >
        <div className="modal-heading">
          <div>
            <p className="eyebrow">YOUR PERSONAL LIBRARY</p>
            <h2 id="editor-title">{memory ? 'Edit memory' : 'Save a memory'}</h2>
          </div>
          <button
            className="icon-button modal-close"
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <p className="editor-intro">Keep the details that matter, exactly as you remember them.</p>
        <form className="editor-form" onSubmit={submit}>
          <label>
            Title
            <input
              name="title"
              defaultValue={memory?.title ?? ''}
              placeholder="Give this memory a name"
              maxLength={200}
              required
              autoFocus
            />
          </label>
          <label>
            Memory
            <textarea
              name="content"
              defaultValue={memory?.content ?? ''}
              placeholder="Write it down in your own words…"
              rows={7}
              required
            />
          </label>
          <label>
            Category
            <input
              name="category"
              defaultValue={memory?.category === 'uncategorized' ? '' : (memory?.category ?? '')}
              placeholder="e.g. Work, Ideas, Personal"
              maxLength={100}
            />
            <small>Choose a simple label that helps you find it later.</small>
          </label>
          <label className="favorite-check">
            <input
              name="is_favorite"
              type="checkbox"
              defaultChecked={memory?.is_favorite ?? false}
            />
            <span className="custom-check" aria-hidden="true" />
            <span>Keep this one in my favorites</span>
          </label>
          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}
          <div className="modal-actions">
            <button
              className="button button-outline"
              type="button"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </button>
            <button className="button button-primary" type="submit" disabled={busy}>
              {busy ? 'Saving…' : memory ? 'Save changes' : 'Save memory'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}

function categoryLabel(category: string) {
  return category === 'uncategorized' ? 'Uncategorized' : category;
}

function humanize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function categoryTone(category: string) {
  const tones = ['lavender', 'peach', 'mint', 'blue'];
  let hash = 0;
  for (const character of category) hash = (hash + character.charCodeAt(0)) % tones.length;
  return tones[hash] ?? tones[0];
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Recently updated';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'a later time';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

export default App;
