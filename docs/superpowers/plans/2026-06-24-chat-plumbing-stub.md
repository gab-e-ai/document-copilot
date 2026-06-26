# Chat Plumbing (Stub) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the end-to-end streaming chat pipeline: FastAPI `POST /chat/stream` (canned stub response) + AI SDK `useChat` React UI, replacing the `/` redirect placeholder with a real chat interface at `/chat`.

**Architecture:** The frontend uses `@ai-sdk/react`'s `useChat` hook pointed at `${apiBaseUrl}/chat/stream`. Auth is injected by passing a custom `fetch` override that calls `supabase.auth.getSession()` before each request and adds the `Authorization: Bearer` header. FastAPI verifies the JWT via `get_current_user`, then streams a canned response word-by-word in the AI SDK Data Stream Protocol v1 (`text/plain; charset=utf-8` body, `X-Vercel-AI-Data-Stream: v1` response header). No database persistence in this step — Step 4 replaces the stub with real retrieval and LLM generation.

**Tech Stack:** Backend — FastAPI `StreamingResponse`, `asyncio`. Frontend — `ai` (Vercel AI SDK v4 core), `@ai-sdk/react` (v1 React hooks), React Router v7.

## Global Constraints

- Backend: Python ≥ 3.12; all commands via `uv run` from `backend/`
- Backend: async by default in request-path code — no blocking I/O on the event loop
- Backend: `app.config.settings` is the single source of truth — no `os.getenv` in app code
- Backend: unit tests only (no live network); mock `get_current_user` via `app.dependency_overrides`
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
│   ├── api/
│   │   ├── __init__.py          CREATE — empty package marker
│   │   └── chat.py              CREATE — ChatStreamRequest + POST /chat/stream stub
│   └── main.py                  MODIFY — include chat APIRouter
└── tests/
    └── api/
        ├── __init__.py          CREATE — empty
        └── test_chat.py         CREATE — auth guard + streaming format tests

frontend/
├── src/
│   ├── App.tsx                  MODIFY — add /chat protected route; redirect / → /chat
│   ├── lib/
│   │   └── api.ts               MODIFY — add getAccessToken() export
│   ├── pages/
│   │   └── chat/
│   │       └── ChatPage.tsx     CREATE — useChat hook, auto-scroll, layout composition
│   └── components/
│       └── chat/
│           ├── MessageList.tsx  CREATE — renders message history from useChat
│           └── MessageInput.tsx CREATE — textarea with Enter-to-send + Send button
```

---

## Task 1: Backend chat streaming endpoint (stubbed)

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/api/__init__.py`
- Create: `backend/tests/api/test_chat.py`

**Interfaces:**
- Consumes: `AuthUser`, `get_current_user` from `app.auth.dependencies`
- Produces:
  - `POST /chat/stream` — requires `Authorization: Bearer <token>` header (403 if absent); accepts `{"thread_id": str, "messages": [...]}` body; returns `StreamingResponse` with `Content-Type: text/plain; charset=utf-8` and `X-Vercel-AI-Data-Stream: v1` header; streams AI SDK Data Stream Protocol v1 parts
  - Consumed by: Task 2 frontend via `useChat({ api: "${env.apiBaseUrl}/chat/stream" })`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/api/__init__.py` — empty file.

Create `backend/tests/api/test_chat.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthUser, get_current_user
from app.main import app


def _auth_override() -> AuthUser:
    return AuthUser(id="test-user-id", email="analyst@driftwood.com")


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = _auth_override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    yield TestClient(app)


def test_stream_requires_auth(unauth_client):
    response = unauth_client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": []},
    )
    assert response.status_code == 403


def test_stream_returns_200_with_ai_sdk_headers(client):
    response = client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.headers.get("x-vercel-ai-data-stream") == "v1"


