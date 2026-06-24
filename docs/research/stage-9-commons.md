# Stage 9 — Commons (design)

*Workplan Stage 9. Draft v0.1 — June 24, 2026. Builds on Stage 6 (the episode pipeline + the forked commons write (T3) — designed, not yet built per gap-audit C1); consumes Stage 2's reserved `:CommonsObservation`/`:CommonsStat` labels and the k=confidence-floor unification (Decision Log §7, §11–12). Gated by **T6** (OSM/ODbL + consent) before any public release.*

> **Status: DESIGN.** Specifies the de-identification pipeline (sever link · endpoint-trim · unlinkability proof), the k-anonymity + aggregation design with **k as the single confidence floor (one gate, two jobs)**, contributor-side capability-band computation, the **pace-calibration model first** (the first emergent attribute) and how the other emergent attributes follow it, and the differential-privacy posture. Decisions in §11. Honors rules #1, #2, #3, #4, #5, #6, #8, #9, #10.

> **What this produces (per workplan):** the de-identification pipeline (sever link / endpoint-trim) · k-anonymity + aggregation design · capability-band computation · the **pace-calibration model first**, then the other emergent attributes · the differential-privacy posture.

> **What this stage does NOT do:** it does not switch the commons public. The forked write (T3) is **designed to accrete** `:CommonsObservation` rows from Phase 0 — **not yet built (gap-audit C1)**; **aggregation stays dormant until volume**, and **public exposure is gated by T6** (§8). Stage 9 is the design that turns the accreted substrate into trustworthy aggregate statistics — and the privacy proof that lets it ship.

> **Legend:** ✅ decided · 🔶 recommended, confirm in build · ❓ open.

> ⚠️ **Correction (gap-audit C1, 2026-06-24):** this doc was drafted assuming the T3 forked write is already accreting. It is **not** — `create_episode()` does not yet write `:CommonsObservation` (decision-log §32's ✅ is wrong memory, demoted to 🔶 in `decision-log-additions-proposed.md §40`). Read every "✅ accreting since Phase 0" below as **🔶 designed, not yet built — Commons Fork epic pending**. The design here is correct; the write half must actually ship (inside `create_episode()`'s transaction) before any of it accretes, and the structural privacy test (§2) must land with it. The earlier a builder reads this, the more it matters: nothing is accreting yet.

---

## 1. The two ends of the pipe — what already exists vs. what Stage 9 adds

The commons is built in two halves, deliberately separated in time (Decision Log §12 "build now: *only* the forked write"):

| Half | Where built | State today |
|---|---|---|
| **The write** (`:CommonsObservation` per episode, de-identified at write) | Stage 5 §6 / Stage 6 §6.2 (T3) | 🔶 **designed, NOT yet built** (gap-audit C1) — must ship before anything accretes |
| **The read** (aggregate `:CommonsStat` on shared nodes, k-gated, served into the feed) | **Stage 9 (this doc)** | dormant; designed here |

