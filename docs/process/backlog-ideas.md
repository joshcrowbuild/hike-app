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

---

## Dump 002 — 2026-06-28

### B006 · Kill dummy messaging in the UI
**Essence:** Placeholder/sample copy is showing in the UI. It needs to go.

**Expansion — what I found (verified in code):**
- **Sample episodes exist** in `frontend/src/data/mock/episodes.ts` — "Hawksbill Summit with Ruby," "Stony Man Loop," with invented pace notes/outcomes. Tagged `provenance: 'sample'` and disclosed as sample-about-a-sample-subject (R11).
- **Live mode is already honest.** With `VITE_USE_MOCK=false`, the HTTP adapter returns `[]` episodes / `null` card (`httpPlanner.ts:154`) — it shows nothing rather than fabricating. So sample episodes only render in **mock mode**.
- **Therefore the bug is one of two things** — *(needs Josh to confirm which he's seeing)*:
  1. **The deployed frontend is still in mock mode** (`VITE_USE_MOCK` not flipped to `false` on Vercel) → no code change, an env/deploy fix. *Most likely, given we just went live.*
  2. **Hardcoded filler copy somewhere else** (a greeting, empty-state line, preset prompt) is reading as dummy → needs locating + rewriting. Candidates to check: `Home.tsx`, the Tuning presets/origins, empty-state strings.
- **Adjacent cleanup worth doing regardless:** decide the long-term fate of the sample-episode store. Options: (a) keep it strictly mock-only (current), (b) delete it once a real episode endpoint exists, (c) gate it behind a dev flag so it can never reach a production build. Ties to **B003** (real imported history is what eventually replaces it) and the missing episode-list endpoint (backend ask #1).

**Collisions / synergy:** Honesty is a non-negotiable (Rule #1 source-or-silence; R11 sample-disclosure) — so this is *invariant-aligned*, not just polish. The real fix path runs through **B003** (real episodes) + the missing episode endpoint.

**Open questions:** Which mode is the deployed app in? · Is it the sample episodes specifically, or other copy? · Delete vs. dev-gate the sample store?

**Ripeness:** `ready` — concrete cleanup. Likely a one-line env flip + a decision on the sample store. *Pending Josh pointing at the exact screen.*

---

### B007 · Deep review — state of the art (direct competitors)
**Essence:** A deep review of similar apps/experiences — what's out there, what we can be inspired by.

**Expansion — seeded comparison set (the frame for the research):**
- **Trail discovery / planning:** AllTrails (the gorilla — crowd reviews, discovery), Komoot (route planning + community routes), Gaia GPS (topo + backcountry nav), onX Backcountry (maps + land ownership + offline), CalTopo (SAR-grade planning), FarOut/Guthook (thru-hike waypoint guides), Hiking Project (REI, free DB), Outdooractive, Wikiloc, PeakVisor.
- **Recording / social / taste:** Strava (activity tracking, segments, the social axis — our deliberate *anti*-pattern on engagement), Garmin Connect / Coros (device ecosystems — our watch seam, Epic 004).
- **Live-conditions:** Mountain-Forecast, OpenSnow, avalanche.org, NWS — the JIT-overlay sources we already verify against.
- **What to extract from each:** their candidate-generation, how (or whether) they personalize, how they present uncertainty/conditions, where they're engagement-seeking (and we won't be), and the gaps they leave that a calm, source-or-silence, personal-intelligence utility could own.

**Collisions / synergy:** Pure research; informs everything (search B001, routing B005, the feed). Should explicitly map each competitor against our **non-negotiables** to find our defensible difference (provenance, private overlay, calm-utility).

**Ripeness:** `promoted → docs/research/competitive-lateral-review.md` (2026-06-28). Ran as a 57-agent adversarially-verified deep review (22 apps + 5 themes). Headline: the whole field's dominant failure is *epistemic* — almost everyone shows undated, unsourced data as current truth; best-in-class provenance exists only at the **feature** level (FarOut Water Status), never the app level. Our defensible white space = honest uncertainty + un-paywalled live truth + private personal intelligence.

---

### B008 · Lateral inspiration — same *mechanics*, different domains
**Essence:** Review experiences with similar mechanics we wouldn't obviously think to compare — non-obvious inspiration.

**Expansion — the non-obvious set (this is the high-value lens):**
- **onX Hunt ("honey holes")** — ⭐ private saved spots + *share-by-exception* with trusted people. This is *almost exactly* our private-overlay + Rule #5 (share the conclusion, not the substrate) model, in another domain. Closest structural analog out there.
- **Citymapper** — slow static map + **JIT live overlay** (transit times), presented with freshness. Mirrors our four-layer corpus + JIT-verification architecture.
- **Flighty** — calm, honest, **source-backed** travel utility; surfaces authoritative data with provenance, anti-anxiety tone. Strong tonal + architectural analog to source-or-silence + calm-utility.
- **Letterboxd** — **log-what-you-did → refine taste**, with a deliberately calm, anti-engagement community. Near-identical to our outcome loop (Epic 002) + belief pipeline (Epic 001).
- **Oura / Whoop** — **readiness scores** (the Body Battery analog) — directly relevant to **Epic 007** (readiness filter). How they present a single composite readiness number honestly.
- **Spotify Discover Weekly** — taste modeling → a calm *finite* curated drop (not infinite scroll). The personalization-without-bait pattern.
- **Beli (restaurant ranking)** — personal ranking from pairwise comparisons; novelty-vs-revisit tension (our novelty filter, Epic 006).
- **Notion / Obsidian** — personal knowledge **graph** as a product surface (our overlay analog).
- **Yuka** — **confidence/source scoring of a single fact** with a transparent rationale (our Confidence primitive).
- **Duolingo** — included as an **anti-pattern**: streaks/engagement mechanics we are explicitly *not* building.

**Collisions / synergy:** Several map 1:1 onto open epics/risks (onX Hunt→Rule #5, Oura→007, Letterboxd→002, Beli→006, Citymapper/Flighty→architecture+tone). The richest source of design moves precisely because the domains differ.

**Ripeness:** `promoted → docs/research/competitive-lateral-review.md` (2026-06-28). The "steal these first" list maps onto our existing work — the most actionable extractions:
- **FarOut Water Status (source-or-silence shipped)** → the template for Rule #1 at the Verifier layer: *no fresh source → no claim*, per-data-type freshness windows, four distinct empty-states (no-data / no-hazard / not-fetched / stale-degraded).
- **Yuka worst-element ceiling** → Rule #2 Confidence: one critical hazard *caps* the safety verdict, but confidence still never penalizes desirability ranking.
- **Beli pairwise capture** → **Epic 006** (taste/novelty): 3-bucket sentiment → binary-insertion-sort → derived 0–10 the user never types; store the private ordinal as substrate. (Note the cold-start gap: needs a bootstrap before a ranked list exists.)
- **Oura/WHOOP readiness + watch-as-capability-floor** → **Epic 007**: readiness as a JIT, hedged, capability-only effort floor (never a score/ring/streak); party = weakest-link with per-member disclosure.
- **onX Hunt folder grants + Find My time-boxed revocation** → Rule #5 / Stage 8: conclusion-level, revocable, no-re-share sharing enforced at the Cypher layer; strip residual substrate before emit (Strava's leak is the cautionary tale).
- **Spotify finite drop + Citymapper subscribe-to-entity alerts** → Rule #6 Curator feed: replace-don't-accumulate, finiteness driven by what's verifiable; opt-in per-trail/gauge/permit alerts that state the *derived consequence*.
- **Duolingo (+ Strava/Garmin/Beli engagement machinery)** → explicit do-not-build list. Key insight: anti-engagement is also **pro-accuracy** — gamified logging poisons the taste signal.

These are candidate sources for future epics (notably a Rule #1 Verifier-freshness epic, Epic 006, Epic 007) — not yet promoted to epics themselves.

---

## Dump 003 — 2026-06-29

### B009 · Cross-domain pattern research (round 2 — beyond hiking/fitness)
**Essence:** Review #1 covered competitors + consumer-app lateral mechanics; the only true outlier was Duolingo (anti-pattern). Go *further* — mine genuinely distant domains for adoptable methods: high-stakes professions (aviation, marine, trucking), rigorous provenance/trust systems, graph-database/connected-data use cases, and calm/boring-by-design utilities.

**The thesis (the reframe):** the outdoor-app world is immature at our hardest invariants *because the stakes are usually low*. The domains where bad data is **lethal** — aviation, marine nav, avalanche, emergency medicine, intelligence — have spent decades formalizing exactly source-or-silence, confidence rating, staleness/validity, and go/no-go under uncertainty. Product thesis to pressure-test: **"bring cockpit-grade decision discipline to the trailhead."** Review #1 was "what UX widgets do we steal"; this is "what rigorous *methods, formal models, architecture patterns, and cautionary failures* do we adopt."

**The 5 research lenses** (weighted to 2 & 3 per Josh):
1. **High-stakes go/no-go under uncertainty** — aviation personal-minimums + NOTAM-overload (cautionary), marine CATZOC spatial confidence bands, avalanche conceptual-model, clinical GRADE (evidence-quality vs recommendation-strength), SAR probability-of-detection, wildfire ICS.
2. **Provenance, trust & validity** *(HEAVY)* — Admiralty Code (2-axis source×info rating), Analysis of Competing Hypotheses (conflict resolution), legal **Shepardizing/citators** (is this fact still "good law"?), journalism/OSINT chain-of-custody, NewsGuard source labels, FAIR/W3C-PROV, Wikipedia verifiability, supply-chain (+ blockchain-theater cautionary).
3. **Connected-data & graph architecture** *(HEAVY)* — **Google Zanzibar/ReBAC** (permissions as graph edges → Rule #4/#5), fraud/AML graphs, KG provenance (named graphs/RDF-star), Palantir entity+access model, graph recsys (Pinterest Pixie → Epic 006), entity-resolution/conflation, temporal/bitemporal graphs (→ Rule #3), spatial routing/isochrones, genealogy household modeling.
4. **Capability vs. preference & readiness, formalized** — trucking HOS/ELD (mandated capability floor → Epic 007), conjoint analysis (→ Epic 006), blind tasting (revealed vs stated), dating stated-vs-revealed gap.
5. **Calm utility & boring-by-design** — GOV.UK design system, glass-cockpit UI under stress, medical-device alarm design, ambient/glanceable info.

**Decisions made (with Josh):**
- **Breadth + depth**, ultracode — ~76 agents, Lenses 2 & 3 weighted (9 domains each).
- **Decision-ready** — every pattern tagged `adopt / adapt / cautionary / just-interesting` with an actual decision + epic candidate.
- **UX dimension woven in** — every pattern carries a "what the user literally sees/does" field + one consolidated UX-implications section (first-class, not over-indexed).
- **Output format** *(designed to serve feature-dev + evaluation)*: an **adopt-first decision queue** up top (the direct feature-dev input), a full **pattern register** index, per-lens cards, and a consolidated **evaluation-hooks** section (each adopt → how we'd know it works, feeding Epic 009). **Two docs**: `cross-domain-pattern-library.md` (product/design-facing) + `graph-architecture-patterns.md` (architecture-lane technical brief, Lens 3).

**Ripeness:** `promoted → docs/research/cross-domain-pattern-library.md` + `docs/research/graph-architecture-patterns.md` (2026-06-29). 76 agents, 33 domains, 132 patterns, 20-item adopt queue (CDP-01…20). **Headline:** the six invariants aren't design preferences — 13 independent high-stakes disciplines converged on the same four load-bearing moves (two orthogonal axes never collapsed · the tool scores, the human decides · safety is a perishable state · corroboration is the engine but *independence* is the governor), so they're "discovered law." The sharpest correction to the thesis: "cockpit-grade" ≠ *more information* — the documented enemy is burying the critical fact in a flat wall of true-but-trivial ones (Air Canada 759; clinical alarm override 49–96%). The moat only a provenance **graph** can build: walk lineage to *distinct origins* so corroboration is real, propagate staleness + grants along those same edges.

**Top adopt-queue candidates for epics** (decision-ready, from the review):
- **CDP-08 + CDP-03** (substrate) — per-data-type freshness windows (SWR/SIE, ephemera never persisted) + capture-at-boundary provenance bundle `{source, timestamp, digest, role}`. → a **Verifier-freshness epic**.
- **CDP-02 + CDP-07** (cheap high-leverage UX, once a Confidence component exists) — three fact-states with *loud silence* (tombstone template) + two-axis trust grade (authority separate from corroboration). → **Confidence-v2**.
- **CDP-01** (the moat, gated on a feasibility spike) — independence-checked corroboration: count distinct **origins** via Cypher walk, fuse weakest-link, never re-ingest own output (anti-citogenesis).
- **CDP-04** (highest-risk, needs a design session) — advisory go/marginal/no-go verdict naming ONE binding constraint, always overridable; the tool scores, the human decides.
- **CDP-09 + CDP-10** → **Epic 007** (capability floor buffered above a hard line) + Curator non-compensatory **screen-then-rank**.
- **CDP-12** → the deferred **auth provider (R3)** on Zanzibar-style tuples + grant-as-stop-point.

Build-state caveat the review flags: Confidence/Staleness are *not yet built* as components (only the verify/Signal primitive ships), and corroboration currently = a raw edge count (the exact thing CDP-01 says to replace) — so several CDPs are net-new builds, not extensions.

---

## Dump 004 — 2026-07-09

### B010 · Trail connectivity & loop composition (credit: Carter)
**Essence:** AllTrails links trails/segments together — Whiteoak Canyon can be an out-and-back *or* close into the Cedar Run loop via two connectors. We model trails as isolated nodes; a *hike* (a composition over the trail network) isn't a thing yet.

**Expansion:** fully explored in **`docs/research/trail-connectivity-loops.md`** — three-layer problem split (topology · composition · judgment), gap audit (the Stage-2 schema designed `:Junction`/`CONNECTS_TO`/`:Route` and deferred all three; geometry is stored but never noded), open-source landscape (AllTrails' documented OSM-derivative junction-cut segment DB; GraphHopper round-trip; NP-hardness of loop-finding → enumerate-screen-curate, not generate), the bad-loop screen (TSI tags; the AllTrails-AI SAR backlash as the cautionary tale), the "worth recommending" rubric (Naismith bands · anchor quality · connector fraction · loop premium), and sustainability (topology as deterministic derivation + staleness propagation to dependent routes).

**Collisions / synergy:** hard-gated on **Phase A identity stability** (same collision as CoMaps E1 — noding re-cuts segment identity); companions: E1 (OSM relations = tier-2 named routes), E3 (POI anchors), **B005** (same junction substrate — topology-first makes B005 mostly UI), B001/B002 (the spatial-query axis).

**Open questions:** are unnamed connectors (fire roads, horse trails) even in the corpus? (fetch is named-ways-only — possibly the real long pole) · `:Route` in the feed vs. Detail-screen "extensions & loops" tray first · route identity per (trailhead, direction) vs. variants-on-one.

**Ripeness:** `shaped` — research done, spike defined (one-region offline notebook; falsification target: rediscover the NPS Cedar Run–Whiteoak Circuit from structure alone and rank it top-3). Next step is the spike, post-Phase-A.
