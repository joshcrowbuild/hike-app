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

## 20. Design system ❓→🔶
- Josh's actual domain — his call. Considerations: **token-first**, because web-then-native means the same tokens should express in both **Tailwind (web)** and **SwiftUI (native)** — design tokens as the single source of truth (literally his Capital One world).
- 🔶 Web: shadcn/ui + Radix + Tailwind for speed and themeability, with a custom theme expressing the calm-utility aesthetic. A parallel SwiftUI token set when native arrives.
- The system should encode the *honesty* primitives too: how confidence/staleness, "unverified," and "verify before you go" render consistently — these are first-class UI states, not afterthoughts.

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
Watch-sync fine details (mostly settled, §10) · **conflation** (spike) · schemas (belief entry; episode→semantic promotion; grant relationship; provenance-stop semantics; FIT-to-episode extractor + capability-vs-preference tagging) · **eval methodology** (scenarios, N-run pass rates, regression, LLM-judge for the soft half — hardest, undesigned) · party preference-merging algorithm ("minimize the bigger disappointment") · commons aggregation (k-threshold value, capability-band computation, the pace model) · orchestration substrate (Claude API + framework? Claude Code? MCP-native?) · routing provider · cold-start calibration design · UX flows + design system (Part V) · auth provider choice · cost budget (spike) · retention windows · backup cadence · OSM/ODbL handling before public commons · novelty mechanism, decay model, naming.

## 25. Roads not taken (so we don't re-litigate)
Fine-tuning open UI-gen models + verifiable design-system reward (frontier products own it; repair-loop dissolved the need to train; needs GPUs — *the verifier-with-two-halves idea survived and ported here*) · game domains (DM/RPG, whodunit, AI town) · work-adjacent concierges (loan/benefits/claims) · AllTrails-style social condition reports (→ passive anonymized commons) · pre-seeding with the 27-destination workbook (want real ingest) · parallel variants (garden, kitchen — parked spin-offs).

## 26. Proposed next step
Build the **Phase 0 thin vertical slice**: ingest one East-Coast region; minimal Neo4j (canonical trails + provenance, stub profile/party); origin as a runtime parameter with device-location default; Verifier JIT overlay (weather + drive time + dog/trail facts, source-stamped) on the shortlist; a basic feed rendering the ranked, verified set; the truthfulness eval against a few known trips. End-to-end and real, just narrow. **Before that, two de-risking spikes:** conflation on a small set of trails, and a real measurement of LLM cost-per-session.
