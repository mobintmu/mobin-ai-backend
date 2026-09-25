# Mobin'AI backend implementation prompt

Use this document as the build prompt for a **new, independent Python repository named `mobin-ai-backend`**. The existing `docs/mobin-ai-implementation-proposal.md` gives project context, and `docs/mobin-ai-frontend-implementation-prompt.md` defines the browser integration this API must support. Follow this document where earlier plans conflict: the browser receives an opaque conversation bearer token, each issued token allows **100 successful or evidence-limited questions**, and the RAG source files are **manually copied** from `mobinshaterian.com` into the backend repository. The frontend is a different repository and calls this API over HTTPS.

## Mission and boundaries

Build a production-ready, stateless FastAPI service that registers visitors, creates conversations, accepts questions, retrieves evidence from Mobin Shaterian's copied knowledge graph and articles, calls a configurable AI gateway, stores the full authenticated RAG request and its final response or failure in PostgreSQL, and exposes documented `/api/v1` endpoints through OpenAPI/Swagger. Ship Docker Compose files suitable for a single-server deployment at `https://api.mobinshaterian.com`.

**Backend scope only.** Do not create the React chat UI, embeddable JavaScript widget, or a duplicate website. Do not put provider credentials, database credentials, Graphify caches, or private contact lists in frontend artifacts. The API must be usable by `mobin-ai-frontend` at `https://chat.mobinshaterian.com`; the existing website embeds that frontend and does not call the backend directly. No dependency on the website repository at runtime is allowed.

Deliver implementation, migrations, tests, container/deployment configuration, an example environment file with placeholders, generated OpenAPI contract, and exact operator instructions. Avoid a demo that stores conversations only in memory. If a provider or source artifact is unavailable during development, use deterministic test fixtures while keeping production code wired to configured real resources.

## Existing source material and manual knowledge import

The source website currently contains:

- `src/data/kg/md/graphify-out/graph.json`: Graphify nodes, links, and hyperedges.
- `src/data/kg/build_kg_docs.py` and `src/data/kg/md/*.md`: source-derived Markdown inputs.
- `src/data/posts/*.json`, `src/data/posts.json`, and other `src/data/*.json` files: article and profile content used by the site.
- `src/data/kg/graph_rag.py`: an experimental graph traversal and model-call prototype.

These are source references, not production backend modules. Create a documented, **manual copy** process from `mobinshaterian.com` into a versioned `knowledge/releases/<version>/` directory in `mobin-ai-backend`. A human runs the copy/import command when articles change; do not build an automatic watcher, cross-repository live mount, network fetch from the website, or scheduled sync. Copy the accepted `graph.json`, only the article content and metadata needed for retrieval/citations, and a manifest with source commit, copy date, graph hash, article hashes, and canonical URLs. Never copy `.env`, keys, Git metadata, Graphify caches, or temporary outputs. Check file size and licensing/privacy before adding artifacts to Git; permit a versioned deployment artifact if the files should not be committed.

Provide commands such as `make knowledge-stage SOURCE_SITE=/path/to/mobinshaterian.com`, `make knowledge-validate`, `make knowledge-ingest`, and `make knowledge-activate VERSION=...`, but implement them only inside this backend repository. `knowledge-stage` must preview or stage an explicit copy, not silently replace the active release. Validation checks JSON schema, unique stable IDs, source URL allowlist, required article fields, cross-references, suspicious graph count regressions, and content hashes. Ingestion uses stable chunk IDs and content hashes, embeds changed chunks only, and records the knowledge version. Activation is atomic after validation and smoke tests; retain the previous version for rollback. The running API loads the active graph into an immutable in-memory index at startup and reads persistent article chunks from PostgreSQL. A bad graph must fail readiness rather than silently use unrelated fallback nodes.

## Required runtime and architecture

Use Python 3.12 or newer, FastAPI, Pydantic v2/settings, async SQLAlchemy 2, Alembic, PostgreSQL with `pgvector`, an async PostgreSQL driver, and `httpx` or an OpenAI-compatible async client for the AI gateway. Pin dependencies and a lockfile. Add Ruff and a Python type checker, pytest, and HTTP integration tests. Use a layered package structure; adjust names as needed while preserving boundaries:

```text
mobin-ai-backend/
├── app/
│   ├── api/v1/              # FastAPI routers, request/response schemas
│   ├── core/                # settings, errors, logging, security, lifespan
│   ├── clients/             # registration, consent, IP capture
│   ├── conversations/       # scoped tokens, history, quota, feedback
│   ├── rag/                 # graph, passages, ranking, prompts, citations
│   ├── providers/           # gateway and embeddings adapters
│   ├── persistence/         # SQLAlchemy models and repositories
│   └── main.py
├── alembic/
├── knowledge/releases/     # manually staged, versioned source artifacts
├── scripts/                # knowledge stage/validate/ingest/activate, admin jobs
├── tests/
├── deploy/                 # Dockerfile, compose, proxy configuration
├── contracts/openapi.json  # pinned public API contract
├── .env.example
├── pyproject.toml
├── Makefile
└── README.md
```

Keep HTTP routers thin: validate input, call an application service, map typed failures to HTTP responses. Services own registration, quota, conversation, and RAG use cases. Repositories own SQL. Retrievers return structured evidence; provider adapters own gateway calls. Use dependency injection to substitute a fake provider and small graph in tests. Avoid global mutable conversation state. Stateless API replicas must share PostgreSQL as the authoritative source for clients, tokens, quota, messages, request outcomes, and active knowledge version. Loading an immutable graph index into each process is allowed. No request may depend on which API replica handles it.

Use one request/correlation ID across FastAPI logs, PostgreSQL audit rows, gateway calls where supported, and client responses. Return `X-Request-ID`. Do not log raw bearer tokens, email, phone, full prompts, or full answers in ordinary application logs; the required request/response content belongs in access-controlled PostgreSQL tables.

## Visitor registration and IP capture

The visitor supplies **given name**, **family name**, and **at least one of email or phone**. Both names are required, trimmed, and validated without excluding non-Latin names. Normalize email and phone for storage and lookup; phone should use E.164 when possible. Email/phone are contact information, not proof of ownership. Require explicit `privacy_accepted=true`, a `privacy_policy_version`, and a separate optional `marketing_consent=false` default. Declining marketing must not block use. Store consent timestamps and version. Never reveal whether an email or phone is already in the database in public responses.

Require a Cloudflare Turnstile response on public registration. Verify it server-side with the private secret, expected hostname `chat.mobinshaterian.com`, and action `client_register` before committing contact data. Bound Siteverify timeouts and retries; expired, reused, invalid, or unavailable verification fails safely. Protect verification with an IP rate limit. Do not store the Turnstile token. Permit official test keys only in local/test settings, never as production defaults.

Capture the visitor's **public client IP** for each registration and each authenticated RAG request. Configure an explicit trusted proxy list or network boundary; accept `Forwarded`/`X-Forwarded-For` only from known reverse-proxy addresses, otherwise use the socket peer address. Never trust an arbitrary client-supplied header. Validate the resulting IPv4/IPv6 value and store it in PostgreSQL `inet` columns with request timestamp and request ID. Keep IP history available for the documented retention period and use a derived short-lived key for rate limiting. Treat IP as personal data: restrict exports/access, avoid printing it in normal logs, and delete it with the associated request when retention/deletion runs. Record the source of IP resolution (`socket` or `trusted_proxy`) for operations and tests.

Registration should return a public `client_id` and a short-lived, one-time `registration_grant` for the immediately following conversation-creation call; it must not return a conversation bearer token. The grant is a credential, so do not log or persist its plaintext. The next call exchanges it for the scoped access token. The frontend may submit separate name fields; make them first-class API fields rather than forcing concatenation. If an older client sends `name`, document a temporary compatibility mapping only if needed. Define a deduplication policy that does not allow a visitor to mint unlimited 100-question tokens merely by re-registering with the same unverified email or phone. Because contact ownership is not verified, do not treat matching contact text as authorization to another visitor's conversations.

## Conversation credential and 100-question quota

`POST /api/v1/conversations` creates a new conversation for a successfully registered client and returns `conversation_id`, a cryptographically random **opaque bearer `access_token`**, `expires_at`, and a quota object with `limit`, `used`, and `remaining`. The limit is **100 successful or insufficient-evidence answers per issued token**. Document the exact validity period and server-side policy for additional conversations; choose a conservative default such as one active token per newly registered browser session and refuse silent quota reset. Do not rely on email or phone alone to restore a token or issue a replacement. If stronger recovery is needed later, add verified ownership in a separate phase.

