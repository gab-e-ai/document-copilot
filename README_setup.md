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
| `DATABASE_URL` | Dashboard → Settings → Database → connection string. **Use the Session pooler** (`aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<ref>`). The direct host `db.<ref>.supabase.co` is IPv6-only and unreachable on IPv4-only networks. The Session pooler (port 5432) is IPv4 and works for both the app and Alembic migrations. Do NOT use the Transaction pooler (port 6543) for migrations. See Step 6. |
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

## Step 4 — Ingestion pipeline ✅

**Complete.** Plan: `docs/superpowers/plans/2026-06-24-ingestion-pipeline.md`

CLI that reads `data/downloads/manifest.json`, converts SEC HTML filings to Markdown, chunks into 512-token paragraphs with 64-token overlap, embeds via OpenAI `text-embedding-3-small`, and writes `source_documents` + `document_chunks` to Supabase.

```bash
cd backend
uv run python -m app.ingestion          # uses data/downloads/ by default
uv run python -m app.ingestion --manifest path/to/manifest.json
```

### Backend layout additions

```
backend/app/ingestion/
├── html_to_markdown.py   # html2text wrapper
├── chunker.py            # paragraph-aware token-bounded chunker (512 tok / 64 overlap)
├── embedder.py           # OpenAI batched embedder (batch=100)
├── writer.py             # SQLAlchemy idempotent writer (checks accession_number)
├── pipeline.py           # orchestrator with per-filing error isolation
└── __main__.py           # CLI entry point
```

---

## Step 5 — Semantic search, retrieval agent & citation UI ✅

**Complete.** Plan: `docs/superpowers/plans/2026-06-25-semantic-search-retrieval-agent.md`

Replaces the `/chat/stream` stub with a real hybrid retrieval pipeline:
- **pgvector semantic search** + **Postgres full-text search** fused with **Reciprocal Rank Fusion**
- **PydanticAI document agent** (`gpt-4o-mini`) with `search_filings` tool and typed `GroundedAnswer` output
- **Citation grounding validator** — raises `GroundingError` if model cites unretrieved passages
- **SSE streaming** — answer text + `message-annotation` citation events
- **Citation cards** in the frontend (company, filing type, date, excerpt)

### Backend layout additions

```
backend/app/
├── schemas/chat.py           # ChatMessage, ChatStreamRequest (shared, no circular import)
├── retrieval/
│   ├── queries.py            # pgvector + tsvector SQL (async)
│   ├── fusion.py             # Reciprocal Rank Fusion
│   └── retriever.py          # DocumentRetriever: embed → search → fuse → SourcePassage list
├── assistant/
│   ├── outputs.py            # SourcePassage, Citation, GroundedAnswer (Pydantic)
│   ├── deps.py               # DocumentAgentDeps dataclass
│   ├── agent.py              # PydanticAI Agent with search_filings tool
│   └── instructions.md       # System prompt / product contract
├── grounding/
│   └── validator.py          # GroundingValidator + GroundingError
├── chat/
│   ├── messages.py           # WireMessage, extract_user_query
│   ├── streaming.py          # SSE helpers, stream_answer_and_citations
│   └── orchestrator.py       # run_chat_turn: retrieve → agent → validate → stream → persist
└── database/
    ├── session.py            # async engine (psycopg_async) + get_session FastAPI dep
    └── chats.py              # get_or_create_thread, save_message, save_citations
```

### Frontend layout additions

```
frontend/src/components/chat/
└── CitationCard.tsx          # renders one citation (index, company, filing, date, excerpt)
```

`MessageList.tsx` updated to extract `message.annotations` and render citation cards under assistant messages. `ChatPage.tsx` updated with context-aware error messages.

### Config additions

`backend/.env` — add:
```
OPENAI_CHAT_MODEL=gpt-4o-mini    # optional, defaults to gpt-4o-mini
```

### Running

```bash
# Backend:
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend:
cd frontend && npm run dev
```

Visit `http://localhost:5173` → sign in → ask a question about the ingested SEC filings.

---

## Step 6 — End-to-end verification & fixes ✅

The full stack was tested end-to-end in the browser (login → streamed answer → citation card). Several bugs that passed the build and unit tests but broke the running app were found and fixed.

### Bugs fixed

| Area | Problem | Fix |
|------|---------|-----|
| Backend deps | `greenlet` was missing; SQLAlchemy async crashes on the first DB query. Unit tests mock the DB, so they never caught it. | Declared `sqlalchemy[asyncio]` in `pyproject.toml` (pulls in `greenlet`). |
| Ingestion | A single paragraph larger than the model limit (e.g. a big table) was sent whole to OpenAI → embedding API rejected it → MSFT/GOOGL/AMZN filings failed. | `chunker.py` now hard-splits oversized paragraphs at the token level. |
| DB connection | `DATABASE_URL` pointed at the IPv6-only direct host → unreachable on IPv4 networks. | Switched to the Session pooler (see Step 1 table). |
| Frontend | AI SDK v6: `useChat({ api, fetch })` is ignored → requests went to `/api/chat` with no auth. | Use `DefaultChatTransport({ api, fetch })` in `ChatPage.tsx`. |
| Backend | AI SDK v6 sends message text in `parts`, not `content` → "No user message found". | `extract_user_query` reads both; orchestrator preserves `parts`. |
| Citations | Backend emitted a `message-annotation` event, which is not a valid AI SDK v6 stream part → error banner + citations dropped. | Emit a `data-citations` data part; frontend reads it from `message.parts`. |

### Corpus & security

- **Corpus populated:** ran `uv run python -m app.ingestion` → 25 filings, ~4,900 chunks (AAPL, MSFT, NVDA, AMZN, GOOGL × 5 years).
- **RLS enabled** on `document_chunks`, `source_documents`, `alembic_version` (they were exposed to the anon key). The backend uses the `postgres` role, which bypasses RLS, so retrieval is unaffected.

### Local dev note

If Vite's default port `5173` is taken it uses `5174` — add both to `ALLOWED_ORIGINS` in `backend/.env`, e.g. `http://localhost:5173,http://localhost:5174`.

### Restricted networks

Some corporate/ISP networks firewall outbound Postgres ports (5432/6543) — every DB call times out while HTTPS works. If that happens, use a different network (e.g. a mobile hotspot) or run against the deployment.