def test_stream_body_contains_data_stream_parts(client):
    response = client.post(
        "/chat/stream",
        json={"thread_id": "test-thread", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer fake-token"},
    )
    lines = response.text.splitlines()
    # At least one text part
    assert any(line.startswith('0:"') for line in lines), "missing text part (0:)"
    # Finish event
    assert any(line.startswith("e:") for line in lines), "missing finish event (e:)"
    # Data finish
    assert any(line.startswith("d:") for line in lines), "missing data finish (d:)"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && uv run pytest tests/api/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.api'`

- [ ] **Step 3: Create `app/api/__init__.py`**

```bash
mkdir -p backend/app/api && touch backend/app/api/__init__.py
```

- [ ] **Step 4: Implement `app/api/chat.py`**

Create `backend/app/api/chat.py`:

```python
import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import AuthUser, get_current_user

router = APIRouter()

_STUB_TEXT = (
    "This is a stubbed response. "
    "Full retrieval and LLM integration coming in Step 4."
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    thread_id: str
    messages: list[ChatMessage]


async def _stream_stub() -> AsyncGenerator[str, None]:
    for word in _STUB_TEXT.split():
        yield f'0:{json.dumps(word + " ")}\n'
        await asyncio.sleep(0.02)
    finish = json.dumps(
        {
            "finishReason": "stop",
            "usage": {"promptTokens": 0, "completionTokens": 0},
            "isContinued": False,
        }
    )
    yield f"e:{finish}\n"
    data_finish = json.dumps(
        {"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}}
    )
    yield f"d:{data_finish}\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_stub(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Vercel-AI-Data-Stream": "v1"},
    )
```

- [ ] **Step 5: Wire router into `app/main.py`**

Add two lines to `backend/app/main.py`. The file currently ends after the `/health` route. Add the import at the top and include the router after the middleware:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.config import settings

app = FastAPI(title="Document Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run all backend tests — expect 19 passing**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: 19 passed (16 existing + 3 new chat tests), output pristine.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/__init__.py backend/app/api/chat.py \
        backend/tests/api/__init__.py backend/tests/api/test_chat.py \
        backend/app/main.py
git commit -m "feat(backend): add stubbed POST /chat/stream endpoint"
```

---

## Task 2: Frontend chat UI

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/pages/chat/ChatPage.tsx`
- Create: `frontend/src/components/chat/MessageList.tsx`
- Create: `frontend/src/components/chat/MessageInput.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes:
  - `supabase` from `src/lib/supabase.ts` — to get the session access token
  - `env.apiBaseUrl` from `src/lib/env.ts`
  - `ProtectedRoute` from `src/components/ProtectedRoute.tsx`
  - `useChat` from `@ai-sdk/react` — manages message state, streaming, and form input
- Produces:
  - `getAccessToken(): Promise<string>` from `src/lib/api.ts` — used by ChatPage auth fetch
  - `/chat` protected route — full-screen chat with streaming assistant responses
  - `/` redirects to `/chat` (was placeholder homepage)

**Before starting:** install the AI SDK packages:

```bash
cd frontend && pnpm add ai @ai-sdk/react
```

**Version note:** The `useChat` hook API surface (especially `status` values and the `Message` type export path) should be verified against the installed version's TypeScript types. Run `pnpm exec tsc --noEmit` after each file to catch mismatches early.

- [ ] **Step 1: Install AI SDK packages**

```bash
cd frontend && pnpm add ai @ai-sdk/react
```

Verify TypeScript is happy with the new packages:

```bash
cd frontend && pnpm exec tsc --noEmit
```

Expected: no errors.

- [ ] **Step 2: Update `src/lib/api.ts` — add `getAccessToken`**

Replace `frontend/src/lib/api.ts`:

```typescript
import { supabase } from './supabase'

export async function getAccessToken(): Promise<string> {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return session.access_token
}
```

- [ ] **Step 3: Create `src/components/chat/MessageList.tsx`**

Create the directory and file `frontend/src/components/chat/MessageList.tsx`:

```typescript
import type { Message } from '@ai-sdk/react'

interface Props {
  messages: Message[]
}

export function MessageList({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Ask a question about the SEC filing corpus.
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-4 p-4">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-2xl rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
              message.role === 'user'
                ? 'bg-violet-600 text-white'
                : 'bg-gray-100 text-gray-900'
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}
    </div>
  )
}
```

**If `Message` is not exported from `@ai-sdk/react`**, check `import type { UIMessage } from '@ai-sdk/react'` or `import type { Message } from 'ai'` — use whichever the installed version exports, then update the `Props` interface and the type annotation in ChatPage.tsx to match.

- [ ] **Step 4: Create `src/components/chat/MessageInput.tsx`**

Create `frontend/src/components/chat/MessageInput.tsx`:

```typescript
import type { ChangeEvent, FormEvent } from 'react'

interface Props {
  input: string
  onInputChange: (e: ChangeEvent<HTMLTextAreaElement>) => void
  onSubmit: (e: FormEvent<HTMLFormElement>) => void
  isStreaming: boolean
}

export function MessageInput({ input, onInputChange, onSubmit, isStreaming }: Props) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      e.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <form onSubmit={onSubmit} className="border-t p-4">
      <div className="flex gap-2 items-end">
        <textarea
          value={input}
          onChange={onInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask about SEC filings… (Enter to send, Shift+Enter for newline)"
          disabled={isStreaming}
          rows={2}
          className="flex-1 resize-none rounded border px-3 py-2 text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-violet-500"
        />
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          className="rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {isStreaming ? 'Streaming…' : 'Send'}
        </button>
      </div>
    </form>
  )
}
```

- [ ] **Step 5: Create `src/pages/chat/ChatPage.tsx`**

Create the directory and file `frontend/src/pages/chat/ChatPage.tsx`:

```typescript
import { useChat } from '@ai-sdk/react'
import { useEffect, useRef } from 'react'
import { MessageInput } from '../../components/chat/MessageInput'
import { MessageList } from '../../components/chat/MessageList'
import { getAccessToken } from '../../lib/api'
import { env } from '../../lib/env'

