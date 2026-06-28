# Runbook — Deploy the API to Render (free tier)

**Owner:** infra · **Status:** ready-to-deploy (no creds provisioned yet)

Stand up the FastAPI backend (`api.app:app`) on a Render **Docker web service** so the
Vercel frontend can call real data instead of mocks. Everything here is committed and
green; the only thing missing is credentials. Once they exist, deploy is a ~5-minute
button-press.

The repo already contains everything Render needs:

| File | Role |
|---|---|
| `Dockerfile` | Builds the serve image — installs the lighter `serve` extra (api + graph + live + providers + shapely), runs `uvicorn api.app:app` on `$PORT`. |
| `render.yaml` | Blueprint: a `free` Docker web service, health check `/health`, env-var contract. |
| `.dockerignore` | Keeps `.env`, data, frontend, and caches out of the build context. |

> **Rule #10 — secrets never in the repo.** This runbook and `render.yaml` contain
> **no** real values. Every secret is pasted into Render's dashboard at deploy time.

---

## Prerequisites (provision once)

1. **A Neo4j database reachable from Render.** Neo4j Aura Free works
   (<https://neo4j.com/cloud/aura-free/>). Note the connection URI
   (`neo4j+s://<id>.databases.neo4j.io`), username (`neo4j`), and password.
   Apply the schema (`graph/schema.cypher`) and load region data before or after the
   first deploy — the API serves honest empty/`null` results against an empty graph.
2. **A Render account** (<https://render.com>) with this GitHub repo accessible.
3. **The frontend origin** you will allow through CORS — for the live Vercel app that is
   `https://hike-app.vercel.app`. It is already pre-set in `render.yaml`.

---

## Environment contract (what the hosted API reads)

`render.yaml` declares the **required** vars. Secrets are `sync: false` (injected in the
dashboard); the non-secret CORS origin carries a value. The table below is the full
contract — the optional rows are added in the dashboard only if you turn those features on.
Every var is documented in `.env.example`.

| Variable | Required? | Secret? | In `render.yaml`? | Notes |
|---|---|---|---|---|
| `NEO4J_URI` | **yes** | yes | `sync: false` | Aura bolt URI (`neo4j+s://…`). |
| `NEO4J_USER` | **yes** | yes | `sync: false` | Usually `neo4j`. |
| `NEO4J_PASSWORD` | **yes** | yes | `sync: false` | Aura password. |
| `ADVENTURE_CORS_ALLOW_ORIGINS` | **yes** | no | value set | Comma-separated exact browser origins. Empty = default-deny (browser blocks every call). |
| `ADVENTURE_DEV_VIEWER_SECRET` | for non-anonymous viewers | yes | `sync: false` | Must equal the frontend's `X-Dev-Viewer-Secret` (Epic 014). Absent → only anonymous browsing works (fail-closed 403). |
| `ADVENTURE_REGION` | no (default `shenandoah-gwj`) | no | — | Pilot ingest region. |
| `ADVENTURE_LIVE_ADAPTERS` | no (default none) | no | — | Comma-separated live probes (`nws,airnow,…`). Empty = no live conditions; the engine still runs (source-or-silence). |
| `NWS_USER_AGENT` | only if `nws` enabled | no | — | Contact string required by api.weather.gov. |
| `AIRNOW_API_KEY` | only if `airnow` enabled | yes | — | EPA AirNow key. |
| `FIRMS_MAP_KEY` | only if `firms` enabled | yes | — | NASA FIRMS map key. |
| `RIDB_API_KEY` | only if `ridb` enabled | yes | — | Recreation.gov key. |
| `VALHALLA_BASE_URL` | only for drive-time | no | — | Self-hosted Valhalla URL; absent → no drive-time line. |
| `ANTHROPIC_API_KEY` | only if a tier is set to `anthropic` | yes | — | Cloud yardstick; local-first by default, so unset is fine. |

Model providers default to a **local** OpenAI-compatible endpoint
(`LOCAL_OPENAI_BASE_URL`), which a Render box cannot reach. The anonymous browse + maps
surface does not call a model, so the default deploy serves fine; wire a reachable
provider before relying on model-backed phrasing.

---

## Deploy (the click-path)

1. **Connect the repo.** Render dashboard → **New** → **Blueprint**. Pick this GitHub
   repo and the `main` branch. Render finds `render.yaml` at the repo root and shows one
   service: **adventure-planner-api** (Docker, free).
2. **Fill the secrets.** Render prompts for every `sync: false` var before it will apply.
   Paste:
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — the Aura connection from step 1 of
     Prerequisites.
   - `ADVENTURE_DEV_VIEWER_SECRET` — the shared secret the frontend sends (leave blank to
     run anonymous-only).
   `ADVENTURE_CORS_ALLOW_ORIGINS` is already set to the Vercel origin; edit it here if your
   frontend lives elsewhere.
3. **Apply.** Render builds the `Dockerfile` and starts the service. First build pulls
   wheels and takes a few minutes; watch the build/deploy logs in the dashboard.
4. **Wait for green.** The deploy is healthy once Render's health check hits
   `/health` and gets `200`. Render shows the public URL
   (`https://adventure-planner-api.onrender.com` or similar).

---

## Verify

```sh
# Liveness + which probes/region are wired (200 even before Neo4j is reachable):
curl -s https://<your-service>.onrender.com/health | jq

# Anonymous world browse — no auth header needed:
curl -s "https://<your-service>.onrender.com/trail/<canonical_id>" | jq

# CORS preflight from the Vercel origin should echo the allow-origin header:
curl -si -X OPTIONS "https://<your-service>.onrender.com/plan" \
  -H "Origin: https://hike-app.vercel.app" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin
```

A healthy `/health` returns `status: "ok"` plus `region`, `probes_available`, and a
`graph` block (or `graph: null` until Aura is reachable / loaded).

---

## After deploy

- **Point the frontend at the API.** Set the frontend's API base URL (in Vercel) to the
  Render service URL and redeploy the frontend.
- **CORS mismatch** is the most common first failure: the browser console shows a blocked
  cross-origin request. Fix by making `ADVENTURE_CORS_ALLOW_ORIGINS` exactly match the
  frontend origin (scheme + host, no trailing slash), then redeploy.
- **403 on non-anonymous calls** means `ADVENTURE_DEV_VIEWER_SECRET` is unset or does not
  match what the frontend sends — fail-closed by design.
- **Free-tier spin-down:** Render free web services sleep after inactivity; the first
  request after a sleep is slow while the container cold-starts. Expected on free tier.
- **Redeploy:** `autoDeploy` is on, so a push to `main` rebuilds. Env-var edits take
  effect on the next deploy (trigger one from the dashboard).

See [`../../CLAUDE.md`](../../CLAUDE.md) for the non-negotiable rules this deploy upholds
(source-or-silence, secrets-never-in-repo, access-control-at-the-data-layer).
