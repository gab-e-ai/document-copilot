# Auth Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Supabase Auth end-to-end: backend JWT verification dependency + frontend login/signup pages + protected routing, replacing the Vite boilerplate.

**Architecture:** The frontend uses `@supabase/supabase-js` for browser auth and stores the session. All backend routes that require authentication use a FastAPI `get_current_user` dependency that calls Supabase Auth's `/auth/v1/user` endpoint via httpx to verify the bearer token asynchronously. The frontend lib layer (`env.ts`, `supabase.ts`, `http.ts`) is shared infrastructure for all future features.

**Tech Stack:** Backend — FastAPI, httpx, pytest-asyncio. Frontend — React 19, React Router v7, `@supabase/supabase-js` v2, Vite + Tailwind CSS v4.

## Global Constraints

- Backend: Python ≥ 3.12; all commands via `uv run` from `backend/`
- Backend: async by default in request-path code — no blocking I/O on the event loop
- Backend: `app.config.settings` is the single source of truth — no `os.getenv` in app code
- Backend: unit tests only (no live network); mock httpx calls in `tests/auth/`
- Frontend: all commands via `pnpm` from `frontend/`
- Frontend: TypeScript strict mode; no `any` casts
- Frontend: `src/lib/env.ts` is the single source of truth for env vars — no `import.meta.env` elsewhere
- Frontend: never expose `SUPABASE_SERVICE_ROLE_KEY` or any backend secret to the browser
- Frontend: no Next.js, no SSR, no server components — plain Vite SPA only

---

## File Map

```
backend/
├── app/
│   └── auth/
│       ├── __init__.py          CREATE — empty
│       └── dependencies.py      CREATE — AuthUser dataclass + get_current_user FastAPI dependency
└── tests/
    └── auth/
        ├── __init__.py          CREATE — empty
        └── test_dependencies.py CREATE — unit tests mocking httpx

frontend/
├── vite.config.ts               MODIFY — add tailwindcss() plugin
├── src/
│   ├── App.tsx                  MODIFY — replace boilerplate; React Router routes
│   ├── App.css                  MODIFY — strip boilerplate; keep only :root tokens
│   ├── index.css                MODIFY — add @import "tailwindcss"
│   ├── lib/
│   │   ├── env.ts               CREATE — validates and exports VITE_* env vars
│   │   ├── supabase.ts          CREATE — browser Supabase client singleton
│   │   ├── http.ts              CREATE — fetch wrapper with bearer token injection
│   │   └── api.ts               CREATE — empty placeholder for product-level calls
│   ├── pages/
│   │   ├── LoginPage.tsx        CREATE — email/password sign-in form
│   │   └── SignupPage.tsx       CREATE — email/password sign-up form
│   └── components/
│       └── ProtectedRoute.tsx   CREATE — redirects unauthenticated users to /login
```

---

## Task 1: Backend auth dependency

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/tests/auth/__init__.py`
- Create: `backend/tests/auth/test_dependencies.py`
- Modify: `backend/pyproject.toml` (add `pytest-asyncio` dev dep)

**Interfaces:**
- Produces: `AuthUser(id: str, email: str)` dataclass; `get_current_user` FastAPI dependency with signature `async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> AuthUser`
- Consumed by: every future protected route via `user: AuthUser = Depends(get_current_user)`

- [ ] **Step 1: Add pytest-asyncio dev dependency**

```bash
cd backend && uv add --dev pytest-asyncio
```

Then add to `backend/pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write failing auth tests**

Create `backend/tests/auth/__init__.py` — empty file.

Create `backend/tests/auth/test_dependencies.py`:

```python
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.dependencies import AuthUser, get_current_user


def _make_creds(token: str):
    creds = MagicMock()
    creds.credentials = token
    return creds


async def test_valid_token_returns_auth_user():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user-abc", "email": "analyst@driftwood.com"}

    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_cls.return_value = mock_client

        user = await get_current_user(_make_creds("valid-token"))

    assert user.id == "user-abc"
    assert user.email == "analyst@driftwood.com"
    assert isinstance(user, AuthUser)


async def test_supabase_returns_non_200_raises_401():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_creds("bad-token"))

    assert exc_info.value.status_code == 401


async def test_network_error_raises_401():
    with patch("app.auth.dependencies.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("network down")
        mock_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(_make_creds("any-token"))

    assert exc_info.value.status_code == 401
```

- [ ] **Step 3: Run tests — expect failure**