**Why the split matters.** The write is cheap and must start early or the commons is never viable (T3's whole point). The read is where privacy risk concentrates — aggregation is the moment individual contributions could leak — so it is designed late, against real accreted volume, and gated. Stage 9 is overwhelmingly about the **read** half and the **proof** that the write half is actually unlinkable. **Why now:** the episode pipeline (Stage 6) is the only feeder, so the commons could not be designed before it existed.

**The non-negotiable invariant inherited from Stage 2 §6:** `:CommonsObservation` carries no `owner_id` and **no edge ever links it to a `:Person`** — a security/privacy test target (Decision Log §17). Everything in §2 exists to make that invariant true *and provable*, not merely asserted.

---

## 2. The de-identification pipeline — severing the person link

Three transforms fire **inside the same transaction** as the `:Episode` write (Stage 6 §6.2), so a commons observation never exists in a linkable intermediate state. Stage 9 specifies each precisely and adds the **unlinkability proof** that was deferred from Stage 2.

### 2.1 Sever the person link (structural, not just unset)

The `:CommonsObservation` is a **new node with no inbound or outbound edge to any `:Person`/`:Episode`/`:Outcome`**. It is not the episode node with the owner stripped — it is a separate node born without a back-edge.

```cypher
// Written in the SAME transaction as the Episode MERGE (Stage 6 §3.1), but NEVER edge-linked to it.
CREATE (co:CommonsObservation {
    observation_id:   randomUUID(),
    trail_id:         $trail_id,           // FK-by-value to the shared CanonicalTrail (world layer, unowned)
    segment_ids:      $segment_ids,        // for sub-trail effort topology (§7.1)
    capability_band:  $band,               // computed contributor-side (§4) — NEVER raw pace
    month:            $month,              // "2026-06" — coarse temporal bucket, not the date
    ascent_bucket:    $ascent_bucket,      // bucketed, not raw (§3.3)
    distance_bucket:  $distance_bucket,
    trimmed_track:    $trimmed_wkt,        // endpoint-trimmed (§2.2); null if no GPS
    writer_hash:      $writer_hash,        // one-way; for revocation lookup ONLY, by re-derivation (§2.3)
    ingest_version:   $ingest_version,
    written_at:       datetime()
})
```

Note `trail_id`/`segment_ids` are stored **as scalar values, not edges** — a commons observation references the shared world layer by *value* so an aggregation job can group on it, but there is no traversable relationship out of the observation at all (not even to the unowned `:CanonicalTrail`). The only join is a value-match performed inside the batch aggregation job (§3.1), never a graph path.

**Why a born-severed node, not a stripped copy:** a copy-then-strip pattern has a window where the link exists; a security test cannot prove a *transient* edge never existed. A node that is `CREATE`d without the edge has no such window. The access-layer test (§6) asserts the structural property "no path of any length from `:CommonsObservation` to `:Person`" — which is only checkable if the edge is *never* written, not written-then-deleted.

**Why same-transaction:** atomicity. Either both the private episode and the de-identified twin commit, or neither does. A half-state where the commons twin exists but the episode rolled back (or vice versa) would either orphan an observation or silently drop a contribution. (This matches Stage 6 §6.2 "written in the same transaction as Episode.")

### 2.2 Endpoint-trim (the re-identification vector)

The dominant re-ID risk on a GPS track is the **endpoints**: an out-and-back commonly starts at the contributor's home or a habitually-used trailhead parking spot (Decision Log §12). Trim is the defense.

- **Strip the first and last 250m** of the polyline before the commons write (Stage 5 §6 / S5-10; Stage 6 §6.2). The private `:Episode` retains the full track; only the commons twin is trimmed.
- 🔶 **250m is provisional** (S5-10 flagged it; S5-11 likewise for bands). It must be **validated empirically against the accreted track distribution** before public release — the right trim is the smallest that defeats trailhead/home clustering, which depends on real parking-lot geometry. **Recommend** computing, per region, the distance at which trimmed startpoints stop clustering below the k threshold, and setting the trim to that (region-specific, not a global constant) — *why:* a fixed 250m over-trims sparse rural trailheads (losing signal) and under-trims dense suburban ones (leaking).
- **Trim is also hygiene, not only privacy** (Decision Log §17: "endpoint-trim for the commons (hygiene + privacy in one)") — GPS noise and auto-pause artifacts cluster at endpoints; trimming improves the pace signal *and* the privacy posture in one pass. One transform, two jobs — the same economy as k (§3).

### 2.3 Exactly how the forked write stays unlinkable

Three independent properties, each separately testable, together make re-identification structurally impossible from the commons layer alone:

1. **No back-edge** (§2.1) — there is no graph path from observation to person. Re-ID by traversal is impossible by construction.
2. **No raw quasi-identifiers** — the observation holds *bucketed/banded* values (capability band, month, ascent/distance buckets), never the raw pace, raw timestamp, or raw totals that could fingerprint a contributor against their public Strava-style footprint elsewhere. (Raw values stay on the private `:Episode`, behind `scopedQuery`.)
3. **Trimmed geometry** (§2.2) — the one remaining high-entropy field (the track) has its identifying endpoints removed.

**The `writer_hash` — and why it does not reopen the link.** Revocation needs *some* handle to find a contributor's observations ("delete my contributions"). `writer_hash = HMAC(secret_salt, member_id)` is a **one-way** keyed hash:
- It is **deterministic** (the same member always hashes to the same value → their observations are findable for deletion) but **non-reversible** (the salt is in the secrets manager, never in the graph; without it the hash is opaque).
- It is **not a quasi-identifier**: it is a single opaque value shared across all of one person's observations, carrying zero external linkage. An attacker with full graph read sees a column of opaque hashes with no key.
- **Why HMAC, not a plain hash of member_id:** a plain hash is brute-forceable (the member_id space is small and enumerable). The keyed salt defeats a dictionary attack; an attacker who dumps the graph still cannot map a hash back to a member without the secrets-manager salt.
- **Why the `writer_hash` does NOT violate the no-path invariant (§6, S9-13).** A `writer_hash` is a *functional* one-way reference, not a graph edge, and revocation never traverses from observation to person. The revocation flow runs in the **forward direction only**: take the *requesting* member's id, recompute `HMAC(salt, member_id)`, and **property-match** that freshly-computed value against the `writer_hash` column to find their pre-aggregate rows for deletion. It is a **property lookup keyed by a re-derived hash, never a graph traversal** — so "no path of any length from `:CommonsObservation` to `:Person`" holds exactly. There is no stored mapping from a hash back to a person anywhere in the graph; the only thing that can produce the hash is the secrets-manager salt plus the member's own id at request time.
- **Revocation honesty (the hard part).** `writer_hash` lets us delete a person's *raw observations*. But once an observation has been **folded into a k-aggregated `:CommonsStat`**, the individual contribution is no longer separable — the aggregate is a sum/mean over a bucket, not a list. **Pre-aggregation deletion is exact; post-aggregation deletion is unrecoverable** (Decision Log §11 "revocation is only real if nothing was copied" — the aggregate *is* the copy; Decision Log §14 "harder once aggregated → another reason for k-gating + capability-bands"). This is **disclosed in consent** (Stage 5 §6; Stage 6 §6.2) and is one of the two jobs k does (§3): k-gating keeps the pre-aggregate window honestly revocable, and capability-banding (§4) means even a recovered raw observation isn't a raw biometric. **Why we accept this:** the alternative (never aggregating, or storing a reversible link to enable post-hoc removal) defeats the entire privacy model. Irreversible aggregation is the *point*, not a bug — we make the irreversibility honest by disclosing it and by gating it behind k so nothing aggregates while the contributor set is still small enough for one person's withdrawal to matter.

---

## 3. k-anonymity + aggregation — one gate, two jobs

This is the load-bearing unification of the whole project (Decision Log §7, §11; Rule #2): **the commons k-anonymity threshold IS the confidence floor.** Below k contributors, a fact is *both* privacy-unsafe (too few to hide in) *and* too thin to trust (too small a sample). One config value (`k`) does both jobs.

### 3.1 The gate

A `:CommonsStat` is only **computed and exposed** when its contributor count `n >= k`. Below k, the underlying `:CommonsObservation` rows accrete privately but **no aggregate node exists** and **no fact is ever stated** (source-or-silence, Rule #1, as the bottom of the confidence gradient — Decision Log §7).

```cypher
// Aggregation job (scheduled, batch — NOT in the request path). Per (trail/segment, kind, band, month-bucket):
MATCH (co:CommonsObservation)
WHERE co.trail_id = $trail_id AND co.capability_band = $band AND co.month IN $window
WITH co.trail_id AS tid, co.capability_band AS band, count(co) AS n, collect(co) AS obs
WHERE n >= $k                                   // ← THE GATE. k = confidence floor = privacy floor.
// ... compute the stat over `obs` (§5), then attach to the shared node by value-match:
MATCH (ct:CanonicalTrail {canonical_id: tid})
MERGE (ct)-[:HAS_COMMONS_STAT]->(s:CommonsStat {kind: $kind, capability_band: band, window: $window})
SET s.value = $value, s.n = n, s.computed_at = datetime()
```

The observation joins to the shared trail by **value-match** (`co.trail_id = $trail_id`), never by traversing an edge out of `co` — preserving §2.1's severance. The `:HAS_COMMONS_STAT` edge lands between two *unowned world-layer* nodes (`:CanonicalTrail → :CommonsStat`), never touching a person.

### 3.2 Choosing k (and why it's one number)

🔶 **Recommend k = 5 as the starting floor**, tuned upward against real volume before public release — *why 5:* it is the smallest value at which a single contributor's withdrawal does not de-anonymize the rest (the classic k-anonymity intuition: you must be indistinguishable from at least k−1 others), and small enough that lesser-traveled trails (which the product makes *first-class*, Decision Log §3) can still earn a commons layer rather than only popular trails getting one. **The same k is the confidence floor:** below 5 contributors, an empirical pace is too thin to state plainly. The threshold is stored as **one config value** (Stage 2 §4: "store `k` as one config value"), so raising it for privacy automatically raises it for trust, and vice versa — they can never drift apart, which is the entire reason for the unification.

**Why not separate a privacy-k from a trust-k:** if they were two numbers, an operator could lower the privacy floor for coverage without realizing they'd lowered the trust floor too (or shipped a privacy regression while tuning trust). Collapsing them to one number makes the dangerous mistake impossible to make — a structural guardrail, not a documented caution.

### 3.3 What gets bucketed before aggregation (the quasi-identifier reduction)

Aggregation groups on **coarse buckets**, never raw values, so that the *grouping keys themselves* can't fingerprint a rare contributor:
- **Temporal:** `month` ("2026-06"), not the date — *why:* a date + trail can be near-unique on an obscure trail; a month is not.
- **Distance / ascent:** bucketed (e.g. ascent in 200m bands) — *why:* the exact totals are a near-unique fingerprint against a public activity feed elsewhere; the band is shared by many.
- **Capability:** the 4-band label (§4), never raw pace.

This is k-anonymity applied to the *grouping dimensions*, not only the contributor count — a rare combination of raw quasi-identifiers would create a singleton group that passes a naive `n >= k` count on the wrong axis. **Buckets first, then count.**

### 3.4 Aggregation runs as a scheduled batch job, never in the request path

The aggregation job is an **ordinary scheduled job** (consistent with Decision Log §8 "batch ingestion = scheduled jobs, not MCP," and Rule #3 "graph holds slow/structural data only"). `:CommonsStat` is **slow derived data that lives in the graph** on shared nodes (Decision Log §12) — it is *not* a live overlay (it changes monthly, not per-minute), so unlike weather it legitimately persists as nodes. The Verifier/Curator read pre-computed `:CommonsStat` at feed time; they never aggregate on the hot path. **Why:** aggregation is expensive and privacy-sensitive; doing it offline keeps the per-session cost model (Stage 4 §cost) clean and keeps the k-gate in one auditable place.

---

## 4. Capability-band computation — contributor-side, before the write

**Rule (Decision Log §12, Rule #5):** the contributor computes their own capability band; the commons receives the *band*, never the raw pace. "Share the conclusion, not the substrate" applied to the commons.

### 4.1 Where and when

Band computation happens **contributor-side, at episode-write time** (Stage 6 §6.2 / S6-10), inside the de-identification transform, *before* the value crosses into `:CommonsObservation`. The raw `pace_on_grade` exists only on the private `:Episode`; the commons twin is born with the band already substituted. **Why contributor-side:** if the raw pace reached the commons even momentarily, the substrate would have been shared — the band must be computed on the private side of the boundary and only the conclusion crosses. The substitution is pure arithmetic (a threshold lookup), so it routes nowhere — no model call, no cloud, no leak (consistent with the local-first sensitivity routing, Stack §model-providers).

### 4.2 The four bands

| Band | Range (min/km, grade-adjusted) |
|---|---|
| `easy` | `< 12` |
| `easy-moderate` | `[12, 16)` |
| `moderate` | `[16, 20)` |
| `strenuous` | `≥ 20` |

**Boundaries are half-open** (`[lo, hi)`) so no value falls in two bands — a banding spec with overlapping bins is a correctness gap, and Stage 9 is the document that owns band computation, so it fixes it here.

🔶 **Band labels and thresholds are provisional and Stage 9 is canonical for them.** The source docs disagree: **S5-11** (Stage 5) names the four bands `easy-moderate / moderate / moderate-strenuous / strenuous`, while **S6-10** (Stage 6) names them `easy / easy-moderate / moderate / strenuous`. **S9-9 supersedes both and adopts the Stage 6 label set** (`easy / easy-moderate / moderate / strenuous`) — *why this set:* it is the one carried by the episode pipeline that actually writes the band (Stage 6 §6.2), so adopting Stage 5's divergent labels would require re-plumbing the writer for no gain. The label *names* matter little anyway because **the boundaries become quartile-fit (below), not fixed**; the canonical contribution of S9-9 is the fit rule, not the literal cutoffs. (Stage 5's S5-11 should be treated as superseded by S9-9 on the band set; the trim half of S5-10 stands.)

🔶 **Tuning rule:** **fit the band boundaries to quartiles of the accreted contributor-side pace distribution per region**, not to fixed constants — *why:* fixed min/km cutoffs misclassify across terrain types (a "strenuous" pace on rocky Appalachian tread is a "moderate" pace on smooth rail-trail); quartile-fit bands self-normalize to the actual population and keep roughly balanced band populations (which helps each band clear k independently). The `< 12 / [12,16) / [16,20) / ≥ 20` numbers above are the v0 seed, replaced by per-region quartiles once volume allows.

### 4.3 Why banding does double duty (privacy + signal quality)

The band is simultaneously (a) the **privacy mechanism** — a raw pace is a near-continuous quasi-identifier, a 4-way band is not — and (b) the **signal the commons actually wants** — empirical pace *conditioned on capability* (Decision Log §12: "empirical pace conditioned on capability beats Naismith"). The aggregate must be **stratified by band** anyway (a "moderate" hiker's pace and a "strenuous" hiker's pace are different facts and must not be averaged together), so banding is required for correctness regardless of privacy. The privacy win is free. **This is the §3 economy again:** the transform we'd need for a *correct* conditional statistic is exactly the transform we need for *privacy*.

---

## 5. The pace-calibration model — FIRST emergent attribute

Pace calibration is the **first** emergent attribute to ship (workplan: "the pace-calibration model **first**, then other emergent attributes") — *why first:* it has the cleanest signal (FIT gives measured pace + grade directly, no inference), the highest value (it beats Naismith for *every* trip-time estimate, the single most-used number in the feed), and it is the template the other attributes follow (§7). It is also the attribute that most needs the commons: a *personal* pace model needs only the contributor's own episodes (Stage 5/6, the EWMA on `PhysicalProfile`), but a pace model for a trail the user **has never hiked** can only come from *others'* traversals — which is precisely "aggregate = behavior, only knowable from many traversals" (Decision Log §12).

### 5.1 What it produces

A **per-(segment, capability-band) empirical pace distribution** — the time a hiker *of a given band* actually takes on *that specific tread*, conditioned on the real grade and surface, learned from many traversals.

```cypher
(:Segment)-[:HAS_COMMONS_STAT]->(:CommonsStat {
    kind:            "pace_on_grade",
    capability_band: "moderate",
    window:          ["2026-04","2026-05","2026-06"],   // rolling, seasonal where relevant
    value:           {median_min_per_km: 17.2, p25: 15.8, p75: 19.1},  // distribution, not a point
    n:               23,                                  // contributor count; n >= k enforced
    computed_at:     datetime()
})
```

**Why a distribution, not a mean** (median + IQR): a single mean hides variance and is fragile to outliers; the spread *is* information the feed should show ("moderate hikers take ~17 min/km here, most between 16 and 19"). It also feeds the confidence presentation (Decision Log §7): a tight IQR → state plainly; a wide one → hedge.

### 5.2 How it beats Naismith — and how it degrades

- **The personal model (Stage 6, Naismith approximation `(distance + ascent×10)/1000`) is the prior;** the commons distribution for the matching band is the **empirical correction**. The Curator's trip-time estimate = personal pace where the user has history, else the commons band-pace for the trail, else the Naismith prior (graceful degradation across three tiers — Decision Log §3 popularity axis: "obscure trail still fully served; popular trail gains the emergent layer").
- **Degrade-and-disclose** (Rule #6, Rule #1): if `n < k`, the commons pace does not exist → fall back to Naismith **and say so** ("estimated; few recorded traversals"). Never a silent fabrication. The commons is **enrichment, never a dependency** (Rule #6) — every trip-time estimate works with zero commons data.

### 5.3 Confidence on the pace stat

Computed-on-read from the three axes (Stage 2 §4), like every other fact:
- **Corroboration** = `n` (contributor count) — and `n >= k` is the *floor*, with confidence rising as `n` grows past it.
- **Freshness** = `window` recency (a pace from this season weighs more; trail conditions change).
- **Authority** = the commons is its own authority tier (measured behavior, not an agency assertion) — and per Rule #2, **low confidence on a thin commons stat must never penalize the trail's rank**; it only hedges the *presentation* of the pace number. Uncertainty ≠ low quality.

---

## 6. Aggregation security — proving the invariant holds

The commons is one of "the two hardest promises" (Decision Log §17). The aggregation read path gets the same access-layer rigor as the personal overlay.

- **`:CommonsStat` and `:CommonsObservation` are unowned world-layer nodes** → readable by everyone, including the anonymous product (Stage 2 §7: "world/commons nodes unowned → public"). They contain no personal data by construction, so public readability is safe — *that is the whole design*.
- **The property test (Decision Log §17, the §6 security/privacy suite):** three assertions, run in CI —
  1. **No path** of any length from any `:CommonsObservation`/`:CommonsStat` to any `:Person`/`:Episode`/`:Outcome` (the severed-link invariant, §2.1). The `writer_hash` is *not* a graph edge and does not constitute a path (§2.3) — the test asserts graph reachability, which the property-lookup revocation flow never creates.
  2. **No `:CommonsStat` is ever computed or returned with `n < k`** (the gate, §3.1) — fuzz the aggregation job with sub-k buckets and assert zero output.
  3. **Endpoint-trim actually fired** (Decision Log §17: "does endpoint-trimming actually fire?") — assert no `:CommonsObservation.trimmed_track` startpoint falls within the trim radius of a private `:Episode` startpoint.
- **`scopedQuery(viewer)` still wraps every read** (Rule #4) — even though commons nodes are public, the *same* single wrapper is the only path to the graph, so a commons query can never accidentally join back to an owned node and leak it. The wrapper's "unowned → public, owned → viewer-scoped" rule handles commons for free.

---

## 7. Other emergent attributes — following the pace template

Once pace calibration ships, the remaining attributes (Decision Log §12) follow the **same pipeline** (severed observation → bucket → k-gate → stratified aggregate → degrade-and-disclose), differing only in the statistic computed. **Why pace is the template:** each is "aggregate = behavior, only knowable from many traversals," each is k-gated, each is enrichment-not-dependency. Build order is by signal cleanliness and value.

| # | Attribute | Statistic | Signal source | Notes / why |
|---|---|---|---|---|
| 7.1 | **Effort topology** ("where people slow/stop") | per-`:Segment` pace deviation + stop-density, banded | the sub-segment pace + `lap`/`record` stops (Stage 6 §1.3 reserved `lap` for exactly this) | needs sub-trail resolution — *why Stage 2 modeled `:Segment` as the conflation unit* (§3); attaches at `:Segment`, not `:CanonicalTrail` |
| 7.2 | **De-facto season** (from *absence*) | months with `n >= k` traversals vs. months empty | the `month` bucket on observations | "absence is signal" — a trail with zero winter observations is *de-facto* closed/unhiked; **stated as inference, hedged** (no traffic ≠ confirmed closure — defer the hard fact to the land manager, per the OSM dog-rule discipline, Decision Log §27); see §7.5 for the differencing risk this presence/absence signal carries |
| 7.3 | **Crowding / solitude by time** | observation density by (day-type, time bucket), banded coarse | `month` + coarse time-of-day bucket | time bucketing must stay coarse (§3.3) — a precise timestamp + obscure trail is a re-ID vector; **bucket to morning/midday/evening**, never the hour; also a presence/density signal → §7.5 |
| 7.4 | **Heat-exposure sections** | per-`:Segment` HR-elevation correlated with NWS temp, banded | `heat_response` signal (Stage 6 §4.4) aggregated | the *only* attribute touching HR — extra care: HR never leaves the private side; only the **derived "this segment runs hot for moderate hikers" band-conclusion** crosses (Rule #5 again) |

**Explicitly skipped** (Decision Log §12, unchanged): scenery/subjective ratings ("reviews again" — the thing the passive commons exists to *replace*), noisy reroute detection, sparse completion rates. *Why:* these are either low-signal/high-noise or they reintroduce the social-review substrate the whole product is defined *against* (Decision Log §2, §25).

**Selection-bias caveat carries to all of them** (Decision Log §12): frequent watch-owners ≠ everyone. The commons is **less biased than reviews, not unbiased** — disclosed, not hidden. *Why disclose:* honesty is the product (Rule #1); an aggregate that hides its sampling bias is the AllTrails-review failure mode in new clothes.

### 7.5 The one place k-anonymity is weak: snapshot-differencing on presence/absence

🔶 The presence/density attributes (§7.2 de-facto season, §7.3 crowding) publish **counts and absence** on possibly-sparse obscure trails — exactly the cohort the product makes first-class (Decision Log §3). The static k-gate (§3.1) defends a single release, but **not the cross-release differencing case:** an attacker who diffs successive monthly `:CommonsStat` snapshots can observe a bucket *cross* the k threshold (n: 4 → 5) between refreshes and infer that one specific new contributor's traversal appeared in that exact month/segment/band — re-identifying the marginal contributor even though every individual snapshot satisfies `n ≥ k`. The pace stat (§5) is less exposed because it publishes a distribution, not a raw presence indicator, but season/crowding publish presence directly.

**Posture (v0):** acknowledge, defer the fix. **Recommend, when these attributes ship:** *either* suppress buckets whose `n` is within a small margin of `k` until they clear it comfortably (a hysteresis band, e.g. publish only at `n ≥ k+2`), *or* add Laplace noise to the published counts (the §9 DP upgrade applied narrowly to count-based stats first). *Why defer the full fix:* pace ships first (§5) and is the least exposed; season/crowding are later in the build order, by which point the DP chokepoint (§9.2) exists. *Why name it now:* it is the one threat the headline "k = privacy floor" claim does **not** fully cover, and the honesty promise (Rule #1) means stating where the mechanism is weak rather than implying k closes every gap.

---

## 8. The T6 gate — what must resolve before anything public

**Nothing in the commons goes public until T6 resolves** (workplan Stage 9 gate; Decision Log §27 marks this "a Stage-2 schema constraint" now coming due). Two independent gates:

### 8.1 OSM / ODbL (Decision Log §27)

The commons is a statistical layer derived from many traversals — but those traversals are matched to trails whose geometry is **OSM-derived** (the spine, Stage 1 §5.1). A public commons cross-referenced against OSM geometry is a **Derivative Database** → ODbL share-alike triggers on public conveyance. **Three resolved escape routes** (Decision Log §27, §28; pick before launch, do not relitigate):
1. **Accept ODbL** on the conflated database (attribution + share-alike on the DB layer), **or**
2. **Collective Database** — keep the OSM-derived `:SourceRecord` layer separate/non-cross-referencing (Stage 2 §3 made this *free*: "OSM-originated facts only ever live on `:SourceRecord {source:"OSM"}`" → separable), **or**
3. **Produced Work** — expose only the rendered aggregate output (the pace number, the band), not the underlying database.

**Recommend route 2 or 3** for the commons specifically — *why:* the commons statistic (band pace, effort topology) is a *Produced Work* over behavior, not a redistribution of OSM geometry; serving the derived number while keeping the OSM `:SourceRecord` layer non-conveyed is the lightest-obligation path and the schema already supports it for free.

### 8.2 Consent (Rule #8, Decision Log §12, §14)

Commons contribution has its **own explicit opt-in, separate from person-to-person sharing grants** (Decision Log §12: "own consent, separate from grants"; §11: grants are orthogonal — Carter can contribute anonymously while sharing nothing with Josh). The consent must disclose, in plain terms:
- **What is contributed** (de-identified band + trimmed track + bucketed totals — never raw biometrics or precise location).
- **The irreversibility** (§2.3): pre-aggregation contributions are deletable; **post-aggregation, the individual contribution is unrecoverable** (Stage 5 §6; Decision Log §14 "a deletion path for commons contributions — harder once aggregated"). This is *why* k-gating + capability-banding exist (so an unrecoverable contribution is never a recoverable *individual*).
- **The selection-bias honesty** (§7).

**Consent gates *exposure*, not the *write*.** The forked write is **designed** to accrete `:CommonsObservation` rows from day one (T3, by construction) — though the write itself is **not yet built (gap-audit C1)**. Accretion is permitted pre-consent precisely because the write is unlinkable — the severed, de-identified, endpoint-trimmed observation (§2) carries no path to a person and no raw quasi-identifier, so accreting it is not a contribution *of identifiable data*. What consent governs is whether a contributor's rows are ever **folded into a public aggregate**; the structural de-identified write is not itself a privacy event. This is the precise reading of Decision Log §12's "build now... dormant until volume": the *substrate accretes structurally* (once the write ships), while *public exposure is consented*. **Public-exposure default: OFF** — a contributor's data is excluded from every public aggregate until they opt in.

🔶 **Open (pending T6 legal/privacy read):** whether pre-consent observations (accreted before a user opts in) become retroactively eligible on opt-in, or only post-consent observations count toward aggregates. **Recommend post-consent only** — *why:* even though the pre-consent write is structurally unlinkable and therefore permissible, "we aggregated data you contributed before you agreed" is the wrong message to send; counting only post-consent observations keeps the consent story clean at the cost of a slightly slower ramp. This is a presentation/ethics call, not a structural one — the write's privacy posture is settled **in design** (permitted, unlinkable), though the write itself is unbuilt (C1); only the eligibility boundary is open.

---

## 9. Differential-privacy posture

Decision Log §12 names DP as "the principled endpoint" — Stage 9 fixes the posture without over-building it for a single-household v0.

### 9.1 Posture: k-anonymity now, DP as the named upgrade path — not v0

🔶 **Recommend: k-anonymity + bucketing + banding as the v0 mechanism; differential privacy designed-for but not implemented until the commons is genuinely multi-contributor and public.** *Why this order:*
- **k-anonymity is the right primitive for *this* data.** The commons publishes **grouped aggregate statistics** (per-band, per-segment distributions), which is exactly what k-anonymity protects. DP's strength is defending against *repeated adaptive queries* on a dataset; the commons is not a query API — it is a small set of precomputed, monthly-refreshed `:CommonsStat` nodes. The repeated-query attack surface DP defends is mostly absent by design (§3.4: no aggregation in the request path). **The one residual exception is snapshot-differencing on the presence/absence stats (§7.5)** — DP on counts is the named fix there, applied narrowly first.
- **DP has a real cost: noise.** Calibrated noise on a thin commons (the lesser-traveled trails we made first-class, Decision Log §3) would **degrade exactly the sparse-trail signal that needs the most help** — the worst place to spend a privacy budget. k-gating is a cleaner fit for the distribution stats: it *withholds* below the floor rather than *noising* a thin sample into uselessness.
- **DP is the principled endpoint for the *public, many-contributor* future** (Decision Log §12), where the query surface widens and the contributor base is large enough that calibrated noise costs little relative to the sample. Naming it now keeps the option; implementing it now would tax the v0 commons for a threat that (outside §7.5) doesn't yet exist.

### 9.2 What the DP-ready design preserves

So DP can slot in later without retrofit:
- **Aggregation is already centralized** in one batch job (§3.4) and one k-gate — the single place Laplace/Gaussian noise on counts and a privacy-budget accountant would be added (and the first place §7.5's count-noise lands). *Why this matters:* DP added at one chokepoint is tractable; DP retrofitted across a scattered read path is not.
- **Statistics are already bucketed/banded** (§3.3, §4) → bounded sensitivity, which is the precondition for calibrating DP noise. Unbounded raw values would have to be clamped first; bands clamp for free.
- **The `writer_hash`** (§2.3) gives a per-contributor handle for a future per-contributor privacy budget, without ever reopening the person link.

### 9.3 The honest caveat (carried, not solved)

DP does **not** fix selection bias (§7) — it bounds *individual disclosure*, not *population representativeness*. A perfectly DP commons of frequent-watch-owners is still a commons of frequent-watch-owners. We **disclose** the bias (Rule #1) rather than claim a privacy mechanism erases it. *Why state this explicitly:* conflating "differentially private" with "unbiased" is a common and dangerous error; the two are orthogonal, and the product's honesty promise (Rule #1) requires keeping them so.

---

## 10. What Stage 9 deliberately defers

- **The exact k value, trim radius, and band boundaries** — all 🔶, **tuned against real accreted volume** before public release (§3.2, §2.2, §4.2). v0 starts at k=5 / 250m / seed band cutoffs and re-fits per region.
- **DP implementation** — designed-for (§9.2), built only at public-multi-contributor scale; the narrow count-noise/hysteresis fix for snapshot-differencing (§7.5) lands when the season/crowding attributes ship.
- **Cross-region / national aggregation** — v0 commons is per-region (Shenandoah + GWJ pilot), matching the corpus extent (Decision Log §5); national rollup follows national corpus.
- **Retroactive vs. post-consent eligibility** of pre-opt-in observations (§8.2) — pending the T6 legal/privacy read.
- **The always-on aggregation cadence** — the aggregation batch job's schedule rides on the same always-on infra decision deferred to Stage 8 (Decision Log §8, §16); until then it runs on machine-wake like the watch sync (Stage 6 §2.1).

---

## 11. Stage 9 decisions

| # | Decision | Status |
|---|---|---|
| S9-1 | De-identification is three same-transaction transforms (sever link · endpoint-trim · band-substitute); `:CommonsObservation` is **born without a person back-edge**, never a stripped copy; world-layer references are by value, not edge | ✅ (formalizes Stage 2 §6 / Stage 6 §6.2) |
| S9-2 | Unlinkability rests on three independently-testable properties: no back-edge · no raw quasi-identifiers (bucketed/banded only) · trimmed geometry | ✅ |
| S9-3 | `writer_hash = HMAC(secrets-manager salt, member_id)` — deterministic for revocation lookup, non-reversible, not a quasi-identifier; salt never in the graph. Revocation is a **forward property lookup keyed by a re-derived hash, not a graph traversal** → does not violate the no-path invariant (S9-13) | 🔶 (confirm HMAC construction in build) |
| S9-4 | **k = the single confidence floor = the privacy floor** — one config value, two jobs; raising one raises the other by construction | ✅ (Decision Log §7, §11 — load-bearing) |
| S9-5 | k = 5 starting floor; tune upward against real volume before public release | 🔶 |
| S9-6 | Aggregation groups on **coarse buckets** (month · ascent/distance bands · capability band), then counts — k-anonymity on the grouping dimensions, not only contributor count | ✅ |
| S9-7 | Aggregation is a **scheduled batch job**, never in the request path; `:CommonsStat` persists as slow derived data on shared nodes (legitimate graph residency — not a live overlay) | ✅ (Rule #3, Decision Log §8, §12) |
| S9-8 | Capability band computed **contributor-side at write time** (pure arithmetic, no model call), before crossing into the commons; raw pace never enters `:CommonsObservation` | ✅ (Rule #5; S5-11, S6-10) |
| S9-9 | 4 bands (`easy` / `easy-moderate` / `moderate` / `strenuous`), **half-open boundaries** `[lo, hi)`; thresholds **fit to per-region pace quartiles**, not fixed constants. **Supersedes S5-11's divergent band set**; adopts S6-10's labels (the set the writer plumbs) | 🔶 |
| S9-10 | **Pace calibration ships FIRST**: per-(segment, band) empirical pace **distribution** (median + IQR), not a mean; beats Naismith, degrades to Naismith-with-disclosure below k | ✅ |
| S9-11 | Pace model degrades across three tiers: personal history → commons band-pace → Naismith prior; enrichment never a dependency (Rule #6) | ✅ |
| S9-12 | Other emergent attributes (effort topology · de-facto season · crowding-by-time · heat-exposure) follow the **same pipeline**, build-ordered by signal cleanliness; subjective/scenery/reroute/completion **skipped** | ✅ (Decision Log §12, unchanged) |
| S9-13 | Security suite (CI): no observation→person *graph path* · no `:CommonsStat` with `n<k` · endpoint-trim provably fired | ✅ (Decision Log §17 targets) |
| S9-14 | **Snapshot-differencing on presence/absence stats (season, crowding) is the one place k-anonymity is weak**; v0 acknowledges + defers; fix = hysteresis (`publish at n ≥ k+2`) or narrow count-noise when those attributes ship | 🔶 |
| S9-15 | **DP posture: k-anonymity + bucketing now; DP designed-for but deferred** to public-multi-contributor scale (noise would harm the sparse-trail distribution signal we made first-class); count-noise lands first at §7.5 | 🔶 |
| S9-16 | Aggregation centralized at one k-gated chokepoint so DP noise + a budget accountant slot in later without retrofit; bands give bounded sensitivity for free | ✅ |
| S9-17 | **T6 gate (blocks public release):** ODbL handled via Collective-Database / Produced-Work route (Stage 2 §3 made this free) **AND** explicit commons-contribution consent. **Consent gates *exposure*, not the *write*** — de-identified accretion pre-consent is permitted because it is unlinkable; public-exposure default OFF, separate from person-grants | ✅ (gate) — 🔶 retroactive-vs-post-consent eligibility open pending T6 legal read |
| S9-18 | Selection bias is **disclosed, not solved** — DP bounds individual disclosure, not population representativeness; the two are orthogonal and kept so (Rule #1) | ✅ |

> **◆ Phase-3 commons design complete** — the de-identification proof, the k=floor unification, contributor-side banding, the pace-calibration model (first) + the emergent-attribute template, the snapshot-differencing caveat, and the DP posture are fully specified. **Build is gated by volume (dormant aggregation) and by T6 (ODbL + consent) before anything goes public.** The forked write (T3) is **designed to accrete from Phase 0 but is not yet built** (gap-audit C1; Commons Fork epic pending); once it ships, Stage 9 turns that substrate into trustworthy, unlinkable aggregate statistics when the volume and the consent are both there.
