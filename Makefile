.PHONY: help install install-dev fmt lint typecheck test check \
        format-check db-up db-down schema schema-aura ingest ingest-dry preflight api-dev eval \
        ground state docs-lint

# Python interpreter. Defaults to python3; override with `make PYTHON=python` if needed.
PYTHON ?= python3

help:
	@echo "make targets:"
	@echo "  install      editable install with all extras"
	@echo "  install-dev  editable install with dev tooling only"
	@echo "  fmt          auto-format (ruff format)"
	@echo "  format-check verify formatting (ruff format --check)"
	@echo "  lint         lint (ruff check)"
	@echo "  typecheck    static types (mypy)"
	@echo "  test         DB-free unit tests (pytest -m \"not neo4j\")"
	@echo "  check        format-check + lint + typecheck + test"
	@echo "  preflight    check environment before running the sprint"
	@echo "  db-up        start local Neo4j (reads NEO4J_PASSWORD from .env)"
	@echo "  db-down      stop local Neo4j"
	@echo "  schema       apply graph/schema.cypher to the local docker Neo4j"
	@echo "  schema-aura  apply graph/schema.cypher to a remote/Aura Neo4j (NEO4J_URI)"
	@echo "  ingest       run Stage-3 ingestion for ADVENTURE_REGION"
	@echo "  ingest-dry   dry-run ingestion (fetch + conflate, no DB writes)"
	@echo "  api-dev      start FastAPI dev server on :8000"
	@echo "  eval         truthfulness eval / provider bake-off"
	@echo "  ground       print the current-state grounding report (git/corpus/PRs)"
	@echo "  state        refresh the generated state.json + STATUS.md snapshot"
	@echo "  docs-lint    run the doc-lint gate (links, stale markers, generated-doc sync)"

install:
	pip install -e ".[all]"

install-dev:
	pip install -e ".[dev]"

fmt:
	ruff format .

format-check:
	ruff format --check .

lint:
	ruff check .

typecheck:
	mypy ingestion orchestration graph api evals

test:
	pytest -q -m "not neo4j"

check: format-check lint typecheck test

preflight:
	python scripts/preflight.py

db-up:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	docker compose up -d neo4j

db-down:
	docker compose down

schema:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	docker compose exec -T neo4j cypher-shell \
		-u "$${NEO4J_USER:-neo4j}" -p "$${NEO4J_PASSWORD}" \
		< graph/schema.cypher

schema-aura:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	$(PYTHON) scripts/apply_schema.py

ingest:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	$(PYTHON) -m ingestion.pipeline --region $${ADVENTURE_REGION:-shenandoah-gwj} && \
	$(PYTHON) -m ingestion.ingest_trailheads --region $${ADVENTURE_REGION:-shenandoah-gwj}

ingest-dry:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	$(PYTHON) -m ingestion.pipeline --region $${ADVENTURE_REGION:-shenandoah-gwj} --dry-run && \
	$(PYTHON) -m ingestion.ingest_trailheads --region $${ADVENTURE_REGION:-shenandoah-gwj} --dry-run

api-dev:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	uvicorn api.app:app --reload --port 8000

eval:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	$(PYTHON) -m evals.run_bakeoff

ground:
	@$(PYTHON) scripts/ground.py

state:
	$(PYTHON) scripts/gen_state.py --refresh

docs-lint:
	$(PYTHON) scripts/doc_lint.py
