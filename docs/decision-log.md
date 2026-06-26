# Adventure Planner — Design & Decision Log

*Working title. Living document — last updated June 18, 2026.*

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
- **Graph-based context = the answer to "RAG pointed at the self":** hand the agent a *subgraph* (the trail, your similar episodes, the beliefs from them, Ruby's capability, nearby alternatives) — *why*, not just *what*. Hybrid GraphRAG (Neo4j vector index + traversal). Double-duty with the role's team.
- **Discipline — keep live data OUT of the graph.** Slow/structural in-graph; fast/ephemeral fetched JIT and overlaid, never persisted as nodes to expire.
- **Neo4j fit:** local Community, Cypher traversals, spatial point types for "near my origin," vector index for hybrid retrieval. *Caution:* don't let it become a schema project — v0 graph is thin (canonical trails + provenance, stub profile/party), grown as episodes/beliefs accrue.

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
**Now in:** Stage 2 — the graph schema & provenance/confidence model (design against the real data shape from Stage 1; see `docs/research/stage-1-data-sources.md`). Then Stage 3 corpus pipeline, Stage 4 engine.
Eventual **Phase 0 thin vertical slice**: ingest one East-Coast region (proposed pilot: Shenandoah NP + GW & Jefferson NF — a clean NPS+USFS conflation test); minimal Neo4j (canonical trails + provenance, stub profile/party); origin as a runtime parameter with device-location default; Verifier JIT overlay (weather + drive time + trail facts, source-stamped) on the shortlist; a basic feed; the truthfulness eval. **Remaining de-risking spike:** real LLM cost-per-session (needs a flow to measure → Stage 4). The conflation desk-research spike is **done** (§27); the hands-on conflation run folds into Stage 3.

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
- **◆ Phase-0 design (Stages 1–4) complete** — the end-to-end verified-synthesis slice is fully specified; next is build + the cost spike, not more design.

## 30. Stage 5 — Personalization decisions ✅ *(June 23, 2026 — design: `docs/research/stage-5-personalization.md`)*
- **Belief store schema:** ✅ Five personal-overlay node types: `:Episode` (completed trip), `:Outcome` (post-hike reflect-back, separate node), `:Belief` (semantic belief with provenance), `:PhysicalProfile` (capability summary), `:PartyProfile` (party-specific inferences). All carry `owner_id`; all gated by `scopedQuery(viewer)`.
- **Belief axes:** ✅ Four values: `capability` / `preference` / `taste` / `constraint`. Watch/FIT-derived data may only populate `capability` — **capability ≠ preference** is enforced at the schema level, not just at query time (Rule #7).
- **Belief type:** ✅ `stated` (user-affirmed, never decays by default) vs. `inferred` (behavioral/watch-derived; always labeled provisional until confirmed). An inference never poses as a stated fact (Rule #7).
- **Episode→semantic promotion:** ✅ Capability beliefs updated via EWMA (α=0.3) on every FIT-parsed episode. Preference/taste beliefs require N=3 corroborating episodes above threshold; below N=3, belief exists at provisional confidence (<0.4) and is not injected into Curator context. 🔶 N=3 floor is a starting point — tune against real episode volume.
- **Decay model:** ✅ Computed on read (same pattern as confidence — store inputs, compute at read time). Half-lives: capability 180d, preference 90d, taste 120d, constraint=never. 🔶 Validate half-lives against real data before treating as settled.
- **Context assembly:** ✅ At query time: top-20 active beliefs by recency (above decayed confidence floor) + relevant episodes (same trail or area as candidates, last 18 months, cap 10). Raw biometric data, full episode history, and provisional beliefs are never injected into the model context.
- **Watch data integration:** ✅ Live readiness (Body Battery / HRV) enters the readiness filter only — never the belief store. Raw HR time series and biometric archive are NOT held in Neo4j. Belief store holds only capability signals extracted at ingest. Every watch-enriched ranking carries a disclosure tag (Rule #6).
- **Privacy tiers for Stage-5 data:** ✅ T1 = derived capability/preference beliefs (grantable to household members); T2 = episode history + outcomes (grantable explicitly, context-scoped to joint planning); T3 = raw biometrics (not stored in the graph, therefore not grantable). Grant enforcement deferred to Stage 8.
- **Commons write for episodes:** ✅ Forked write on episode creation: person→observation link severed; GPS track endpoint-trimmed (250m strip, 🔶 threshold TBD); raw pace bucketed into 4 capability bands before commons write. Private episode retains full data. Post-aggregation deletion of individual contribution is not recoverable — disclosed in consent.
- **Memory eval:** 🔶 A thin memory-on vs. memory-off harness runs alongside the Stage-4 truthfulness eval; the deep stochastic methodology is Stage 7.
- **`:Route` node (custom itineraries):** ✅ Deferred — Stage 5 uses `:CanonicalTrail` as the episode target; `:Route` added only when party planning needs custom itineraries (consistent with Stage 2 §2).
- **◆ Phase-1 personalization design complete** — belief store, promotion, decay, context assembly, watch discipline, and privacy tiers fully specified; next is build (watch integration = Stage 6) + the memory eval.

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
- **Commons fork:** ✅ `CommonsObservation` written in same transaction as Episode; person link severed at write; 250m endpoint trim; raw pace substituted with 4-band capability label before commons write.
- **MCP write discipline:** ✅ MCP tools (Coros) never write Episode nodes — they are read-only in interactive context; all Episode writes are owned by the scheduled batch job.
- **◆ Phase-1 design (Stages 5–6) complete** — personalization schema + watch ingestion pipeline fully specified. Next: build the Phase-0 vertical slice (Shenandoah+GWJ) + Stage-4 cost spike; then Stage-6 build.
