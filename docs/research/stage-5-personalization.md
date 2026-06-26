# Stage 5 — Memory & Personalization (design)

*Workplan Stage 5. Draft v0.1 — June 23, 2026. Builds on Stages 2–4; independent of multiplayer (Stage 8).*

> **STATUS: IMPLEMENTED** — shipped via Epics 001–005 (belief pipeline, outcome card, context assembly) + Epic 010 (commons fork). *(Design below kept as spec provenance.)* Specifies the personal-overlay schema extensions, episode→semantic promotion logic, decay model, context-assembly at query time, watch-data integration discipline, and the privacy model for Stage-5 data. Decisions listed in §7. Honors rules #1, #2, #4, #5, #6, #7, #9, #10.

> **What this produces (per workplan):** belief-store schema (provenance + confidence + timestamp + type) · episode model · **episode→semantic promotion rules** (capability-vs-preference tagging) · decay model · memory retrieval / **context-assembly** (subgraph selection) · watch-data integration discipline · privacy model for Stage-5 data.

---

## 1. Belief store — personal overlay schema

Stage 2 fixed the attachment points (`:Person`, `:Episode`, `:Belief`); Stage 5 fills in the full property set. All nodes carry `owner_id` and are accessible only via `scopedQuery(viewer)` (Stage 2 §7).

### Node: `:Episode`

One completed trip. The primary episodic record.

```cypher
(:Episode {
    episode_id:      UUID,
    owner_id:        String,         // member_id of the Person who did this trip
    trail_id:        String,         // FK → CanonicalTrail.canonical_id
    date:            Date,
    source:          "watch_fit"     // | "manual_add" | "inferred_from_watch_activity"
                     | "watch_activity",
    duration_min:    Integer,        // moving + stopped
    moving_min:      Integer,
    distance_m:      Integer,
    ascent_m:        Integer,
    descent_m:       Integer,
    pace_on_grade:   Float,          // min/km normalized for grade; null if no GPS
    party_members:   [String],       // member_ids or ["ruby"] for the dependent
    conditions_note: String,         // LLM-extracted from outcome card, optional
    watch_activity_id: String,       // external ID from Garmin/Coros; null if manual
    fit_parsed:      Boolean,
    created_at:      DateTime,
    updated_at:      DateTime
})
```

**Edges:**
```cypher
(:Person {member_id})-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)
(:Episode)-[:WITH]->(:Dependent)        // Ruby present; Dependent is :Person-:HAS_DEPENDENT
(:Episode)-[:HAS_OUTCOME]->(:Outcome)
```

### Node: `:Outcome`

The post-hike reflect-back. Minimal: one tap rating plus one delta question.

```cypher
(:Outcome {
    outcome_id:     UUID,
    owner_id:       String,
    episode_id:     String,
    overall:        Integer,    // 1 | 2 | 3  (😞 / 😐 / 🙂)
    delta_question: String,     // the question that was asked (null if skipped)
    delta_answer:   String,     // free text or null
    surfaces_at:    DateTime,   // when the outcome card was shown
    completed_at:   DateTime,   // null if skipped
    skipped:        Boolean
})
```

### Node: `:Belief`