Store only a keyed hash or strong one-way hash of the token, never the plaintext token. Show the plaintext once in the creation response. Bind it to exactly one conversation and authorize every read/write by that binding. Accept it in `Authorization: Bearer ...` over HTTPS, never in a URL or query parameter. Use constant-time verification where applicable. Token expiry, revocation, and new-session behavior must be explicit. Backend responses must expose authoritative quota values; the frontend must not estimate them from button clicks.

Use a database transaction and row lock or equivalent atomic reservation so concurrent requests cannot exceed 100. Generate an idempotency key per intentional question on the frontend and require or accept `Idempotency-Key` on both streamed and non-streamed POST routes. Uniquely constrain `(conversation_id, idempotency_key)` and associate it with one RAG request. Repeating a completed key returns the same stored outcome and does not charge twice. A different payload with the same key returns a typed conflict. If a provider fails or a stream is cancelled before a final answer, retain the audit record but do not charge the 100-question quota; release a reservation safely. A completed answer, including an honest insufficient-evidence answer, consumes one. Define recovery for a process crash with a pending reservation, and test it. For simplicity, allow only one in-flight generation per conversation unless a fully tested multi-request reservation strategy is implemented.

Rate limits for IP, token, registration, and a global monthly model budget are additional protections and distinct from the token's 100-question lifetime quota. Return `429` with a typed code and `Retry-After` where appropriate. Do not reintroduce the earlier proposal's 10-per-day limit as the primary product quota. Make operational limits configurable and visible in docs.

## Public API and Swagger/OpenAPI

Expose FastAPI's Swagger UI at `/docs`, ReDoc at `/redoc`, and machine-readable `/openapi.json`. Also commit or publish a versioned `contracts/openapi.json` artifact for `mobin-ai-frontend` to pin and generate a TypeScript client from. Document authentication, examples, status codes, SSE events, errors, quota semantics, and whether a route is safe to retry. Use `/api/v1`; breaking changes require a new version or a supported migration window. Health routes do not need a bearer token.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| `GET` | `/health/live` | Process liveness; fast and no model call. |
| `GET` | `/health/ready` | Database, active knowledge version, and gateway configuration readiness; no model call. |
| `POST` | `/api/v1/clients` | Validate Turnstile and register contact/consent; return `client_id`. |
| `POST` | `/api/v1/conversations` | Create scoped conversation and return opaque token, expiry, and quota. |
| `GET` | `/api/v1/conversations/{id}` | Return authorized metadata and current quota. |
| `GET` | `/api/v1/conversations/{id}/messages` | Paginated authorized question/answer history. |
| `POST` | `/api/v1/conversations/{id}/messages` | Store question, execute RAG, return final answer and citations. |
| `POST` | `/api/v1/conversations/{id}/messages:stream` | Same use case with typed SSE over a POST response. |
| `POST` | `/api/v1/messages/{id}/feedback` | Record helpful/not-helpful feedback for the authorized answer. |

Example registration request:

```json
{
  "given_name": "Ada",
  "family_name": "Lovelace",
  "email": "ada@example.com",
  "phone": null,
  "privacy_accepted": true,
  "privacy_policy_version": "2026-09-25",
  "marketing_consent": false,
  "turnstile_token": "turnstile-response"
}
```

Example registration response:

```json
{
  "client_id": "01900000-0000-7000-8000-000000000000",
  "registration_grant": "short-lived-one-time-grant",
  "grant_expires_at": "2026-09-25T12:05:00Z"
}
```

Example conversation creation response; the token appears only here:

```json
{
  "conversation_id": "01900000-0000-7000-8000-000000000001",
  "access_token": "opaque-random-token",
  "expires_at": "2026-10-25T12:00:00Z",
  "quota": { "limit": 100, "used": 0, "remaining": 100 }
}
```

Document how the recently returned `client_id` is passed to `/conversations`, and protect that creation step against arbitrary client ID reuse. A bare `client_id` is not an authentication credential: use a short-lived, one-time registration grant returned by `/clients`, or an equally safe proof from the completed registration flow. Include this grant in the OpenAPI schemas and ensure it cannot create multiple tokens without following the issuance policy. Do not permit `POST /conversations` with only a guessed UUID.

Example non-streaming question request and response (exact names should be frozen in OpenAPI):

```json
{ "question": "How should a high-TPS Kafka to ClickHouse pipeline be designed?" }
```

