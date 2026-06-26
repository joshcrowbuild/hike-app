# Stage 4 — Engine + Live Data + Cost (design)

*Workplan Stage 4. Draft v0.1 — June 19, 2026. The Phase-0 spine. Builds on Stages 1–3.*

> **Status: DESIGN (planning mode).** Specifies the orchestration substrate, the Scout → Verifier → Curator engine, the live-adapter pattern, the truthfulness eval, and a **cost estimate** to be replaced by a real measurement (the Stage-4 spike). Decisions marked 🅓 are flagged for review (§9).

> **What this produces (per workplan):** the orchestration substrate choice · **Scout** (candidate generation) · **Verifier** (live-call logic + per-source adapters + source-or-silence enforcement) · **Curator** (constraints-as-filters + ranking) · a thin **truthfulness eval** (T4) · a **real cost number** (estimated here, measured in the spike). **Honors:** source-or-silence (#1), confidence-never-penalizes-rank (#2), graph-holds-slow-data (#3), access-at-query-layer (#4), no-training (#9).

---

## 1. Orchestration substrate — a code-orchestrated workflow, not an autonomous agent

The single most important Stage-4 decision. The engine is a **deterministic, code-controlled pipeline** (Scout → Verifier → Curator), **not** an open-ended agent that decides its own trajectory. Each stage is either plain code (graph query, threshold filter) or a *scoped* LLM call. This is the **design/runtime separation** the role cares about: the *shape* of the flow is authored and legible; only bounded judgment is delegated to the model.

- **Substrate:** a thin **provider-abstraction seam** in Python (matching the ingestion toolchain from Stage 3), behind which sit pluggable model adapters — **local/self-hosted by default** (via an OpenAI-compatible endpoint: Ollama / vLLM / LM Studio) with the **official Anthropic SDK as one hot-swappable adapter** for comparison (§2). **No heavyweight agent framework** (LangGraph/CrewAI/etc.): the flow is a fixed DAG we own, so a framework adds indirection, hurts observability, obscures the design/runtime boundary, **and would lock us to one provider's tool-runner.** We orchestrate the loop in our own code — which is exactly what makes a provider swap clean.
- **Tool use** is used *narrowly* — the Verifier's live-data calls are modeled as tool functions (the SDK tool-runner drives the call→execute→feed-back loop), but the agent never roams: it's handed a fixed candidate and a fixed tool set.
- **MCP is deferred to genuinely interactive moments** (Decision Log §8): a future "ask the planner" chat, and the agent-facing watch tools (Coros official MCP; Garmin). **The Phase-0 JIT Verifier uses direct HTTP adapters, not MCP** — MCP's value is mid-reasoning tool discovery for an interactive agent; a batch/JIT pipeline gets simpler, cheaper, more testable code from direct calls. Clean split preserved: *batch + JIT pipeline = direct calls; agent-reaching-for-a-tool = MCP.*

🅓 *Confirm: Python for orchestration (recommended — one toolchain with ingestion + watch libs). The frontend/API layer can be separate.*

---

## 2. Model providers & tiering (provider-agnostic, local-first)

**The model is a swappable component, not the moat** (§2 of the Decision Log: the value is the verified-synthesis graph, not the LLM). Two orthogonal axes pass through one config-driven seam: **which provider** (local vs. cloud) and **which capability tier** (mechanical vs. judgment).

**Tier by job** — cheap/small model for mechanical work, strong model only for judgment:

| Stage / job | Tier | Local viability today |
|---|---|---|
| Scout query understanding (parse "near me this weekend, dog-friendly") | **mechanical** | ✅ strong locally; often skippable (structured UI inputs) |
| Verifier condition normalization / hedged phrasing | **mechanical** | ✅ strong locally |
| Curator taste/novelty/party judgment | **judgment** | 🔶 the gap, if any, shows here — measure it |
| Truthfulness LLM-judge (eval) | **judgment** | 🔶 frontier helps; compare via the eval |

**Provider policy — default local, hot-swap cloud:**
- **Default to a local/self-hosted model** (privacy-aligned with the local-first "crown jewels" stance, §14; no per-token cost). Keep a **cloud adapter (Claude) hot-swappable** as the quality/cost/latency **yardstick** — not as the default.
- **Route by data sensitivity** (mirrors the auth boundary = shared/private boundary, §13): the **anonymous world + conditions** layer (no personal data in the prompt) may use a cloud model; anything touching the **private overlay** (beliefs, watch, party) routes to the **local** model so personal data never leaves the machine. A principled policy, not all-or-nothing.
- **Provider + model + tier all live in config** (`.env` / a small provider registry), never hardcoded — so a swap is config-only and the eval (§7) can A/B providers on the *same* flow.

**The seam (keep it thin):** a small capability interface — roughly `extract()`, `normalize()`, `judge()` — with two adapters: an **OpenAI-compatible** adapter (local: Ollama/vLLM/LM Studio) and an **Anthropic SDK** adapter (Claude). Provider-specific optimizations live *behind* the seam as opt-in enhancements (Claude: prompt caching, adaptive thinking; local: quantization/context settings) — **not** flattened into a lowest-common-denominator interface. Because we own the tool loop (§1), neither adapter depends on a provider's tool-runner.

**Reference pricing for the cloud yardstick** (per 1M tokens in/out, June 2026): Opus-tier ~$5/$25 · Sonnet-tier ~$3/$15 · Haiku-tier ~$1/$5. Local marginal token cost ≈ $0, traded for hardware + latency (a single consumer GPU or Apple Silicon runs quantized 7B–70B models; far lighter than the abandoned fine-tune branch, §1/§25).

🅓 *Open: which local runtime (Ollama vs. vLLM vs. llama.cpp) and which candidate local models — decide against the hardware envelope + the eval, in the spike.*

---

## 3. Scout — candidate generation (mostly deterministic)

Generates the candidate set from the corpus within the query radius + profile. **Primarily a scoped Cypher traversal, not an LLM call:**

- Spatial query: trailheads within the drive-radius of the origin (origin = runtime parameter, Decision Log §5), using the Neo4j point index.
- Profile/constraint pre-filter at the **query layer** (#4): the traversal is parameterized by the viewer's permission set via the `scopedQuery(viewer)` wrapper (Stage 2 §7) — Scout *cannot* emit a query returning ungranted nodes.
- Optional Haiku-tier call only to parse free-text intent into filter parameters; structured UI inputs skip it.
- Output: a ranked-by-cheap-heuristics candidate list (proximity, profile fit) — **capped to top-K** (e.g. K≈8–12) before the expensive Verifier stage. The cap is a primary cost lever (verify few, not all — §4 architected this).

---

## 4. Verifier — the heart (source-or-silence enforced in code)

For the top-K candidates *only*, fetch live conditions JIT and attach **source + timestamp** to every fact. Source-or-silence is a **code invariant**, not a model behavior:

- Per candidate, call the live adapters (§5). Each returns `{value, source, fetched_at, confidence_inputs}` or **nothing**.
- **Enforcement:** a fact with no `(source, fetched_at)` is **never surfaced as stated** — it's dropped or flagged "unverified / verify before you go" (confidence floor, Decision Log §7). This lives in deterministic code wrapping the adapters; the LLM cannot manufacture an unsourced fact because the LLM never produces the facts — it only *phrases* facts the code already verified.
- The Haiku-tier call (optional) turns verified facts + their confidence into **hedged, sourced language** ("~3h10 based on a handful of hikers; creek running high per USGS gauge 6 mi away, 15 min ago"). The hedge *is* the honesty (#2/§7).
- **Caching / TTLs per source** (don't re-verify unchanged conditions within a window — the cost lever):

| Source | TTL | Note |
|---|---|---|
| NWS forecast | ~10 min (honor `Cache-Control`) | alerts effectively real-time |
| USGS Water (OGC API) | ~15 min | gauge cadence |
| NASA FIRMS | ~10 min | URT/near-real-time |
| EPA AirNow | ~60 min | EPA guidance: cache within the hour |
| RIDB availability | minutes–hours | unofficial endpoint; degrade-and-disclose |

- **Live data never persisted as graph nodes** (#3) — held in a short-TTL cache keyed by the resolution ids stored on nodes (Stage 2 §8). FIRMS/AirNow caveats from Stage 1 (thermal anomalies ≠ fire; AQI is "preliminary") are surfaced as disclosures.

---

## 5. Live adapters (the per-source Verifier tools)

One small adapter per source, each a pure function `(lat/lon or site_id) → verified fact | None`, wrapped as a tool the Verifier can call. Built from the Stage-1 catalog:

- **NWS** (`api.weather.gov`): keyless + User-Agent; `/points` → forecast/hourly + `/alerts/active`. Flash-flood/red-flag alerts are the hard-guardrail feed.
- **USGS Water** (`api.waterdata.usgs.gov/ogcapi`): streamflow/gage; **new OGC API, not legacy** (§27). Disclose nearest-gauge distance.
- **NASA FIRMS**: Area API + MAP_KEY; hotspots near the route.
- **EPA AirNow**: keyed; AQI/PM2.5; label preliminary.
- **RIDB**: requirements (corpus) vs. availability (live, unofficial — risk-flagged).
- **Valhalla** (self-hosted): drive-time isochrone / matrix for the origin-radius and per-candidate drive time.

Each adapter has integration tests with **mocked responses + outage/rate-limit handling** (Decision Log §17): NWS fair-use, AirNow 500/hr, FIRMS 5000/10min, RIDB ~50/min. An adapter that errors or rate-limits **degrades and discloses** — it never fabricates and never blocks the feed.

---

## 6. Curator — constraints-as-filters + taste (+ party + novelty)

Ranks the verified candidates. Two distinct halves (Decision Log §9 — constraint vs. taste → different agents):

- **Constraints = hard filters (deterministic guardrails):** drop closed trails, unavailable permits, off-leash-required when Ruby's along, hard fire/AQI thresholds. A violation here is a *bug*, not a soft loss. These run in code, not the model.
- **Taste = Opus-tier ranking (soft):** orders the survivors by taste, season, novelty, party-suitability. **Confidence must NOT penalize this ranking** (#2) — a low-confidence trail ranks on its merits and is shown *honestly* (hedged), not buried.
- **Party composition** (when present): constraints compose conservatively (most-restrictive wins); readiness gates on the *less*-recovered; taste merges by "minimize the bigger disappointment" (full algorithm → Stage 8; Phase 0 is single-user).
- **Novelty / explore-exploit** stub: memory that predicts you too well makes you smaller (§9) — a lever introduced properly in Stage 5.

The Curator's input is a **subgraph** (the candidate trail + its sourced facts + — later — your episodes/beliefs), realizing graph-as-context (Decision Log §6). The output is the calm, curated feed: ranked, verified, each card showing its sourced facts phrased to their confidence.

---

## 7. Truthfulness eval (T4) — the thin Phase-0 check

A real eval rides with Phase 0 (the deep stochastic methodology is Stage 7). Scope:

- **What it measures:** does **every surfaced fact carry a source + timestamp**, and does it **match the live data** the adapters returned? (The core promise.) Plus: are closed/unavailable/guardrail-violating trails ever surfaced? (Should be never.)
- **Method:** an **Opus-tier LLM-judge** scores each card against the captured adapter outputs for that run; deterministic checks catch guardrail violations (no judge needed). Because the flow is **stochastic**, run **N times per scenario** and report a pass rate, not a single pass/fail (the seed of the Stage-7 methodology).
- **Golden set:** bootstrap from a handful of known trips in the pilot region (Shenandoah/GWJ), with hand-verified expected facts — the first eval-set question (Decision Log §17). Watch-logged trips feed this later.
- **Runnable in CI** (eval-as-test): regression across engine versions; memory-on-vs-off once Stage 5 exists.

---

## 8. Cost model — estimate now, **measure in the spike**

LLM tokens dominate **the cloud path**; everything else (NWS/USGS/FIRMS/AirNow/RIDB free; Valhalla self-hosted; Neo4j local) is cheap. Cost has **two different shapes** depending on provider, which is exactly why the spike measures both:

- **Local/self-hosted (the default):** marginal token cost ≈ $0; the real costs are **hardware** (a GPU / Apple Silicon) and **latency**. The budget question becomes "does it fit the machine and feel fast enough," not "$/session."
- **Cloud (the yardstick):** a **rough** per-session estimate (one feed render, K≈8 candidates), to be replaced by measurement:

  | Stage | Calls | Rough cloud cost |
  |---|---|---|
  | Scout | 0–1 mechanical-tier (often deterministic) | ~$0.00–0.01 |
  | Verifier | ~K mechanical-tier normalizations + free HTTP | ~$0.02–0.04 |
  | Curator | 1 judgment-tier call over K + context | ~$0.08–0.13 |
  | **Per session (uncached)** | | **~$0.10–0.18** |

**Cost/perf levers (already architected):**
1. **Shortlist cap K** — verify/curate top-K only (the biggest structural lever; helps local latency too).
2. **Prompt caching (cloud)** — stable system prompt + candidate subgraph cache at ~0.1× read; keep volatile bits (live readings, timestamps) *after* the breakpoint. (Local KV-cache reuse is the analog.)
3. **Provider + tier routing** (§2) — mechanical tiers local-cheap; reserve the cloud yardstick for the judgment call when comparing.
4. **Condition caching / TTLs** (§4) — a re-open within the TTL re-verifies nothing.

🅓 **The Stage-4 spike (now a provider bake-off):** run the real flow against the real Shenandoah/GWJ corpus and **measure, through the same truthfulness eval (§7), local vs. cloud on three axes — quality, cost, latency.** This turns "which provider" into an empirical call, not an ideological one, and sets the actual budget. Do not ship a budget (or a provider default) off the estimate above.

---

## 9. Open decisions (🅓) & deferrals
**Open:** orchestration language = Python (recommend yes); K value (tune in the spike); Haiku-vs-Sonnet for normalization (A/B in the spike); whether the Verifier's phrasing call is worth its cost vs. templated hedging (measure).
**Deferred:** memory/personalization in Scout+Curator (Stage 5); party-merge algorithm (Stage 8); the deep stochastic-eval methodology + golden-set bootstrap at scale (Stage 7); the always-on poller for push (later).

## 10. ◆ Phase-0 design checkpoint
With Stages 1–4 designed, the **end-to-end verified-synthesis slice is fully specified**: ingest one region (S3) → thin Neo4j graph (S2) → Scout/Verifier/Curator over real corpus + live overlay (S4) → calm feed → truthfulness eval. The remaining work is **build + the cost-measurement spike**, not more design. This is the natural point to start writing the vertical slice.