A lasting semantic belief about a Person, Dependent, or trail. Every belief is **provenance-tagged, timestamped, typed, and decaying** (Rule #7). Capability and preference are explicitly separate axes — never conflated.

```cypher
(:Belief {
    belief_id:        UUID,
    owner_id:         String,
    subject_id:       String,        // member_id | dependent_id | canonical_id (what it's about)
    subject_type:     "person"       // | "dependent" | "trail"
                      | "dependent",
    axis:             "capability"   // | "preference" | "constraint" | "taste"
                      | "constraint",
    type:             "stated"       // | "inferred" (never poses as stated — Rule #7)
                      | "inferred",
    key:              String,        // "pace_on_grade_moderate" | "prefers_ridge_trail" | ...
    value:            String,        // "14.5 min/km" | "true" | "low" | ...
    confidence:       Float,         // 0.0–1.0; computed from corroboration_n + recency
    corroboration_n:  Integer,       // # of episodes that support this belief
    source_episode_ids: [String],    // traceable back to episodes (Rule #7)
    created_at:       DateTime,
    last_updated_at:  DateTime,
    decays:           Boolean,       // false for hard constraints; true for taste/preference
    decay_half_life_days: Integer,   // null if decays=false
    confirmed_by_user: Boolean       // user affirmed this belief explicitly
})
```

**Edges:**
```cypher
(:Belief)-[:DERIVED_FROM]->(:Episode)      // one edge per supporting episode
(:Belief)-[:ABOUT]->(:Person|:Dependent|:CanonicalTrail)
```

### Node: `:PhysicalProfile`

Computed capability summary from the belief store. **Capability, not preference** (Rule #7: watch is a good capability sensor, a poor preference sensor). Updated when beliefs change.

```cypher
(:PhysicalProfile {
    profile_id:         UUID,
    owner_id:           String,
    pace_on_grade:      Float,        // min/km normalized; best estimate from episodes
    pace_confidence:    Float,        // corroboration-based
    max_distance_m:     Integer,      // empirical from completed episodes
    max_ascent_m:       Integer,
    heat_response:      String,       // "normal" | "sensitive" — inferred from HR data
    hr_zone2_threshold: Integer,      // bpm; null if no HR data
    typical_season:     [String],     // months with completed episodes
    episode_count:      Integer,
    last_episode_at:    Date,
    updated_at:         DateTime
})
```

### Node: `:PartyProfile`

Party-specific inferences (who hikes together, Ruby's participation rate, pace in group context). Does NOT hold merged constraints — constraint composition happens at query time (Stage 8; Phase-0 single-user: just Josh + optional Ruby).

```cypher
(:PartyProfile {
    profile_id:       UUID,
    owner_id:         String,           // the organizer (Josh)
    party_key:        String,           // sorted(member_ids).join("+")  e.g. "josh+ruby"
    episode_count:    Integer,
    typical_pace_m:   Float,            // observed pace when this party hikes together
    ruby_keep_rate:   Float,            // fraction of solo Josh trips where Ruby came
    created_at:       DateTime,
    updated_at:       DateTime
})
```

### Key `Belief.key` vocabulary (representative, not exhaustive)

| key | axis | subject_type | example value |
|---|---|---|---|
| `pace_on_grade_easy` | capability | person | `"12.3 min/km"` |
| `pace_on_grade_moderate` | capability | person | `"15.8 min/km"` |
| `max_distance_km` | capability | person | `"22"` |
| `heat_sensitivity` | capability | person | `"sensitive"` |
| `prefers_ridge_trail` | preference | person | `"true"` |
| `prefers_loop` | preference | person | `"true"` |
| `avoids_crowds` | preference | person | `"high"` |
| `trail_type_affinity` | taste | person | `"ridge"` |
| `dog_tolerated_pace` | capability | dependent | `"14.0 min/km"` |
| `dog_max_distance_km` | capability | dependent | `"16"` |
| `recalled_positively` | taste | trail | `"true"` |
| `been_on` | constraint | trail | `"2025-09"` |

---

## 2. Episode → semantic promotion

Raw episodes do not directly become beliefs. Promotion requires **evidence and threshold**, and the result is explicitly typed as `inferred` until confirmed.

### Promotion rules

**Capability beliefs** (from measured data — highest confidence):
- After each FIT-parsed episode: update `PhysicalProfile.pace_on_grade` using an exponentially weighted moving average (recent episodes weighted more — §3).
- `max_distance_m` and `max_ascent_m` are the empirical maxima from all completed episodes (not a mean — the user *can* do that).
- `heat_response`: if `hr_zone2_threshold` climbs >15% on episodes tagged with high heat (>28°C, from NWS at time of trip), set `heat_sensitivity = "sensitive"` after 2 such episodes.

**Preference beliefs** (from behavioral + outcome signals — always `inferred`, decaying):
- After N=3 episodes with `overall >= 2` on trails sharing a tag (e.g. `trail_surface:ridge`, `setting:exposed_ridge`): promote `prefers_ridge_trail = true`, confidence = corroboration-weighted.
- After N=3 `overall = 3` episodes on loops vs. out-and-backs: promote `prefers_loop`.
- After outcome card `delta_answer` contains an explicit statement: immediate promotion at `type:stated`, `confidence=1.0` (user stated it), no decay.

**Constraint beliefs** (non-decaying):
- `been_on` is set immediately on `Episode.created_at` — novelty mechanism (the Curator uses it for explore/exploit, §4).
- Hard physical limits (e.g. doctor-stated max HR) enter only via `type:stated` from user input — never inferred from behavior.

**Evidence threshold:** N=3 is the default corroboration floor. Below 3, the belief exists in a **provisional** state (`confidence < 0.4`) and is not injected into the Curator ranking context unless the query has no stronger signal. Above N=10, confidence saturates at ~0.9 (corroboration alone cannot reach 1.0 — recency still matters).

**The capability ≠ preference invariant:** any belief derived from watch/FIT data goes on the `capability` axis. Preference axis beliefs require either explicit user statement or behavioral + outcome convergence (the episode rate + the rating). A 22 km episode means capability = "can do 22 km," not preference = "wants to do 22 km."

---

## 3. Decay model

Preferences drift; capability changes too. Beliefs stale in different ways by axis.

| Axis | `decay_half_life_days` | Rationale |
|---|---|---|
| `capability` | 180 | Fitness changes slowly; a 6-month-old FIT pace is still informative |
| `preference` | 90 | Tastes shift on a seasonal basis; a 3-month-old preference is worth half weight |
| `taste` | 120 | Between capability and preference — terrain affinity is more stable than novelty signals |
| `constraint` | `null` (no decay) | Hard constraints ("Ruby can't do >16 km") are stated, not inferred |

**Decay computation:** weight applied at query time, not stored (same pattern as confidence — store inputs, compute on read):

```python
def decayed_confidence(belief) -> float:
    if not belief.decays:
        return belief.confidence
    age_days = (today - belief.last_updated_at.date()).days
    half_life = belief.decay_half_life_days
    return belief.confidence * (0.5 ** (age_days / half_life))
```

**Recency weighting in EWMA (for `PhysicalProfile.pace_on_grade`):**

```
new_pace = α * latest_pace + (1 - α) * current_estimate   (α = 0.3)
```

Recent episodes weight at 30%; the existing estimate carries 70%. A single outlier episode (bad day) does not flip the profile.

**Episode supersession:** if a newer episode covers the same trail with the same party on the same axis, the old one's contribution is halved at belief-update time (not deleted — it remains for provenance traversal).

---

## 4. Retrieval — context assembly at query time

The risk: injecting the user's entire belief store into every prompt is expensive, noisy, and leaks unnecessary personal data into the model's context window. The goal is a **minimal, relevant subgraph** — not a history dump.

### Assembly strategy

At query time (post-Scout, pre-Curator), the access layer runs a targeted traversal:

```cypher
// Fetch active beliefs for the viewer — decay is computed in Python (not Cypher),
// so we pull all non-expired beliefs and filter after decayed_confidence() is applied.
MATCH (b:Belief)-[:ABOUT]->(p:Person {member_id: $viewer_id})
WHERE b.owner_id = $viewer_id
RETURN b ORDER BY b.last_updated_at DESC LIMIT 50
// Python then applies: decayed_confidence(b) > $confidence_floor → keep top 20
```

```cypher
// Fetch relevant episodes: same trail OR same area as a candidate
MATCH (p:Person {member_id: $viewer_id})-[:DID]->(e:Episode)-[:ON]->(ct:CanonicalTrail)
WHERE ct.canonical_id IN $candidate_ids
RETURN e, ct ORDER BY e.date DESC LIMIT 10
UNION
MATCH (p:Person {member_id: $viewer_id})-[:DID]->(e:Episode)-[:ON]->(ct:CanonicalTrail)
      <-[:CONTAINS]-(a:Area)
WHERE a.area_id IN $candidate_area_ids
RETURN e, ct ORDER BY e.date DESC LIMIT 10
```

The assembled context passed to the Curator contains:
1. **`PhysicalProfile`** — capability summary (pace, range, heat).
2. **High-confidence, non-decayed beliefs** — top-20 by recency.
3. **On-trail episodes** — if any candidate has been hiked before: last visit date + outcome.
4. **Party facts** — if Ruby is in the party: `dog_max_distance_km`, `dog_tolerated_pace`.
5. **`been_on` beliefs** — so the Curator can apply the novelty lever.

What is **NOT injected:**
- Raw FIT track data (too large, private, not useful to the ranking call).
- Full episode history (date-capped to last 18 months to prevent unbounded growth).
- Provisional beliefs below the confidence floor.
- Watch biometric archive (HR time series, etc.) — raw biometrics stay in the belief store and are never passed to a model call.

### Curator prompt injection

The context block passed to the Curator's judgment-tier call:

```
[PERSONAL CONTEXT — private, not for disclosure]
Capability: pace ~15.8 min/km on moderate grade, max 22 km, max 1100m ascent.
Preferences (inferred, 3+ episodes): prefers ridges, prefers loops.
Ruby: max 16 km, pace ~14 min/km.
Novelty: Old Rag visited 2025-09 — apply novelty discount.
[END PERSONAL CONTEXT]
```

The Curator is instructed: **never output raw personal data verbatim in the feed card** — only its *effect* on the ranking and rationale ("good ridge terrain, within Ruby's range").

---

## 5. Watch data integration

Watch integration is Stage 6; Stage 5 defines what the memory layer accepts and what it refuses.

### What the belief store accepts from watch data

| Data | Source | Accepted as |
|---|---|---|
| Completed route (GPS track) | FIT file | `Episode.{distance_m, ascent_m, pace_on_grade}` — capability inputs |
| HR on climbs / zone-time | FIT file | `PhysicalProfile.hr_zone2_threshold`, `heat_response` — capability |
| Moving time vs. stopped time | FIT file | `Episode.{moving_min, duration_min}` |
| Body Battery / recovery | Garmin Connect | **Readiness filter only** — never enters the belief store |
| Training readiness / HRV | Garmin / Coros | **Readiness filter only** — never enters the belief store |

### What watch data is explicitly NOT allowed in the belief store

- **Live readiness scores** — these are the readiness filter, a user-toggled JIT query parameter (Decision Log §10), not a persistent belief. They have a short freshness window; persisting them is meaningless and misleading.
- **Capability as preference.** A high HR on a climb does not imply the user dislikes climbs. A long episode does not imply preference for long hikes. The belief store enforces this by column: FIT-derived data goes to `axis:"capability"` only.
- **Raw biometric archive** — HR time series, detailed sleep data, VO2max estimates. These stay in the watch vendor's system; the belief store holds only the *derived capability signals* extracted at ingest time. This limits both the privacy surface and the personal-data footprint.

### Disclosure on watch enrichment

Any feed card or Curator rationale that used watch-derived capability data to inform a ranking carries a **disclosure tag** (per Rule #6: every watch use degrades-and-discloses):

> *"Matched to your typical pace range (from past hikes)."*

This is shown in the card's rationale section, not a banner. The belief store's `source_episode_ids` makes the provenance traversable by the user via the belief-store UI.

---

## 6. Privacy model

### Private-by-default (all Stage-5 data)

`:Episode`, `:Outcome`, `:Belief`, `:PhysicalProfile`, `:PartyProfile` all carry `owner_id`. `scopedQuery(viewer)` enforces visibility — no Stage-5 node is reachable without an explicit viewer match.

### Share-by-exception: grant structure for Stage-5 data

The full grant model is Stage 8; Stage 5 defines the **sensitivity tiers** for its data so Stage-8 grants can use them:

| Tier | Data | Default |
|---|---|---|
| T1 | Derived capability beliefs (`pace`, `max_distance`, physical profile summary) · preference beliefs | Private; grantable to household members |
| T2 | Episode history (trail, date, duration, party) · outcomes | Private; grantable explicitly, context-scoped to joint planning only |
| T3 | Raw watch biometric data (HR archive) · GPS track geometry | **Not held in the belief store** — never grantable because never stored |

**Grant semantics for Stage-5 data:**
- A T1 grant lets the grantee see derived beliefs, not the episodes behind them. "Share the conclusion, not the substrate" (Rule #5). The grantee can't traverse `DERIVED_FROM` to see which trips generated the belief.
- A T2 grant exposes episode records but is **context-scoped**: the data enters joint-planning queries only, never the grantee's solo feed.
- No grant exposes T3 — it doesn't exist in the graph to expose.

### Commons provenance chain for Episodes

The forked write (T3, Stage 2) applies to episodes too: when an episode is created, it also writes a `:CommonsObservation` with:
1. **Person→observation link severed** at write time (not the episode node — the commons observation is a new node with no edge back to `:Person`).
2. **Endpoint trimming**: the GPS track (if present) has the first and last 250m stripped before the commons observation is written. This is the primary re-identification defense for out-and-back tracks that start at home.
3. **Capability-band substitution**: raw pace is bucketed into a capability band (`"easy-moderate"` / `"moderate"` / `"moderate-strenuous"` / `"strenuous"`) before the commons write. The commons observation carries the band, not the raw value.

The private episode retains the full data; the commons observation is irreversibly de-identified. Revocation of the commons contribution is possible until `n >= k` (the contributor set is small enough to delete without aggregated data existing); after aggregation, deletion of the individual contribution is no longer recoverable — disclosed in onboarding consent.

---

## 7. Stage 5 decisions

| # | Decision | Status |
|---|---|---|
| S5-1 | `:Episode` is the primary episodic record; `:Outcome` is a separate linked node (not a property bag on Episode) | ✅ |
| S5-2 | Belief `axis` has four values: `capability` / `preference` / `taste` / `constraint`; watch-derived data can only go on `capability` | ✅ |
| S5-3 | Belief `type` is `stated` vs. `inferred`; `inferred` never poses as `stated` in the feed | ✅ |
| S5-4 | Promotion threshold N=3 for behavioral inferences; below N=3 the belief exists as provisional (confidence < 0.4) | 🔶 |
| S5-5 | Decay computed on read (not stored); half-lives: capability 180d, preference 90d, taste 120d, constraint=never | 🔶 Measure against real episodes — adjust if too aggressive |
| S5-6 | EWMA α=0.3 for pace-on-grade rolling update | 🔶 Tune in the Stage-6 spike |
| S5-7 | Context assembly at query time: top-20 beliefs by recency + relevant episodes (same trail/area) — no full-history dump | ✅ |
| S5-8 | Raw biometric archive (HR time series, VO2max) is NOT held in the belief store — capability signals extracted at ingest only | ✅ |
| S5-9 | Body Battery / live readiness: readiness filter only, never persisted as a belief | ✅ |
| S5-10 | Endpoint trimming = 250m strip on commons write; raw track retained in private episode | 🔶 Adjust threshold pending re-identification analysis |
| S5-11 | Capability-band for commons write: 4 bands (easy-moderate / moderate / moderate-strenuous / strenuous); computed contributor-side | 🔶 Band thresholds: tune against pace distribution in Stage 9 |
| S5-12 | T1/T2 grant sensitivity tiers defined here; grant enforcement deferred to Stage 8 | ✅ |
| S5-13 | `:Route` node (custom itineraries) deferred; Stage 5 uses CanonicalTrail as the episode target | ✅ (per Stage 2 §2) |
| S5-14 | Memory eval harness (memory-on vs. memory-off, recommendation quality) — thin version runs in Stage 5 alongside truthfulness eval; deep methodology is Stage 7 | 🔶 |
