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
COPY regions ./regions

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
#
# --proxy-headers --forwarded-allow-ips='*': every request's TCP peer is Render's proxy
# (the container port is not directly reachable from the public internet), so without
# these flags request.client.host is the proxy for ALL clients. Historically this repo
# relied on uvicorn's trust-all rewrite (taking the FIRST X-Forwarded-For entry) to
# restore per-IP keying for the rate limiter — VERIFIED (2026-07-02, AH2) that trust-all
# takes X-Forwarded-For[0] with no hop-count check, so its safety depended entirely on an
# unverified claim that Render always overwrites (never appends to) a client-supplied
# X-Forwarded-For. That could not be confirmed within a safe live-test budget, so
# api/ratelimit.py no longer trusts request.client.host at all — it reads the raw header
# itself and takes the LAST entry (the one hop closest to us can only have appended,
# never the client). These flags stay on for `request.scope["client"]` consumers other
# than the limiter; they are NOT what makes rate-limit keying spoof-resistant anymore —
# see api/ratelimit.py:real_client_ip for the load-bearing logic.
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
