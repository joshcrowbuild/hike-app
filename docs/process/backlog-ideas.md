# Backlog Ideas — Dogfood Inbox

*Josh's raw idea dump while dogfooding, caught and expanded. This is the **inbox**, not the plan — fast capture over polish. When an idea ripens it graduates to a real `docs/epics/epic-NNN-*.md` and the row here points at it.*

**Owner:** PM/planner lane · **Started:** 2026-06-28 (first live-data dogfood)

> Not the SSOT for anything. Live status → `roadmap.md`; committed features → `epics/README.md`; decisions → `decision-log.md`. Ideas here are candidates, some may die.

**Ripeness legend:** `raw` (just caught) · `shaped` (expanded, collisions mapped) · `ready` (clear enough to write an epic) · `promoted →epic-NNN` · `dropped`

---

## Dump 001 — 2026-06-28 (first live dogfood)

### B001 · Search — "near me now" + "dreaming from home"
**Essence:** Two distinct entry points beyond the curated feed: (A) search from my *arbitrary current location* ("what's near me right now"), and (B) search a place I'm *not at*, planning from home ("show me Glacier", "waterfalls in Oregon").

**Expansion:**
- **Mode A — proximity ("near me now").** Needs device geolocation → spatial query from an arbitrary lat/lon, bounded by distance *or drive-time*. **Substrate partly exists:** Valhalla drive-time (Epic 005/013) already computes "within X minutes of a point" — so "trails within 45 min of where I'm standing" is closer than it looks.
- **Mode B — destination ("dreaming").** Needs geocoding (name → bbox/region) and/or attribute search ("waterfalls", "fire lookouts", "above treeline"). This is query-driven, not feed-driven — a different interaction shape than the calm feed.
- **Both flow through the engine, not around it.** A search is an *intent*; the Scout generates candidates for that intent and the Verifier/Curator still apply (source-or-silence, taste, party). Search must not become an un-personalized raw-list — keep it honest and curated. Ties to the query-time intent-parse path (the R5 cost concern).
- **Calm-utility guard (Rule: not engagement-seeking):** search is a tool you reach for, not an infinite-scroll. Results verified, hedged when low-confidence, finite.

**Collisions / synergy:** Hard dependency on **B002** (coverage) — search is thin until data exists beyond Shenandoah. Shares the "spatially query the trail graph" substrate with **B005** (routing). No existing epic covers an explicit search entry point — this is a genuine gap.

**Open questions:** Does search bypass or flow through the Curator's novelty/taste? (I lean: flow through, with intent as an override knob.) · Attribute search needs attributes in the graph — which facets are queryable today vs. need enrichment?

**Ripeness:** `shaped` — splits cleanly into A (proximity, mostly substrate-ready) and B (destination, needs geocoding). A could ship first.

---

### B002 · Continental data coverage (US → Canada → beyond)
**Essence:** Eventually query real data for the whole US, then Canada, then more. Today: one pilot region (Shenandoah-GWJ, 1458 trails, Aura Free).

