.PHONY: help install install-dev fmt lint typecheck test check db-up db-down schema eval

help:
	@echo "make targets:"
	@echo "  install      editable install with all extras"
	@echo "  install-dev  editable install with dev tooling only"
	@echo "  fmt          auto-format (ruff format)"
	@echo "  lint         lint (ruff check)"
	@echo "  typecheck    static types (mypy)"
	@echo "  test         smoke/unit tests (pytest)"
	@echo "  check        lint + typecheck + test"
	@echo "  db-up        start local Neo4j (reads NEO4J_PASSWORD from .env)"
	@echo "  db-down      stop local Neo4j"
	@echo "  schema       apply graph/schema.cypher to the running Neo4j"
	@echo "  eval         truthfulness eval / provider bake-off (Stage 4+)"

install:
	pip install -e ".[all]"

install-dev:
	pip install -e ".[dev]"

fmt:
	ruff format .

lint:
	ruff check .

typecheck:
	mypy ingestion orchestration graph api evals

test:
	pytest -q

check: lint typecheck test

db-up:
	docker compose up -d neo4j

db-down:
	docker compose down

schema:
	docker compose exec -T neo4j cypher-shell -u "$${NEO4J_USER:-neo4j}" -p "$${NEO4J_PASSWORD}" -f /graph/schema.cypher

eval:
	@echo "Not implemented yet — see docs/research/stage-4-engine-and-cost.md §7-§8 (truthfulness eval / provider bake-off)."