```json
{
  "message_id": "01900000-0000-7000-8000-000000000002",
  "conversation_id": "01900000-0000-7000-8000-000000000001",
  "answer": "### Recommended pipeline\n\n1. Use bounded batches. [c1]",
  "grounded": true,
  "citations": [
    {
      "citation_id": "c1",
      "title": "Example article title",
      "url": "https://mobinshaterian.com/blog/example",
      "snippet": "Relevant source passage",
      "source_type": "article"
    }
  ],
  "quota": { "limit": 100, "used": 1, "remaining": 99 },
  "request_id": "01900000-0000-7000-8000-000000000003"
}
```

Return structured errors with `code`, `message`, `request_id`, and optional safe `details`; use meaningful HTTP status codes for validation, Turnstile failure, unauthorized/expired token, forbidden conversation, conflict/idempotency mismatch, quota exhausted, rate limit, provider unavailable, and internal error. Do not return raw provider exceptions, private prompts, tokens, or stack traces. Add accurate OpenAPI examples and bearer security schemes so Swagger can execute authorized requests with a test token.

## PostgreSQL persistence and complete RAG audit

Use Alembic migrations from day one. PostgreSQL is the source of truth; no production SQLite fallback. Use UUID public IDs, UTC timestamps, foreign keys, indexes, and constraints. Enable `pgvector` for article passage embeddings. At minimum, model:

| Table | Required data |
| --- | --- |
| `clients` | ID, given/family name, encrypted or access-controlled email/phone, normalized keyed lookup hashes, consent choices/version/timestamps, registration IP (`inet`), created/updated timestamps. |
| `registration_grants` | One-time short-lived proof for conversation creation, hashed grant, client ID, expiry, consumed timestamp. |
| `conversations` | ID, client ID, status, token hash, issue/expiry/revocation dates, 100-question limit, used count, created/last-message dates. |
| `rag_requests` | **One row per authenticated chat POST attempt**, including rejected or failed attempts: ID, request ID, conversation/client ID, idempotency key, full submitted question, normalized request JSON if useful, client IP (`inet`), endpoint mode (`stream` or `sync`), status, acceptance/charge flags, model and knowledge version, start/end times, latency, error code, and gateway usage/cost metadata when available. |
| `rag_responses` | One row for each RAG attempt's terminal outcome: request ID, full final answer Markdown or safe failure message, complete response JSON/citations, grounded flag, completion timestamp, and terminal status. A failed attempt still has a response/outcome row even when no model answer exists. |
| `messages` | Ordered user and assistant transcript entries linked to the RAG request; statuses include pending/completed/failed/cancelled. Preserve exact accepted question and final displayed answer. |
| `citations` or structured `rag_responses.citations` | Stable citation IDs, source article IDs, title, canonical URL, snippet, and retrieval score where available. |
| `feedback` | Authorized answer ID and helpful/not-helpful rating; unique per answer/client policy. |
| `knowledge_releases` and `article_chunks` | Version hashes, activation state, article metadata, passages, embeddings, and full-text indexes. |

“Store all RAG requests and responses” means every **authenticated question POST** gets a durable `rag_requests` row before a gateway call and a terminal `rag_responses` outcome, including provider errors, timeouts, cancellations, insufficient-evidence answers, and quota/rate-limit rejections. For invalid/unauthenticated traffic where no conversation can be established, keep a bounded, redacted security event with request ID, IP, status, and reason; do not store attacker-supplied unbounded bodies as chat content. Record the final aggregated answer for a stream, not every token event. Never leave a row permanently `pending`: repair stale attempts after process death and mark a terminal outcome. Do not save provider chain-of-thought or secret configuration.

Persist the user question before RAG begins, then complete the answer/outcome in a transaction with quota reconciliation. If the provider returns after a client disconnect, define whether to finish and store the answer or cancel; in either case the database must state the true outcome. An API success must never be sent before its persisted outcome is durable. An idempotent retry must return the stored result, not create another request, answer, or charge. Provide pagination for transcript retrieval and indexes for client, conversation/time, request ID, idempotency key, status, and retention cutoffs.

Because names, contacts, IPs, and full chats are sensitive, restrict DB roles and operator access, encrypt backups, use application-level encryption for email/phone when practical, keep raw content out of general logs, and document the 12-month retention/deletion job. Provide a dry-run preview and explicit execution command that removes old clients, IPs, conversations, RAG requests/responses, messages, feedback, and related export files without deleting retained knowledge artifacts. Document the user access/deletion request process. Do not create a public contact-list endpoint.

## RAG pipeline