**Expansion:**
- **The long pole.** US-wide is orders of magnitude more than one region — millions of trail segments. **Aura Free will not hold it**; this forces the hosting/DB-tier decision (R7) and likely Aura paid or self-hosted Neo4j.
- **The seam is already right.** The `CorpusSource` seam (Epic 012) + `regions/` dir were built for exactly this — pluggable, per-region ingestion. Scaling is an *operations + cost* problem more than an architecture rewrite.
- **Enrichment is the expensive part.** 3DEP elevation (Epic 017) samples every segment — doing that for the continent is slow and costly. Need batched/lazy enrichment, not eager.
- **Lazy region loading is the elegant bridge to B001/B002:** ingest a region on first query ("someone searched the Sierra → load it"), instead of preloading the continent. Caps the upfront cost, grows the corpus with actual usage.
- **Canada = different sources.** No USGS/NPS/USFS; needs Canadian equivalents (NRCan, provincial parks, Parks Canada). The `CorpusSource` seam absorbs this — declare new sources, same contract.
- **Non-negotiable check:** ✅ This is slow/structural data (Rule #3 — graph holds it). Source-or-silence (Rule #1) holds — bulk ingest with provenance.

**Collisions / synergy:** Gates **B001** and **B005** (both useless without coverage). Forces the **R7** DB-tier/cost decision and intersects **R5** (cost spike) at ingest scale.

**Open questions:** Preload vs. lazy-load-on-search? · Which DB tier/host survives continental scale within budget? · Enrichment backfill strategy (which regions first — by likely use?).

**Ripeness:** `raw` — needs a scaling/cost design session. Biggest infra decision in this dump.

---

### B003 · Import my history — "know my haunts"
**Essence:** A way to import old activity data so the system already knows where I've been and what I keep coming back to.

**Expansion — ⭐ highest-leverage idea in this dump:**
- **This is the missing `been_on` producer.** Epic 006 (novelty) is `DEFINED` but blocked on a producer of "trails you've already done." **Imported history *is* that producer.** This idea directly unblocks a stuck epic.
- **It also feeds the belief pipeline (Epic 001) immediately.** Imported trips → `Episode` nodes → EWMA pace / maxima / preference inference. Instead of cold-starting your taste from zero, you arrive pre-warmed.
- **"Haunts" carry two signals — keep them separate (Rule #7: capability ≠ preference).** Frequency you've hiked somewhere is *history* (→ novelty: "show me something new"). It is **not automatically a preference** ("you keep coming back" ≠ "you like this" — could be it's just close). Provenance + confidence on every derived belief.
- **Sources:** GPX/FIT files, Strava export, Garmin Connect / Coros history, AllTrails. The device seam (Epic 004) handles *going-forward* sync; this is the **historical backfill** sibling — possibly the same adapter, run over an archive.
- **Hard sub-problem: map-matching.** Raw GPX tracks → which corpus trail nodes? Snapping noisy tracks to the trail graph is non-trivial. Fallback: store as free-floating episodes with geometry, match opportunistically.
- **Privacy (Rule #5 private-by-default):** imported haunts are deep personal overlay. The commons fork (Epic 010) already de-identifies before anything is shared — this data must be born-severed if it ever feeds the commons.

**Collisions / synergy:** **Unblocks Epic 006.** Feeds Epic 001. Sibling to Epic 004 (device seam). Privacy path already built (Epic 010/014). Overlaps **B005** if "import" includes tracing recorded routes.

**Open questions:** Which import format first? (GPX is universal; Strava/Garmin export are richest.) · Map-match to trail nodes vs. store free-floating? · One-time bulk import vs. ongoing sync (the device seam may already cover ongoing).

**Ripeness:** `ready` — clearest path, unblocks a defined epic, well-supported by existing substrate. Strong candidate to promote first.

---

### B004 · User auth + multi-user personalized experiences
**Essence:** Real user auth, and many users each getting their own personalized experience.

**Expansion — mostly *already designed*, front door is what's missing:**
- **The data model already anticipates this.** CLAUDE.md identity model = "a household of individual members, each = own login + watch connections + private overlay + grants." The personal overlay is **already keyed per `viewer_id`** — multi-user isolation is a built invariant, not a new concept.
- **The hard part — query-layer isolation — is built and CI-proven (Thread T2).** `ScopedSession`, owner-scoping, viewer-auth hardening (Epic 011/014) are done; a forgotten owner clause reds the build (Epic 015). The substrate for "many users, each only sees their own overlay" exists.
- **What's actually missing is the front door:** a managed auth *provider* (Supabase / Clerk / Auth0 — **undecided, this is R3**), signup/login/session, and wiring real identities in place of the interim shared dev-secret (Epic 014's `X-Dev-Viewer-Secret`).
- **This is a promotion, not a discovery.** It moves R3 from "deferred" to "active" and also unblocks **Stage 8 multiplayer** (same auth boundary = the shared/private line).
- **Anonymous browsing stays a real product** (Rule: anonymous browsing of world + live conditions). Auth gates the *personal overlay*, not the map.

**Collisions / synergy:** = **R3** (open risk, provider undecided). Gates Stage 8. Substrate built (Epics 011/014/015). Decision needed *before* dogfooding spreads beyond you.

**Open questions:** Which provider? (gates multiplayer too — pick once.) · Does picking it now vs. after more solo dogfooding matter? · Migration path from the interim dev-secret → real sessions.

**Ripeness:** `shaped` — design exists, substrate built; blocked only on the provider decision. Mostly a *decision*, then an integration epic.

---

### B005 · Route building & drawing (user-authored routes)
**Essence:** Build and draw my own routes, not just consume system-assembled ones.

**Expansion:**
- **Today the map shows an *assembled* route (system-generated, Epic 016). This is the inverse: *user-authored*** — draw on the map, snap to trails, compose a custom loop/out-and-back.
- **The graph is literally built for this.** Trail routing = graph traversal over connected trail segments in Neo4j. (Valhalla does *road* drive-time; *trail* routing is native graph work.) Snap-to-trail + shortest/loop path = Cypher + a routing layer.
- **Reuses 3DEP enrichment (Epic 017) for free:** a drawn route's elevation profile is the same per-segment computation already shipped — assemble it along the drawn path.
- **A drawn route is also a first-class object:** can be verified (conditions along it), saved, shared (grant), or logged as a *planned* trip (vs. an outcome episode).
- **Scope-creep flag:** this is a big feature. **Split the intent first** — *planning* ("build the route I'll hike") vs. *recording* ("trace what I did"). Recording overlaps heavily with **B003** import. Planning is the larger net-new build.
- **Calm-utility check:** drawing is a deliberate tool, fits the utility framing — but it's heavy; sequence it after coverage + search make it useful.

**Collisions / synergy:** Extends Epic 016 (maps). Reuses Epic 017 (elevation). *Recording* mode overlaps **B003**. Depends on **B002** coverage + **B001** search to be worth using. Shares the spatial-graph-query substrate with B001.

**Open questions:** Planning vs. recording — which first (or is recording just B003)? · Snap-to-trail routing engine: build on Neo4j traversal or pull a dedicated router? · Save/share semantics (grant a drawn route?).

**Ripeness:** `raw` — needs the planning-vs-recording split decided; sequence after B001/B002.

---

## Cross-cutting reads (across this dump)

- **Two axes emerge.** *Spatial-query* axis: **B001 search · B002 coverage · B005 routing** all want one substrate — "query the trail graph spatially at scale." *Identity/personalization* axis: **B003 import · B004 auth** — who you are and what the system knows about you.
- **Suggested leverage order (my read, not a decision):** **B003 import** first (ripe, unblocks Epic 006, pre-warms personalization, small-ish). Then **B004 auth** (a decision + integration; substrate's built; needed before sharing the app). **B002 coverage** is the long pole that gates **B001/B005**, so start its scaling/cost design session early even if the build comes later. **B001 search** Mode A (proximity) can sneak in early on Valhalla. **B005 routing** last — biggest, most dependent.
- **No non-negotiable is violated** by any of the five. Watch for: Rule #7 (B003 — history ≠ preference) and Rule #5 (B003 — haunts are private overlay).
