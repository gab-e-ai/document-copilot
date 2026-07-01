# Architecture — Document Copilot

How the system is put together: components, data flow, the data model, and the
key contracts between the frontend, backend, database, and external services.

For build history and setup steps see [README_setup.md](README_setup.md); for the
product brief see [README.md](README.md).

---

## 1. Overview

Document Copilot answers plain-English questions about a corpus of SEC filings
and returns **grounded, cited** answers. It is a classic RAG (retrieval-augmented
generation) system with three moving parts:

1. **Ingestion** (offline CLI) — turns SEC HTML filings into embedded, searchable chunks.
2. **Retrieval + agent** (online) — finds relevant chunks and has an LLM write a cited answer.
3. **Chat UI** (online) — a React SPA that streams the answer and renders citations.

```
                          ┌────────────────────────────────────────────┐
                          │                External APIs                 │
                          │   OpenAI (embeddings + chat)   Supabase Auth │
                          └───────▲───────────────▲──────────────▲───────┘
                                  │               │              │
   ┌───────────────┐  HTTPS  ┌────┴───────────────┴──────┐  SQL  ┌┴──────────────────┐
   │  React SPA    │────────▶│      FastAPI backend       │──────▶│ Supabase Postgres │
   │ (Vite, AI SDK)│  SSE    │  auth · retrieval · agent  │       │  pgvector + FTS   │
   └───────────────┘◀────────│  grounding · streaming     │       └───────────────────┘
                             └────────────▲───────────────┘
                                          │ (offline, one-off)
                             ┌────────────┴───────────────┐
                             │   Ingestion CLI            │
                             │ HTML→MD→chunk→embed→write  │
                             └────────────────────────────┘
```

---

## 2. Tech stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Vite + React 19 + TypeScript | SPA; `@ai-sdk/react` v3 (`ai` v6) for streaming chat |
| Backend | Python 3.12 + FastAPI | async; `uv` for deps |
| LLM / embeddings | OpenAI | `gpt-4o-mini` (chat), `text-embedding-3-small` 1536-dim |
| Agent | PydanticAI | typed tool-calling agent with structured output |
| Database | Supabase Postgres | `pgvector` (semantic) + `tsvector` full-text |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic | `psycopg` v3 driver |
| Auth | Supabase Auth (email) | JWT verified server-side |
| Hosting | Railway (target) | not yet deployed |

---

## 3. Components

### Backend (`backend/app/`)

```
app/
├── main.py               # FastAPI app, CORS, /health
├── config.py             # pydantic-settings; single source of env truth
├── api/chat.py           # POST /chat/stream (auth + DB session deps)
├── auth/dependencies.py  # get_current_user → verifies JWT via Supabase /auth/v1/user
├── schemas/chat.py       # ChatStreamRequest / ChatMessage (wire models)
├── chat/
│   ├── orchestrator.py   # run_chat_turn — ties the whole turn together
│   ├── messages.py       # extract_user_query (handles AI SDK `parts`)
│   └── streaming.py      # SSE helpers + AI SDK v6 stream events
├── retrieval/
│   ├── queries.py        # raw SQL: semantic_search + fulltext_search
│   ├── fusion.py         # reciprocal_rank_fusion (RRF)
│   └── retriever.py      # DocumentRetriever: embed → search → fuse → SourcePassage
├── assistant/
│   ├── agent.py          # PydanticAI Agent + search_filings tool
│   ├── deps.py           # DocumentAgentDeps (per-turn dependencies)
│   ├── outputs.py        # SourcePassage / Citation / GroundedAnswer
│   └── instructions.md   # system prompt / product contract
├── grounding/validator.py # rejects citations to un-retrieved chunks
├── ingestion/            # offline CLI (see §6)
└── database/
    ├── session.py        # async engine + get_session dependency
    ├── chats.py          # get_or_create_thread, save_message, save_citations
    └── models.py         # SQLAlchemy models (see §5)
```

