.PHONY: help install install-dev fmt lint typecheck test check \
        format-check db-up db-down schema ingest ingest-dry preflight api-dev eval

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
	@echo "  schema       apply graph/schema.cypher to the running Neo4j"
	@echo "  ingest       run Stage-3 ingestion for ADVENTURE_REGION"
	@echo "  ingest-dry   dry-run ingestion (fetch + conflate, no DB writes)"
	@echo "  api-dev      start FastAPI dev server on :8000"
	@echo "  eval         truthfulness eval / provider bake-off"

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

ingest:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	python -m ingestion.pipeline --region $${ADVENTURE_REGION:-shenandoah-gwj} && \
	python -m ingestion.ingest_trailheads --region $${ADVENTURE_REGION:-shenandoah-gwj}

ingest-dry:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	python -m ingestion.pipeline --region $${ADVENTURE_REGION:-shenandoah-gwj} --dry-run && \
	python -m ingestion.ingest_trailheads --region $${ADVENTURE_REGION:-shenandoah-gwj} --dry-run

api-dev:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	uvicorn api.app:app --reload --port 8000

eval:
	@set -a && [ -f .env ] && . ./.env; set +a; \
	python -m evals.run_bakeoff
