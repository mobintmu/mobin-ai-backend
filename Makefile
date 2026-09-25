VERSION ?=
SOURCE_SITE ?=
COMPOSE = docker compose --env-file .env -f deploy/compose.yaml

.PHONY: knowledge-stage knowledge-validate knowledge-ingest knowledge-activate local-up local-down migrate test lint contract
knowledge-stage:
	uv run python -m scripts.knowledge stage --source "$(SOURCE_SITE)"
knowledge-validate:
	uv run python -m scripts.knowledge validate --version "$(VERSION)"
knowledge-ingest:
	uv run python -m scripts.knowledge ingest --version "$(VERSION)"
knowledge-activate:
	uv run python -m scripts.knowledge activate --version "$(VERSION)"
local-up:
	$(COMPOSE) -f deploy/compose.local.yaml up -d --build db migrate api
local-down:
	$(COMPOSE) -f deploy/compose.local.yaml down
migrate:
	uv run alembic upgrade head
test:
	uv run pytest
lint:
	uv run ruff check .
	uv run mypy app
contract:
	mkdir -p contracts
	uv run python -c 'import json; from app.main import app; open("contracts/openapi.json", "w").write(json.dumps(app.openapi(), indent=2))'
