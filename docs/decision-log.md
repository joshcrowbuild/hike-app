# Adventure Planner — Design & Decision Log

*Working title. Living document — last updated 2026-07-14.*

**Last verified:** 2026-06-26 · **Owner:** project (decisions of record)

A personal, agentic, self-verifying trip planner for hiking/backpacking, built deliberately as a skills-building artifact for a Capital One generative-AI-platform design-lead role. Fun and useful in real life; architecturally a small mirror of the platform org's actual work. A calm, private **utility** — not social, not engagement-seeking.

> **Legend:** ✅ decided · 🔶 recommended, confirm · ❓ open question to resolve.

---

# PART I — CONCEPT

## 1. The frame — why this project
- **Target role:** design lead on Capital One's *enterprise generative AI platform* org. Discipline: **platform design for non-deterministic multi-agent systems** — agent-builder DX, evals for stochastic multi-agent workflows, guardrails across threat boundaries, observability, human-in-the-loop, design/runtime separation, model specialization.
- **Reference architecture:** Chat Concierge (multi-agent: customer-facing agent, planner from rules + allowed tools, evaluator/accuracy agent, validator). Our planner mirrors this.
- **Why it beats a work-adjacent concierge as a portfolio piece:** personal + fun, and "I can eval a stochastic *trip* planner against real outcomes" shows the chops vividly. AllTrails-as-foil sells itself.
- **Hardware:** none needed — orchestration + a console. (Earlier fine-tune branch, which needed GPUs, was abandoned — see Roads Not Taken.)

## 2. Core thesis — the differentiation
- **AllTrails has no trail-data moat.** The map is open: OSM, USGS National Digital Trails/TRAILS, USFS Enterprise Data Warehouse, NPS — all public domain; OpenTrailMap is CC0. AllTrails' moat is reviews/photos/brand, not geometry.
- **Differentiation is temporal + personal, not volumetric.** Win on "right now, for me and Ruby," not "more trails." The value is **live, verified synthesis at decision time** — what a static app structurally can't be.

## 3. Two graceful-degradation axes (core product principle)
The floor is high and universal; everything else is upside, never a prerequisite.
- **Watch-data axis:** no watch → still fully works on static + live conditions.
- **Popularity/traffic axis:** an obscure, never-tracked trail → still fully served. A popular trail → gains the bonus emergent layer (§11).
- **Net:** *deeply useful as-is, more useful with traffic.* Valuable at zero crowd data and zero watch data, so neither cold-start gates the product. Lesser-traveled trails are first-class.

---

# PART II — ARCHITECTURE

## 4. Four layers
The crawl-vs-fetch question resolves by splitting data by rate of change.
1. **Corpus (slow data, indexed ahead)** — geometry, length, elevation, surface, dog rules, land manager, permit *requirements*, description. **Bulk-ingested, not crawled:** Geofabrik OSM extracts + USGS/USFS/NPS datasets, filtered to hiking features and joined. Built once, refreshed monthly. *The index is what makes a feed possible at all.*
2. **Background ranking (ambient)** — continuously narrows the corpus to a personal shortlist using profile + memory + season, while you're not looking. Cheap. Makes it "passive but intelligent" — you glance, you don't query.
3. **JIT verification (fast data, fetched live)** — for the shortlist *only*: NWS weather, USGS streamflow, NASA FIRMS + EPA AirNow (fire/smoke), Recreation.gov RIDB (permit availability). Source-or-silence applied. Never corpus-wide.
4. **Feed (the surface)** — scroll an already-verified, curated set; tapping a card shows the sourced facts. Calm and curated ("what's good this weekend"), not search, not engagement-baiting.

**Engine agents (mirror Chat Concierge):** **Scout** (candidates from corpus within query radius + profile) → **Verifier** (the heart; per-candidate live calls, source+timestamp, flags the unverifiable) → **Curator** (ranks by taste, season, novelty, Ruby-suitability).