The backend owns all retrieval and generation. On startup, validate and load the active Graphify `graph.json` once per process. Index nodes, links, hyperedges, and source mappings. Normalize English/Persian queries, find relevant seed entities without brittle fixed fallback IDs, expand a bounded deterministic subgraph, and retrieve relevant article passages using PostgreSQL full-text search plus `pgvector`. Fuse/rank evidence, enforce source diversity and a prompt token budget, then build a prompt with stable citation IDs and exact source URLs. Do not send the entire article corpus or graph to the model on each question.

Treat retrieved articles as untrusted input, never as system instructions. Instruct the model to answer in English from supplied evidence, acknowledge when the source material is insufficient, and cite supported claims with returned IDs such as `[c1]`. Validate that every emitted citation ID exists in the selected evidence. Return `grounded=false` and a clear insufficient-evidence answer when support is weak. Do not claim to have browsed the web or to know unpublished facts. Limit graph hops/nodes, retrieved chunks, context size, question length, output tokens, and recent conversation history. Keep context ordering deterministic for reproducible tests.

Maintain conversation context through a bounded recent-message window and optional compact server-side summary; do not resend unlimited history. Store the original visitor question exactly. Keep active knowledge version in each `rag_requests` record so a later audit can explain which graph/articles supported the answer. Expose canonical source links only from validated imported article metadata. Existing `graph_rag.py` can inform graph traversal, but refactor it into tested backend components rather than importing the CLI directly.

## AI gateway adapter

Call a configurable OpenAI-compatible AI gateway, initially the existing AvalAI endpoint if credentials are provided. Use environment settings for `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, timeout, maximum tokens, concurrency, and optional fallback model; never hard-code a provider model or API key. Support both normal and streaming chat-completion responses through a provider interface. If embeddings use a different endpoint/model, configure them separately and call them only during manual knowledge ingestion. Use an async HTTP client with connection pooling, bounded retries for safe transient failures, and cancellation/timeout handling. Do not retry an ambiguous generation in a way that creates a second charge or duplicate answer without an idempotency policy.

The public API must hide provider-specific payloads. Capture provider model alias, request/response timings, token usage when returned, and a safe error class in PostgreSQL. Never persist the AI gateway API key, private system prompts in public responses, or raw HTTP authorization headers. Keep a deterministic fake gateway for tests and local development. If the gateway is unavailable, return a typed retryable error and persist that failure as the RAG attempt's terminal outcome.

## Streaming and browser integration

Implement `POST /api/v1/conversations/{id}/messages:stream` as `text/event-stream` over a `fetch` response. Standard `EventSource` is GET-only and cannot carry this bearer header, so document the POST stream accurately. Emit typed `retrieving`, `citation`, `delta`, `complete`, and `error` events with JSON data and stable IDs. `complete` includes the persisted `message_id`, citations, grounded flag, and authoritative quota; it is emitted only after the final database write. `error` includes a safe code and request ID. Send heartbeats if an intermediary would otherwise time out. Configure reverse-proxy buffering/timeouts so chunks are delivered promptly. A client disconnect must be reconciled to a completed or cancelled database state, not left pending.

The non-streaming and streaming routes call the **same** application service and share validation, authorization, idempotency, RAG, persistence, citation checks, and quota behavior. Do not implement two divergent pipelines. CORS must permit the exact production origin `https://chat.mobinshaterian.com` and explicit local development origins; do not use wildcard origins with credentials. The site domain is an embed host, while the iframe's API origin is the chat subdomain. Protect bearer-token routes against cross-origin leakage and avoid token values in URL-based SSE.

## Docker Compose and server deployment

Provide a multi-stage Dockerfile with a non-root runtime user, pinned Python dependencies, small image, health checks, and no secrets baked into layers. Provide `deploy/compose.yaml` (or a root `compose.yaml`) that runs:

1. `api`: FastAPI/Uvicorn workers behind a reverse proxy, with bounded worker/concurrency settings and restart policy.
2. `db`: PostgreSQL with the `pgvector` extension, a persistent named volume, health check, and **no publicly exposed database port** in production.
3. `proxy`: Caddy, Nginx, or Traefik with HTTPS/TLS for `api.mobinshaterian.com`, request-size limits, streaming-friendly configuration, and security headers.
4. A one-shot migration job or a documented migration step that runs before API rollout; never run competing migrations from every API worker.