### Frontend (`frontend/src/`)

```
src/
├── App.tsx                       # routes: /login /signup /chat (protected)
├── lib/
│   ├── env.ts                    # validates VITE_* env at load
│   ├── supabase.ts               # browser Supabase client
│   └── api.ts                    # getAccessToken() from the Supabase session
├── components/
│   ├── ProtectedRoute.tsx        # redirects unauthenticated users to /login
│   └── chat/
│       ├── MessageList.tsx       # renders messages + citation cards
│       ├── MessageInput.tsx      # textarea, Enter-to-send
│       └── CitationCard.tsx      # one citation (company, filing, date, excerpt)
└── pages/
    ├── LoginPage.tsx / SignupPage.tsx
    └── chat/ChatPage.tsx         # useChat + DefaultChatTransport (auth + backend URL)
```

---

## 4. Request lifecycle — a chat turn

This is the core online flow (`POST /chat/stream`).

```
User types question in ChatPage
        │
        ▼
useChat(DefaultChatTransport)  ── POST /chat/stream ──▶  FastAPI
  body: { id, messages:[{role, parts:[{type:text,text}]}], trigger }
  header: Authorization: Bearer <supabase JWT>   (added by custom fetch)
        │
        ▼
1. get_current_user      verify JWT against Supabase /auth/v1/user → AuthUser(id, email)
2. extract_user_query    pull text from the last user message's `parts`
3. get_or_create_thread  ensure a chat_threads row (id from body, or a fresh UUID)
4. save_message(user)    persist the question
5. run_agent             PydanticAI agent runs; calls the search_filings tool:
        │                     DocumentRetriever.retrieve(query):
        │                        a. OpenAI embeds the query (1536-dim)
        │                        b. semantic_search (pgvector cosine)  ┐
        │                        c. fulltext_search (tsvector ts_rank) ┘ top 20 each
        │                        d. reciprocal_rank_fusion → top 10 passages
        │                     agent writes GroundedAnswer{answer, citations[]}
6. GroundingValidator    raise if any citation.chunk_id was not retrieved
7. save_message(assistant) + save_citations   persist answer + citations, commit
        │
        ▼
8. stream_answer_and_citations  →  Server-Sent Events (see §7)
        │
        ▼
ChatPage renders streamed text; MessageList renders citation cards
```

Errors short-circuit to an SSE error stream (`type:"error"` → `finish` →
`[DONE]`) so the client always terminates cleanly.

---

## 5. Data model (Supabase Postgres)

```
auth.users (Supabase)
      │ 1:1 (on_auth_user_created trigger)
      ▼
  profiles ──1:N──▶ chat_threads ──1:N──▶ chat_messages ──1:N──▶ message_citations
                                                                        │ N:1
  source_documents ──1:N──▶ document_chunks ◀───────────────────────────┘
```

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `profiles` | one row per user | `id` (=auth user id), `email` |
| `chat_threads` | conversations | `id`, `user_id`, `title` |
| `chat_messages` | turns | `id`, `thread_id`, `role`, `content`, `message_json` |
| `message_citations` | answer→chunk links | `message_id`, `chunk_id`, `excerpt` |
| `source_documents` | one filing | `ticker`, `company`, `filing_type`, `filing_date`, `accession_number` (unique), `content_markdown` |
| `document_chunks` | retrieval unit | `document_id`, `chunk_text`, `embedding vector(1536)`, `search_vector tsvector` (generated), `token_count` |

Indexes: **HNSW** on `document_chunks.embedding` (cosine), **GIN** on
`search_vector` and `metadata_json`. `search_vector` is a Postgres
`GENERATED ALWAYS ... STORED` column (`to_tsvector('english', chunk_text)`) —
the app never writes it.

---

## 6. Ingestion pipeline (offline)

`uv run python -m app.ingestion` reads `data/downloads/manifest.json` and, per filing:

```
HTML file ─▶ html_to_markdown ─▶ chunker ─▶ embedder ─▶ writer
             (html2text)         (512 tok,   (OpenAI     (idempotent insert:
                                  64 overlap)  batch=100)  skips existing accession_number)
```

- **Chunker** splits on paragraphs; a single paragraph larger than the limit is
  **hard-split at the token level** so no chunk exceeds the embedding input cap.
- **Writer** is idempotent (keyed on `accession_number`), so re-runs only add new filings.
- Per-filing error isolation: one bad filing doesn't abort the batch.

Corpus source: `data/download.py` fetches recent 10-Ks for AAPL, MSFT, NVDA,
AMZN, GOOGL from SEC EDGAR (downloads gitignored).

---

## 7. Streaming protocol (AI SDK v6 contract)

The backend speaks the **AI SDK UI Message Stream v1** over SSE
(`Content-Type: text/event-stream`, header `x-vercel-ai-ui-message-stream: v1`).
Each line is `data: {json}\n\n`. Event sequence for a successful turn:

```
text-start                → { type, id }
text-delta  (repeated)    → { type, id, delta }        # answer, word by word
text-end                  → { type, id }
data-citations            → { type, data:{ citations:[…] } }   # custom data part
finish-step               → { type }
finish                    → { type, finishReason:"stop" }
[DONE]
```

Three v6-specific rules this system depends on (all were fixed during
end-to-end testing — see [README_setup.md](README_setup.md) Step 6):

1. **Transport, not options.** The client must use
   `useChat({ transport: new DefaultChatTransport({ api, fetch }) })`.
   Passing `{ api, fetch }` at the top level is silently ignored in v6.
2. **Messages carry `parts`.** Requests send
   `messages:[{ role, parts:[{type:"text", text}] }]`, not `content` — the
   backend reads text from `parts`.
3. **Citations are a `data-*` part.** Custom data must use `type:"data-citations"`;
   the invalid `message-annotation` type breaks the stream. The client reads it
   from `message.parts`.

---

## 8. Auth & security

- **Auth flow:** the SPA signs in with Supabase (email/password) and holds a JWT.
  Every `/chat/stream` request carries `Authorization: Bearer <JWT>`; the backend
  verifies it against Supabase `GET /auth/v1/user` and derives `AuthUser(id, email)`.
  No token → 403; invalid/expired → 401.
- **Row Level Security:** enabled on all tables. User-owned tables restrict rows
  to their owner; corpus tables (`source_documents`, `document_chunks`) are locked
  to client roles. The backend connects as the `postgres` role (bypasses RLS), so
  server-side retrieval is unaffected while the public anon key cannot read/write
  those tables directly.
- **SQL safety:** all retrieval SQL is parameterized.

---

## 9. Configuration & connectivity

Backend env (`backend/.env`): `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `OPENAI_API_KEY`,
`OPENAI_CHAT_MODEL` (default `gpt-4o-mini`), `ALLOWED_ORIGINS`.
Frontend env (`frontend/.env.local`): `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`.

- **`DATABASE_URL` must use the Session pooler** (`aws-0-<region>.pooler.supabase.com:5432`,
  user `postgres.<ref>`). The direct host `db.<ref>.supabase.co` is IPv6-only.
  `config.py` rewrites `postgresql://` → `postgresql+psycopg://`; `session.py`
  rewrites again to `psycopg_async` for the async engine (which needs `greenlet`).
- **Restricted networks** may firewall Postgres ports (5432/6543) — DB calls then
  time out while HTTPS still works. Use a different network or the deployment.

---

## 10. Known gaps / next steps

- **No conversation history UI** — each page load starts a fresh thread (threads
  are persisted, but not listed or resumable in the UI yet).
- **Not deployed** — target is Railway; needs prod env vars and `ALLOWED_ORIGINS`
  set to the deployed frontend URL.
- **Single filing type** — corpus is 10-Ks; the schema already supports others.
```
