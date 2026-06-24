# Setup Progress

Tracks what has been built so far and the manual steps required at each stage.

---

## Step 1 — Backend skeleton + DB schema ✅

### What was built

| Commit | Description |
|--------|-------------|
| `6cd763d` | FastAPI skeleton: `app/config.py`, `app/main.py`, `/health` endpoint, 13 unit tests |
| `0ca315e` | SQLAlchemy models (6 tables) + Alembic env wired to `Base.metadata` |
| `b9053ee` | Initial Alembic migration: pgvector, all tables, HNSW/GIN indexes, RLS, signup trigger |
| `479e133` | Fix: `include_object` to exclude `document_chunks` from autogenerate; `set_updated_at()` trigger |
| `648650d` | Fix: `ALLOWED_ORIGINS` comma-string parsing; psycopg3 URL scheme; plain PL/pgSQL trigger |

### Backend layout

```
backend/
├── app/
│   ├── config.py           # pydantic-settings — single source of truth for env
│   ├── main.py             # FastAPI app, CORS, /health
│   └── database/
│       └── models.py       # 6 SQLAlchemy models (Profile, ChatThread, ChatMessage,
│                           #   MessageCitation, SourceDocument, DocumentChunk)
├── alembic/
│   ├── env.py              # wired to Base.metadata; reads DATABASE_URL from settings
│   └── versions/
│       └── 0001_initial_schema.py   # full schema migration
└── tests/                  # 13 unit tests (no live DB)
```

### DB tables created in Supabase

- `profiles` — one row per user (auto-created by `on_auth_user_created` trigger)
- `chat_threads` — conversation threads, owned by user
- `chat_messages` — user and assistant messages
- `message_citations` — citations linking assistant messages to document chunks
- `source_documents` — SEC filings (ticker, company, markdown content)
- `document_chunks` — retrieval-ready passages with `vector(1536)` embeddings and `tsvector` full-text search

Indexes: HNSW on `embedding` (cosine, m=16, ef=64), GIN on `search_vector`, GIN on `metadata_json`.

RLS: enabled on all user-owned tables; corpus tables (`source_documents`, `document_chunks`) are read-only for `authenticated` role.

### Config notes

`backend/.env` (copy from `.env.example`, never commit):

| Key | Notes |
|-----|-------|
| `SUPABASE_URL` | Dashboard → Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Dashboard → Settings → API → anon public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Dashboard → Settings → API → service_role secret |
| `DATABASE_URL` | Dashboard → Settings → Database → **Session** connection string (host `db.<ref>.supabase.co:5432`). Do NOT use the pooler URL. |
| `OPENAI_API_KEY` | platform.openai.com |
| `ALLOWED_ORIGINS` | Comma-separated, e.g. `http://localhost:5173` |

`DATABASE_URL` must use `postgresql://` — the config automatically rewrites it to `postgresql+psycopg://` for psycopg v3.

### Running the backend

```bash
cd backend
cp .env.example .env   # fill in values
uv run uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`

### Running tests

```bash
cd backend
uv run pytest tests/ -v
```

### Applying / re-applying migrations

```bash
cd backend
uv run alembic upgrade head      # apply
uv run alembic downgrade base    # revert everything (destructive)
```

---

## Step 2 — Auth wiring ✅

**Complete.** Plan: `docs/superpowers/plans/2026-06-23-auth-wiring.md`

| Commit | Description |
|--------|-------------|
| `99ceb47` | Backend: `app/auth/dependencies.py` — `AuthUser` dataclass + `get_current_user` dependency (httpx call to Supabase `/auth/v1/user`) |
| `6add257` | Backend fix: remove unused import, add `timeout=5.0` to httpx client |
| `70e1de7` | Frontend: `src/lib/env.ts`, `supabase.ts`, `http.ts`, `api.ts` + Tailwind CSS |
| `e270270` | Frontend: `App.tsx` (React Router), `ProtectedRoute.tsx`, `LoginPage.tsx`, `SignupPage.tsx` |
| `fe7e28a` | Frontend fix: strip `index.css` boilerplate, use `navigate('/', { replace: true })` on login |

### Backend layout additions

```
backend/app/auth/
├── __init__.py
└── dependencies.py     # HTTPBearer → get_current_user → AuthUser(id, email)
```

### Frontend layout additions

```
frontend/src/
├── lib/
│   ├── env.ts          # validates VITE_* env vars, fail-fast at module load
│   ├── supabase.ts     # browser Supabase client singleton
│   ├── http.ts         # apiFetch<T> with bearer token injection, HttpError class
│   └── api.ts          # placeholder (populated in Step 3)
├── pages/
│   ├── LoginPage.tsx   # email/password sign-in, redirects to /chat on success
│   └── SignupPage.tsx  # email/password sign-up, shows confirmation screen
└── components/
    └── ProtectedRoute.tsx  # redirects unauthenticated users to /login
```

### Frontend env required

Create `frontend/.env.local` (never commit):
```
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key
VITE_API_BASE_URL=http://localhost:8000
```

---

## Step 3 — Chat plumbing (stubbed) 🔄

**In progress.** Plan: `docs/superpowers/plans/2026-06-24-chat-plumbing-stub.md`

| Commit | Description |
|--------|-------------|
| `1e87df3` | Backend: `app/api/chat.py` — `POST /chat/stream` stub (AI SDK Data Stream Protocol v1) |
| `8798130` | Backend fix: test for `credentials=None` → 403, rename unused `_user` param |
| `d83cca1` | Frontend: `ChatPage.tsx`, `MessageList.tsx`, `MessageInput.tsx`, updated `App.tsx` and `api.ts` |

**Note:** Frontend commit `d83cca1` uses AI SDK v6 (`ai@6.0.209`, `@ai-sdk/react@3.0.211`) — breaking changes from v1 were handled: `HttpChatTransport` for auth, `UIMessage` type, `sendMessage({ text })` API. 3 minor fixes still pending in the next session before Step 3 is marked complete.

### Backend layout additions

```
backend/app/api/
├── __init__.py
└── chat.py             # POST /chat/stream — streams canned text in AI SDK Data Stream Protocol v1
```

### Frontend layout additions

```
frontend/src/
├── lib/
│   └── api.ts          # getAccessToken() helper for streaming auth
├── pages/
│   └── chat/
│       └── ChatPage.tsx    # useChat (AI SDK v6) + auto-scroll + auth transport
└── components/
    └── chat/
        ├── MessageList.tsx  # renders UIMessage[] parts
        └── MessageInput.tsx # textarea with Enter-to-send + Send button
```

### Running Step 3

```bash
# Backend (Terminal 1):
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend (Terminal 2):
cd frontend && pnpm dev
```

Visit `http://localhost:5173` → redirects to `/login` → after sign-in, `/chat` shows streaming stub response.

## Step 4 — Retrieval + LLM 📋

Planned. Ingestion pipeline → hybrid search (pgvector + FTS + RRF) → PydanticAI document agent.

## Step 5 — UI polish 📋

Planned. Citation cards, source passage drawers, empty states, error handling.
