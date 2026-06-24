# Novelty Filter (design)

*Workplan Stage 5 / unblocks the downstream Novelty-filter epic (Epic 006, named in epic-003). Draft v0.1 — June 24, 2026. Extends `stage-5-personalization.md` §1 (the `been_on` constraint belief), §2 (constraint promotion), §4 (the "novelty lever" referenced but left unspecified). Depends on context assembly + populated `been_on` beliefs (`docs/process/plan-analysis.md` dependency order: context assembly → novelty filter). Honors rules #1, #2, #4, #5, #7.*

> **Status: DESIGN.** Specifies how `been_on` beliefs surface in the Curator, whether novelty is a hard filter or a soft discount (recommendation + reasoning), the concrete discount rule, and how it preserves the rule-#2 invariant (confidence never penalizes rank, decision-log §7) and the explore/exploit principle (decision-log §9: *memory too good at predicting you makes you smaller*).

> **Legend:** ✅ decided · 🔶 recommended, confirm · ❓ open.

---

## 1. What novelty is, and what it is not

The novelty filter answers one question at rank time: *has the viewer been on this trail before, and how recently?* It is a **Curator concern only** — novelty lives with taste and season (decision-log §28 engine shape: "Curator = guardrails + Opus-tier taste ranking"), never with the Verifier (constraints) and never with the guardrails (hard filters).

Three things it is **not**, stated up front because each is a known trap:

1. **Not a confidence signal.** Novelty is orthogonal to how sure we are about a trail's facts. A trail you've hiked twice is *high-confidence* and *low-novelty* simultaneously — the two axes must never be folded into one number (rule #2; §5 below).
2. **Not a guardrail.** A repeat is not a violation. Re-hiking Old Rag is a perfectly valid recommendation; it is just *less surprising*. Guardrails are deterministic-code rejections (closed trail, unavailable permit, off-leash-required with Ruby) — novelty is none of these.
3. **Not a preference belief.** `been_on` is a `constraint`-axis fact (a record of what happened, S5 §1 vocabulary table), not a `preference`-axis inference that the user *wants* repetition or variety. Whether the user is a re-hiker or a completionist is a *separate* future preference belief (`prefers_novelty`, §6), not assumed by this filter.

---

## 2. How `been_on` beliefs surface in the Curator

### 2.1 The belief (extends S5 §1)

`been_on` is a `:Belief` with `axis:"constraint"`, `subject_type:"trail"`, `decays:false`, set on `Episode.created_at` (S5 §2). Human-readable `value` is a **year-month string** (e.g. `"2025-09"`). One `been_on` belief per (viewer, trail); a re-hike updates it in place.

> 🔶 **N-6 — property + provenance additions (S5 §1).** `been_on` carries two **dedicated** structured properties so novelty recency is exact and the discount (§4) is computable in deterministic Python:
> - `last_visit_date` (Date) — the most recent visit. **Novelty keys off this property, never the belief's `last_updated_at` or `created_at`** (§6.2 explains why this matters).
> - `visit_count` (Integer) — number of visits. **This is a fresh, dedicated property. It does NOT reuse `corroboration_n`.**
>
> The year-month `value` stays for the legible belief store.
>
> **Why a dedicated `visit_count`, not `corroboration_n` (the rule-#2 fix):** under the schema (`schema.cypher:279`) and S5 §2, `corroboration_n` is *the corroboration axis of the confidence score* ("# of episodes that support this belief"; "above N=10, confidence saturates"). If `been_on`'s visit count rode on `corroboration_n`, then visit count would be a confidence input — and §4 also feeds visit count into the rank discount. That is exactly the back-door §5 must foreclose: one field simultaneously feeding confidence *and* rank. `been_on` therefore **carries no confidence semantics** — its `corroboration_n` is not maintained and not read; recency/repetition live solely in `last_visit_date` / `visit_count`.
>
> **Provenance on re-hike (rule #7).** Each re-hike, in addition to bumping `last_visit_date`/`visit_count` and `value`, **appends the new episode id to `source_episode_ids` and adds a `(:Belief)-[:DERIVED_FROM]->(:Episode)` edge** (S5 §1 edge set). Without this, "which trips are these N visits?" stops being a traversal and provenance is lost.
>
> **Migration note.** `been_on` is a *new* belief shape: the committed `graph/schema.cypher` only ever instantiates `(:Belief)-[:ABOUT]->(:Person)` (line 293; the §8 edge-comment block at line 190 lists `->(:Person)` only). A trail-subject `been_on` belief with `ABOUT->(:CanonicalTrail)` and the two new properties is **not** in the artifact today. N-6 therefore requires a **forward-only Cypher migration in `graph/migrations/`** (decision-log §28 versioning convention) — it is not a no-op. S5 §1 already lists `:CanonicalTrail` as a valid `ABOUT` target, so this is additive, not a shape conflict.

### 2.2 The subgraph traversal

`been_on` is fetched in the **same** context-assembly pass already specified in S5 §4 (item 5: "*`been_on` beliefs — so the Curator can apply the novelty lever*"). The per-candidate join is restricted to trails actually in the shortlist (Scout output, capped at K — decision-log §29 cost lever), never corpus-wide, and runs **through the `scopedQuery(viewer)` wrapper** — the only path to owned data (decision-log §28, rule #4). The wrapper injects the viewer scope; spec code never hand-writes an `owner_id` filter, which is the bypass the wrapper exists to prevent:

```python
# Per-candidate novelty lookup — scoped via the wrapper, restricted to shortlist.
rows = scopedQuery(viewer).run(
    """
    MATCH (b:Belief {subject_type: "trail", key: "been_on"})
          -[:ABOUT]->(ct:CanonicalTrail)
    WHERE ct.canonical_id IN $candidate_ids
    RETURN ct.canonical_id  AS trail_id,
           b.last_visit_date AS last_visit,
           b.visit_count     AS visits
    """,
    candidate_ids=shortlist_ids,
)
# scopedQuery binds owner_id = viewer; the query body never names it (rule #4).
```

A candidate with no `been_on` row is simply novel (`novelty = 1.0`). Absence of memory is the high-novelty case — never an error.

### 2.3 What reaches the Curator prompt

The Curator receives novelty as a **per-candidate scalar already computed in deterministic Python** (§4), not as raw belief text it must reason over. This keeps the lever auditable and stops the judgment-tier LLM from improvising its own recency math. The injected block is bounded by the shortlist cap K (decision-log §29 cost lever), so it never grows the judgment-tier prompt corpus-wide. Extending the S5 §4 example:

```
[PERSONAL CONTEXT — private, not for disclosure]
...
Novelty (1.0 = never hiked, 0.0 = hiked this month, repeatedly):
  Old Rag Loop ............ 0.55  (last hiked 2025-09, 2 visits)
  Riprap Hollow ........... 1.00  (new to you)
  Whiteoak Canyon ......... 0.78  (last hiked 2024-04, 1 visit)
[END PERSONAL CONTEXT]
```

The Curator follows S5 §4's disclosure rule: when a known trail ranks, the rationale may say *"you've hiked this before — surfacing it because conditions are unusually good"* but must **never** dump raw visit history into the feed card. Share the conclusion, not the substrate (rule #5).

---

## 3. Hard filter vs. soft discount — recommendation

**🔶 Recommended: SOFT ranking discount, not a hard filter.** Confirm against the first real multi-episode dataset.

### 3.1 Reasoning

A hard filter ("never show a trail you've hiked") is wrong for this product for four reasons:

1. **It contradicts the product thesis.** The differentiation is live verified synthesis for *right now, for me*. The single most valuable recommendation this app can make is often *"your favorite ridge, and today the smoke has cleared and the streamflow is perfect."* A hard novelty filter deletes exactly that. Re-visiting a known-good trail under freshly-verified good conditions is a feature, not a failure.
2. **It makes memory hostile.** A hard filter means *the more you use the app, the smaller your feed gets* — every hike permanently removes a trail. That is the inverse of a calm utility; it punishes engagement with attrition.
3. **It collapses two signals into a binary.** "Hiked yesterday" and "hiked three years ago" are radically different, and a hard filter treats them identically. Recency is continuous; the lever must be too.
4. **It belongs to no other layer.** Hard exclusions live in the guardrails (deterministic, safety/correctness — decision-log §28). Novelty is a *taste* dimension. Putting it in the hard-filter set would make a known trail as un-rankable as a *closed* one — a category error.

The explore/exploit principle (decision-log §9) cuts the *same* way: the danger is a system that *over-exploits* (only ever your three known favorites) **and** the opposite failure of a system that *over-explores* (refuses to ever re-show what you love). A soft discount is the only mechanism that tunes that balance; a hard filter is stuck at one extreme (pure explore). The discount is the explore/exploit dial.

### 3.2 The one bounded exception

The **only** hard-filter case is user-stated, not inferred: if the user explicitly sets a session intent like *"somewhere new"* (a query-time filter, a future Epic 006 surface), novelty becomes a hard gate **for that session only** — drop everything with `novelty < θ_new` (🔶 θ_new = 0.5). This is a *stated constraint the user typed*, identical in spirit to "no dogs-required trails when Ruby's along," so it lives in the Scout/guardrail filter set for that session, not in the Curator. Default (no such intent) = soft discount only.

---

## 4. The discount formula

### 4.1 Novelty score (deterministic, computed pre-Curator)

```python
def novelty_score(last_visit: date | None, visit_count: int, today: date) -> float:
    """1.0 = never hiked (or effectively forgotten); -> 0 = hiked very recently / often.
    Pure function. Inputs are ONLY last_visit and visit_count — no confidence,
    freshness, or authority value can enter (rule #2 by construction; §5)."""
    if last_visit is None:
        return 1.0                                   # never been — fully novel
    months = (today - last_visit).days / 30.44
    recency = 1.0 - 0.5 ** (months / HALF_LIFE_M)    # 0 at visit, -> 1 as it ages
    repeat_penalty = 0.85 ** (visit_count - 1)       # each prior visit shaves a little
    return clamp(recency * repeat_penalty, 0.0, 1.0)
```

- `HALF_LIFE_M = 9` months 🔶 — a trail hiked 9 months ago is "half fresh again." Rationale is the **appetite to re-hike returns within a season-and-a-half**; tune against real re-hike intervals. *(This is novelty re-rise, a distinct mechanism from the belief-confidence decay half-lives in S5 §3 — those govern how a belief's confidence stales, not how a trail's novelty recovers. The two are not anchored to each other.)*
- `repeat_penalty` makes a 5th visit score lower than a 1st at equal recency — a trail you return to constantly is the *least* surprising, even if the last visit has aged. Floors out gently (0.85^n), never to zero.
- The signature takes **only** `last_visit` and `visit_count`, and `visit_count` is the dedicated `been_on` property that carries no confidence semantics (§2.1, N-6). The function is therefore structurally incapable of reading any confidence component — see §5 for why the separation is real and not merely apparent.

### 4.2 Applying the discount to rank

The Curator produces a taste/fit score `S ∈ [0,1]` per candidate (quality of match — terrain, season, party-suitability, freshly-verified conditions). Novelty applies as a **bounded multiplicative discount**, *after* `S`, never inside it:

```python
adjusted = S * (1 - λ * (1 - novelty))      # λ = novelty weight, default 0.25
```

- `novelty = 1.0` (new trail) → `adjusted = S` (no discount; novelty never *boosts* above merit, it only gently discounts repetition — sibling to rule #2's "confidence shapes presentation, not rank").
- `novelty = 0.0` (hiked this month, repeatedly) → `adjusted = S * (1 - λ)` = `0.75·S` at λ=0.25 — a **25% maximum** haircut, never elimination.
- `λ = 0.25` 🔶 is the explore/exploit dial. λ=0 → pure exploit (favorites dominate forever); λ→1 → near-hard-filter (over-explore). 0.25 keeps a genuinely-better repeat ahead of a mediocre novel trail while letting a *roughly-tied* novel trail win. Tune in the Stage-7 memory eval (memory-on vs memory-off vs outcomes, S5 §7 / S5-14).

**Why multiplicative-after-`S`, not a term inside `S`:** keeping novelty as a post-multiplier on the Curator's merit score means (a) it is fully auditable in a trace — read `S` and `adjusted` side by side and the novelty effect is exact; and (b) a high-merit trail (`S` near 1) can absorb the discount and still rank well, so the favorite-under-great-conditions case (§3.1) survives. A novel trail only wins when it is *close on merit* — precisely the explore behavior we want.

### 4.3 Worked check

| Trail | `S` (merit) | novelty | adjusted (λ=0.25) | Outcome |
|---|---|---|---|---|
| Old Rag (favorite, perfect conditions) | 0.95 | 0.55 | 0.84 | Still surfaces — great repeat beats mediocre new |
| Riprap Hollow (new, decent) | 0.80 | 1.00 | 0.80 | Edged out narrowly — but in reach |
| Whiteoak (new, also great) | 0.92 | 0.78 | 0.87 | Beats Old Rag — near-tie on merit, novelty breaks it |
| Old Rag (hiked last week) | 0.95 | 0.10 | 0.74 | Discounted hard but not deleted — soft, not hard |

Novelty breaks near-ties toward exploration and discourages just-hiked repeats, while never deleting a clearly-superior known trail. That is the explore/exploit balance made concrete.

---

## 5. Invariant: confidence never penalizes ranking (rule #2 / decision-log §7)

This is the load-bearing constraint, and the filter is designed so it **cannot** be violated:

1. **Separate inputs, enforced by signature AND by field separation.** `novelty_score()` takes `(last_visit, visit_count, today)` — no parameter through which confidence, freshness, or authority could enter. Critically, `visit_count` is a **dedicated `been_on` property with no confidence semantics** (§2.1, N-6); it is *not* `corroboration_n`. This second point is what makes the first one true: if visit count rode on `corroboration_n` (a confidence axis), the signature would be clean while the value still smuggled confidence into rank. With the fields divorced, the separation is physical, not cosmetic.
2. **Novelty discounts repetition; confidence shapes *presentation*.** They act on different things: novelty multiplies the *rank score*; confidence sets the *floor, the phrasing, and the safety flag* (decision-log §7) and is forbidden from touching rank. A lesser-traveled, low-corroboration trail is therefore *advantaged* by novelty (almost always new → `novelty = 1.0`) and *untouched* in rank by its low confidence — reinforcing the "lesser-traveled trails are first-class" guarantee (decision-log §3, line 64), not threatening it.
3. **Property test as a guardrail (mirrors the access-layer invariant test).** Two assertions, not one:
   - *Holding visit history fixed, varying a candidate's confidence/freshness/authority inputs produces an identical `adjusted` score.*
   - *Varying `corroboration_n` on any belief produces an identical `novelty_score` and `adjusted` score* — i.e. confidence corroboration cannot reach rank through the novelty path.
   The second assertion is what proves the §2.1 field separation holds in code (without it, the first test would pass while visit-count-as-corroboration still leaked). This sits alongside the decision-log §28 "does the access layer ever emit an ungranted node?" property test as a first-class invariant check.

---

## 6. The deeper principle — *memory that predicts you too well makes you smaller*

Decision-log §9 names the failure mode: a personalization system that models you perfectly converges your world onto your past. The novelty filter is this project's structural answer; three design choices encode it:

1. **The discount is the explore dial, and it defaults non-zero.** λ=0.25 means the system *always* spends a little rank budget on the unfamiliar, by default, without being asked. Exploitation is never total. A user who has hiked the same five trails fifty times will still, every weekend, see one or two genuinely new options surfaced *because* their familiarity was discounted — the app actively widens the world rather than mirroring the past back.
2. **Novelty resists its own forgetting.** `been_on` is a non-decaying `constraint` belief (§2.1; S5 §3 constraint axis = no decay) — the system *remembers permanently that you've been somewhere* (provenance intact, rule #7). But the *novelty score* re-rises over months (§4.1 half-life), so the trail *feels fresh again* with time. Memory is honest about the fact without being tyrannical about the consequence. **This re-rise reads `last_visit_date`, not the belief's `last_updated_at` or `created_at`** — a re-hike bumps `last_updated_at` and the year-month `value` in place, so keying novelty off `last_updated_at` would conflate the two; the dedicated `last_visit_date` property (N-6) is therefore load-bearing here, not optional.
3. **Capability ≠ preference, extended to novelty.** This filter never infers that a re-hiker *wants* repetition or that an explorer *wants* variety — `been_on` is behavioral history, not a preference (rule #7; §1.3). A future **`prefers_novelty`** preference belief (promoted via the S5 §2 N=3 outcome-convergence path) could *tune λ per user* — a self-described completionist gets λ→0, a "show me somewhere new" user gets λ↑. That is a clean future extension (Epic 006+), explicitly **out of this filter's scope**, and deliberately gated behind stated/confirmed preference so the app never assumes who you are from what you did.

---

## 7. Decisions

| # | Decision | Status |
|---|---|---|
| N-1 | Novelty is a **Curator-only** lever (with taste/season/party); never a Verifier constraint or a guardrail | ✅ |
| N-2 | Novelty acts as a **soft multiplicative discount**, not a hard filter — re-visiting a known-good trail under good conditions is a feature | 🔶 confirm on first multi-episode data |
| N-3 | The sole hard-gate case is a **user-stated** session intent ("somewhere new"), handled in Scout/guardrail for that session only — never inferred | ✅ |
| N-4 | `novelty_score()` is deterministic Python from `(last_visit, visit_count)` only; `visit_count` is a dedicated property with no confidence semantics — **structurally cannot** read confidence/freshness/authority (rule #2 by construction) | ✅ |
| N-5 | Discount: `adjusted = S · (1 − λ·(1 − novelty))`, λ=0.25; novelty re-rises with a 9-month half-life + a per-visit repeat penalty | 🔶 tune λ, half-life, repeat factor in Stage-7 memory eval |
| N-6 | `been_on` gains dedicated `last_visit_date` (Date) + `visit_count` (Integer) properties (**not** `corroboration_n`); keeps year-month `value`; each re-hike appends `source_episode_ids` + a `DERIVED_FROM` edge. Requires a **forward-only migration in `graph/migrations/`** (trail-subject `ABOUT->(:CanonicalTrail)` + new props are not in `schema.cypher` today) | 🔶 confirm; migration required |
| N-7 | Two-part property test: (a) holding visit history fixed, varying confidence inputs must not change rank; (b) varying `corroboration_n` must not change novelty/rank — proves the field separation. Sits with the decision-log §28 access-layer invariant tests | ✅ |
| N-8 | Per-user λ tuning via a future `prefers_novelty` preference belief is **out of scope** here, gated behind stated/confirmed preference (capability ≠ preference) | ✅ (deferred to Epic 006+) |

**◆ Novelty-filter design complete** — `been_on` surfacing, the soft-discount recommendation, the formula, the rule-#2 guarantee (now sound: visit count is divorced from `corroboration_n`), and the explore/exploit encoding are concrete enough to implement. Unblocks Epic 006; build depends on context assembly + populated `been_on` beliefs (plan-analysis.md dependency order) and the N-6 migration. Open items are empirical-tuning 🔶 (λ, half-life, repeat penalty), best closed by the Stage-7 memory eval, plus the N-6 migration to land.
