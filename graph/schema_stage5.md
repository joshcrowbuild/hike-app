# graph/schema_stage5.md — Stage 5 personal-overlay additions (schema v0.2.0)

Applied in schema.cypher §6–8. Design spec: docs/research/stage-5-personalization.md.

---

## Nodes added

| Node | Key property | owner_id? | Purpose |
|---|---|---|---|
| `Episode` | `episode_id` | yes | One completed trip; the primary episodic record |
| `Outcome` | `outcome_id` | yes | Post-hike reflect-back card (rating + delta question) |
| `Belief` | `belief_id` | yes | Lasting semantic belief: provenance-tagged, typed, decaying |
| `PhysicalProfile` | `profile_id` | yes | Computed capability summary; one node per Person |
| `PartyProfile` | `profile_id` | yes | Observed pace/composition when a specific party hikes together |
| `Dependent` | `dependent_id` | no (sub-node) | Non-account household member (Ruby); linked from Person |

---

## Edges

```
(:Person)-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)
(:Episode)-[:WITH]->(:Dependent)
(:Episode)-[:HAS_OUTCOME]->(:Outcome)
(:Belief)-[:DERIVED_FROM]->(:Episode)      // one edge per supporting episode
(:Belief)-[:ABOUT]->(:Person|:Dependent|:CanonicalTrail)
(:Person)-[:HAS_PROFILE]->(:PhysicalProfile)
(:Person)-[:HAS_PARTY_PROFILE]->(:PartyProfile)
(:Person)-[:HAS_DEPENDENT]->(:Dependent)
(:Person)-[:MEMBER_OF]->(:Household)
```

---

## Constraints (§6)

All single-property uniqueness (Community Edition safe):

```cypher
episode_id        FOR (e:Episode)          REQUIRE e.episode_id   IS UNIQUE
outcome_id        FOR (o:Outcome)          REQUIRE o.outcome_id   IS UNIQUE
belief_id         FOR (b:Belief)           REQUIRE b.belief_id    IS UNIQUE
phys_profile_id   FOR (pp:PhysicalProfile) REQUIRE pp.profile_id  IS UNIQUE
pp_profile_id     FOR (pa:PartyProfile)    REQUIRE pa.profile_id  IS UNIQUE
dependent_id      FOR (d:Dependent)        REQUIRE d.dependent_id IS UNIQUE
```

`pp_profile_id` / `phys_profile_id` use different constraint names because both node types share the `profile_id` property name.

---

## Indexes (§7)

```cypher
episode_owner        ON (e:Episode)           (e.owner_id)
belief_owner_subject ON (b:Belief)            (b.owner_id, b.subject_id)   -- composite
belief_key           ON (b:Belief)            (b.key)
phys_profile_owner   ON (pp:PhysicalProfile)  (pp.owner_id)
```

The composite `belief_owner_subject` index requires Neo4j 5.x (Community Edition supports composite range indexes).

---

## Access pattern (Rule #4)

Every Stage-5 node carries `owner_id`. No read of an owned node may bypass `scopedQuery(viewer)`:

```cypher
MATCH (b:Belief)-[:ABOUT]->(p:Person {member_id: $viewer_id})
WHERE b.owner_id = $viewer_id
RETURN b ORDER BY b.last_updated_at DESC LIMIT 50
```

Decay is computed on read in Python (`decayed_confidence(belief)`), not stored. The Cypher query returns all non-expired beliefs; Python filters by `decayed_confidence > threshold`.

---

## Belief invariants (Rules #2, #7)

- `axis` in `{capability, preference, taste, constraint}`. Watch/FIT data → `capability` only; never `preference`.
- `type` in `{stated, inferred}`. Inferred beliefs never pose as stated in the feed.
- `confidence` stores the raw corroboration-weighted value; decay applied at query time.
- `source_episode_ids` links every belief back to the episodes that generated it (provenance traversable by the user).
- Provisional state: `corroboration_n < 3` → `confidence < 0.4`; not injected into Curator context unless no stronger signal exists.

---

## Decay half-lives

| Axis | `decay_half_life_days` |
|---|---|
| `capability` | 180 |
| `preference` | 90 |
| `taste` | 120 |
| `constraint` | null (no decay) |