```bash
cd backend && uv run pytest tests/auth/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 4: Create `app/auth/__init__.py`**

```bash
mkdir -p backend/app/auth && touch backend/app/auth/__init__.py
```

- [ ] **Step 5: Implement `app/auth/dependencies.py`**

Create `backend/app/auth/dependencies.py`:

```python
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer()


@dataclass
class AuthUser:
    id: str
    email: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    token = credentials.credentials
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.supabase_anon_key,
                },
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not verify credentials",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    data = response.json()
    return AuthUser(id=data["id"], email=data["email"])
```

- [ ] **Step 6: Run all backend tests — expect all pass**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: 16 passed (13 existing + 3 new auth tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/dependencies.py \
        backend/tests/auth/__init__.py backend/tests/auth/test_dependencies.py \
        backend/pyproject.toml backend/uv.lock
git commit -m "feat(backend): add Supabase JWT verification dependency"
```

---

## Task 2: Frontend lib layer (env, supabase client, http client)

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/index.css`
- Create: `frontend/src/lib/env.ts`
- Create: `frontend/src/lib/supabase.ts`
- Create: `frontend/src/lib/http.ts`
- Create: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces:
  - `env.supabaseUrl`, `env.supabaseAnonKey`, `env.apiBaseUrl` (from `src/lib/env.ts`)
  - `supabase` Supabase client singleton (from `src/lib/supabase.ts`)
  - `apiFetch<T>(path, options?) → Promise<T>`, `HttpError` class (from `src/lib/http.ts`)
- Consumed by: Task 3 (auth pages use `supabase`), future chat feature (uses `apiFetch`)

**Before starting:** create `frontend/.env.local` (never commit):

```
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 1: Configure Tailwind in Vite**

Replace `frontend/vite.config.ts`:

```typescript
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Replace the first line of `frontend/src/index.css` — add before all other rules:

```css
@import "tailwindcss";
```

(Keep the existing `:root` tokens below it — Tailwind and custom properties coexist fine.)

- [ ] **Step 2: Implement `src/lib/env.ts`**

Create `frontend/src/lib/env.ts`:

```typescript
function requireEnv(key: string): string {
  const value = import.meta.env[key]
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`)
  }
  return value as string
}

export const env = {
  supabaseUrl: requireEnv('VITE_SUPABASE_URL'),
  supabaseAnonKey: requireEnv('VITE_SUPABASE_ANON_KEY'),
  apiBaseUrl: requireEnv('VITE_API_BASE_URL'),
}
```

- [ ] **Step 3: Implement `src/lib/supabase.ts`**

Create `frontend/src/lib/supabase.ts`:

```typescript
import { createClient } from '@supabase/supabase-js'
import { env } from './env'

export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey)
```

- [ ] **Step 4: Implement `src/lib/http.ts`**

Create `frontend/src/lib/http.ts`:

```typescript
import { env } from './env'
import { supabase } from './supabase'

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'HttpError'
  }
}

async function getAccessToken(): Promise<string> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) throw new HttpError(401, 'Not authenticated')
  return session.access_token
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getAccessToken()
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  })
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText)
    throw new HttpError(response.status, message)
  }
  return response.json() as Promise<T>
}
```

- [ ] **Step 5: Create placeholder `src/lib/api.ts`**

Create `frontend/src/lib/api.ts`:

```typescript
// Product-level API calls (threads, messages) — populated in Step 3 (chat plumbing).
export {}
```

- [ ] **Step 6: Verify TypeScript compilation**

```bash
cd frontend && pnpm exec tsc --noEmit
```

Expected: no errors. Fix any type errors before proceeding.

- [ ] **Step 7: Smoke-test in dev server**

```bash
cd frontend && pnpm dev
```

Open `http://localhost:5173` in a browser. The Vite boilerplate should still appear (we haven't replaced `App.tsx` yet) and the console should show no errors about missing env vars (because `.env.local` provides them).

- [ ] **Step 8: Commit**

```bash
git add frontend/vite.config.ts frontend/src/index.css \
        frontend/src/lib/env.ts frontend/src/lib/supabase.ts \
        frontend/src/lib/http.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add env validation, Supabase client, and API http client"
```

---

## Task 3: Frontend routing + auth pages

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css` (strip boilerplate, keep tokens)
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/SignupPage.tsx`

**Interfaces:**
- Consumes: `supabase` from `src/lib/supabase.ts`; `Link`, `Navigate`, `Route`, `Routes`, `BrowserRouter`, `useNavigate` from `react-router-dom`
- Produces: a working app with `/login`, `/signup`, and `/` (protected) routes

- [ ] **Step 1: Create `src/components/ProtectedRoute.tsx`**

Create `frontend/src/components/ProtectedRoute.tsx`:

```typescript
import { type ReactNode, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setAuthenticated(!!session)
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setAuthenticated(!!session)
    })

    return () => subscription.unsubscribe()
  }, [])

  if (loading) return null
  if (!authenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 2: Create `src/pages/LoginPage.tsx`**

Create `frontend/src/pages/LoginPage.tsx`:

```typescript
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    setLoading(false)
    if (error) {
      setError(error.message)
    } else {
      navigate('/')
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm space-y-6 p-8">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 block w-full rounded border px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 block w-full rounded border px-3 py-2 text-sm"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="text-sm text-center">
          No account?{' '}
          <Link to="/signup" className="text-violet-600 underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  )
}
```

- [ ] **Step 3: Create `src/pages/SignupPage.tsx`**

Create `frontend/src/pages/SignupPage.tsx`:

```typescript
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'

export function SignupPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    const { error } = await supabase.auth.signUp({ email, password })
    setLoading(false)
    if (error) {
      setError(error.message)
    } else {
      setSuccess(true)
    }
  }

  if (success) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="w-full max-w-sm space-y-4 p-8">
          <h1 className="text-2xl font-semibold">Check your email</h1>
          <p className="text-sm">
            We sent a confirmation link to <strong>{email}</strong>. Click it
            to activate your account, then{' '}
            <Link to="/login" className="text-violet-600 underline">
              sign in
            </Link>
            .
          </p>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm space-y-6 p-8">
        <h1 className="text-2xl font-semibold">Create account</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="text-sm font-medium">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 block w-full rounded border px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="mt-1 block w-full rounded border px-3 py-2 text-sm"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <p className="text-sm text-center">
          Already have an account?{' '}
          <Link to="/login" className="text-violet-600 underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  )
}
```

- [ ] **Step 4: Replace `src/App.tsx`**

Replace the entire content of `frontend/src/App.tsx`:

```typescript
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'

