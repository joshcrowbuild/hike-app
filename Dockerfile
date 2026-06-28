# Adventure Planner API — serve-time image for Render (Docker web service).
#
# Installs only the lighter serve surface (pyproject `serve` extra: api + graph +
# live + providers + shapely), never the rest of the heavy ingestion geo stack.
# shapely's manylinux wheel bundles GEOS, so the only apt package needed is
# ca-certificates (for strict TLS to Neo4j Aura over neo4j+s://).
# Full deploy click-path: docs/runbooks/deploy-api-render.md
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OS trust store for strict TLS to Aura (neo4j+s://). certifi (a serve dep) also
# ships a bundle that graph/client.py points ssl at — this is belt-and-suspenders so
# verification has a CA bundle no matter which path the ssl module takes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Project manifest + readme first (pyproject declares `readme = "README.md"`).
COPY pyproject.toml README.md ./

# Serve-time source packages only — no frontend / regions / evals / tests / docs.
COPY api ./api
COPY orchestration ./orchestration
COPY graph ./graph
COPY ingestion ./ingestion

# Editable install (the repo's documented norm) of the API + its serve-time deps.
RUN python -m pip install --upgrade pip \
 && python -m pip install -e ".[serve]"

# Drop root: run the server as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

# Render injects $PORT at runtime; default to 8000 for a local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Bind 0.0.0.0 and honor $PORT. A single worker keeps the lifespan-built graph-client
# singleton simple on the free tier.
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
