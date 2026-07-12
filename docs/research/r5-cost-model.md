# R5 Cost Model — Current, Projected, At-Scale, Over Time

*The full cost picture for a one-person, personal, not-for-sale Adventure Planner: every dollar surface (runtime LLM · hosting · live APIs · development), bottom-up per-`/plan` math with scenario bands, the warmer cost finding, three cost postures, and the optimization mindset. Closes the modeling half of roadmap risk R5; the measured half needs one 5-minute log read (§2).*

**Last verified:** 2026-07-12 · **Owner:** research/PO · **Status:** `ACTIVE`

> **Status:** bottom-up model from repo code + current published prices (external prices fetched 2026-07-12, sources §10; LLM prices from Anthropic's current catalog). The single ground-truth validation is deliberately cheap: every `/plan` logs a `PlanMetrics` line with `est_tokens`/`est_cost_usd`/`warmed` (`api/observability.py:159-178`) — **one paste of a day's Render log lines into any session turns every band in this doc into a measured number.**
> **Legend:** ✅ verified · 🔶 estimated band · ❓ unknown until a dashboard/log check

---

## 0. TLDR

The app's costs live in four buckets. Three are boring; one needs a decision **this week**.

| Bucket | Today | Trajectory |
|---|---|---|
| Hosting (Render + Aura Free + Vercel) | **~$7/mo** ✅ (Render Starter; confirm tier ❓) | Flat until the graph outgrows Aura Free → **$66/mo cliff**; a ~$6.50/mo VPS is the escape hatch |
| Live condition APIs (NWS/USGS/AirNow/FIRMS/RIDB/3DEP/Overpass) | **$0** ✅ | $0 at any personal scale — all free government/open APIs with quotas ~100× our needs |
| Runtime LLM (intent parse + taste rank per cold `/plan`) | was **~$1–5/mo** organic · **now warmer-dominated: 🔶 $15–470/mo depending on prod config** (§4) | Collapses back to ~$2–10/mo once Epic 040 (two-phase render) retires the warmer |
| Development (Claude Max plan, GitHub Team) | **~$104–204/mo** ✅ | The largest real line by far — and it's the hobby itself, not the app |

**The bar:** never paying for AllTrails again = beating ~$36–80/yr (Plus/Peak); a typical two-app hiker stack is $110–180/yr. **The steady-state app clears that bar easily (~$85–110/yr all-in runtime)** — provided the warmer decision (§4) is made and the Aura cliff (§5) is dodged when it comes.

---

## 1. Cost anatomy — what costs money at all

Grounded in code:

- **Per cold `/plan`** (`orchestration/engine.py`): up to two LLM calls — `parse_intent` on the *mechanical* tier (`engine.py:709`, skipped entirely if the tier is unconfigured) and the taste-rank *judgment* call (~10 candidate names + hints; skipped when scout finds zero candidates). Everything else in the request is free: graph reads (Aura), live probes (free APIs), rendering.
- **Cache-hit `/plan`**: zero LLM, zero live calls (`feed_cache_hit` zeroes `est_tokens` — `api/observability.py:102`).
- **The feed warmer** (`api/feed_warmer.py`, live since PR #164): every `ADVENTURE_FEED_WARM_INTERVAL_S` (default 240s) it re-primes **each of the 11 region configs' default frames** — 1 loaded region (full pipeline + judge) + 10 unloaded (intent parse only, if the mechanical tier is LLM-backed; near-free otherwise).
- **Ingestion/enrichment**: one-time per region re-ingest (Overpass/agency fetches free; 3DEP free); no LLM.
- **Evals/CI**: hermetic (cassettes, no LLM). GitHub Actions minutes on a Team plan: 3,000 free/mo; a heavy day (~10 runs × ~15 job-min) uses ~5% ✅.
- **Not deployed / $0**: Valhalla drive-time (`VALHALLA_BASE_URL` default unset ❓ confirm), Sentry, map tiles (USGS/OpenTopoMap free within polite volume).

Per-call price math (current Anthropic catalog ✅): Haiku 4.5 $1/$5 per MTok in/out · Sonnet-class $3/$15 · Opus-class $5/$25. Estimated tokens per call 🔶: intent ≈ 200–600 in / 50–150 out; judge ≈ 1,200–2,500 in / 100–300 out.

**→ One cold `/plan` ≈ $0.002–0.005 (Haiku-class) · $0.007–0.016 (Sonnet-class) · $0.011–0.027 (Opus-class).** The repo's own blended estimator ($0.009/1K tokens, `observability.py:43`) prices a ~2.5K-token plan at ~$0.02 — consistent with the upper band.

## 2. Ground truth in 5 minutes (the measured half of R5)

The bands below span a 30× range because two prod facts live only in the Render dashboard ❓: **(a)** which tiers are LLM-backed (`ADVENTURE_PROVIDER_MECHANICAL/JUDGMENT` + model ids) and **(b)** the warmer/TTL env values. To collapse the bands: copy one day of `PlanMetrics` log lines (they carry `est_tokens`, `est_cost_usd`, `feed_cache_hit`, `warmed`) from Render into any Claude session. `sum(est_cost_usd) × 30` = the monthly runtime LLM number, split organic vs `warmed=True`.

## 3. Current monthly — organic use only (pre-warmer baseline)

Josh-only dogfood, ~5–15 plans/day, most missing the 5-minute cache:

| Prod config | LLM $/mo |
|---|---|
| Judge-only (mechanical tier unconfigured), Haiku-class | **~$1–2** |
| Both tiers Sonnet-class | **~$3–7** |
| Both tiers Opus-class | **~$5–12** |

Plus hosting $7 ⇒ **~$8–19/mo all-in** before the warmer. Comfortably under the AllTrails bar.

## 4. ⚠️ The warmer finding — a decision needed now

The B5 warmer (merged tonight) converts cold-start latency into scheduled LLM spend. At **current defaults** (interval 240s, anon-cache TTL 300s → every frame re-primed *every round*; 11 frames):

| Scenario (prod config ❓) | Warmer $/day | $/mo |
|---|---|---|
| Judge-only prod, Haiku-class (10 empty frames ≈ free; loaded frame 360×/day) | ~$0.7–1.8 | **~$20–55** |
| Judge-only, Sonnet-class | ~$2.5–5.8 | **~$75–175** |
| Both tiers Sonnet-class (10 unloaded frames each burn an intent parse, 360×/day) | ~$7–16 | **~$220–470** |

Corrections and mitigations, in order:
1. **Owner env flips (already queued) help immediately:** TTL→600 halves the cadence (re-prime every 480s). Optionally raise `ADVENTURE_FEED_WARM_INTERVAL_S` (e.g. 480–540) — or set `0` to kill the warmer and accept 4–14s cold starts until Epic 040.
2. **Scope the warmer to the served region** (small follow-up lane): the process serves ONE region; warming the other 10 configs' frames buys nothing a visitor can hit warm anyway *in this deployment shape*. Cuts frames 11→1. 🔶 recommended, and my kickoff prompt caused the 11-frame scope — the builder disclosed the cost note; the PO underestimated it.
3. **A2 fast judge** (`ADVENTURE_MODEL_JUDGMENT` → Haiku-class, with an ordering spot-check per the Epic 039 ladder): ÷3 on the dominant call, *and* it shrinks the cold path the warmer exists to hide.
4. **Epic 040 two-phase render** (DEFINED, ready to build): cards paint in <1.5s from the corpus with no LLM on the critical path's first paint → **the warmer becomes unnecessary and turns off**, returning LLM spend to the organic ~$2–10/mo. The external literature is blunt here: scheduled warming at single-user visit frequency is a >100:1 write-to-read waste; the durable fix is a cheap on-demand path, not a hotter cache.

**Recommended posture: flips now (1) + scoping lane (2) + build Epic 040 soon (4); treat the warmer as scaffolding with a planned demolition date.**

## 5. At scale and over time

- **More users (household, Phase F):** anonymous browsing is nearly free at any household scale (shared anon cache + free APIs). Personalized plans bypass the anon cache → each member adds organic-cold-plan spend (~$1–5/mo each). LLM cost is never the scale problem.
- **The graph is the scale problem.** Aura Free: 200K nodes / 400K relationships ✅ (Neo4j FAQ; some pages still say 50K/175K — verify in console ❓). Shenandoah = ~2.2K trails ≈ single-digit % of the cap; **every added region marches toward the $65.70/mo Professional cliff** — the single biggest cost risk in the managed path (it alone would triple the annual cost of everything else combined). Escape hatch, when needed: Neo4j Community on a ~€6/mo Hetzner-class VPS (4GB is comfortable ✅) or a home box — the migration genre consistently reports 70–90% savings past ~$40/mo managed spend.
- **Also on the Aura Free fine print:** instances **auto-pause after 72h of no queries and can be deleted after extended pause** ✅ — the warmer/health probes currently double as keep-alive; if the warmer is turned off, confirm `/health`'s graph probe still queries often enough. Re-runnable ingest (Phase A, done) is the real insurance: the corpus can be rebuilt from sources.
- **Over time, tailwinds:** token prices trend down (Sonnet 5 launched at an intro discount; Haiku-class handles more each generation), and the app's local-first provider seam means the judgment tier can move to a home Mac/Ollama at ~$0 marginal whenever quality suffices — the strategic hedge is already built.
- **Vercel Hobby is contractually non-commercial** ✅ — fine forever for a personal project; a constraint to remember only if this ever stops being personal.

## 6. Development costs — the honest biggest line

- **Claude Max plan: $100/mo (5×) or $200/mo (20×)** — powers every builder session, PO session, and research fan-out. Today's cadence (multiple long build waves + research) fits the 20× tier. **$1,200–2,400/yr — an order of magnitude above everything the app itself costs.**
- GitHub Team: ~$4/user/mo; Actions well within free minutes.
- Framing that keeps this honest: the Max plan is the *workshop*, not the *product* — it's the hobby's cost the way a woodworker prices their table saw, and it already existed before this project. The app's own bill is the $7–19/mo runtime; the development spend buys the fun. But on a pure ledger, this project's true annual cost is **~$1,300–2,500**, of which ~93% is the workshop.

## 7. The "never pay for AllTrails again" scorecard

| Path | $/yr | Notes |
|---|---|---|
| AllTrails Plus / Peak | $36 / $80 | the bar |
| Typical two-app hiker stack (Peak + Gaia/onX) | $110–180 | the realistic bar |
| **This app, steady state** (Render Starter + Aura Free + organic LLM, post-040) | **~$85–110** | beats the two-app stack; ~ties Peak |
| This app, warmer left at defaults, Sonnet both tiers | up to ~$5,700 | the one bad path — don't |
| This app, self-host VPS + local-first LLM | **~$85** | flat forever, no Aura cliff, more ops chores |
| This app, home server | ~$25–60 (power) | cheapest; backups/uptime are on you |

## 8. Three postures (pick a lane, revisit yearly)

1. **Managed-lean (recommended now):** Render Starter + Aura Free + Vercel Hobby + Haiku-class judge + warmer scoped-then-retired by Epic 040. **~$8–12/mo.** Zero ops burden; the Aura cliff is the watch item.
2. **Self-host pivot (when Aura Free binds or bill >$25/mo):** one ~€6 Hetzner/DO VPS runs Neo4j Community + API + jobs; Vercel stays. **~$7/mo flat, no cliff.** Costs a weekend of migration + ongoing patch/backup discipline.
3. **Home-server endgame (matches the local-first vision):** mini PC/Mac at home runs graph + API + Ollama judgment tier; cloud = Vercel + nothing. **~$3–5/mo power.** Pairs naturally with the far-horizon on-device companion; weakest on away-from-home reliability.

## 9. The optimization mindset (rules of thumb, evidence-backed)

1. **Measure before optimizing** — the `PlanMetrics` line exists for exactly this; one log read beats every estimate in this doc.
2. **Pay for compute once, serve it many times** — but only where reads actually outnumber writes. A single-user app fails that test for scheduled warming (>100:1 waste); it passes for one-time enrichment (3DEP), corpus ingest, and stored artifacts.
3. **Right-size the model to the task, statically.** Intent parsing and 10-item ranking are the canonical small-model tasks (RouteLLM: ~95% of frontier quality at 85% cost reduction on routed workloads; Haiku-class ≈ 2–5% off Sonnet on classification/ranking per practitioner consensus 🔶). No dynamic router needed at this volume — set the tier in config, gate with a 50-case eval.
4. **Make the fast path free and the fresh path honest** — Epic 040's whole premise: corpus cards need no LLM; conditions stream in. Latency fixes that remove LLM from the hot path are also cost fixes.
5. **Batch the offline lane** (50% off): nightly Scout pre-ranking, eval runs, any future corpus-scale LLM enrichment. Never for interactive traffic.
6. **Local models are a privacy play, not a cost play, at this volume** — API spend at hundreds of calls/day is single-digit dollars; the local seam's value is rule #5 (private overlay) and the on-trail future.
7. **Watch the cliffs, not the pennies**: Aura Free→Pro (+$66/mo) and warmer-at-defaults (+$50–450/mo) dwarf every other decision. Everything else in this stack moves by single dollars.

## 10. Owner actions (fold into the queue)

1. **Warmer decision** (Render env, 2 min — supersedes/extends the earlier flips): set `ADVENTURE_ANON_FEED_CACHE_TTL_S=600`; then either accept the interim warmer spend, raise `ADVENTURE_FEED_WARM_INTERVAL_S` (480–540), or set it `0` until Epic 040.
2. **Paste a day of `PlanMetrics` lines** into a session → collapses this doc's bands to measured numbers (closes R5 fully).
3. **Confirm in dashboards** ❓: Render service tier ($7 vs $25) · prod `ADVENTURE_PROVIDER_*`/`ADVENTURE_MODEL_*` values · whether `VALHALLA_BASE_URL` is set anywhere.
4. Later, when convenient: Aura console → check node/relationship count vs the Free cap (sizes the runway to the cliff).

## 11. Sources

Anthropic pricing: current model catalog (Haiku $1/$5 · Sonnet $3/$15 · Opus $5/$25 /MTok; cache reads ~0.1×; Batches −50%). Competitor pricing: AllTrails Plus $35.99 / Peak $79.99 (support pages 403'd; 3+ corroborating 2026 sources) · Gaia w/ Outside+ $89.99 · onX Backcountry $29.99–99.99 · komoot Premium $59.99. Hosting: render.com/pricing (Starter $7, Standard $25; free tier spins down 15min) · neo4j.com/pricing + Aura FAQ (Free 200K/400K, 72h auto-pause; Professional ~$65.70/mo/GB) · vercel.com Hobby docs (free, non-commercial, 100GB transfer). Free APIs: NWS (~5k/hr unofficial) · USGS Water (50/hr keyless, free key) · AirNow (500/hr/key) · FIRMS (5k/10min) · RIDB (~50/min) · OpenTopoData (1k/day public) · Overpass (~10k/day fair use). Self-host: Hetzner post-2026-06 price rise (CX23 €5.49) · Neo4j Community 2GB/2-core minimum. Optimization evidence: RouteLLM (lmsys.org, arxiv 2406.18665) · Anthropic prompt-caching economics (reads 0.1×, writes 1.25–2×, min prefix 1–4K tokens) · dev.to prompt-cache postmortem (datetime-in-prompt) · cache-warming literature ("schedules are not traffic patterns"). Full URLs preserved in the two research-agent reports of 2026-07-12 (session transcript).
