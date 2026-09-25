# Mobin AI backend

FastAPI GraphRAG service for the separate frontend at `https://chat.mobinshaterian.com`. PostgreSQL stores registrations, scoped bearer tokens, quota, transcripts, feedback, article chunks, and every authenticated question outcome. Swagger is at `/docs`, ReDoc at `/redoc`, and the pinned contract at `contracts/openapi.json`.

## Local start

Requires Python 3.12+, uv, and Docker Compose. Copy `.env.example` to `.env`, generate `TOKEN_HASH_KEY` with a secure random generator and `CONTACT_ENCRYPTION_KEY` with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`, and set separate local `POSTGRES_PASSWORD` and `APP_DB_PASSWORD` values. Use `DATABASE_URL=postgresql+asyncpg://mobin:<password>@127.0.0.1:5432/mobin` for host commands. `.env` is ignored.

```bash
uv sync --frozen
make local-up
curl http://127.0.0.1:8000/health/live
```

Local mode uses a deterministic fake gateway and accepts `turnstile_token: "test-pass"`; production requires real gateway, embedding, and Turnstile credentials. Before questions can be answered, stage and activate a knowledge release:

```bash
make knowledge-stage SOURCE_SITE=/path/to/mobinshaterian.com
make knowledge-validate VERSION=<version printed by stage>
make knowledge-ingest VERSION=<version>
make knowledge-activate VERSION=<version>
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.local.yaml restart api
curl http://127.0.0.1:8000/health/ready
```

Staging is an explicit manual copy. It never activates or replaces a release. It copies the accepted graph and public article text and metadata, writes hashes and the source commit to the manifest, and excludes the website's `.env`, Git metadata, and Graphify caches. Review licensing, privacy, and size before publishing a release. For rollback, activate the prior ingested version and restart the API. Each worker loads its immutable graph at startup; chunks live in PostgreSQL.

## API flow

1. `POST /api/v1/clients` with separate names, email or E.164 phone, `privacy_accepted: true`, policy version, optional marketing consent, and a Turnstile token. It returns a fresh public `client_id` handle and a one-time registration grant valid for five minutes. The handle is scoped to this registration attempt; repeat registration does not reveal an internal client ID.
2. `POST /api/v1/conversations` with that `client_id` and grant. It returns one opaque bearer token, valid for 30 days. Store it only in chat-origin memory or session storage. The server stores a keyed hash. One conversation may be issued per normalized contact; unverified contact text cannot recover or reset a token.
3. Send `Authorization: Bearer <token>` and a stable `Idempotency-Key` on either `POST /api/v1/conversations/{id}/messages` or `POST /api/v1/conversations/{id}/messages:stream`. A completed or insufficient-evidence answer consumes one of 100; a failed generation does not. A completed key replays its stored result. The stream is POST SSE for `fetch`, with `retrieving`, `citation`, `delta`, `complete`, and `error` events; `complete` follows the database commit.
4. `GET /api/v1/conversations/{id}` gives authoritative quota. `GET /messages` pages completed history. `POST /api/v1/messages/{id}/feedback` records a rating for an authorized answer.

The token is bound to one conversation; a UUID alone grants nothing. `X-Request-ID` is shared by responses and audit rows. Errors use `{code, message, request_id}`. English and Persian questions are accepted; the model is instructed to answer in English using supplied article citations. CORS allows the exact chat origin and configured local origins; it does not authenticate a request.

For a local Swagger smoke request, open `http://127.0.0.1:8000/docs`, register with `test-pass`, create a conversation, click **Authorize** and paste the token, then POST a question with `Idempotency-Key: smoke-0001`.

## Production deployment

Point DNS `api.mobinshaterian.com` to the server, allow inbound 80/443, and keep 5432 closed. Caddy obtains TLS certificates and proxies unbuffered SSE to one API worker. The `db-init` job creates a restricted `mobin_app` role after migrations; the API never connects as the migration user. Fill `.env` with real secrets, `APP_ENV=production`, origins, trusted proxy CIDRs, model and embedding settings, and the Turnstile secret. Use a versioned `API_IMAGE` tag. Keep the reviewed `knowledge/releases/<version>` artifact on the server; Compose mounts it read-only. PostgreSQL is internal with a named volume.

```bash
docker compose --env-file .env -f deploy/compose.yaml build api
docker compose --env-file .env -f deploy/compose.yaml up -d db
docker compose --env-file .env -f deploy/compose.yaml run --rm migrate
docker compose --env-file .env -f deploy/compose.yaml up -d db-init api proxy
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.knowledge ingest --version <version>
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.knowledge activate --version <version>
docker compose --env-file .env -f deploy/compose.yaml restart api
curl -f https://api.mobinshaterian.com/health/ready
```

Run migrations once before API rollout, never from every worker. To roll back code, use the previous image tag; to roll back knowledge, activate the prior version and restart. View logs with `docker compose --env-file .env -f deploy/compose.yaml logs --tail=100 api`. Back up with `docker compose --env-file .env -f deploy/compose.yaml exec -T db pg_dump -U mobin -Fc mobin > backup.dump`; test a restore into an isolated database before relying on backups:

```bash
docker compose --env-file .env -f deploy/compose.yaml exec -T db createdb -U mobin mobin_restore
docker compose --env-file .env -f deploy/compose.yaml exec -T db pg_restore -U mobin --no-owner -d mobin_restore < backup.dump
```

Encrypt and access-control dumps and keep the knowledge artifact separately.

## Operations and privacy

Contact values are encrypted when `CONTACT_ENCRYPTION_KEY` is set; lookup hashes use `TOKEN_HASH_KEY`. PostgreSQL `inet` columns hold registration and RAG request IPs and their resolution source. Forwarded addresses are accepted only from configured trusted proxies. The proxy overwrites client-supplied forwarding headers and has a fixed address `172.30.80.10`; set `TRUSTED_PROXIES=172.30.80.10/32` in production. The internal `/metrics` endpoint is blocked by the public Caddy route. Restrict database roles, encrypt backups, and deny public access to the DB and operator commands.

```bash
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.maintenance recover --minutes 5
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.maintenance retention
docker compose --env-file .env -f deploy/compose.yaml run --rm api python -m scripts.maintenance retention --execute
```

Run stale-request recovery regularly after worker loss. `MONTHLY_REQUEST_BUDGET` is a global request-count guard, separate from the per-token quota. In production, `MONTHLY_MODEL_BUDGET_USD` also caps reserved plus completed estimated model spend across replicas. Set `MAX_REQUEST_COST_USD` above the worst expected call cost, and configure the input/output token prices for the selected model. Missing provider usage is billed at that reservation amount. Retention dry-run prints counts for clients older than `RETENTION_DAYS` (default 365), their related registration events, grants, conversations, requests, outcomes, messages, and feedback, plus expired security events and rate buckets. `--execute` deletes those records while retaining public knowledge releases. Review the dry-run and backup before execution. Handle visitor access/deletion through an authenticated operator process; matching unverified contact text is not proof of identity. There is no public contact export endpoint.

## Checks

```bash
make lint
make test
make contract
docker compose --env-file .env -f deploy/compose.yaml build api
```

E2E tests use PostgreSQL with pgvector and a deterministic fake provider. CI applies migrations to an empty database, runs lint, typing, E2E tests, checks the OpenAPI diff, and builds the image. No live model is needed. Deployment readiness reports the active knowledge version; a missing or invalid graph returns `503`.