const THREAD_ID = crypto.randomUUID()

async function authFetch(url: RequestInfo | URL, options?: RequestInit): Promise<Response> {
  const token = await getAccessToken()
  return fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      Authorization: `Bearer ${token}`,
    },
  })
}

export function ChatPage() {
  const bottomRef = useRef<HTMLDivElement>(null)

  const { messages, input, handleInputChange, handleSubmit, status, error } = useChat({
    api: `${env.apiBaseUrl}/chat/stream`,
    id: THREAD_ID,
    fetch: authFetch,
  })

  // streaming | submitted → input disabled; ready | error → input enabled
  const isStreaming = status === 'streaming' || status === 'submitted'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex flex-col h-screen">
      <header className="border-b px-4 py-3">
        <h1 className="text-sm font-semibold">Document Copilot</h1>
      </header>
      <MessageList messages={messages} />
      {error && (
        <p role="alert" className="text-sm text-red-600 px-4 pb-2">
          {error.message}
        </p>
      )}
      <div ref={bottomRef} />
      <MessageInput
        input={input}
        onInputChange={handleInputChange}
        onSubmit={handleSubmit}
        isStreaming={isStreaming}
      />
    </div>
  )
}
```

**`status` values:** `useChat` in `@ai-sdk/react` v1 uses `'submitted'`, `'streaming'`, `'ready'`, `'error'`. If tsc reports type errors on the `status` comparison, check `typeof status` and adjust to the actual union the installed version exports.

- [ ] **Step 6: Replace `src/App.tsx`**

Replace the entire content of `frontend/src/App.tsx`:

```typescript
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ChatPage } from './pages/chat/ChatPage'
import { LoginPage } from './pages/LoginPage'
import { SignupPage } from './pages/SignupPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 7: Verify TypeScript compilation**

```bash
cd frontend && pnpm exec tsc --noEmit
```

Expected: no errors. Fix any type mismatches (especially around `Message` type import path or `status` union) before proceeding.

