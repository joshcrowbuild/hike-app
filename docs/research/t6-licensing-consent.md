# T6 — Licensing, Consent & Source-ToS Swappability (cross-cutting thread)

*Cross-cutting thread T6 (Workplan, thread T6 — line 25). Design v0.1 — June 24, 2026. Builds on `stage-1-data-sources.md` §5 (per-source license obligations), Decision Log §27 (ODbL handling, off-limits sources) / §11–§12 (commons) / §14 (retention/deletion) / §28 (Stage-2 separability) / §30–§31 (the Stage-5/6 commons fork — designed, not yet built; see §4.1). The gate on Stage 9's public release.*

> **Status: DESIGN.** T6 is a *thread*, not a stage — it runs through every stage rather than sitting at one point. This document formalizes it: (a) the OSM/ODbL obligations in concrete, code-shaping terms and how the Stage-2 source-separability classification discharges them; (b) the per-source ToS/license summary plus the **swappability discipline** (no source becomes load-bearing); (c) the **consent flows** required before any user FIT data enters the commons (Rule #8); (d) a **go/no-go checklist** that gates Stage 9's public release. Honors Rules **#1** (source-or-silence), **#4** (access at the query layer), **#5** (private-by-default; share the conclusion not the substrate), **#8** (fork the FIT write early, aggregate above k), **#9** (no training), **#10** (secrets never in the repo). **Design only — no new build in this doc.**

> **Legend (matches the Decision Log):** ✅ decided · 🔶 recommended, confirm · ❓ open. Confidence on factual claims uses the Stage-1 legend (✅ verified · 🟡 verify-before-coding · 🔴 flagged/changing) where it adds signal.

> **Scope note — what T6 is *not*.** This thread governs *inbound source licenses* and *outbound contribution consent*. It is **not** legal advice and **not** a privacy-engineering spec (the de-identification mechanism is Stage 9; the access-control implementation is Stage 8 / §28). T6 owns the **policy and the gate**; those stages own the **mechanism**. Where T6 asserts a legal reading (esp. ODbL), it cites the primary source and flags the one place (🔴 G-6) where counsel is required before public release.

---

## 1. Why this thread exists (the two asymmetric risks)

The project sits between two legal surfaces that fail in opposite directions:

- **Inbound (sources we consume).** Most of the stack is US-Government public domain (clean), but **OSM is ODbL share-alike** and a handful of sources are encumbered or off-limits. The risk is *contamination*: an encumbered source silently becoming load-bearing, or OSM's share-alike forcing the public commons open. This is a **build-time / architecture** risk — cheap to honor early (the Stage-2 separability classification already does most of it), expensive to retrofit.
- **Outbound (user data we publish).** The commons republishes a *derived* product of users' FIT tracks. The risk is *consent failure*: data entering the aggregate the contributor didn't knowingly authorize, or being un-deletable after the fact. This is a **trust** risk — and trust, once broken, doesn't retrofit at all.

**The thread's job:** make both risks *structural impossibilities by construction*, not policies someone has to remember. Each lands as either a Stage-2/Stage-9 schema invariant or a hard gate (§6) — never a runtime judgment call.

---

## 2. OSM / ODbL — the obligations in concrete terms

ODbL 1.0 is the only share-alike license in the stack and the **single load-bearing legal fact** in the whole design (Stage-1 §5.1 ✅, verified against the OSMF Legal FAQ). Getting its three distinctions right at the schema layer is what keeps the commons-public option open. This section makes them concrete.

### 2.1 The three artifacts ODbL distinguishes

ODbL governs *databases*, and its obligations turn entirely on **which of three things you produce and whether you publicly convey it**:

| Artifact | ODbL definition | What it is *for us* | Obligation if **publicly conveyed** |
|---|---|---|---|
| **Produced Work** | A work (e.g. a rendered map, an image, a text) algorithmically derived from the Database | A feed card, a trail-detail screen, a route suggestion, an LLM-phrased recommendation | **Attribution only.** May be licensed however we like. *Explicitly not a Derivative Database (ODbL §4.5b).* |
| **Derivative Database** | A database "based upon the Database … including any translation, adaptation, … or any other alteration" | Our conflated corpus where OSM geometry is merged/cross-referenced with USFS/NPS attributes into one interlinked record | **ODbL share-alike on the whole derivative** — machine-readable, alterations documented, offered under ODbL. |
| **Collective Database** | An "independent and separate" assemblage of databases that are *not* merged into one | OSM-derived layer + government-derived layer kept **separable, non-cross-referencing** | **ODbL on the OSM layer only.** The other layers keep their own (public-domain) terms. ODbL §4.5a. |

**The escape hatch is architectural, not legal** (Stage-1 §5.1, finding #3): you don't negotiate your way out of share-alike — you *store your way out of it*, by keeping the OSM-derived facts in a separable layer so the published thing is a Collective Database (or a Produced Work), never a Derivative Database.

### 2.2 "Produced Work" vs. "Derivative Database" — the line that matters for *our* corpus

The distinction is **merge vs. render**:

- The moment OSM geometry is **conflated** with a USFS allowed-use attribute into a *single interlinked record* — one row, one node, that you could publish as data — you have created a **Derivative Database**. (Stage-1 §5.1: *"The moment we merge/conflate OSM geometry with USFS attributes into one interlinked record, that record is a Derivative Database."*)
- The moment you take that record and **render** it — a card, a map tile, a sentence the Curator emits — you have created a **Produced Work**, which owes attribution only.

So our corpus is *both*, depending on the cut:
- **The internal corpus graph** (Neo4j, with OSM facts conflated onto canonical trails) **is a Derivative Database.** Privately held, this triggers nothing (see §2.4). Published as data, it would trigger share-alike.
- **Everything the user sees** (the feed, trail detail, recommendations) **is a Produced Work** — attribution-only, regardless of how the graph was built.

### 2.3 How the Stage-2 source-separability classification discharges this ✅

Decision Log **§28 (decision 1)** already chose the storage shape that makes the escape hatch *free*:

> *"Facts on `:SourceRecord` + `SAME_AS` edges + computed best-view on the canonical node. OSM-derived facts stay isolated on OSM SourceRecords → ODbL-separable (Collective-Database escape hatch is free)."*

Concretely, the schema gives every fact a **provenance home**, and OSM facts never lose their label:

```
(:CanonicalTrail {name, …})                         // Produced-Work surface: attribution-only
  -[:SAME_AS {source:"OSM",  …}]-> (:SourceRecord {source:"OSM",  geom, name, …})   // ODbL-licensed island
  -[:SAME_AS {source:"USFS", …}]-> (:SourceRecord {source:"USFS", trail_cn, …})     // public domain
  -[:SAME_AS {source:"NPS",  …}]-> (:SourceRecord {source:"NPS",  trlname, …})       // public domain
```

This yields a precise **source-separability classification** every fact carries (a single property, computed from `SourceRecord.source` — no new storage):

| Class | Meaning | Members | Publication rule |
|---|---|---|---|
| **PD** (public-domain) | No license obligation on republication | USFS, NPS, USGS (all), PAD-US, NWS, A.T. centerline, FIRMS (CC0) | Freely republishable as data. |
| **SA** (share-alike) | Republishing the *data* triggers ODbL on the derivative | **OSM only** | Republishable as data **only** under ODbL, **or** kept separable (Collective DB), **or** exposed as Produced Work only. |
| **ATTR** (attribution / terms) | Republishable with attribution + specific clauses | RIDB (no-endorsement), AirNow (label "preliminary") | Republishable with the named clause attached. |
| **NR** (no-redistribute) | Personal/reference use only; **never** in a distributed product | VA DCR Conservation Lands, Fairfax County (verify), PATC | **Never** crosses the publication boundary — enforced as a hard gate (§6, G-2). |

**The single derived rule the engine enforces:** *the publication class of any republished artifact is the **most-restrictive class of any source that contributed to it**.* A Produced Work that rendered an OSM fact owes OSM attribution; a data export that touched an NR source is blocked outright. Because every fact already knows its source (§28), this is a pure lookup — **no separate license-tracking system to build.**

**Why this is enough (and why it's a §28 confirmation, not a new decision):** the schema *already* isolates OSM. T6's contribution is to name the **invariant that keeps it isolated** — that the de-identification/aggregation pipeline (Stage 9) must **never collapse the OSM-derived layer into the published commons as conflated data**, and the publication path must compute the most-restrictive-class. Both are checked at the gate (§6).

### 2.4 Phase-by-phase: when does anything actually trigger?

Share-alike attaches only on **public conveyance of a Derivative Database** (Stage-1 §5.1 ✅; Decision Log §27). This maps cleanly onto the phasing:

| Phase | What's published | Derivative DB conveyed? | ODbL obligation |
|---|---|---|---|
| **0–1** (personal/household, single-user, local) | Nothing — the graph never leaves the machine | **No** | **None.** Ingest, conflate, transform OSM freely. Attribution is courtesy if maps are ever shown. |
| **2** (multiplayer, household) | Grants between household members — *derived conclusions only* (Rule #5), not the corpus | **No** (a derived belief is a Produced Work, and is person-data anyway, not the OSM corpus) | **None on the OSM layer.** (Grant consent is a *separate* axis — §4 / §11.) |
| **3** (commons, public) | **The aggregated trail-property database** — empirical pace, effort topology, etc., on shared nodes | **This is the trigger.** The commons *is* a conflation of OSM + government + user-derived data. | **Decided at the gate (§6, G-6):** either (a) publish the commons under **ODbL** (likely fine — see §2.5), or (b) keep the OSM-derived layer **separable** (Collective DB), or (c) expose only **Produced Works** (rendered output / an API of recommendations, not the database). |

The critical read (Stage-1 §5.1 🔴, Decision Log §27): **the public commons is exactly the artifact that lands in "Derivative Database."** Phases 0–2 are genuinely unencumbered; **Phase 3 is where T6's gate bites.**

### 2.5 The commons-public decision — three lawful options, one recommendation 🔶

When Stage 9 goes public, the OSM-touching commons must take one of three ODbL-compliant forms. T6 does not pre-decide which (that's a §6 gate item with counsel in the loop), but it states the recommendation and the *why*:

| Option | Mechanism | Cost | Fit |
|---|---|---|---|
| **A — Commons under ODbL** | Publish the aggregated database under ODbL: attribution, share-alike, machine-readable, document alterations | We give up proprietary control of the *aggregate statistics* (not user data — that's de-identified bands) | **🔶 Recommended default.** The commons is a calm public-good utility (CLAUDE.md framing), not a moat (Decision Log §2: "AllTrails has no trail-data moat" — we don't either). The aggregate *being open* is consistent with the project's stance, costs us nothing we were monetizing, and is the simplest to defend. |
| **B — Collective Database** | Keep the OSM-derived layer separable/non-cross-referencing; commons references government + user-derived layers only | Engineering discipline forever — the separability invariant must hold through every aggregation; one conflated join breaks it | Viable (§28 keeps OSM separable already), but **brittle**: the commons' whole value is *empirical properties of trails*, and trails come from the OSM spine — keeping them non-cross-referencing while making them useful is in tension. |
| **C — Produced Works only** | Never expose the commons *as a database*; expose only rendered recommendations / a query API that returns conclusions | We can't offer a bulk data download or a "commons dataset," only answers | Always-available fallback. Aligns with Rule #5 (*share the conclusion, not the substrate*) — but forecloses an open-data contribution that would otherwise be on-brand. |

**Recommendation: default to A (ODbL the commons), with C as the always-safe fallback for any artifact where ODbL is awkward.** Why: the project explicitly *isn't* building a data moat (Decision Log §2), treats the commons as a public good (§12), and an ODbL commons is the lowest-discipline, highest-defensibility path. B's separability discipline is real engineering debt for a benefit (proprietary aggregate) we don't want. **This is a 🔶 to confirm with counsel at the G-6 gate**, because the precise boundary between "ODbL-clean aggregate" and "still a Derivative Database needing the full ODbL machine-readable offer" is the one place a lay reading isn't safe.

### 2.6 OSM attribution — the always-on obligation

Independent of the database question, **every Produced Work derived from OSM owes attribution** (ODbL §4.3). This is cheap and starts the moment any map/feed is shown to *anyone* outside the household:

- **Required string:** "© OpenStreetMap contributors" with a link to the ODbL, on any surface that renders OSM-derived geometry or facts. (Per the OSMF attribution guideline.)
- **Where:** the trail-detail map, any feed card showing an OSM-sourced fact, and a colophon/about surface. The Stage-2 best-view already records *which source won* per attribute (§28), so the renderer can attribute precisely — and only attribute OSM when an OSM fact is actually shown.
- **🔶 Decision:** attribution is **a first-class UI honesty primitive**, rendered by the same machinery as confidence/staleness/"verify before you go" (Decision Log §20 — *"how confidence/staleness… render consistently — these are first-class UI states"*). It is not a footnote bolt-on. **Why:** it's the same problem (provenance made legible) and the same renderer; folding attribution into the honesty system means it can never be forgotten on a new surface.

---

## 3. Per-source license summary & the swappability discipline

### 3.1 The summary (T6's canonical license table)

Consolidated from Stage-1 §5 and the §1 catalog into one decision-ready license register. **Class** = the source-separability class from §2.3. This table *is* the policy that the publication gate (§6) reads.

| Source | License / terms | Class | Obligation on republish | Load-bearing? |
|---|---|---|---|---|
| **OSM** (geometry spine) | **ODbL 1.0** | **SA** | Attribution always (Produced Work); share-alike if conveyed as a Derivative Database | **🔴 YES — the one structural dependency** (see §3.3) |
| USFS NFS Trails | US-Gov public domain | PD | None (attribution courtesy) | No — allowed-use is authoritative but swappable to NPS/state |
| USGS (NTD, 3DEP, Water) | Public domain | PD | None | No — 3DEP elevation is the only near-sole source, but interchangeable with other DEMs |
| NPS (Content API + GIS) | Public domain | PD | None | No |
| PAD-US 4.1 | Public domain | PD | None | No |
| **Recreation.gov RIDB** | **Access Agreement** (attribution-style) | **ATTR** | Mandatory no-endorsement clause; attribution encouraged (🟡 exact license name + rate limit verify-before-coding, §3.3) | No — permits *requirements* only; degrades to "verify on recreation.gov" |
| NWS api.weather.gov | Public domain (fair-use; **User-Agent required**) | PD | None (set a contact User-Agent — an access term, not a license term) | Live weather is safety-critical but the *source* is swappable in principle |
| NASA FIRMS | CC0 | PD | None (citation encouraged, not mandated — CC0 ≈ PD per Stage-1 §5.2) | No |
| **EPA AirNow** | EPA terms | **ATTR** | **Must label data "preliminary"** | No |
| **VA DCR Conservation Lands** | Signed agreement — **no redistribution / no for-profit** | **NR** | **Never in a distributed product** | No — personal/reference only; hard-gated (§6 G-2) |
| **Fairfax County** | County copyright + permission | **NR** (🟡 verify for redistribution) | Permission required to redistribute | No |
| **PATC** | Closed (Avenza/print) | **NR** | Not ingestible | No |
| Valhalla / OSRM (engine) | MIT / BSD | PD (engine) | Engine permissive; **underlying OSM data still ODbL** | Engine swappable; the *data* inherits OSM's SA class |
| **Off-limits apps** (Strava, AllTrails, Hiking Project/onX, Gaia, Komoot) | Proprietary — **AI/scraping banned** | — | **No lawful path** | **Hard-blocked** (§6 G-5) — never adapters, never ingested |

🟡 **Verify-before-coding (carried from Stage-1 §9):** the exact RIDB license name + rate limit in the live Access Agreement; Fairfax County's precise redistribution terms; whether any VA Open Data dataset we actually use is ODC-BY (→ would add an ATTR row). These move from desk-research to the first ingestion task.

### 3.2 The swappability discipline — the principle

The non-negotiable, from Workplan thread T6 (line 25): **source-ToS swappability is honored from Stage 1 — no single source may become load-bearing such that its license changing, its API sunsetting, or its terms tightening can break the product.** Two forces make this real:

- **Sources change terms.** Stage-1 §5 / Appendix B is a graveyard of this: Strava added an explicit AI ban; AllTrails issued an MCP takedown (Jan 2026); onX deprecated the Hiking Project API in 2020; the legacy USGS Water API decommissions ~Q1 2027. A source that's clean today can be off-limits tomorrow.
- **The architecture has decided the seam — but not yet built it.** Decision Log §29 *decided* the live-adapter pattern (each `(loc)→verified fact|None`) and the device seam (`device-integration-seam.md`) decided the device-adapter pattern: **every external source should sit behind a normalized adapter contract, selected by config.** Today this is a *decision*, not realized architecture — the live adapters are hardcoded (`verifier.build_probes()` wires five named adapters) and `run_pipeline()` names osm/nps/usfs literally; no `LiveAdapter`/`CorpusSource` contract or `ingestion/sources/*` registry exists yet (gap-audit C5/C6). T6 extends that decided pattern with a *license obligation* on each adapter, to be honored when the seam is built.

### 3.3 The discipline made concrete — six rules

| # | Rule | Why | Status |
|---|---|---|---|
| **SW-1** | **Every source is an adapter behind a normalized contract** (mirrors §29 live adapters + the device seam). A source's license/auth/transport is the adapter's private business; downstream sees normalized facts + a class tag. | Swapping a source = swapping one adapter, zero downstream change. | ✅ as a §29 *decision*; the normalized-adapter contract/registry is designed but **not yet built in code** — live + corpus sources are currently hardcoded (gap-audit C5/C6). T6 reads as forward discipline to honor when the seam lands, not realized architecture. |
| **SW-2** | **Each adapter declares its `license_class`** (PD/SA/ATTR/NR from §2.3) and its obligation clause (attribution string, "preliminary" label, no-endorsement). The class rides with every fact to publication. (For ATTR sources whose exact terms are still 🟡 — RIDB — the declared clause carries the same verify-before-coding flag as §3.1.) | The publication gate (§6) can't enforce the most-restrictive-class rule unless every fact carries its class. Cheap: it's `SourceRecord.source` → a lookup table. | 🔶 |
| **SW-3** | **No source is the *sole* support for a user-facing fact class unless it's authoritative-by-nature** (allowed-use = USFS/NPS; elevation = 3DEP). Where a source is sole-support, source-or-silence (#1) degrades gracefully when it's gone. | Single points of failure are the swappability risk. Most fact classes have ≥2 sources (the conflation premise); the few that don't must degrade, not break. | ✅ (follows from #1) |
| **SW-4** | **OSM is the one acknowledged structural dependency — and that's accepted, because the fallback is architectural, not another source.** OSM provides the breadth no other source has (Stage-1 §6: county/regional/private trails are *only* in OSM). Its license is permanent and known (ODbL won't "tighten"); the risk isn't license change, it's the *share-alike* obligation — already handled by separability (§2.3). | You can't swap away from the only source of the long tail of trail mileage (Stage-1 §6 — OSM is the sole source for county/regional/private trails; the precise share is unmeasured, so treat "majority of mileage" as an estimate, not a sourced figure). The honest move is to *name* OSM as load-bearing and ensure the dependency is on *open* data with a *stable* license, not to pretend it's swappable. | ✅ |
| **SW-5** | **An NR-class source may never become an adapter that feeds the corpus** — only a personal/reference lookup outside the publication boundary. | VA DCR / Fairfax / PATC are authoritative but encumbered; baking them into a distributed product is the contamination risk. Keeping them out of the adapter registry makes it structurally impossible. | ✅ |
| **SW-6** | **A new source passes a license-clearance check before it gets an adapter** (the §6 G-1 checklist, applied per-source at add-time, not just at the Stage-9 gate). | Cheaper to clear a source on the way in than to discover an encumbered fact in the commons on the way out. | 🔶 |

**The swappability test (a thing to actually run):** for each user-facing fact class, ask *"if this source vanished or banned us tomorrow, does the product break, degrade, or shrug?"* The answer must be **degrade or shrug** for every class except OSM-breadth — and for OSM, the answer is "we'd lose breadth gracefully (federal blocks still work), and the license can't change against us." Anything that answers *"break"* is a T6 bug.

---

## 4. Consent flows before user FIT data enters the commons (Rule #8)

This is the outbound surface. Rule #8 (*"fork the FIT write early… aggregate only above the k-anonymity threshold"*) and §12 (*"contribution consent is its own thing, separate from grants"*) set the frame. T6 specifies the **consent gating** that must sit on the fork before *anything* a user contributed becomes part of a published aggregate.

### 4.1 The two-stage reality the consent must match

The commons fork is **designed but not yet built** (Decision Log §30 / §31): on episode creation, a de-identified twin is *designed to be* written to a `:CommonsObservation` with the person link severed, endpoints trimmed (250m), and pace bucketed into capability bands. **This write does not exist in code today** — `create_episode()` writes the `:Episode` and wires `:Person-[:DID]->`, but does **not** write `:CommonsObservation` (gap-audit C1; the §30/§31 ✅ for the fork is *wrong memory* being demoted to 🔶 "designed, not yet built — Commons Fork epic pending"). The design is that the fork *will* happen at write time so the commons **accretes from day one, dormant until volume** (§12: *"Build now: only the forked write… accretes from day one, dormant until volume"*) — but until the Commons Fork epic ships, nothing accretes. This gives consent two distinct moments once the fork is built:

```
   FIT episode created
          │
          ▼
   ┌─────────────────┐   Rule #8: fork the de-identified write EARLY so it accretes.
   │  COMMONS FORK    │   (DESIGNED, not yet built — Commons Fork epic pending.)
   │  (write-time)    │   When built: gated by CONSENT-TO-CONTRIBUTE (§4.2).
   └────────┬─────────┘   No consent → no fork. The private episode is unaffected.
            │  (dormant, below k)
            ▼
   ┌─────────────────┐   Below k-anonymity → privacy-unsafe AND too-thin (§7: k = the
   │  AGGREGATION     │   confidence floor). Never surfaced, never published.
   │  (volume-time)   │   Above k → enters the published aggregate.
   └────────┬─────────┘
            ▼
      PUBLIC COMMONS
```

**The consent gate is on the fork (write-time), not on aggregation.** Rationale: aggregation is anonymous-by-then (link severed, above k), so the meaningful consent moment is *"may my de-identified twin be written at all?"* If we waited until aggregation to ask, we'd either be holding un-consented forked data (bad) or have nothing to aggregate (the accretion premise fails). **So: no contribute-consent → the fork does not fire → the `:CommonsObservation` is never created.** The private episode (Rule #5 substrate) is entirely unaffected either way. Note that consent gating the *exposure* of the fork only matters once the fork write itself exists; the consent gate and the fork write are **both** unbuilt and must ship together (the consent gate as a precondition of the Commons Fork epic — gap-audit C1 action).

### 4.2 The consent itself — what it must be

Consent to contribute to the commons is a **distinct, explicit, separately-revocable opt-in** — never bundled with sign-up, never bundled with sharing-to-a-person (grants, §11), never on by default (Rule #5: *private-by-default*).

| Property | Requirement | Why |
|---|---|---|
| **Separate axis** | Commons-contribution consent is orthogonal to person-grants (§12: *"Carter can contribute anonymously while sharing nothing with you"*). Two different toggles, two different mental models. | Conflating them would let a household grant leak into a public contribution, or vice versa — a Rule #5 violation. |
| **Opt-in, default off** | The fork does **not** fire until the user affirmatively enables commons contribution. Sign-in alone grants nothing. | Rule #5 (private-by-default; shared-by-exception). Anonymous browsing and even signed-in private use never contribute. |
| **Informed** | The consent surface must state, in plain language: *what* is contributed (de-identified pace/effort, not your name/route endpoints), *what is stripped* (identity, the 250m endpoints — §31), *that it's irreversible once aggregated*, and *that nothing surfaces below k contributors*. | Informed consent is the trust contract. The irreversibility disclosure is mandatory and load-bearing (§4.4). |
| **Granular (🔶)** | At minimum a single contribute on/off. 🔶 Consider per-attribute granularity later (contribute pace but not crowding-by-time) — deferred to Stage 9 UX, not a Phase-0 concern. | Start coarse (one toggle) to ship; granularity is upside, not a gate. |
| **Revocable (forward)** | Toggling off **stops future forks immediately** and removes any *still-dormant* (below-k, not-yet-aggregated) observations. | Revocation must be *real* for everything not yet irreversibly mixed (§11: "revocation is only real if nothing was copied"; retention/deletion policy §14). |
| **Auditable** | The consent state + its timestamp + version-of-terms is recorded on the member's private overlay, queryable. | "Did this user consent, when, to which version?" must be answerable — for trust, deletion requests, and the §6 gate. |

### 4.3 Consent for *dependents* (Ruby) — the special case

Ruby is a dependent node, not an account (CLAUDE.md identity; §13). A dependent **cannot consent.** Therefore:

- **🔶 R-1: Dependent-attributable data does not contribute to the commons.** A FIT episode tagged as Ruby's (or a party episode where the readiness/capability signal is Ruby's) is **excluded from the fork** — there is no party who can authorize publishing a dependent's derived data, even de-identified.
- **Why:** the whole commons-consent edifice rests on *the contributor authorizing their own de-identified twin.* A dependent has no one with standing to authorize that (the guardian authorizes *care*, not *publication of the dependent's biometric-derived data*). The safe, defensible default is exclusion. **This is a 🔶 to confirm** — it may be over-conservative for, e.g., pure trail-property signals that aren't dependent-attributable, but exclusion is the right *default* until Stage 9 examines it.

### 4.4 The irreversibility disclosure (the hard truth, stated honestly)

Once a contribution is **aggregated above k**, the individual contribution is **not recoverable** (§14 right-to-delete policy; §30: *"Post-aggregation deletion of individual contribution is not recoverable — disclosed in consent"*). T6 makes this a **mandatory, non-buried disclosure** on the consent surface, in plain language: *"Once enough hikers have contributed for a stat to appear, your individual contribution is blended in and can't be pulled back out. We can stop future contributions and remove ones not yet blended, but blended ones are part of the anonymous aggregate for good."*

**Why state it so bluntly:** this is the one place the consent could be accused of over-promising "delete." The honest move — and the only one consistent with Rule #1's source-or-silence ethic applied to *our own promises* — is to disclose the limit up front. The k-gate + capability-bands + endpoint-trim (§12) are *why* this is acceptable: an aggregated contribution isn't individually identifiable anyway, so "can't delete it" means "can't delete an anonymous statistic you're one of ≥k people inside," not "we kept your data." The deletion *of the private substrate* (the episode itself) is always honored (§14 right-to-delete) — it's only the already-anonymized aggregate twin that's irreversible.

### 4.5 What consent does **not** unlock (the Rule #5 / #8 guardrails)

Even with full commons consent, these remain structurally true *by design* (they're not consent-gated, they're invariant) — noting that, like the fork itself, they are **designed, not yet built** (§4.1):

- The **person→observation link is severed at write** regardless (§28 decision 6: *`:CommonsObservation` label **reserved**, guaranteed never edge-linked to a `:Person`* — the label is reserved in schema; the write that would create it is **not yet built**, see §4.1). Consent authorizes the fork; it does **not** authorize keeping the link.
- **Endpoints are trimmed** regardless (the re-ID vector — §12).
- **Raw pace is bucketed to a band contributor-side** before the commons write (§30/§31) — the commons never sees raw biometrics, consent or not.
- **Nothing surfaces below k** (§7) — consent doesn't lower the floor.

Consent is the gate on *whether the de-identified twin is written*; the de-identification itself is non-negotiable mechanism (Rule #8). The two are independent layers of protection — and both must be built (gap-audit C1).

---

## 5. How T6 threads through every stage (the continuity obligation)

T6 is a thread (Workplan, thread T6 — line 25): it must be honored *continuously*, not at one stage. The per-stage touchpoints, so nothing is dropped between here and Stage 9:

| Stage | T6 obligation | Already honored? |
|---|---|---|
| **1** (sources) | License obligations catalogued; off-limits/encumbered sources mapped *before* any ingestion | ✅ (Stage-1 §5, §27) |
| **2** (schema) | OSM-derived facts kept **separable** (`:SourceRecord` islands) → Collective-DB escape hatch free; class is a lookup on `source` | ✅ (§28 decision 1) |
| **3** (pipeline) | NR-class sources **never enter the corpus** (SW-5); each source adapter declares its class (SW-2); attribution recorded per fact | 🔶 (pipeline must carry the class tag — §3.3) |
| **4** (engine) | Publication path computes most-restrictive-class; **no LLM training on any source** (Rule #9 — already ✅ §29, pure orchestration); attribution renders as a Produced-Work obligation | 🔶 (§2.6, §6 G-3) |
| **5–6** (memory/watch) | The **commons fork is consent-gated** (SW-2 outbound); dependent data excluded (R-1); fork severs link + trims + bands | 🔶 **designed, not yet built** — Commons Fork epic pending (§30/§31 design; gap-audit C1). The consent gate ships *with* the fork (§4.1). |
| **8** (multiplayer) | Person-grants are a **separate consent axis** from commons-contribution (§4.2); grants share the *conclusion not the substrate* (Rule #5) | 🔶 (Stage 8 designs grants; T6 asserts the orthogonality) |
| **9** (commons) | **The gate fires** (§6). ODbL-vs-Collective-vs-Produced-Work decided with counsel; k-gate live; consent-audit complete | ❓ → the §6 checklist |

The thread's discipline: **each upstream stage must not foreclose a downstream T6 option.** Stage 2 kept OSM separable so Stage 9 *can* choose Collective-DB. Stages 5–6 *will* fork de-identified (once the Commons Fork epic ships) so Stage 9 *can* aggregate. T6's job is to ensure that chain never breaks — and to flag where a link (the fork) is assumed-done but isn't.

---

## 6. The go/no-go checklist — the gate on Stage 9's public release

This is the operative artifact: **the public commons does not ship until every gate below is GO.** The Workplan makes Stage 9 explicitly *"gated by T6 for public release"* (Stage 9 heading + its *Gate* bullet: "OSM/ODbL + consent resolved (T6) before anything public") — this is that gate, made checkable. Each item names the decision, the evidence required, and the rule it protects. **A single NO-GO blocks the whole public release** (not the private/household product — Phases 0–2 are unaffected).

### 6.1 Inbound — licensing & contamination

| Gate | Requirement | Evidence | Protects | Status |
|---|---|---|---|---|
| **G-1** | **Every source feeding the published commons has a cleared license** (PD / SA-handled / ATTR-with-clause). License-clearance checklist run per source. | The §3.1 register, current as of release, every 🟡 resolved against the live terms. | SW-6, #1 | ❓ |
| **G-2** | **No NR-class source contributed to any published artifact.** VA DCR / Fairfax / PATC never crossed the publication boundary. | Provenance query: no published commons node has a `SAME_AS` to an NR `:SourceRecord`. (A property-based test, sibling of the §28 access-control test.) | SW-5 | ❓ |
| **G-3** | **OSM attribution renders on every Produced-Work surface** that shows an OSM-derived fact. | "© OpenStreetMap contributors" + ODbL link present on map/feed/colophon; renderer reads the §28 best-view to attribute precisely. | ODbL §4.3, §2.6 | ❓ |
| **G-4** | **The OSM-derived layer is verifiably separable** — the commons did not collapse OSM facts into the published aggregate as conflated *data* (only as rendered conclusions or as a properly-labeled ODbL layer). | Schema audit: OSM facts still on isolated `:SourceRecord`s; the publication cut is either a Produced Work, an ODbL'd Collective layer, or an ODbL'd derivative — never an un-licensed Derivative DB. | §2.3, §28 | ❓ |
| **G-5** | **Zero off-limits-app data anywhere in the lineage.** No Strava/AllTrails/onX/Gaia/Komoot data was ever ingested. | Adapter registry contains none of them; provenance has no such source. | §27, Stage-1 Appendix B | ✅ (structurally — never built) |
| **G-6** | **The commons-public license form is chosen and counsel-confirmed** (ODbL the aggregate / Collective-DB / Produced-Work only — §2.5). The one place a lay reading isn't safe. | A written decision + legal sign-off on the Derivative-Database boundary. | §2.4–2.5 | ❓ 🔴 **counsel required** |

### 6.2 Outbound — consent & privacy

| Gate | Requirement | Evidence | Protects | Status |
|---|---|---|---|---|
| **G-7** | **Commons contribution is opt-in, default-off, separate from grants.** No fork fires without explicit, informed, separate consent. | The consent surface exists, is off by default, is a distinct toggle from person-sharing; consent state is audited per member. | Rule #5, #8, §4.2 | ❓ |
| **G-8** | **The consent disclosure is complete and honest** — states what's contributed, what's stripped, the k-floor, and the **irreversibility** of aggregated contributions. | The §4.4 disclosure text is present and plain-language; reviewed. | #1 (applied to our own promises), §4.4 | ❓ |
| **G-9** | **The de-identification invariants hold regardless of consent** (and the fork itself is built — gap-audit C1): link severed at write, endpoints trimmed (250m), pace banded contributor-side, **nothing below k**. | The Stage-9 privacy tests (sibling of §14 / §17 security tests) pass against *real* fork code: the commons write *never* retains a person link; endpoint-trim *always* fires; no sub-k stat surfaces. (Note: today these tests would pass vacuously — no `:CommonsObservation` write exists yet.) | Rule #8, §28 decision 6, §12 | ❓ |
| **G-10** | **Dependent (Ruby) data does not contribute.** No dependent-attributable episode produced a `:CommonsObservation`. | Provenance query: no commons observation traces to a dependent-tagged episode. | R-1, §13 | ❓ 🔶 (confirm R-1 scope) |
| **G-11** | **Forward revocation works**: toggling consent off stops future forks and removes still-dormant (below-k) observations. | A test: revoke → new episodes don't fork → below-k twins are gone; above-k aggregates correctly remain (and that limit was disclosed per G-8). | §4.2, §11, §14 | ❓ |
| **G-12** | **k-anonymity floor is set and enforced** as both the privacy threshold and the confidence floor (one gate, two jobs). | The k value is chosen (Stage 9 — undesigned) and the aggregation refuses to emit below it. | §7, §12 | ❓ (k value is a Stage-9 decision) |

### 6.3 The gate's operating rule

- **Default state = NO-GO.** The public commons is closed until every gate is GO. (Phases 0–2 — personal, household, private — are *not* gated by this; they ship freely, since §2.4 shows nothing triggers privately.)
- **G-6 is the long pole** and the only one needing outside counsel — start it early in Stage 9, not at the end.
- **G-2, G-4, G-5, G-9, G-10 are property-based tests**, not manual reviews — they join the §14 / §17 / §28 security-test suite so the gate is *continuously* green, not a one-time audit. This mirrors the project's existing discipline (Decision Log §28: *"Property-based test asserts no ungranted node ever returns"*) applied to licensing + consent. **Caveat (gap-audit C1):** G-9 / G-10 only test something real once the Commons Fork write exists; against today's absent code they pass vacuously, which is itself a false guarantee — the fork must ship before these gates carry weight.

---

## 7. Decisions

| # | Decision | Status |
|---|---|---|
| **T6-1** | **Source-separability classification:** every fact carries a license class (**PD / SA / ATTR / NR**) derived from `SourceRecord.source`. Republished artifacts take the **most-restrictive class of any contributing source.** No new storage — a lookup on the §28 provenance. | ✅ (formalizes §28 / §27) |
| **T6-2** | **OSM = the one accepted structural dependency.** Its license can't tighten against us (ODbL is permanent); its share-alike is handled by **separability** (§28), not by swapping it out. We name it load-bearing rather than pretend otherwise. | ✅ |
| **T6-3** | **The commons-public form (ODbL the aggregate / Collective-DB / Produced-Work only) defaults to ODbL the aggregate**, with Produced-Work as the always-safe fallback — **confirmed with counsel at gate G-6.** Why: no data moat (Decision Log §2), public-good framing (§12), lowest-discipline path. | 🔶 (counsel at G-6) |
| **T6-4** | **OSM attribution is a first-class UI honesty primitive**, rendered by the same machinery as confidence/staleness (§20), precise per the §28 best-view. | 🔶 |
| **T6-5** | **Swappability discipline (SW-1…SW-6):** every source is a config-selected adapter declaring its `license_class`; no source is sole-support except authoritative-by-nature ones (which degrade per #1); **NR sources never enter the corpus adapter registry**; a source is license-cleared before it gets an adapter. The normalized-adapter seam is **decided (§29) but not yet built** — sources are hardcoded today (gap-audit C5/C6). | ✅/🔶 (extends §29; seam unbuilt) |
| **T6-6** | **Commons-contribution consent is opt-in, default-off, separate from person-grants, informed, separately revocable, audited.** The consent gate sits on the **fork (write-time)**; no consent → no `:CommonsObservation`. The fork itself is **designed, not yet built** (gap-audit C1); the consent gate ships as a precondition of the Commons Fork epic. | 🔶 |
| **T6-7** | **The aggregation-irreversibility limit is disclosed plainly in consent** (Rule #1 applied to our own promises). Private-substrate deletion is always honored; only the already-anonymized above-k twin is irreversible. | ✅ (formalizes §14/§30 disclosure) |
| **T6-8** | **Dependent (Ruby) data does not contribute to the commons** — no party can authorize publishing a dependent's derived data. Default exclusion. | 🔶 (confirm scope at Stage 9 / G-10) |
| **T6-9** | **The go/no-go gate (§6) is the operative blocker on Stage 9's public release.** Default NO-GO; G-2/G-4/G-5/G-9/G-10 are property-based tests in the §14/§17/§28 suite; **G-6 needs outside counsel** and starts early. Phases 0–2 are not gated by it. | ✅ (this is the T6 deliverable) |

---

## 8. What this thread does **not** decide (handoffs)

- **The k value** — Stage 9 (undesigned). T6 only asserts k = the confidence floor (§7) and that it gates publication (G-12).
- **The de-identification mechanism** (sever / trim / band) and **the commons fork write itself** — designed in §30/§31 but **not yet built** (gap-audit C1; Commons Fork epic pending). T6 owns the *consent gate on it*, not the mechanism — and flags that the gate and the write must ship together.
- **The grant tuple semantics** — Stage 8 (undesigned). T6 asserts only that grants are a *separate consent axis* from commons-contribution (§4.2).
- **The precise attribution UI** — Stage 10 design system (§20); T6 sets that it *is* an honesty primitive, not how it looks.
- **The legal ruling at G-6** — outside counsel; T6 frames the three lawful options and the recommendation, and makes it a gate.

---

*Primary legal references: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (§4.3 attribution, §4.4 share-alike, §4.5 Collective vs. Derivative Database) · [OSMF Licence & Legal FAQ](https://osmfoundation.org/wiki/Licence/Licence_and_Legal_FAQ) · [OSMF Attribution Guideline](https://wiki.osmfoundation.org/wiki/Licence/Attribution_Guidelines). Source license details: `docs/research/stage-1-data-sources.md` §5 + Appendix B. Schema separability: `docs/research/stage-2-schema.md` (Decision Log §28). Commons fork (designed, not yet built — gap-audit C1) + consent disclosure: Decision Log §11–§12, §14, §30–§31. Off-limits sources verified 2026-06-19; re-check before any public release (ToS change often).*
