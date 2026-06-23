#!/usr/bin/env bash
# Adventure Planner — autonomous sprint runner
# Run after: 1) filling ANTHROPIC_API_KEY in .env, 2) starting Docker Desktop
# Usage: bash scripts/sprint.sh  (or let the agent run it)
set -euo pipefail

cd "$(dirname "$0")/.."
set -a && [ -f .env ] && . ./.env && set +a

log() { echo "[sprint] $*"; }

# ── Phase 1: Pre-flight ───────────────────────────────────────────────────────
log "Running pre-flight..."
python3 scripts/preflight.py || { log "Pre-flight FAILED — fix errors above first."; exit 1; }

# ── Phase 2: Database setup ───────────────────────────────────────────────────
log "Starting Neo4j..."
docker compose up -d neo4j

log "Waiting for Neo4j to accept connections (up to 60s)..."
for i in $(seq 1 30); do
    if python3 -c "
import neo4j, os
d = neo4j.GraphDatabase.driver(
    os.environ.get('NEO4J_URI','bolt://localhost:7687'),
    auth=(os.environ.get('NEO4J_USER','neo4j'), os.environ.get('NEO4J_PASSWORD',''))
)
d.verify_connectivity()
d.close()
" 2>/dev/null; then
        log "Neo4j ready."
        break
    fi
    echo -n "."
    sleep 2
done

log "Applying schema..."
docker compose exec -T neo4j cypher-shell \
    -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD}" \
    < graph/schema.cypher

# ── Phase 3: Ingestion ────────────────────────────────────────────────────────
log "Running dry-run ingestion to validate fetch + conflation..."
python3 -m ingestion.pipeline --region "${ADVENTURE_REGION:-shenandoah-gwj}" --dry-run

log "Running live ingestion (OSM + NPS; USFS skipped unless data/usfs/trails.geojson exists)..."
python3 -m ingestion.pipeline --region "${ADVENTURE_REGION:-shenandoah-gwj}"

# ── Phase 4: Live adapter spot-checks ────────────────────────────────────────
log "Spot-checking live adapters (NWS, USGS Water)..."
python3 -c "
from orchestration.config import Settings
from orchestration.verifier import build_probes, verify

s = Settings.from_env()
probes = build_probes(s)
print('Active probes:', list(probes.keys()))

# Old Rag Mountain: lat=38.5519, lon=-78.2861
facts = verify(38.5519, -78.2861, probes)
print('Facts returned:', list(facts.keys()))
for k, f in facts.items():
    print(f'  {k}: source={f.source}, value_keys={list(f.value.keys()) if isinstance(f.value, dict) else type(f.value).__name__}')
"

# ── Phase 5: Eval bake-off ────────────────────────────────────────────────────
log "Running provider bake-off (n=3 for speed)..."
python3 -m evals.run_bakeoff --n-runs 3 || log "Bake-off skipped (may need pilot data in graph)"

# ── Phase 6: Final check ──────────────────────────────────────────────────────
log "Running full test suite..."
python3 -m pytest -q

log "Sprint complete!"
log "Start API server: make api-dev"
log "Try a plan: curl -s -X POST http://localhost:8000/plan \\"
log "  -H 'Content-Type: application/json' \\"
log "  -d '{\"query\": \"something mellow with good views\", \"lat\": 38.55, \"lon\": -78.45}'"