function HomePage() {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-semibold">Document Copilot</h1>
        <p className="text-sm text-gray-500">Chat interface coming soon.</p>
      </div>
    </main>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 5: Strip boilerplate from `src/App.css`**

Replace `frontend/src/App.css` with just the counter style that's safe to keep (or just empty it — the boilerplate styles are for the removed template):

```css
/* App-level styles — add here as the UI grows. */
```

- [ ] **Step 6: Verify TypeScript compilation**

```bash
cd frontend && pnpm exec tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Manual browser testing**

```bash
cd frontend && pnpm dev
```

Test this checklist in the browser at `http://localhost:5173`:

- [ ] `/login` renders sign-in form with email + password fields
- [ ] `/signup` renders sign-up form
- [ ] Navigating to `/` while logged out redirects to `/login`
- [ ] Signing up with a new email shows the "check your email" confirmation screen
- [ ] After confirming email and signing in, `/` shows "Document Copilot — Chat interface coming soon."
- [ ] Browser back/forward works correctly between `/login` and `/signup`
- [ ] Unknown URL (e.g. `/foo`) redirects to `/` (which then redirects to `/login` if not authed)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css \
        frontend/src/components/ProtectedRoute.tsx \
        frontend/src/pages/LoginPage.tsx \
        frontend/src/pages/SignupPage.tsx
git commit -m "feat(frontend): add auth routing, login/signup pages, and protected route"
```

---

## Self-Review

**Spec coverage:**

| Architecture requirement | Task |
|---|---|
| `app/auth/dependencies.py` — JWT verification → `get_current_user` | Task 1 |
| Verify token by calling Supabase Auth (not local key) | Task 1 |
| Reject unauthenticated requests before any work | Task 1 (401 on non-200) |
| `src/lib/env.ts` validates VITE_* vars, fail fast | Task 2 |
| `src/lib/supabase.ts` browser client singleton | Task 2 |
| `src/lib/http.ts` wraps fetch, injects bearer token, base URL | Task 2 |
| Supabase Auth email sign-in/sign-up | Task 3 |
| Protected route redirects unauthenticated users | Task 3 |
| No service-role key in frontend | Task 2 (env.ts uses only anon key) |
| No direct OpenAI calls from browser | N/A (enforced by architecture) |

**Placeholder scan:** No TBDs or "fill in later" in code blocks.

**Type consistency:**
- `AuthUser.id` and `AuthUser.email` are strings — matches `data["id"]` and `data["email"]` from Supabase Auth response
- `apiFetch<T>` signature is used in `http.ts` and referenced in `api.ts` (empty placeholder)
- `supabase` singleton used in `ProtectedRoute`, `LoginPage`, `SignupPage` — all import from `'../lib/supabase'`