**Console (platform/role-defining surfaces):** Authoring (profile/party as reusable editable object) · Guardrails (never surface unverifiable facts, closed trails, unavailable permits, off-leash-required when Ruby's along; hard fire/AQI thresholds) · Evals for stochastic flows (run against known trips, measure truthfulness; memory-on vs off) · Observability + correction (trace which API said what, when; corrections harden the Verifier; the legible belief store *is* the correction UI).

## 5. Dynamic location — origin as a runtime parameter ✅
- **Corpus extent** (indexed) — large, static, precomputed. Ultimately national; **East Coast first**.
- **Query extent** (where you search from) — a runtime parameter. Device location for default origin; manual override for travel; usual drive tolerance as default radius. Travel mode falls out for free. Per-session compute stays bounded (rank + verify only within the radius).

## 6. Data model — property graph (Neo4j) ✅
- **Why graph:** conflation + provenance and the belief layer are graph-native and the most differentiating parts. "Memory with receipts" = edges. Entity resolution = source-record nodes joined by `SAME_AS` to a canonical trail node, *preserving provenance as structure*. Beliefs `DERIVED_FROM` episodes that are `ON` trails a person `DID` — "why do you believe this?" is a traversal.
- **Graph-based context = the answer to "RAG pointed at the self":** hand the agent a *subgraph* (the trail, your similar episodes, the beliefs from them, Ruby's capability, nearby alternatives) — *why*, not just *what*. Graph traversal for context assembly; vector retrieval deferred until embeddings actually exist. Double-duty with the role's team.
- **Discipline — keep live data OUT of the graph.** Slow/structural in-graph; fast/ephemeral fetched JIT and overlaid, never persisted as nodes to expire.
- **Neo4j fit:** local Community, Cypher traversals, spatial point types for "near my origin." *Caution:* don't let it become a schema project — v0 graph is thin (canonical trails + provenance, stub profile/party), grown as episodes/beliefs accrue.

## 7. Confidence model — one property, applied to every fact 🔶
"Data confidence" unifies source-or-silence, the staleness worry, crowd sample-size, and belief-confidence. **Three axes that roll into one score:**
- **Freshness** — age relative to rate of change (forecast 10 min vs. 2 days old; permit checks decay in hours).
- **Authority** — USGS authoritative geometry vs. a lone 2017 OSM tag.
- **Corroboration** — a crowd pace from 3 hikers vs. 300; a belief from 2 episodes vs. 20.

**What it drives — three things and one deliberate non-thing:**
- **Floor:** below threshold, don't state the fact (source-or-silence as the bottom of a gradient).
- **Presentation:** above the floor, confidence sets phrasing. High → plain. Lower → hedged with its reason ("~3h10, based on a handful of hikers"). *The hedge is the honesty.*
- **Safety flag:** low-confidence *conditions* → "verify before you go," not quiet inclusion.
- **NON-thing:** confidence must **not** penalize ranking. Uncertainty ≠ low quality; burying low-confidence trails punishes the lesser-traveled ones we made first-class. Confidence shapes *how honestly we show* a trail, not *whether it ranks*.

**Unification:** crowd facts carry sample-size confidence intrinsically, and **the commons k-anonymity threshold (§11) doubles as the confidence floor** — below k contributors, a fact is both privacy-unsafe and too thin to trust. One gate, two jobs.

**Refined 2026-07-14 (§42):** the three axes now fuse by **weakest-link `min(a,f,c)`** (not a weighted mean), and a **`source_kind` primary/aggregated** split lets an authoritative single source reach "stated" — this section's principles are unchanged; the fusion + presentation mechanics are in §42.

## 8. System architecture — what runs where ✅/🔶
Three distinct pieces; don't conflate them.
1. **Your app — the backbone.** Runs Scout/Verifier/Curator orchestration, **owns the Neo4j graph**, runs scheduled ingestion, serves the feed. For now: processes on your machine + local Neo4j ("server" is lighter than it sounds). *The graph lives here, nowhere else.*
2. **MCP servers — thin adapters to outside data.** Each wraps a source as LLM-callable tools. Coros runs *theirs* (hosted, official — you just connect). Garmin's is community-built; run that small adapter yourself **or skip MCP for Garmin and call the python library directly.** Stateless pipes — **no graph in them.**
3. **The agent (Claude) — an MCP *client*.** Calls a tool on a server when it needs live data mid-reasoning.

**Key clarifications:**
- MCP is **request/response, pull only** — nothing pushes to you. "Auto-detect a hike" = *your ingestion job polls* the vendor for new activities. The hike-detected notification is generated by *your backend* after a poll, not by the watch.
- **You don't need MCP for the background plumbing.** Batch ingestion = ordinary scheduled jobs (cron calling the Garmin library / Coros API). MCP earns its keep only at *interactive* moments (the Verifier pulling live weather; a future "ask the planner" chat). Clean split: **batch ingestion = scheduled jobs; agent-reaching-for-a-tool = MCP.**
- **Polling needs something always-on.** A closed laptop doesn't poll → "detected on next app open." True same-day push means an always-on poller (cheap VPS / Pi / always-on Mac). Not a v0 concern (async + idempotent → backfills whenever it runs); it's why push is "later, if you want it," not free.
- **Multi-device:** the graph is the single source of truth on the backbone; phone + laptop are both clients against it.

---

# PART III — DATA & INTELLIGENCE

## 9. Memory & personalization ✅
**Principle:** memory is where verification meets personalization — a remembered preference is a new class of hallucination, so *source-or-silence applies to beliefs about the user too.* Every belief carries **provenance + confidence + timestamp**; an inference never poses as a stated fact.

**Layer separations:** stated vs. inferred (constraints vs. falsifiable hypotheses) · episodic vs. semantic (raw log vs. distilled generalizations, *derived-and-traceable* back to episodes) · constraint vs. taste → different agents (constraints = Verifier filters, violation = bug; taste = Curator ranking, miss = soft loss) · **it's a party, not a user.**

**Dynamics:** ground truth arrives later (predict → recommend → go → outcome → update) · beliefs decay (recent > old) · explore/exploit (*memory too good at predicting you makes you smaller*).

**Role-gold:** evals for the memory itself (memory-on vs off vs real outcomes; if it doesn't help, turn it off). **The store:** structured, provenance-tagged, confidence-weighted, decaying, **legible and user-editable** — not just a vector DB. Doubles as the correction surface.

## 10. Smartwatch / passive memory ✅
**The watch is the passive episodic memory.** A completed FIT track auto-becomes the trip episode (route, pace curve, stops, HR on climbs, ascent, moving/stopped). No journaling. Upgrades the outcome loop from *inference* to *measurement*.

**Two strictly separate roles:** **live readiness** (Body Battery / training readiness / HRV; Coros recovery) — **now a user-toggled FILTER, not a background default** (corrected): "tune to today's recovery" / "tune to the group's recovery." You choose when your body shapes the feed; it never silently does. Absent-data case is trivial — apply the filter with no reading and it just says it can't. · **historical capability** (the FIT archive) — feeds semantic beliefs (pace-on-grade, heat response, range, recovery).

**Deep principle:** the watch is an **excellent capability sensor and a poor preference sensor.** Behavior ≠ preference. Provenance tier *inferred-from-behavior* stays provisional until confirmed.

**Access (decided):** Garmin (deep) via python-garminconnect / Garmin MCP — Body Battery, training readiness, HRV, FIT (official Health API gated — skip) · Coros via official COROS MCP · universal: FIT via python-fitparse · shallow fallback: Apple Health (steps/HR/sleep only) · **avoid Strava API** — bans AI/ML use.

**Behavior:** ingestion **async + idempotent**, never blocks. Watch data is **enrichment, never a dependency** — every use degrades-and-discloses. Live readiness has a **freshness window**. **Built watch-free first**, so "no watch" is baseline by construction.

**Sync UX (decided):** ① **Connecting** — one-time auth per watch; Garmin session is fragile and will need occasional re-login → a quiet "connections" area, calm degrade + re-auth prompt. ② **Reflect-back card** (the heart) — on detection, reflect measured facts, ask only what a sensor can't see ("How was it? 🙂/😐/😞"; one delta question if a prediction gap is worth resolving); **fully skippable, decays if ignored.** Auto-detect with **opt-in push** (backend-generated after a poll), else surfaces on next app open. ③ **Readiness** — surfaces as *rationale* via the filter, never as a number. ④ **Beliefs** — pull, not push; live in the legible store; provisional-preference confirmations batched into the outcome card occasionally. ⑤ **Absence** — forgot watch → optional lightweight manual add (degraded episode); not synced → backfills; dead battery → partial episode. None are error states.

**Privacy/wellbeing:** sensitive; local-first, legible, prunable; a *planning input, not a health authority* — no coaching/nagging.

## 11. Multiplayer — shared world, private people ✅
- **The world is shared; the person is private.** Trails/segments/conditions = the commons, one copy, no personal info. People/Ruby/episodes/beliefs/party = personal nodes, **private by default, shared by exception.**
- **Your experience = your private graph (full) + the world (shared) + grants received (partial).** Grants differ by direction → your feed and Carter's legitimately diverge.
- **Share the conclusion, not the substrate.** A grant is a **stop point on a provenance edge** — Carter shares a *derived capability belief*; you can't traverse to her raw biometrics.
- **"Hikes together" is a computed party:** constraints compose conservatively (most-restrictive wins); readiness gates on the *less*-recovered; **taste merges by minimizing the bigger disappointment.**
- **Permission mechanism:** grant = (grantor → grantee, category, scope, revocable). Categories at the right grain (preferences / capability / today's-readiness / full-history / location), **directional**, **context-scoped** (shared data enters *joint* planning only, never your solo feed). **Request-then-approve, not take.**
- **One shared graph, not federated** — revocation is only real if nothing was copied. Cost: colocated sensitive data (fine for a trusted household; revisit encryption/federation for strangers). **Enforce access at the query layer, never in the agent** — pre-filtered subgraph; Neo4j fine-grained security is enterprise-only → enforce in the data-access layer, every Cypher traversal parameterized with the viewer's permission set.
- **Sensitivity tiers:** T1 derived preferences + capability (partner default) · T2 episode history, today's readiness · T3 raw biometric archive, live precise location (locked). "Hikes together" runs on T1 → the safe default already works.

## 12. Emergent commons — passive crowdsourcing (future state) ✅
- **Decouple contribution from signal.** Strip identity at the source: the fact joins the commons, the person stays home. **Passive aggregate is *more* honest than reviews.** Privacy and quality point the same way.
- **Nearly free:** the passive watch-memory forked to a second write — your private overlay + a de-identified twin to the commons.
- **A third data layer:** shared world (map) · private overlays · **emergent commons** (statistical trail properties from many anonymized experiences) — slow derived data, lives **in the graph** on shared nodes.
- **Orthogonal to person-sharing.** Carter can contribute anonymously while sharing nothing with you. Network effect *without* the social network.
- **Produces (aggregate = behavior, only knowable from many traversals):** empirical pace conditioned on capability (beats Naismith) · effort topology (where people slow/stop) · de-facto season from *absence* · crowding/solitude by time · heat-exposure sections. *Skip:* scenery/subjective (reviews again), noisy reroute detection, sparse completion rates.
- **Privacy mechanism (own consent, separate from grants):** sever person→observation link on write · trim track endpoints (the re-ID vector) · **k-anonymity threshold** (also protects solo trips; also = the confidence floor) · share a *capability band* computed contributor-side, never raw · differential-privacy noise = principled endpoint. Caveat: selection bias remains (frequent watch-owners ≠ everyone) — less biased than reviews, not unbiased.
- **Build now:** *only* the forked write (de-identified, endpoint-trimmed observation to a commons store). Accretes from day one, dormant until volume.

---

# PART IV — BUILD FOUNDATIONS

## 13. Identity, auth & anonymous value 🔶
- **The auth boundary = the graph's shared/private boundary.** The shared world needs no identity; the private overlay needs auth. This falls straight out of §11.
- **Anonymous (no sign-in):** the corpus + live verification + a session-local cold-start calibration. You can browse a curated "near me this weekend" feed with zero account — this *is* the n=0 product. ✅ a real goal.
- **Signed-in:** persistent memory, watch data, party/sharing, commons contribution — anything touching your private graph.
- **Identity model:** a **household of individual members.** Each member = own login + own watch connections + own private overlay + own grants. Ruby is a non-account dependent node under Josh. So auth is multi-account even in early *real* use (Carter), though v0 can run single-user/local with no auth at all.
- ❓ Auth mechanism when needed: managed provider (Supabase Auth / Clerk / Auth0) vs. roll-your-own. 🔶 managed — don't hand-build auth.

## 14. Storage & security 🔶
- **Graph store:** Neo4j (local Community v0 → self-hosted on a VPS or managed Aura when always-on). The graph holds the sensitive personal overlay → treat as the crown jewels.
- **Secrets:** watch credentials (Garmin login is sensitive!) and API keys → a real secrets manager / encrypted store, never in the repo or plaintext config. ❗ This is security-critical from the first commit.
- **Encryption:** at rest for the personal/biometric data; in transit everywhere. ❓ per-owner encryption deferred until strangers (noted in §11).
- **Access control:** enforced at the **query/data-access layer**, never the agent (§11) — and covered by tests (§17).
- **Retention & deletion:** a real policy — right-to-delete for a member's private graph, and a deletion path for commons contributions (harder once aggregated → another reason for k-gating + capability-bands so individual contributions aren't recoverable). ❓ retention windows per data type.
- **Backup/recovery:** the episodic memory is irreplaceable personal history → scheduled backups of the graph. ❓ cadence + where.

## 15. Web app vs native 🔶
**Key realization: because we pull watch data server-side (from vendor clouds), a web app loses almost nothing on watch sync.** The deep data (Body Battery, training readiness) lives only in Garmin Connect, which we read on the backend regardless — *not* in HealthKit. So native's on-device HealthKit access only buys the shallow steps/HR/sleep subset we'd already have.
- **Native iOS (SwiftUI) advantages that remain:** reliable push (APNs), background location/geofencing for location-aware origin, on-trail offline maps, marginal HealthKit additions.
- **Web/PWA advantages:** fastest iteration on the feed + all orchestration (which is backend anyway); runs on your phone now; iOS 16.4+ supports web push for installed PWAs.
- 🔶 **Web/PWA first** (the watch-sync penalty is minimal), **native iOS later** as the real home for push reliability, background location, and on-trail use. Front-end shell is the *last* decision, not the first.

## 16. Infrastructure, repo, automation, cost 🔶
- **Repo:** 🔶 monorepo — ingestion, orchestration, graph schema + migrations, API, frontend, evals.
- **Infra path:** local-first v0 (Neo4j + processes on your machine) → small cloud footprint when always-on is needed (polling, push, Carter's access): a VPS/app host + Neo4j (Aura or self-hosted) + secrets manager + CI.
- **CI/CD:** ❓ but plan for it — tests on every change, the eval harness runnable in CI (§17).
- **Automation jobs:** scheduled ingestion; monthly corpus refresh; always-on poller (later); eval runs on change/schedule; backups.
- **Cost model — LLM tokens dominate; everything else is cheap.** Per session = Scout + Verifier (×K shortlist candidates, each maybe several tool calls) + Curator → many calls. **Levers:** cache (don't re-verify unchanged conditions within a TTL), shortlist caps (verify top-K only — already architected), **model tiering** (cheap model for extraction/ranking, stronger only for judgment). Other costs: NWS/USGS/FIRMS/AirNow/RIDB all free; routing free if self-hosted (OSRM/Valhalla) vs. paid commercial; Neo4j free local / cheap hosted; poller VPS ~$5–10/mo. ❓ a real cost-per-active-session budget once token volume is measured (best answered by a spike, not estimation).

## 17. Testing & data hygiene 🔶
- **Test types:** unit (extractors, taggers, conflation mergers) · integration (API adapters with mocked responses + handling for outages/rate limits, e.g. RIDB 50/min) · **eval-as-test** (the truthfulness harness on golden trips — runnable in CI) · **data-quality checks** (conflation correctness, dedup, schema validation on ingest) · **security/privacy tests** (does the access layer *ever* emit ungranted nodes? does the commons write *ever* retain a person link? does endpoint-trimming actually fire?) — these protect the two hardest promises and must be explicit.
- **Data hygiene on ingest:** validate + drop malformed, flag incomplete (recall RIDB blank coords) · dedup/conflation · normalize (units, naming) · track freshness (feeds the confidence model) · provenance integrity (every fact has a source) · endpoint-trim for the commons (hygiene + privacy in one).
- **Eval ground truth:** ❓ where do known-outcome trips come from to score truthfulness? Bootstrap from your own logged/watch trips; this is the first eval-set question.

## 18. Legal, licensing & data-source risk ❓→🔶
- **OSM is ODbL** — a share-alike license on derived *databases*. For a personal/household tool, fine; for a public product with a derived commons, this carries attribution and possible share-alike obligations on the database layer. ❗ Define how OSM-derived data is stored/served before the commons goes public. NWS/USGS/USFS/NPS are **public domain** (clean); Recreation.gov has its own terms.
- **Garmin community library is unofficial** — arguably against Garmin's ToS. Fine for personal use; a real risk if this ever becomes a multi-user product (Coros's official MCP is clean by contrast). 🔶 keep Garmin access swappable so an official path can replace it.
- **Others' data & crowd consent:** Carter's onboarding needs real consent; commons contribution needs its own explicit opt-in (§12). Tie to retention/deletion (§14).

---

# PART V — EXPERIENCE

## 19. UX surfaces & core loops ❓ (largely undesigned — flagged)
The thing we've barely touched. Surfaces to design:
1. **First-run / onboarding** — cold-start calibration (the one bit of active input: drive tolerance, effort, dog, what you're after) · optional watch connect · optional sign-in · **the anonymous path** (skip all, just browse).
2. **The feed** — the calm curated scroll: card anatomy (trail, the verified facts phrased to their confidence, the *why-it's-here* rationale), how filters appear (readiness, party, origin/radius, effort/type), empty/sparse states.
3. **Trail detail** — sourced facts, map, emergent/crowd data when present, confidence/staleness indicators, "verify before you go" flags.
4. **Outcome card** — reflect-back + ≤2 taps (designed, §10).
5. **Belief store** — "what I've learned about you," with the trips behind it; edit/prune. Doubles as the sharing dashboard.
6. **Sharing/grants** — request/approve, category toggles, tiers, revoke.
7. **Connections** — watch link status, re-auth.
8. **Origin/location control** — set/override starting point.
9. **Party setup** — who's coming (Josh/Carter/Ruby), composing constraints.

**Core loops:** the *daily glance* (open → curated feed → maybe detail → go) · the *post-hike nod* (push/next-open → outcome card) · the *periodic tend* (review beliefs, adjust sharing).

**The signature design problem (Josh's to own):** what a *calm, anti-engagement* trail feed feels like — legible honesty (showing confidence + sources without clutter), "what's good this weekend" over endless scroll. A real stance, not a default.

## 20. Design system ❓→🔶→✅ *(stack ratified 2026-06 — contract: `docs/research/design-system-v0.1.md`; prototype: `docs/research/home-curation-prototype-spec-v0.3.md`)*
- Josh's actual domain — **token-first**, because web-then-native means the same tokens express in both web and **SwiftUI (native)** — design tokens as the single source of truth (literally his Capital One world). Tokens authored once in **W3C DTCG JSON → Style Dictionary → web (CSS custom properties) + SwiftUI later**; no platform hand-edits values, three one-directional layers (component → semantic → primitive).
- ✅ **Web stack (ratified — supersedes the earlier shadcn/Radix/Tailwind sketch below):** **no Tailwind, no shadcn/Radix.** Behavior + accessibility via **React Aria**; styling via **vanilla-extract** (Phase 2); **owned** components (authored, not vendored), documented in **Storybook**. *Why the change:* an owned, token-driven, cross-platform system is the portfolio artifact and the calm-utility aesthetic's actual requirement; a generic Tailwind/shadcn theme is speed at the cost of ownership and the SwiftUI path. The matte cartographic system (glassmorphism removed) already ships in `frontend/src/styles.css` consuming only semantic tokens.
- ~~🔶 Web: shadcn/ui + Radix + Tailwind for speed and themeability~~ — **superseded** (placeholder before the contract was ratified).
- The system encodes the **honesty primitives** as first-class, token-backed UI states — confidence, staleness, and "verify before you go" render consistently from semantic `signal.*` tokens, never per-screen improvisation. (Operationalized in `design-system-v0.1.md` §2/§3; the Curator never renders raw personal data verbatim — only its effect.)

---

# PART VI — PLAN

## 21. Decisions locked ✅
Personal hiking planner (not work-adjacent/game) · calm curated **feed**, not search, a utility · four-layer architecture (corpus + ranking + JIT verification + feed) · **bulk-ingest, not crawl**; open data only; East Coast first · Scout/Verifier/Curator + platform console · source-or-silence; hard/soft split · **Neo4j property graph**; slow in-graph, fast fetched · **origin as runtime parameter**, location-aware · provenance + confidence + timestamp on every belief; party-level modeling · watch split live-readiness (now a **filter**) vs. capability; capability ≠ preference; enrichment never dependency; built watch-free first · Garmin community lib/MCP, Coros official MCP, FIT universal; never Strava API · multiplayer: one shared graph, **private-by-default** overlays, grants directional/scoped/revocable, **access enforced at the query layer** · commons: **fork the FIT write now**, aggregate at volume; contribution consent separate from sharing · **confidence as one cross-cutting property** (floor/presentation/safety-flag, never penalize ranking; k = the floor) · **auth boundary = shared/private boundary**; anonymous value is a goal; household/multi-account identity · local-first, legible, editable belief store as correction + sharing surface · no model training · **web/PWA first, native iOS later.**

## 22. Phasing 🔶
- **Phase 0 — spine (single-user, local, no auth):** one East-Coast region ingest · minimal Neo4j (canonical trails + provenance, stub profile) · origin param + device-location default · Verifier JIT overlay (weather + drive time + dog/trail facts, source-stamped) · a basic feed · the truthfulness eval. *Plus the cheap forked-write stub for the commons.* No watch, memory, sharing.
- **Phase 1 — personal intelligence (you):** memory (episodic + semantic beliefs) · confidence model · Garmin ingestion · readiness filter · outcome card · belief-store UI.
- **Phase 2 — multiplayer:** managed auth + household/multi-account · Carter onboarding · grant/sharing system · party planning · access-at-query-layer enforcement + privacy tests. *Requires always-on infra.*
- **Phase 3 — commons:** switch on aggregation at volume · k-gating · pace calibration · emergent attributes.
- **Phase 4 — native + polish:** SwiftUI app · push reliability · background location · on-trail offline · design-system maturation.
- **Cross-cutting from day one:** the forked write, the access-layer discipline (build it right early so the boundary can move), data hygiene + the security/privacy tests, secrets management.

## 23. What truly gates code vs. what can stay provisional (honest counsel)
*Against "define everything first" — some foundations are costly to change; the surface is cheap to change and you learn more by building it.*
- **Must be rigorous before code (expensive to retrofit):** the graph schema's core shape · the **access-control-at-query-layer** pattern (security — dangerous to bolt on later) · the shared/private split · the provenance + confidence model (threads everything) · the commons forked-write + de-identification (privacy doesn't retrofit) · secrets handling.
- **Can stay provisional, learn by building:** exact UX + flows · design-system specifics · web-vs-native (start web) · routing provider · hosting specifics · naming · the precise cost budget.
- **Best answered by a tiny spike, not more docs:** **conflation** (merging OSM/USGS/USFS into canonical trails — the meatiest unknown) and the **real LLM cost-per-session** (measure a few real runs rather than estimate). Both de-risk the big design more than discussion can.

## 24. Open threads — still to resolve
Watch-sync fine details (mostly settled, §10) · schemas (belief entry; episode→semantic promotion; grant relationship; provenance-stop semantics; FIT-to-episode extractor + capability-vs-preference tagging) · **eval methodology** (scenarios, N-run pass rates, regression, LLM-judge for the soft half — hardest, undesigned) · party preference-merging algorithm ("minimize the bigger disappointment") · commons aggregation (k-threshold value, capability-band computation, the pace model) · orchestration substrate (Claude API + framework? Claude Code? MCP-native?) · cold-start calibration design · UX flows + design system (Part V) · auth provider choice · cost budget (spike) · retention windows · backup cadence · novelty mechanism, decay model, naming.
*(Resolved by Stage 1 — see §27: routing provider; streamflow API; conflation approach; OSM dog-rule exclusion; ODbL handling for personal vs. public commons.)*

## 25. Roads not taken (so we don't re-litigate)
Fine-tuning open UI-gen models + verifiable design-system reward (frontier products own it; repair-loop dissolved the need to train; needs GPUs — *the verifier-with-two-halves idea survived and ported here*) · game domains (DM/RPG, whodunit, AI town) · work-adjacent concierges (loan/benefits/claims) · AllTrails-style social condition reports (→ passive anonymized commons) · pre-seeding with the 27-destination workbook (want real ingest) · parallel variants (garden, kitchen — parked spin-offs).

## 26. Proposed next step
*Superseded — Phase-0 and Phase-1 builds are complete. The Phase-0 vertical slice shipped against the Shenandoah NP + GW & Jefferson NF pilot region (the source-stack resolutions it rested on are in §27). Live status, open risks (incl. the still-unmeasured Stage-4 cost spike, R5), and the next-work queue are tracked in **`docs/process/roadmap.md`** — the status SSOT.*

## 27. Stage 1 resolutions ✅ *(June 19, 2026 — full catalog: `docs/research/stage-1-data-sources.md`)*
- **Source stack (Phase-0 pilot):** OSM = geometry **spine** (Geofabrik extract); USFS NFS Trails + NPS Public Trails = authoritative federal overlay; PAD-US 4.1 = land-manager/public-access base; USGS 3DEP = elevation/grade; RIDB = permit/campsite *requirements*; state/county open data (Fairfax) for local trails. Federal data covers federal land only → OSM carries the breadth.
- **Routing provider:** ✅ **Valhalla, self-hosted** (native time-based isochrones for "hikes within N min of origin"; OSM-based, MIT). OSRM is the simpler fallback. *(resolves §24 "routing provider")*
- **Streamflow API:** ✅ build on the **new USGS Water OGC API** (`api.waterdata.usgs.gov/ogcapi`) — the legacy `waterservices.usgs.gov` decommissions ~Q1 2027.
- **Conflation:** ✅ **no shared cross-source trail ID** (GNIS dropped trails in 2021) → match on **name + ref + geometry with human review**. Adopt **OSM Merge** (OSM-US, GPLv3) as the starting tool; verdict = tractable for a pilot, not research-grade. Canonical-route node + `SAME_AS` provenance edges + separate segment layer (validates §6). Never auto-merge conflicting access/usage attrs — surface per-source.
- **OSM dog/leash rules:** ✅ **excluded as a source of truth** (sparse, unreliable in the US) — defer to the land manager. Sharpens source-or-silence.
- **ODbL handling:** ✅ **personal/household use is unencumbered** (share-alike triggers on *public conveyance* of a Derivative Database). For a **public commons**, the conflated OSM+gov database is a Derivative Database → either accept ODbL on it, or architect a **Collective Database** (OSM layer kept separate/non-cross-referencing) or expose only **Produced Works** (rendered output). **This is a Stage-2 schema constraint.** *(resolves part of §18)*
- **Encumbered / off-limits sources:** VA DCR Conservation Lands = no redistribution (personal only); all proprietary apps (Strava, AllTrails, Hiking Project/onX, Gaia, Komoot) = no lawful AI/programmatic path → confirms the open-data-only stance (§25).
- **Secrets to hold (T1):** keys for NPS, EPA AirNow, NASA FIRMS, RIDB, Anthropic (+ Garmin login later); NWS keyless (User-Agent), USGS keyless (token recommended).

## 28. Stage 2 schema decisions ✅ *(June 19, 2026 — design: `docs/research/stage-2-schema.md`; artifact: `graph/schema.cypher`)*
- **World-layer taxonomy:** `:Area` (destination) → `:CanonicalTrail` (named route = unit of recommendation) → `:Segment` (conflation unit) → `:Junction`/`:Trailhead`; `:SourceRecord` as the provenance anchor. Composed loops = a named `:CanonicalTrail` for v0; `:Route` deferred to Stage 5+.
- **Provenance (decision 1):** ✅ **facts on `:SourceRecord` + `SAME_AS` edges + computed best-view** on the canonical node (records the winning source per attribute). "Which source said what" = a traversal. OSM-derived facts stay isolated on OSM SourceRecords → ODbL-separable (Collective-Database escape hatch is free).
- **Geometry (decision 2):** ✅ **computed at ingest in Python (Shapely/GeoPandas/GDAL); Neo4j stores graph + representative `Point` + line `geom_wkt`. No standing PostGIS in v0** → single-database thin v0.
- **Confidence (decision 4):** ✅ **computed on read** from stored inputs (freshness timestamp · authority-tier lookup · corroboration count); never stored stale, never penalizes rank. k-anonymity threshold = the confidence floor.
- **Access control (T2):** ✅ `owner_id` property (decision 5) + a single **`scopedQuery(viewer)`** wrapper as the only path to owned data; world/commons nodes unowned → public (the anonymous product). Property-based test asserts no ungranted node ever returns.
- **Commons (decision 6):** ✅ same Neo4j DB, severed person→observation link; `:CommonsObservation` label reserved, guaranteed never edge-linked to a `:Person`.
- **Live data:** ✅ never persisted as nodes — graph stores resolution keys (`nws_grid_ref`, `usgs_site_id` + distance, `ridb_*_id`); Verifier overlays JIT.
- **Versioning:** `ingest_version` on every SourceRecord/`SAME_AS` (idempotent monthly refresh by `(source, source_id)`); `:Meta.schema_version`; forward-only Cypher migrations in `graph/migrations/`.
- **Deferred to later stages (anti-schema-project discipline):** belief-entry schema + episode→semantic promotion + decay (Stage 5); grant tuple semantics (Stage 8); commons aggregation math + k-value + capability bands (Stage 9); conflation match-score thresholds tuned empirically (Stage 3).

## 29. Stage 4 engine + cost decisions ✅ *(June 19, 2026 — design: `docs/research/stage-4-engine-and-cost.md`)*
- **Orchestration substrate:** ✅ **Claude API via the official Anthropic SDK (Python), code-orchestrated workflow — NOT an autonomous agent and NOT a heavyweight framework** (LangGraph/CrewAI). Scout→Verifier→Curator is a fixed, authored DAG (design/runtime separation). *(resolves §24 "orchestration substrate")*
- **MCP scope:** ✅ deferred to interactive moments only (future "ask the planner" chat; agent-facing watch tools — Coros/Garmin). **Phase-0 JIT Verifier + batch ingestion use direct HTTP adapters, not MCP.**
- **Model providers & tiering:** ✅ **provider-agnostic, local-first.** A thin provider seam (`extract`/`normalize`/`judge`) with two adapters: **local/self-hosted via an OpenAI-compatible endpoint (Ollama/vLLM/LM Studio) as the default**, and the **Anthropic SDK (Claude) hot-swappable as the quality/cost/latency yardstick.** Tier by job (mechanical → small/local; judgment → strongest available). **Route by data sensitivity** (mirrors §13's shared/private boundary): cloud OK for the anonymous world+conditions layer, **local for anything touching the private overlay** so personal data never leaves the machine. Provider + model + tier all in config, never hardcoded; provider-specific optimizations (Claude prompt caching/adaptive thinking; local quantization) live behind the seam, not flattened. We own the tool loop, so neither adapter depends on a provider's tool-runner. *(Consistent with #9 "pure orchestration, no training" and the §1/§25 no-GPU-training stance — inference is far lighter than the abandoned fine-tune branch.)*
- **Engine shape:** Scout = scoped Cypher (via `scopedQuery(viewer)`, honoring #4) + optional intent parse, capped to top-K. Verifier = per-source adapters; **source-or-silence enforced in deterministic code** (the LLM phrases verified facts, never produces them); live data JIT, never persisted (#3); per-source TTL caching. Curator = hard constraint filters (guardrails) + Opus-tier taste ranking that **never lets confidence penalize rank** (#2).
- **Live adapters:** NWS, USGS Water OGC API, FIRMS, AirNow, RIDB, Valhalla — each `(loc)→verified fact|None`, mocked-response integration tests, degrade-and-disclose on outage/rate-limit.
- **Truthfulness eval (T4):** Opus-tier LLM-judge that every surfaced fact has source+timestamp and matches captured adapter output, + deterministic guardrail checks; **N-runs-per-scenario pass rate** (stochastic); golden set bootstrapped from known Shenandoah/GWJ trips; runnable in CI.
- **Cost:** two shapes by provider — **local** = ~$0 marginal tokens, traded for hardware + latency; **cloud (yardstick)** ≈ **$0.10–0.18/uncached session**. Levers = shortlist cap K · prompt caching (cloud) / KV reuse (local) · provider+tier routing · condition-TTL caching. ❓ **real budget + provider default pending the spike, now a bake-off** (run the real flow against the real corpus and measure local vs. cloud through the same eval on quality/cost/latency — do not ship off the estimate). *(the remaining §23 "spike": cost-per-session)*
- **◆ Phase-0 (Stages 1–4) — DESIGNED ✅ and BUILT ✅.** The end-to-end verified-synthesis slice shipped; only the real cost-per-session spike (R5) remains open. Live status: `docs/process/roadmap.md`.

## 30. Stage 5 — Personalization decisions ✅ *(June 23, 2026 — design: `docs/research/stage-5-personalization.md`)*
- **Belief store schema:** ✅ Five personal-overlay node types: `:Episode` (completed trip), `:Outcome` (post-hike reflect-back, separate node), `:Belief` (semantic belief with provenance), `:PhysicalProfile` (capability summary), `:PartyProfile` (party-specific inferences). All carry `owner_id`; all gated by `scopedQuery(viewer)`.
- **Belief axes:** ✅ Four values: `capability` / `preference` / `taste` / `constraint`. Watch/FIT-derived data may only populate `capability` — **capability ≠ preference** is enforced at the schema level, not just at query time (Rule #7).
- **Belief type:** ✅ `stated` (user-affirmed, never decays by default) vs. `inferred` (behavioral/watch-derived; always labeled provisional until confirmed). An inference never poses as a stated fact (Rule #7).
- **Episode→semantic promotion:** ✅ Capability beliefs updated via EWMA (α=0.3) on every FIT-parsed episode. Preference/taste beliefs require N=3 corroborating episodes above threshold; below N=3, belief exists at provisional confidence (<0.4) and is not injected into Curator context. 🔶 N=3 floor is a starting point — tune against real episode volume.
- **Decay model:** ✅ Computed on read (same pattern as confidence — store inputs, compute at read time). Half-lives: capability 180d, preference 90d, taste 120d, constraint=never. 🔶 Validate half-lives against real data before treating as settled.
- **Context assembly:** ✅ At query time: top-20 active beliefs by recency (above decayed confidence floor) + relevant episodes (same trail or area as candidates, last 18 months, cap 10). Raw biometric data, full episode history, and provisional beliefs are never injected into the model context.
- **Watch data integration:** ✅ Live readiness (Body Battery / HRV) enters the readiness filter only — never the belief store. Raw HR time series and biometric archive are NOT held in Neo4j. Belief store holds only capability signals extracted at ingest. Every watch-enriched ranking carries a disclosure tag (Rule #6).
- **Privacy tiers for Stage-5 data:** ✅ T1 = derived capability/preference beliefs (grantable to household members); T2 = episode history + outcomes (grantable explicitly, context-scoped to joint planning); T3 = raw biometrics (not stored in the graph, therefore not grantable). Grant enforcement deferred to Stage 8.
- **Commons write for episodes:** ✅ **Built (Epic 010, 2026-06-24)** *(on Epic 011's scoped-write seam).* Forked write on episode creation: person→observation link severed; GPS track endpoint-trimmed (250m strip, trim threshold still tunable); raw pace bucketed into 4 capability bands before commons write. Private episode retains full data. Post-aggregation deletion of individual contribution is not recoverable — disclosed in consent.
- **Memory eval:** 🔶 A thin memory-on vs. memory-off harness runs alongside the Stage-4 truthfulness eval; the deep stochastic methodology is Stage 7.
- **`:Route` node (custom itineraries):** ✅ Deferred — Stage 5 uses `:CanonicalTrail` as the episode target; `:Route` added only when party planning needs custom itineraries (consistent with Stage 2 §2).
- **◆ Phase-1 personalization — DESIGNED ✅ and BUILT ✅** (Epics 001–005, 010–015): belief store, promotion, decay, context assembly, watch discipline, and privacy tiers shipped. Live status: `docs/process/roadmap.md`.

## 31. Stage 6 — Watch Integration decisions ✅ *(June 23, 2026 — design: `docs/research/stage-6-watch-integration.md`)*
- **FIT parser:** ✅ `fitdecode` as primary (compressed-timestamp support, active maintenance); `fitparse` as fallback on parse failure.
- **Garmin access:** 🔶 `python-garminconnect` (SSO session auth, unofficial); re-auth on expiry; adapter interface keeps it swappable for a future official path. Monitor for Garmin auth breakage.
- **Coros access:** ✅ Official MCP server (`@coros/mcp-server`) for interactive agent queries; direct HTTP to `open.coros.com` for batch ingestion. Coros MCP in `.mcp.json`; Garmin is not.
- **Ingestion trigger:** ✅ Scheduled Python job (`scripts/watch_sync.py`), cron every 6 hours. Not MCP. Idempotent; safe to run more frequently. Always-on poller deferred to Stage 8 / always-on infra decision.
- **Deduplication:** ✅ `Episode.watch_activity_id` keyed as `"garmin:{id}"` or `"coros:{id}"`; MERGE is the idempotent write gate.
- **pace_on_grade:** ✅ Naismith approximation `(distance_m + ascent_m × 10) / 1000` km; no LLM call. EWMA α=0.3 (per S5-6 — tune in spike).
- **Activity→trail matching:** 🔶 Shapely GPS buffer-intersect (100m buffer, ≥0.7 overlap) primary; `rapidfuzz` title-name match (≥80) fallback; `trail_id=null` on no match. Thresholds need empirical tuning on first real data.
- **Party detection:** ✅ Manual toggle on outcome card ("Was Ruby with you?"); no automated proximity detection in Phase 1. Ruby is a dependent, not an account.
- **Belief update trigger:** ✅ `asyncio.Queue` drained by worker coroutine; never blocks ingest path; queue rebuilt from unprocessed Episodes on restart.
- **heat_response:** 🔶 NWS archived temp at episode date + avg_hr from FIT session; 2 heat-hit episodes before belief promotion; degrades gracefully if NWS unavailable for that date.
- **Sensitivity routing:** ✅ All LLM calls in ingest path route to local provider via `provider_registry.route(sensitivity="private")`; enforced at job entrypoint; cloud models never see raw FIT/HR/GPS data.
- **Commons fork:** ✅ **Built (Epic 010, 2026-06-24).** `CommonsObservation` written in same transaction as Episode; person link severed at write; 250m endpoint trim; raw pace substituted with 4-band capability label before commons write.
- **MCP write discipline:** ✅ MCP tools (Coros) never write Episode nodes — they are read-only in interactive context; all Episode writes are owned by the scheduled batch job.
- **◆ Phase-1 (Stages 5–6) — DESIGNED ✅ and BUILT ✅.** Personalization schema + watch ingestion pipeline shipped (device seam = Epic 004, incl. the in-process Garmin poller). Remaining: always-on host (R7) + readiness filter (Epic 007). Live status: `docs/process/roadmap.md`.

---

# PART VII — BUILD DECISIONS (folded from the build lane)

*§32–§40 were folded on 2026-06-26 from the (now archived) `docs/research/archive/decision-log-additions-proposed.md`, which retains the full forensic detail. They record decisions made during the Phase-0/1 build.*

## 32. Stage 3 — Ingestion pipeline (build) ✅ *(June 23, 2026 — code: `ingestion/pipeline.py`, `ingestion/fetch/*`, `ingestion/conflate/match.py`)*
- **Pipeline shape:** ✅ a linear, idempotent **fetch → transform → hygiene → conflate → load** run, one CLI entry (`python -m ingestion.pipeline --region <id> [--dry-run] [--source ...]`). Region = a `regions/{id}.geojson` polygon carrying the `bbox` and `ingest_version`. *Why:* a monthly batch job, not a service (mirrors §8); `--dry-run` lets conflation be inspected before any Neo4j write.
- **Per-source fetchers, isolated:** ✅ OSM via Overpass (keyless, the geometry **spine** per §27); NPS via public ArcGIS FeatureServer (keyless); USFS via **local bulk GeoJSON** (not a live call — see §34). Each fetcher returns a uniform `Feature(name, geom, source, ref)` and degrades to `[]` on non-200 so one source's outage never aborts the run.
- **OSM segment consolidation precedes conflation:** ✅ OSM encodes a continuous trail as many disconnected `way` segments; conflating ~200 m fragments produced score=100 / overlap≈0.02 against full-length agency polylines. Fix = **merge all OSM ways sharing a normalized name** (`unary_union`) into one `Feature` before matching. 🔶 Grouping is by normalized name **within the bbox only**; cross-park name collisions are an accepted pilot-scale risk.
- **Idempotent writes:** ✅ all Neo4j writes are `MERGE`, keyed on synthetic IDs; `ingest_version = "{region}-{props.version}"` stamped on every `CanonicalTrail` / `SourceRecord` / `SAME_AS` (honors §28 versioning).
- **Collision-safe ID generation:** ✅ name-derived `canonical_id` / `sr_uid` slugs append a short content hash when the slug would truncate (two `ref=None` trails sharing a 40-char prefix would otherwise `MERGE` onto one node and corrupt provenance — §38 self-review fix).
- **Hygiene = drop-only-when-undisplayable:** ✅ a feature is skipped (`skipped_hygiene`) only when it has **no name AND no ref**; a named-but-unmatched OSM trail is first-class (§3) and loads as OSM-primary.

## 33. Conflation thresholds — tuned against the real run ✅ *(June 23, 2026 — review: `docs/research/archive/conflation-review-2026-06.md`)*
- **First real conflation:** OSM (2,873 raw ways) × NPS (758) × USFS (459) → 752 auto-accept / 466 review before consolidation. **~90% of "review" cases were the OSM fragmentation artifact, not wrong matches** — the empirical answer to the §23/§24 conflation spike: the meatiest unknown is **tractable**, the lever is geometry repair (§32), not loosening thresholds. Consolidation cuts the total `CanonicalTrail` count to **~800–1,000** (the pre-consolidation ~2,899 **total** of OSM-primary plus NPS/USFS-primary canonicals — not the 2,873 raw OSM ways, which sit close enough to read as a typo).
- **Thresholds held, not loosened:** ✅ keep `name_auto=85`, `overlap_auto=0.5`, `hausdorff_auto_m=80` (resolves §28's "thresholds tuned empirically — Stage 3").
- **Genuine review classes documented:** road-vs-trail same-feature (🔶 auto-accept, NPS name wins — tier-1 authority §27/§28); spur-vs-main (✅ do **not** auto-merge — distinct features, honors §28); USFS ALL-CAPS truncation (✅ `normalize_name()` catches most; 🔶 strip trailing ALL-CAPS suffix in the USFS fetcher).
- **Match provenance recorded:** ✅ `SAME_AS` edges carry `match_method` + `match_score` — "which source said what, how confidently joined" stays a traversal (§6, §28).

## 34. USFS access fallback + live-API field verification ✅ *(June 23, 2026 — `docs/research/archive/api-verification-2026-06.md`)*
- **USFS EDW ArcGIS REST is not publicly reachable:** ✅ returns **403** without USFS network credentials. **Decision:** USFS ingests from the **public bulk shapefile** (`S_USA.TrailNFS_Publish.zip`) converted to GeoJSON via `ogr2ogr`, file-based — USFS is slow/structural corpus data (§4), so periodic bulk download is the right shape. Updates §27's USFS sourcing.
- **Live field names verified against real endpoints:** NWS `api.weather.gov` two-hop `/points` → forecast (keyless, User-Agent); **USGS Water OGC** `monitoring-locations` works, field names corrected to `monitoring_location_name`/`_number`; 🔶 OGC discharge returned 400 → **bridge on legacy `waterservices.usgs.gov/nwis/iv`** until documented, migrate before the ~Q1 2027 legacy decommission. ⚠️ the bridged path's `-999999` no-data sentinel passes `float()` (§38 residue) — guard before treating clean. NPS Trails ArcGIS ❓ verify on first full run.

## 35. Schema v0.2.0 — personal-overlay additions (applied) ✅ *(June 23, 2026 — `graph/schema.cypher`; design: §30, §31)*
- **Schema bumped 0.1.0 → 0.2.0, additive-only:** ✅ the world-layer v0.1 schema (§28) is unchanged; the personal overlay is new constraints/indexes layered on (§28 forward-only migration).
- ⚠️ **`:Meta` version-stamp residue (build-time defect, June 2026):** 🔶 `schema.cypher` set `0.1.0` `ON CREATE` and `0.2.0` only `ON MATCH`, so a fresh DB reports `0.1.0` until a second apply. *Fix:* set `0.2.0` on both branches. *(Logged as build-time residue; current status tracked via roadmap/CI.)*
- **Personal-overlay constraints + indexes:** ✅ uniqueness on the five Stage-5 node ids + `:Dependent` (Ruby, §13); access-pattern indexes on `owner_id` / `(owner_id, subject_id)`. **Community-Edition-safe** (single-property uniqueness; composite keys as synthetic strings).
- **Live data still absent from the graph:** ✅ no readiness/biometric node types; only resolution keys + derived capability signals persist (§28, §30 T3, Rule #3).

## 36. Belief-update pipeline — Epic 001 (built) ✅ *(June 23, 2026 — code: `orchestration/belief_update.py`, `ingestion/ingest_episode.py`; epic: `docs/epics/epic-001-belief-update-pipeline.md`)*
- **Queue-decoupled from ingest:** ✅ `create_episode()` enqueues an `UpdateTask`; a worker drains it — the belief update never blocks the Episode write (Rule #6). 🔶 the `asyncio.Queue` worker loop (§31) lands with the full `watch_sync.py` job.
- **Capability update math:** ✅ `pace_on_grade` via **EWMA α=0.3** (§30); `max_distance_m`/`max_ascent_m` as empirical maxima (lower/`None` never overwrites); `episode_count` incremented.
- **Corroboration derived from edges:** ✅ `Belief.corroboration_n` computed from the `DERIVED_FROM` edge count, not a stored increment — idempotent re-drains never double-count (§6).
- **Provisional sub-floor confidence:** ✅ `corroboration_n < 3` → `confidence = 0.3` (below the 0.4 floor); `≥ 3` → `0.7`; auto-updates only ever write `type:"inferred"`, `axis:"capability"` (Rule #7; §30 capability ≠ preference). 🔶 **Scope note:** Epic 001 guarantees the sub-floor *value*; the "never injected into Curator context" *exclusion* lives in context-assembly (Epic 003, §39 — now **DONE**), so the floor-gate is now wired end-to-end.
- **Scope guard on provenance writes:** ✅ the `DERIVED_FROM` MATCH carries an `owner_id` constraint (§38 self-review fix; Rule #4).
- **Promotion threshold provisional:** 🔶 `N=3` is the §30 starting floor, to be tuned against real episode volume.

## 37. Provider seam + sensitivity routing (built) ✅ *(June 23, 2026 — code: `orchestration/providers/*`)*
- **Two adapters behind one seam:** ✅ `LocalOpenAIProvider` (OpenAI-compatible, the **default**) + `AnthropicProvider` (Claude, the hot-swappable yardstick) on a common `ModelProvider` base; provider + model from `Settings`, never hardcoded (realizes §29).
- **Role → tier mapping:** ✅ `extract`/`normalize` → `mechanical`; `judge`/`curate` → `judgment` (§16/§29 tiering by role).
- **Sensitivity routing is a hard override:** ✅ `resolve(role, …, touches_private_overlay=True)` **forces local** regardless of the tier default; raises if no local/fallback id is set (fail-loud, not silent cloud fallback) — Rule #4 / §13 / §29 made structural. `forced_local` is returned on **both** the override and the already-local branch so callers can always tell privacy routing applied.
- **Secret hygiene:** ✅ the Anthropic key is a private attribute (`_api_key`) — Rule #10 (§38 finding).

## 38. API layer + self-review hardening ✅ *(June 23, 2026 — code: `api/app.py`, `api/schemas.py`; review: `docs/research/archive/self-review-2026-06.md`)*
- **Thin FastAPI over `engine.plan()`:** ✅ `POST /plan` + `GET /health`; graph client + probes wired once at startup (`lifespan`); the per-request `Runtime` is rebuilt so **`viewer_id` varies per request** (§8). *(The outcome endpoint `POST /episode/{id}/outcome` later landed via Epic 002.)*
- **Confidence surfaces as presentation, not a score:** ✅ each feed line carries `text` + `source` + `confidence_level ∈ {stated, hedged, flagged}` — never a raw number (§7; §2 non-thing).
- **Health stats run through the scoped seam:** ✅ graph-stats go through `scoped_session("health-check")` — no access-layer bypass even for ops (Rule #4).
- **Error handling — `/plan` fails closed:** ✅ the route's own `try/except` returns a generic `"Internal error"` 500 with no detail.
- ⚠️ **Build-time residue (June 2026, logged not all-fixed):** the module-level `@app.exception_handler(Exception)` did **not** fail closed — it returned `{"detail": str(exc)}` (leak risk for errors outside the `/plan` catch); the USGS `-999999` sentinel passes `float()`; `engine.py` fell back to **origin** coords for a candidate with no `point`; `graph/load.py` extras used `isidentifier()` (permits Cypher reserved words); the §35 `:Meta` stamp. *(Residue logged so it isn't re-discovered; current status tracked via roadmap + the archived remediation reviews.)*
- **Self-review CRITICALs fixed in-code:** ✅ `curator._alerts()` `None`-guard on a partial NWS success (must degrade, not crash — §4, Rule #1); `scripts/sprint.sh` schema step fixed (`--password-stdin` had eaten the first schema line → schema never applied).

## 39. Epic-driven development process + code hygiene ✅ *(June 23, 2026 — `docs/process/development-process.md`, `docs/epics/`, CLAUDE.md dev-standards)*
- **Three-layer work unit:** ✅ **Epic** → **Story** (Given/When/Then) → **AC** (pass/fail testable); every AC gets ≥1 test, **written before the code**; tests named `test_s{story}_{ac}_{desc}`; epic status `BACKLOG → DEFINED → IN_PROGRESS → REVIEW → DONE`. Building against explicit ACs dogfoods the project's eval thesis (§1).
- **Targeted review replaces ultrareview for routine work:** ✅ a narrow per-epic self-review agent (changed files + specific rules); reserve `/code-review ultra` for phase boundaries / cross-cutting changes; every CRITICAL fixed before commit, MODERATE fixed-or-documented.
- **Atomic commits + fail-loud code standards:** ✅ one logical change per commit; imperative ≤72-char subjects with a *why* body; never commit `.env`/`data/`/commented-out code/debug `print()`/`# TODO`; **fail loudly at boundaries, degrade gracefully at the surface**; `make check` green before every commit.
- **Build order is dependency-driven, recorded as epics:** ✅ the Phase-1 build order — Epic 002 (outcome endpoint) → Epic 003 (context assembly into `engine.plan()`, ≤500-char context block, no raw biometrics) → device seam (Garmin/Coros, Epic 004) → Valhalla drive-time (Epic 013) — has **all since shipped** (§22 phasing made concrete). Live status: `docs/process/roadmap.md`.

## 40. Architecture gap-audit corrections — ALL CLOSED ✅ *(June 24, 2026 — source: `docs/research/archive/architecture-gap-audit-2026-06.md`, 6-lens cross-audit; full forensic detail in `docs/research/archive/decision-log-additions-proposed.md §40`)*
> The June-2026 gap-audit corrected the decision log against the actual tree — six CRITICAL findings of the device-seam failure class (load-bearing seams assumed-built, or rules marked ✅ the code never realized). **All six are now CLOSED**, remediated and shipped; recorded here so the corrected memory is canonical.
- **C1 — Commons forked write (Rule #8 / Thread T3)** was found unbuilt under a false ✅ → **CLOSED: built as Epic 010** (`epic-010-commons-fork-write.md`): the de-identified `:CommonsObservation` write forks inside `create_episode()`'s transaction (no `:Person` edge, writer-hash for revocation, 250 m endpoint trim, raw pace → capability band), with the structural privacy test. *(The §30/§31 + stage-6 S6-10 status glyphs are pinned to 🔶 by `tests/test_commons_doc_lint.py` AC-1.5 until that guard is retired — see PR #1 NEEDS-PM.)*
- **C2 — Owned-node WRITE path bypassed the ScopedSession choke point** → **CLOSED: Epic 011** (scoped-write seam): `ScopedSession.run_write` injects `$viewer_id` and refuses an owned-label MERGE/SET lacking an owner clause; both writers route through `graph.queries`; the fuzz test points at the write builders.
- **C3 — `viewer_id` client-supplied/unauthenticated** → **CLOSED: Epic 014 S3**: `api.app._authorize_viewer` hard-fails (403) any non-anonymous `viewer_id` lacking the configured dev-viewer secret (fail-closed when unset) on `/plan` + `/episode/{id}/outcome`; full managed auth deferred (roadmap R3).
- **C4 — Private overlay egressed to the cloud judge** → **CLOSED: Epic 014 S1/S2**: a split judge — cloud-allowed `judge` on the anonymous/no-overlay path, `personalized_judge` forced local (`touches_private_overlay=True`) whenever a non-anonymous viewer / non-empty context is in play; `tests/test_overlay_egress.py` fails if the flag is dropped.
- **C5 — Corpus sources hardcoded; the `ingestion/sources/*` seam never built** → **CLOSED: Epic 012** (CorpusSource contract + registry; OSM-as-spine a declared source property).
- **C6 — Live-data adapters hardcoded; no LiveAdapter contract** → **CLOSED: Epic 013** (`LiveAdapter` ABC + kind-keyed primary/fallback registry, TTL cache, `ValhallaAdapter` drive-time folding in Epic 005).
- **Process miss that hid C1:** the epic index tracked epics but no cross-cutting threads → **CLOSED: thread-tracker rows added to `epics/README.md`** (every T-thread now has an owner + status), so a build-now thread can't fall behind the code unwatched.

## 41. Verified hazards: show with warning, never hide ✅ *(July 1, 2026 — decided by Josh after the Extreme Heat Warning dogfood; code: `orchestration/curator.py`, `orchestration/engine.py`, `api/schemas.py`, `frontend/src/screens/cardParts.tsx`)*
- **The decision:** a trail under a **VERIFIED active hazard** (an alert carried by a live fact with source + timestamp — e.g. the NWS Extreme Heat Warning) **stays in the feed as a card wearing a prominent, source-stamped warning** (`warnings[]`: text + source + observed-at, mirroring how `lines[]` carries source/confidence). It is never hidden. Ranking is untouched — a safety flag is presentation, never a penalty (Rule #2).
- **Set-aside is reserved for the UNVERIFIABLE class** (source-or-silence, Rule #1): a failed weather probe or a failed alerts sub-call means the alert state is *unknown*, and unknown never reads as "clear" — the trail is held back **with disclosure** (cause + source), surfaced as a quiet feed-level note. Non-weather hard thresholds (hazardous AQI ≥ 201) keep their block semantics.
- **The dogfood that forced it:** `/plan` near Front Royal during the 2026-07-01 Extreme Heat Warning returned 1 card and set aside 9 trails, and the frontend rendered neither the set-aside disclosures nor card warnings — the user saw one lonely hike with no explanation. Hiding a verified hazard threw away exactly the live-synthesis value the product exists for; showing it *with the warning* is the honest behavior.
- **The Compton Gap Road anomaly, resolved:** the one surviving trail was *legitimately* clear — its probe point sits in NWS forecast zone VAZ507 ("Northern Virginia Blue Ridge"), which the warning's zone list (VAZ027–031 + WV zones, the valley floors) deliberately excludes. A verified per-point "no alert," not a false-clear. The investigation did surface a latent Rule-#1 violation, now fixed: the old guardrail collapsed `active_alerts: None` (alerts sub-call failed) into "no alerts", and a fully-failed weather probe passed a trail clean with no disclosure — both now set the trail aside as unverifiable.

## 42. Confidence fusion — weakest-link MIN + primary/aggregated source split (CDP-06) ✅ *(2026-07-14 — PRs #197 #215; code: `orchestration/confidence.py`; refines §7)*
- **The decision:** the three axes (freshness · authority · corroboration) now fuse by **weakest-link `min(a,f,c)`**, not the old weighted mean — a comfortable middle is a lie; two strong axes cannot paper over a weak third.
- **The re-tune that made "stated" reachable:** MIN alone left *every* card hedged (single-source live is corroboration-capped; slow corpus is freshness-capped). A **`source_kind` primary/aggregated** split fixes it: a single *authoritative* origin (one NWS gridpoint, USGS gauge, FIRMS satellite, NPS unit) is single-origin but not under-corroborated → it can reach **"stated"**; an *aggregated/unverified* single source (AirNow's blend; a single-provider corpus fact not yet `SAME_AS`-matched) keeps the lower baseline and must earn "stated" via real cross-provider corroboration. `for_fact()` defaults **fail-closed** to `aggregated` (an untagged source is treated as unverified). Verified live: the NWS weather line renders `stated`.
- **Unchanged:** confidence still never penalizes ranking (Rule #2, guarded by `test_rank_plan_is_confidence_invariant`); the source-or-silence floor is intact.

## 43. Trail-name search — in-graph FULLTEXT (Epic 038 / B001 Problem A); geocoder deferred ✅ *(2026-07-14 — PRs #218 #219 #221; code: `graph/queries.py`, `orchestration/scout.py`+`engine.py`, `api/app.py`, `frontend/src/screens/Home.tsx`)*
- **The decision:** the Omnibox's first capability is **trail-name search over our corpus** — a Neo4j FULLTEXT index (`trail_name_fts`) + `scout_by_name` feeding the *same* verify→present pipeline as `/plan` (via an extracted, behaviour-preserving `_plan_from_candidates`), exposed as `POST /search {query,k?}→FeedResponse`. Results are our verified curated cards, relevance-ordered, honest-empty on no match — **never a raw graph dump** (B001 discipline). Operational tail: the `trail_name_fts` index is created on Aura by hand (the API doesn't auto-apply schema).
- **Relevance (interim):** AND-semantics + length-gated fuzz + a relative-score floor so "old rag" returns just the Old Rag trails; the CoMaps `GetNameScores` scorer (S2) is the eventual graded-relevance answer.
- **Deferred, deliberately:** **Problem B place-name geocoding** (a thin swappable seam) → gated on the provider decision (**Open Decision #3** / B002); the **full unified intent line** (one box routing name vs. intent vs. place) → a separate epic. Note: `origins.ts` was never a fixed enum — origins are already config-driven + "near me" (the B001 spec corrected that premise).

## 44. Access control enforced by construction — M10 closed ✅ *(2026-07-14 — PR #216; code: `scripts/lint_owned_reads.py`, `graph/queries.py`, `graph/client.py`)*
- **The decision:** Rule #4 (every owned-label read viewer-scoped at the query/data layer) is now held **by construction — statically and at runtime**. The owned-read lint became join-aware (assembles multi-fragment Cypher before scope-checking) so all 11 interim `# noqa` markers were removed, and a runtime `assert_scoped_read` guard in `ScopedSession.run` refuses an unscoped owned-label read (explicit `allow_unscoped_owned_read=True` bypass, test-infra only). Fixed a hidden unscoped Episode read in `watch_sync.py` en route.

## 45. Elevation truth — seam-gain + bbox-edge coverage fixes ✅ *(2026-07-14 — PRs #214 #217; code: `ingestion/elevation.py`, `scripts/fetch_dem.py`, `ingestion/pipeline.py`)*
- **The decisions:** (1) multi-part MultiLineString **seam bridges no longer credit their elevation jump to gain/loss** (they were inflating `estimated_duration` 2–5× on 12 trails); (2) the DEM raster is **clipped with a 0.05° (~5.5 km) buffer** beyond the region bbox so boundary-crossing trails keep coverage — the real cause of the "21 null profiles", falsified against live data (an earlier short-trail-brittleness guess was wrong); (3) the coverage gate counts **distinct** canonical_ids. Re-ingested PWF/Douthat/Shenandoah/St-John to Aura → 99.1% elevation coverage.
- **Chose NOT to mass-re-ingest** all regions for the 0.9% residual (23 nulls, thinly spread); the frontend renders a null-elevation trail's missing facts honestly instead, and the buffer clears each region on its next ingest.

## 46. UX direction — "The Confident Call + Quiet Context" 🔶 *(2026-07-14 — design: `docs/research/ux-vision-2026-07.md` (#222); brief: `docs/research/ux-vision-brief.md`; adopting incrementally)*
- **Recommended direction (confirm as we build):** from a live UX review + a divergent design spike (Gemini via Antigravity), the app moves from "a feed of ten near-equal verdict cards" toward **one confident hero recommendation ("The Call")** + docked alternatives, **region context stated once** (the Context Ribbon), Detail conditions as one row/kind + a provenance "inspection layer", and a real desktop layout. Protects the refusals (source-or-silence, anti-engagement, calm, private).
- **Adopting incrementally:** the **Context Ribbon shipped** (#224, honest shared/per-trail split preserved); next lanes — the hero "Call" card, the desktop map-split, and a backend region-conditions probe (so the ribbon can carry a *true* region-level weather/AQI line, flagged not faked). Prior HIGH/MEDIUM UX fixes (#220 #221 #223) already moved the surface toward this.