- [ ] **Step 8: Manual browser test**

Start both services:

```bash
# Terminal 1 — backend:
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend:
cd frontend && pnpm dev
```

Test checklist at `http://localhost:5173`:

- [ ] Unauthenticated visit to `/` redirects to `/login`
- [ ] After signing in, lands on `/chat` with empty state: "Ask a question about the SEC filing corpus."
- [ ] Typing a message and pressing Enter submits it
- [ ] User message appears right-aligned in violet
- [ ] Assistant response streams in word-by-word left-aligned in gray
- [ ] Input textarea is disabled and button shows "Streaming…" during streaming
- [ ] After streaming completes, input re-enables
- [ ] `Shift+Enter` inserts a newline instead of submitting
- [ ] Unknown URLs (e.g. `/foo`) redirect to `/chat`

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/api.ts \
        frontend/src/pages/chat/ChatPage.tsx \
        frontend/src/components/chat/MessageList.tsx \
        frontend/src/components/chat/MessageInput.tsx \
        frontend/src/App.tsx \
        frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(frontend): add chat UI with useChat streaming pointed at /chat/stream"
```

---

## Self-Review

### Spec Coverage

| Architecture requirement | Task |
|---|---|
| `POST /chat/stream` protected by JWT | Task 1 (`get_current_user` dependency, 403 if absent) |
| AI SDK Data Stream Protocol v1: `0:` text, `e:` finish, `d:` data | Task 1 (`_stream_stub` generator) |
| `X-Vercel-AI-Data-Stream: v1` response header | Task 1 |
| Async streaming, no blocking I/O | Task 1 (`asyncio.sleep`, `AsyncGenerator`) |
| Stub only — no LLM/retrieval | Task 1 (`_STUB_TEXT` constant) |
| `useChat` with auth bearer injection | Task 2 (`authFetch` + `getAccessToken`) |
| `/chat` protected route, `/` redirects there | Task 2 |
| Empty state when no messages | Task 2 (`MessageList` empty branch) |
| Streaming indicator (disabled input + button label) | Task 2 (`isStreaming` prop to `MessageInput`) |
| Enter to send, Shift+Enter for newline | Task 2 (`handleKeyDown` in `MessageInput`) |
| Auto-scroll to latest message | Task 2 (`bottomRef.scrollIntoView`) |
| Error display with `role="alert"` | Task 2 (`ChatPage` error rendering) |
| `env.apiBaseUrl` used (not raw `import.meta.env`) | Task 2 |
| No service-role key in frontend | Task 2 (only anon key / session token) |

### Placeholder Scan

No TBDs, no vague steps. Every step has exact code or an exact command.

### Type Consistency

- `getAccessToken()` defined in `src/lib/api.ts` → imported in `ChatPage.tsx` ✓
- `Message` (or `UIMessage`) from `@ai-sdk/react` used as `Props.messages` type in `MessageList.tsx` and inferred from `useChat` in `ChatPage.tsx` ✓
- `handleInputChange` from `useChat` passed to `MessageInput.onInputChange: (e: ChangeEvent<HTMLTextAreaElement>) => void` — compatible because React's change handler for textarea matches ✓
- `handleSubmit` from `useChat` passed to `MessageInput.onSubmit: (e: FormEvent<HTMLFormElement>) => void` ✓
- `ChatStreamRequest.thread_id` (snake_case Python) ↔ `{ thread_id: THREAD_ID }` sent by `useChat` — `useChat` sends the `id` as part of the body in AI SDK format; the backend receives `thread_id` in the JSON body. **Note:** verify that `useChat` body shape matches `ChatStreamRequest` during browser testing. If `useChat` sends `{ id: threadId, messages: [...] }` rather than `{ thread_id: ... }`, update `ChatStreamRequest` to match.
- `AsyncGenerator[str, None]` return type on `_stream_stub` is consistent with `StreamingResponse` accepting an async iterator ✓