The compose file should use an internal network, named volumes, environment/secret injection, versioned image tags, graceful shutdown, and a tested restart path. Include `.env.example` with variable names and dummy placeholders only, and keep real `.env` ignored. Document DNS, firewall, TLS certificate issuance, deployment commands, database backup/restore, log access, schema migration, health verification, knowledge release activation, and rollback. Deploy one API instance initially if graph artifacts are local; make the service stateless so additional replicas can run with the same active knowledge release and shared database later. Do not publish PostgreSQL on `0.0.0.0`.

Provide exact local developer commands using Docker Compose for PostgreSQL and the fake gateway, and exact production commands for pulling/building the API image, applying migrations, starting services, importing a manually staged knowledge release, checking `/health/ready`, and running a Swagger smoke request. Do not require the website repository to be present on the server after the knowledge release has been copied and validated.

## Configuration, operations, and security

Use typed settings and fail startup for missing production configuration. At minimum document `DATABASE_URL`, API/public origins, trusted proxy addresses, token hashing/encryption secrets, token TTL, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, embedding settings, Turnstile secret/hostname/action, rate limits, monthly gateway budget, active knowledge location, and retention period. `OPENAI_BASE_URL`/`OPENAI_API_KEY` aliases may be supported for migration, but choose one canonical setting scheme. Production secrets must come from the deployment environment or a secret manager.

Add metrics and structured logs for request counts, latencies, gateway failures, first-token latency, retrieval time, quota denials, provider cost/usage, and active knowledge version, with no raw contact values or chat bodies in routine logs. Add liveness and readiness probes. Set sensible timeouts for database, Turnstile, retrieval, and gateway calls. Define a global budget guard so model traffic can be stopped safely if spending exceeds the configured ceiling. Use backup and restore drills, retention job monitoring, and alerts on sustained errors or stuck RAG requests.

Authorize every conversation history, question, and feedback operation by the scoped token; a conversation UUID alone grants nothing. Check URL destinations for citations, bound all inputs, use parameterized SQL through the ORM, and keep admin/export operations separate from public Swagger. CORS is a browser control, not authentication. Document limits of unverified email/phone ownership and any policy chosen for repeat registrations and quota renewal.

## Tests and acceptance criteria

Tests must cover meaningful behavior rather than only mirroring functions:

1. Registration with given/family name, email-only, phone-only, both, missing contact, privacy decline, optional marketing, duplicate-contact non-enumeration, and Turnstile success/failure/expiry/wrong hostname/action.
2. Correct IP capture through a trusted proxy and rejection of spoofed forwarding headers from an untrusted peer; IPv4 and IPv6 persistence.
3. One-time registration grant, scoped opaque token issuance, expiry/revocation, and denial of access to another conversation by UUID or token.
4. Exactly 100 chargeable answers, a 101st quota denial, concurrent submissions near the limit, failed-provider refund, cancelled stream, and crash recovery of stale pending work.
5. Idempotent retry of the same question and conflict for reused key with a different question; no duplicate gateway call, audit row, answer, or quota charge.
6. Every authenticated RAG attempt creates a durable request and terminal response record, including success, insufficient evidence, provider error, rate/quota rejection, and cancellation. Verify full question, answer, citation, IP, request ID, timing, and knowledge version fields.
7. Deterministic graph traversal, hybrid passage retrieval, source mapping, invalid citation removal, no-evidence response, and resistance to instructions inside imported articles.
8. Normal and SSE response shapes, event order, final persistence before `complete`, backend disconnect handling, and unbuffered proxy delivery.
9. OpenAPI generation and compatibility with the pinned frontend contract, Swagger bearer authentication, CORS allowlist, safe error responses, and no secrets in API output/logs.
10. Migrations from an empty database, manual knowledge import/validation/activation/rollback, database backup restore, Docker Compose startup, and a production-like smoke request against a fake gateway.

Run lint, type checking, tests, migration checks, OpenAPI contract diff, container build, and secret scanning in CI. Do not require a live AI gateway for ordinary CI. Use a small known graph/article fixture and fake gateway responses for deterministic tests, plus optional controlled live evaluations before model or knowledge releases.

The project is complete when a visitor can register through the documented API, receive a scoped token after a protected conversation-creation step, send English or Persian questions from the separate frontend, receive an English RAG answer with validated article citations, and see the 100-question quota updated accurately. Every authenticated chat attempt and its terminal outcome is stored in PostgreSQL with the visitor IP and request ID. Swagger accurately documents and can exercise the API. Docker Compose can deploy and restart the service on a server with persistent PostgreSQL, TLS, migrations, backup instructions, and a manually imported knowledge release.
