# Adventure Planner API — serve-time image for Render (Docker web service).
#
# Installs only the lighter serve surface (pyproject `serve` extra: api + graph +
# live + providers + shapely), never the rest of the heavy ingestion geo stack.
# shapely's manylinux wheel bundles GEOS, so no apt build/runtime libs are needed.
# Full deploy click-path: docs/runbooks/deploy-api-render.md
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

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
