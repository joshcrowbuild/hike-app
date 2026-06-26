# Stage 8 — Multiplayer & Privacy (design)

*Workplan Stage 8. Draft v0.2 — June 24, 2026. The big additive layer (Phase 2). Builds on Stages 2 (schema + the `scopedQuery(viewer)` seam — in code `ScopedSession` + `owner_scope()`), 5 (belief store + privacy tiers), 6 (watch ingestion), and **7 (the eval methodology that already specifies the privacy invariants this stage implements test-first)**. Honors thread **T2** throughout.*

> **Status: DESIGN (planning mode).** Specifies the identity/household model, the auth mechanism + provider, the grant/permission model (schema + semantics + provenance-stop), the access-control-at-query-layer *implementation* on the existing seam (incl. the property-based fuzz test specified in Stage 7 §7), and the party-composition algorithm (constraint merge / readiness gate / taste merge). Decisions for Josh's call are flagged 🅓 (§11).

> **Legend:** ✅ decided (consistent with the Decision Log) · 🔶 recommended, confirm · ❓ open. Most of the *concept* here is already ✅ in Decision Log §11/§13 and §30's privacy tiers; Stage 8 is where it becomes **schema + mechanism + test**, so much of this doc is 🔶/❓ at the implementation grain, hung off ✅ concepts.

> **Terminology bridge (read first).** The Decision Log (§28/§29/§30), Stage 2, Stage 5, and Stage 7 all call the read wrapper **`scopedQuery(viewer)`**. The *code* names it `ScopedSession` (the session that merges `$viewer_id`/`$granted_ids`) plus `owner_scope(var)` (the clause builder in `graph/queries.py`). **They are the same mechanism** — this doc uses the code names when discussing implementation and notes the equivalence so nothing here reads as a parallel enforcement path. There is exactly one access seam.

> **What this produces (per workplan):** identity/household + account model · auth mechanism + provider · the grant/permission model (schema + semantics) · the access-control-at-query-layer implementation · the party-composition algorithm (constraint merge / readiness gate / taste merge — "minimize the bigger disappointment") · sharing UX (request-approve, tiers, revoke). **Honors:** access-at-query-layer (#4), private-by-default / share-the-conclusion-not-the-substrate (#5), provenance+confidence+timestamp on every belief (#7), capability≠preference (#7), source-or-silence applied to beliefs (#1/§9), secrets-never-in-repo (#10), no-training (#9).

> ✅ **STATUS UPDATE (2026-06-26): all three §0 preconditions are CLOSED** — the scoped-**write** seam (Epic 011), authenticated **viewer_id** (Epic 014), and the **owned-label manifest + live-Neo4j CI guardrail** (Epic 015) all shipped; gap-audit C2/C3/M9 are closed. The grant model below may now build on them. *(Stage 8 multiplayer itself remains Phase-2 / unbuilt.)* The original precondition warning is kept below as provenance.
>
> **Precondition warning — this stage is NOT "purely additive" today.** The June-2026 architecture gap-audit (`docs/research/architecture-gap-audit-2026-06.md`) flags **three Stage-8-blocking gaps** in the seam this stage builds on. They are listed as **§0 hard preconditions** and must be closed *before* the grant model below can be trusted. The seam's *read* path was built right early (Stage 2 §7); the *write* path, the auth contract, and the owned-label manifest were not — and the grant model touches all three. Do not start Stage 8 build until §0 is done.

---

## 0. Hard preconditions (gap-audit, must close before Stage 8 build)

These are not Stage-8 *design* questions — they are foundations the grant model assumes, **now BUILT (Epics 011/014/015; gap-audit C2/C3/M9 closed)**. *(Kept as the spec of what those preconditions required.)* Stage 8 introduces shared/party-level **writes** and **authenticated viewers**, which is exactly where each gap becomes a live leak. Each is owned by the audit; Stage 8 inherits the requirement.

| # | Audit | Gap | Why it blocks Stage 8 | Stage-8 dependency |
|---|---|---|---|---|
| 0a | **C2** | The owned-node **write** path bypasses the access choke point: `belief_update.py` / `ingest_episode.py` write `:Episode`/`:Belief`/`:PhysicalProfile` through a raw unscoped runner with hand-typed `owner_id` clauses. `owner_scope()` governs reads only. | Stage 8 introduces **shared / party-level Belief writes** (§6) and a `:Grant` write path. A writer that forgets the inline `owner_id` clause silently creates or overwrites another member's node — the cross-user **write** leak (C2/M8), which the §5.4 fuzz test (read-side) *cannot see*. | Extend the seam to writes (a `run_write` that refuses an owned-label MERGE/SET without an owner-scoping clause); route all owned-node writes through `graph/queries.py`. Point the fuzz test at the write builders too (§5.4). **Required before any `:Grant` or party-Belief write.** |
| 0b | **C3** | `viewer_id` is **client-supplied and unauthenticated**: `PlanRequest.viewer_id` flows straight into `scoped_session`. Any caller can POST `{"viewer_id":"mem:josh"}`. | The entire grant model resolves `granted_ids` *from* `viewer_id`. If `viewer_id` is forgeable, every grant is forgeable — the access seam protects against a forgotten `WHERE`, not a forged identity. **This is the load-bearing auth contract for §4–§5.** | The §3 auth design **must** establish where `viewer_id` becomes trustworthy: `viewer_id` MUST derive from an authenticated session/token, never the request body; `build_runtime`'s documented contract becomes "`viewer_id` is already authenticated" (§3.3). Until auth exists, hard-fail any request with `viewer_id != "anonymous"`. |
| 0c | **M9** | No **owned-label manifest** / DB invariant: nothing structurally distinguishes owned from world nodes, so a forgotten `owner_scope` *fails open*, and the fuzz test cannot enumerate owned labels to verify coverage. | §5.4's invariant ("no ungranted node ever returns") is **unprovable** without an enumerable owned-label set — and §5.5's added `:CommonsObservation` + grant nodes make the owned/unowned/derived trichotomy subtler exactly when leaks become consequential. | Define the owned-label set in **one manifest** that the scoping seam *and* the fuzz test import; add a CI check that every Cypher touching an owned label carries `owner_scope`, and an ingest-time invariant that no owned node is written without `owner_id`. **Required for §5.4 to be a real proof.** |

🅓 *These three are gating, not optional. Recommend closing 0a/0c jointly with the C2 write-seam epic and 0b as the first task of the Phase-2 auth build, ahead of the grant resolver. The rest of this doc assumes them done.*

---

## 1. Design principles (inherited, non-negotiable)

1. **Access control at the query/data layer, never the agent** (#4, T2). Every Cypher traversal is permission-scoped to the viewer; the agent never sees a query that *could* return ungranted nodes. The seam already exists (`scopedQuery` == `ScopedSession`/`owner_scope`); Stage 8 widens `$granted_ids` from "empty" to "resolved from live grants" — it does **not** introduce a second enforcement path. (Read-side only today — see §0a for the write path.)
2. **Private-by-default; shared-by-exception** (#5). A node is invisible to everyone but its owner until an explicit grant says otherwise. There is no "share with everyone," no public-by-default personal node.
3. **Share the derived conclusion, never the raw substrate** (#5, §11). A grant is a **stop point on a provenance edge**: a grantee can read the *belief* but **cannot traverse `DERIVED_FROM` to the episodes or `ABOUT` to the raw biometrics** behind it — *and* (the non-obvious part, §4.4) cannot read the substrate-pointer *scalar fields the belief node itself carries* (`source_episode_ids`, `corroboration_n`). The provenance chain is the owner's; the conclusion is what's shareable.
4. **Request-then-approve, not take** (§11). No grant is created by the grantee; the grantor is the sole author of every grant. Sharing is an affirmative act, always revocable.
5. **One shared graph, not federated** (§11). Revocation is only real if nothing was copied — so grants are *read-time filters over the single graph*, never data duplication. (Cost: colocated sensitive data; accepted for a trusted household, revisit encryption/federation for strangers — §11, deferred.)
6. **The auth boundary IS the shared/private boundary** (§13). Anonymous = world + live conditions (no identity). Signed-in = anything touching a private overlay. Auth is the same line the schema already draws between unowned (public) and `owner_id`-bearing (private) nodes — but it only holds if `viewer_id` is *authenticated*, not asserted (§0b).
7. **Capability ≠ preference, structurally** (#7, §30). The grant *categories* inherit the belief `axis` already in the schema (`capability`/`preference`/`taste`/`constraint`). A capability grant can never leak a preference, because they're distinct `axis` values on distinct nodes — the boundary is data-level, not query-level discipline.

---

## 2. Identity model — household of individual members

**The shape (✅ Decision Log §13, §11; Stage 2 §5 reserved the labels; `graph/schema.cypher` already MERGEs `:Household`, `:Person`, `:Dependent {dependent_id:"dep:ruby"}`):** a **household** is a container of **individual members**, each a full account. Ruby is a **dependent node, not an account**. Identity is multi-account from the first *real* multiplayer use (Josh + Carter), even though Phase 0/1 ran single-user/local with no auth.

```
(:Household {household_id, name, created_at})
   -[:HAS_MEMBER]->(:Person {member_id, owner_id, auth_subject, display_name, ...})
(:Person)-[:HAS_DEPENDENT]->(:Dependent {dependent_id, name:"Ruby", type:"dog"})   // no owner_id — sub-node
(:Episode)-[:WITH]->(:Dependent)                                                    // "Ruby was along"
```

**Key modeling decisions:**

| # | Question | Resolution | Why |
|---|---|---|---|
| 2a | What is a member? | ✅ `:Person` = own login + own watch connections + own private overlay + own grants. `Person.owner_id == Person.member_id` (a person owns themselves). | Each member is an independent privacy domain; the household is a *grouping*, not a shared identity. Carter's overlay is Carter's, full stop. |
| 2b | What is Ruby? | ✅ `:Dependent`, a **sub-node of a `:Person`** reached via `(:Person)-[:HAS_DEPENDENT]->(:Dependent)`, never an `auth_subject`. **Per the real schema (`schema.cypher:168-169`, Stage 5 §) `:Dependent` carries NO `owner_id`** — it is owner-scoped *by traversal from its owning `:Person`*, not by a direct property (§2e). Capability beliefs `ABOUT` Ruby do carry `owner_id` (her owner's) and live under that overlay. | A dog can't consent, log in, or hold grants. Modeling her as an account would force a fake login and break "every account is a privacy domain that can grant." She rides on her owner's grants. |
| 2c | Is the household a privacy domain? | 🔶 **No — the household grants nothing on its own.** It's a roster + a convenience default (household members are the obvious grant *targets*), not an automatic share. Membership ≠ access. | Living in the same house is not consent to read each other's biometrics. Keeps #2/#5 honest: even within a household, sharing is by-exception. The household only *pre-populates the people-picker*, it does not pre-populate grants. |
| 2d | Does a household own anything? | 🔶 **Defer shared/household-owned objects** (a shared trip plan, a joint party profile). The existing model is single-`owner_id`. A jointly-authored object wants multi-owner. | Stage 2 §7 / decision-log §10 #5 already flagged: "`owner_id` property for v0, revisit `:OWNS` edge if multi-owner appears." Multiplayer is where it *appears*. Don't retrofit the world layer; introduce the `:OWNS`-edge promotion narrowly for joint-planning artifacts only. ❓ deferred to the joint-planning build. |
| 2e | How is a `:Dependent` access-scoped, given it has no `owner_id`? | ✅ **Via the owning `:Person`, not directly.** `owner_scope('d')` cannot scope a node with no `owner_id`. Ruby's data is reachable only by traversal from an owned node: her *beliefs* (which carry `owner_id` + `subject_id = dep:ruby` + `subject_type = "dependent"`) are owner-scoped, and the `:Dependent` node itself is reachable only through `(:Person {owner_scope})-[:HAS_DEPENDENT]->(d)` or `(:Episode {owner_scope})-[:WITH]->(d)`. | Avoids a schema change. The enforcement hook for "who can see Ruby" is the **belief's** `owner_id` + `subject_*` (§5.4), and the traversal-from-owned-Person path — never a property on the `:Dependent`. The fuzz test (§5.4) asserts Ruby surfaces *only* through an owned/granted owning node, never standalone. |

🅓 *2e-alt: if a future query needs to read `:Dependent` nodes directly (not via traversal), add `owner_id` to `:Dependent` (a flagged schema change). For v0, traversal-scoping is sufficient and avoids the change; the fuzz test guards it.*

**The dependent's data path (capability≠preference, watch-free first):** Ruby has capability beliefs (range, heat tolerance, terrain) inferred from the episodes she was **`WITH`** on — party presence recorded by the **manual outcome-card toggle** ("Was Ruby with you?", Decision Log §31 — Party detection / Stage 6), which writes the `(:Episode)-[:WITH]->(:Dependent)` edge. There is **no automated proximity detection** in Phase 1. She has **no watch, no readiness, no preferences** (a dog's "preference" is unknowable — source-or-silence). Her capability beliefs are grantable exactly like a member's capability tier, because they're the same `:Belief {axis:"capability", subject_type:"dependent"}` shape.

---

## 3. Auth mechanism + provider

**Concept ✅ (§13): "managed — don't hand-build auth." Mechanism + provider is the open part (§13 ❓, §24 "auth provider choice"). The load-bearing piece is §3.3 — where `viewer_id` becomes trustworthy (audit C3 / §0b).**

### 3.1 What auth must do (requirements, from the architecture)
1. **Map an authenticated subject → a `:Person.member_id`** — the single value that drives `$viewer_id`. Nothing else in the system needs to know *how* the user authenticated.
2. **Stay out of the graph as a credential store** — passwords/tokens/watch logins are **secrets-store concerns** (#10, §14, audit M6), never `:Person` properties. The graph holds only an opaque `auth_subject` (the provider's stable user id) to join on.
3. **Preserve the anonymous path** (§13, #6). Unauthenticated requests get `viewer_id = "anonymous"` and `granted_ids = []`; the scope clause then matches only unowned world/commons nodes — the anonymous product *is* "the query layer with an empty scope." No separate code path.
4. **Be swappable** — the auth provider is an adapter behind a thin seam, exactly like the model-provider seam (Stage 4 §2) and the notification seam (audit m7), so a managed provider can be replaced without touching the access layer.

### 3.2 Recommendation 🔶
**Managed provider, OIDC/JWT-based, self-hostable.** Ranked:

| Option | For | Against | Verdict |
|---|---|---|---|
| **Supabase Auth** | Local-first ethos (self-hostable, Postgres-backed, open-source); generous free tier; clean JWT; row-level-security mental model matches our query-layer enforcement. | Pulls in a Postgres for auth even though the app data is Neo4j (auth-only Postgres is fine — it's *not* the graph). | 🔶 **Recommended default.** Best fit for the local-first / "crown jewels stay on my infra" stance (§14). |
| **Clerk** | Best DX, drop-in UI, organizations≈households out of the box. | Hosted-only (data leaves your infra); pricing scales; less aligned with local-first. | Strong if DX > sovereignty. |
| **Auth0** | Mature, enterprise-grade. | Heaviest; overkill for a household; hosted. | Over-spec for the scale. |
| **Roll-your-own** | Full control. | Explicitly rejected (§13: "don't hand-build auth"). Auth bugs are security bugs. | ❌ Out. |

**Why managed-but-self-hostable:** the product thesis is *private utility, crown-jewels stay home* (§14). A hosted-only auth provider contradicts that less than it seems (it holds only auth, not the overlay), but Supabase's self-host path keeps the option of *zero* third-party custody. **The household-as-organization** concept maps cleanly onto Supabase/Clerk org primitives, giving §2's roster for free.

### 3.3 The auth contract — where `viewer_id` becomes trustworthy (audit C3 / §0b)

**This is the single most load-bearing auth requirement, and it is currently absent (C3).** The grant model resolves everything *from* `viewer_id`; if `viewer_id` is forgeable, grants are forgeable. The contract:

1. **`viewer_id` MUST derive from an authenticated session/token, never the request body.** ✅ The provider issues a short-lived **JWT** carrying `sub` (= `auth_subject`); the API edge **verifies the JWT**, resolves `auth_subject → member_id` (one indexed Cypher lookup or a cached map), and *that resolved value* — never `PlanRequest.viewer_id` — constructs the `ScopedSession`. The client never supplies its own `viewer_id`.
2. **`build_runtime`'s documented contract becomes "`viewer_id` is already authenticated."** The graph layer keeps doing exactly what it's told; the trust boundary moves up to the API edge where the JWT is verified.
3. **Until auth exists, hard-fail forgery.** Any request whose resolved `viewer_id != "anonymous"` without a verified token is rejected (or gated behind a shared dev secret). This closes the latent hole *before* Epic-003/Stage-8 wire an overlay over the same endpoint.
4. **The JWT never reaches the graph** — only a resolved `member_id` does. Auth (the JWT proves *who*) and authorization (grant resolution computes *what they may see*, §4) stay cleanly separated.

🅓 *Open: Supabase vs. Clerk — a values call (zero third-party custody vs. best DX), not a capability gap; both satisfy every requirement. Defer the **pick** to the Phase-2 login build. The **contract** in §3.3 is not deferrable — it must land with the first authenticated endpoint, ahead of grants (§0b).*

---

## 4. The grant/permission model

**Concept ✅ (§11): grant = (grantor → grantee, category, scope, revocable); directional; context-scoped; request-then-approve. Sensitivity tiers T1/T2/T3 (§11, §30). The schema + semantics + provenance-stop are the Stage-8 work (§24 "grant relationship; provenance-stop semantics").**

### 4.1 The grant tuple → a `:Grant` node

A grant is **first-class, queryable, revocable** — therefore a node, not a property. (A property couldn't carry its own audit, and revocation-as-status-flip is cleaner than property mutation.)

```
(grantor:Person)-[:GRANTED]->(:Grant {
    grant_id,
    owner_id,                   // = grantor_id; this :Grant is an OWNED node, scoped by owner_scope
    grantor_id,                 // = the data owner; indexed
    grantee_id,                 // a :Person.member_id (never a household, never a dependent)
    category,                   // capability | preference | taste | constraint
                                //   | readiness_today | episode_history | location   (§4.2)
    scope,                      // "joint_planning" (default) | "always"             (§4.3)
    tier,                       // T1 | T2 | T3 (derived from category; stored for fast filter)
    status,                     // active | pending | revoked
    requested_at, decided_at,   // request-then-approve audit (§4.5)
    revoked_at,                 // null until revoked; revocation = status flip + stamp, never delete
})-[:TO]->(grantee:Person)
```

**`:Grant` is itself an owned node** (`owner_id = grantor_id`) and joins the owned-label manifest (§0c) — a grantor sees and manages their own grants through the same `owner_scope` seam; a grantee learns of a grant only via the resolver (§5.2), never by reading the `:Grant` node directly.

**Why grantee is a `:Person` only (not a household, not a dependent):** grants are between *consenting privacy domains*. A household can't consent (§2c); a dependent can't either. Ruby's capability becomes visible to Carter because **Josh** grants Carter `category:capability` over his overlay (which *includes* beliefs whose `subject_type = "dependent"`); the grant rides on the owning person.

### 4.2 Categories = belief axes + the three live/historical extras

The four "slow" categories are **exactly the belief `axis` values** already in the schema (Stage 5 §, `b.axis`) — so a `capability` grant is enforced by `WHERE b.axis = 'capability'`, structurally incapable of leaking a `preference`. The three extra categories cover non-belief data:

| Category | Maps to | Owned node kind | Tier (§11/§30) | Default grantability |
|---|---|---|---|---|
| `capability` | `:Belief {axis:"capability"}` (incl. `subject_type:"dependent"`) | `:Belief` | **T1** | partner default (the "hikes together" floor) |
| `preference` | `:Belief {axis:"preference"}` | `:Belief` | **T1** | partner default |
| `taste` | `:Belief {axis:"taste"}` | `:Belief` | **T1** | partner default |
| `constraint` | `:Belief {axis:"constraint"}` | `:Belief` | **T1** | partner default (a hard constraint must be visible to co-plan safely) |
| `episode_history` | `:Episode` + `:Outcome` nodes | `:Episode`/`:Outcome` | **T2** | explicit, context-scoped |
| `readiness_today` | live readiness filter value (Stage 5/6) — **not a graph node** (#3) | *(none — JIT scalar)* | **T2** | explicit, scope-locked to `joint_planning` |
| `location` | live precise location (future) | *(none — JIT)* | **T3** | locked off in v0 (§11) |

**The category predicate is category-kind-specific (audit-noted: there is no `axis` on `:Episode`).** Belief categories match on `b.axis`; non-belief categories match on *node kind*, not `axis`:
- `capability`/`preference`/`taste`/`constraint` → `n:Belief AND n.axis = $category` (+ `subject_*` for dependents, §5.4).
- `episode_history` → `n:Episode OR n:Outcome` (these have no `axis`; the category gates on label).
- `readiness_today` / `location` → **not graph nodes** at all → enforced at context-assembly (§4.3), never by `owner_scope`. There is no node to scope; the grant gates whether the *live JIT scalar* may enter a party context.

This is why §5.2's "second predicate" is implementable for every category: it dispatches on category *kind* (belief-axis vs. label vs. JIT-only), never assuming a universal `axis` field.

**T1 is the safe default that already works** (§11): "hikes together" runs on T1 (derived capability + preference + taste + constraint). A new household member granted the four T1 categories enables party-planning immediately, with **zero** episode/biometric exposure.

**T3 (raw biometric archive, live precise location) is not grantable in v0** — and for biometrics it's *structurally* ungrantable: Stage 5 §watch-data decided raw HR/GPS time series are **not held in Neo4j at all** (#3). You cannot grant what the graph doesn't contain. (#5 enforced by absence — the strongest possible guarantee.)

### 4.3 Scope = context-scoping (`joint_planning` vs `always`)

**The non-obvious, load-bearing semantic (§11: "shared data enters *joint* planning only, never your solo feed").** A grant's `scope` controls *which compute context* may use it:

- `scope:"joint_planning"` (default for everything above T1, and the only option for T2): the granted data is visible **only when the active planning context is a party that includes both the grantee and the grantor.** It never enters the grantee's *solo* feed, never personalizes their individual recommendations.
- `scope:"always"` (T1 only, opt-in): the granted conclusion may inform the grantee's solo context too. Even here, only the *conclusion*, never the substrate.

**Why scope is enforced at context-assembly, not only at query time:** the `ScopedSession` decides *visibility* (can this node be read at all); `scope` decides *eligibility for this compute* (may a visible node enter *this* prompt/ranking). Two gates. A `joint_planning`-scoped belief is *readable* by the grantee but is **filtered out of solo context assembly** — the context-assembly layer (Stage 5 §context-assembly, Epic-003) checks `grant.scope` against the active planning mode. This prevents the leak where granted data legitimately readable for party planning silently colors the grantee's private feed. For `readiness_today`/`location` (no graph node), context-assembly is the *only* gate.

### 4.4 The provenance stop — share the conclusion, not the substrate

**This is rule #5 made mechanical, and the single most important grant semantic. The draft-killing subtlety: the substrate is not only *across an edge* — it is also *scalar fields on the belief node itself*.**

Per the real schema (Stage 5 §, `schema_stage5`), a `:Belief` carries `source_episode_ids: [String]` and `corroboration_n: Integer` **as properties on the node**, plus `subject_id`. A grant on `category:capability` makes the `:Belief` node readable to the grantee. A naïve "return node properties only, just don't traverse" projection therefore **leaks the substrate pointers** (`source_episode_ids` are the exact episode ids; `corroboration_n` is the hike count) even though it never follows `DERIVED_FROM`. **"Stop at the grant" is not achieved by refusing to traverse — the projection must also field-allowlist.**

**Mechanism — two cuts, both required:**

1. **No out-traversal.** When reading on behalf of a grantee (not the owner), the access layer **must not follow `DERIVED_FROM` / `ABOUT`→raw / `HAS_OUTCOME` edges out of a granted belief.** The belief is a *leaf* for the grantee even though it's an *interior node* for the owner.
2. **Field-allowlist (the cut the draft missed).** The grantee-facing projection returns **only the conclusion fields** and **drops the substrate-pointer scalars**:

   - **Returned to grantee:** `{key, value, axis, confidence, last_updated_at, subject_type}` — the conclusion + its honesty metadata. (Note the real property names: there is **no `statement` property** — it is `key` + `value`; the timestamp is **`last_updated_at`**, not `updated_at`.)
   - **Dropped (substrate pointers, never returned to a grantee):** `source_episode_ids`, `corroboration_n`, `subject_id` (the raw subject id; `subject_type` is enough to know it's about a person vs. dependent), and the internal `belief_id`/`owner_id` plumbing.

The owner's own reads return everything and traverse freely (it's their substrate). Same node, two different *returned field sets* and two different reachable subgraphs depending on whether `viewer == owner`. This is *why a grant is "a stop point on a provenance edge"* (§11) literally: it authorizes reading the node *at the edge's head* but caps both the walk *and* the field projection there.

**Confidence still travels** (#7): the grantee sees the belief's `confidence` and `last_updated_at`, hedged-if-low — so "Carter is strong on sustained climbs (~moderate confidence, recent)" is honest without exposing the hikes. The hedge is the honesty (§7) and the privacy boundary doing double duty. **But the *count* behind the confidence (`corroboration_n`) is itself substrate and is dropped** — the grantee gets the calibrated confidence float, not "from 4 hikes."

### 4.5 Request-then-approve + revocation (§11)

- **No self-service take.** The grantee *requests* (`requested_at` stamped, `status:"pending"`); the grant becomes `active` only on the **grantor's** approval (`decided_at`). A pending request grants nothing — `granted_ids` resolution (§5) counts only `status:"active"`.
- **Revocation is real because nothing was copied** (#5, §11): set `status:"revoked"` + `revoked_at`; the next `granted_ids` resolution drops it; the grantee's *very next query* can no longer reach the node. **We keep the revoked node** (don't delete) for audit / right-to-delete bookkeeping (§14, audit M7) — revocation is a status flip, not a tombstone-and-forget.
- **Directional** (§11): a `:Grant` is one-way (grantor→grantee). Reciprocal sharing = two grants. This is *why your feed and Carter's legitimately diverge* (§11) — asymmetric grants, asymmetric subgraphs.

---

## 5. Access-control-at-query-layer — the implementation

**The heart of Stage 8 and the part most expensive to get wrong (#4, §23: "dangerous to bolt on later"). The read seam exists** — `graph/queries.py:owner_scope()` and `graph/client.py:ScopedSession` (= the log's `scopedQuery(viewer)`). Stage 8 does **not** add a parallel enforcement path; it **resolves `$granted_ids` from live grants**, adds the **grantee-projection** discipline (§4.4), and extends coverage to the **write** path and the **owned-label manifest** that §0 closes. Everything below extends what `tests/test_graph_queries.py` already asserts.

### 5.1 What already exists (do not re-architect)
- `owner_scope(var)` → `"(x.owner_id = $viewer_id OR x.owner_id IN $granted_ids)"`. **Unchanged.**
- `ScopedSession(viewer_id, granted_ids, runner)` merges `$viewer_id`/`$granted_ids` into every statement. **Unchanged.**
- The invariant test in `tests/test_graph_queries.py` already asserts owned reads carry the clause.

The Stage-8 access-control work is: **(a) populate `granted_ids` correctly, (b) project-and-allowlist (not traverse, not dump fields) for grantees, (c) extend the seam to writes (§0a) and an owned-label manifest (§0c), (d) prove no ungranted node ever returns.** The read seam was built right early *precisely so this stage is additive on the read side* (Stage 2 §7); the write side and manifest are §0 preconditions, not redesigns.

### 5.2 Resolving `$granted_ids` (the new piece)

Today `granted_ids` defaults to `()`. Stage 8 introduces a **grant resolver** that runs at session construction, *after* the authenticated `viewer_id` is established (§3.3):

```
resolve_granted_ids(viewer_id) -> list[owner_id]:
    # the set of OTHER owners whose nodes this viewer may read,
    # via active grants, BEFORE category/scope narrowing.
    MATCH (g:Grant {grantee_id: $viewer_id, status: 'active'})
    RETURN collect(DISTINCT g.grantor_id)
```

**Critical:** `granted_ids` here is the *coarse* owner-set (which owners' overlays are touchable at all). **Category and scope are enforced on top**, not by widening `owner_scope`:
- `owner_scope` answers *"may the viewer read any node owned by this owner?"* (coarse, the existing clause).
- A **second predicate** narrows by category/tier/scope for *non-self* owners: when `n.owner_id != $viewer_id`, the query also requires that an active grant covers `n`'s category (dispatched by category-kind per §4.2 — `n.axis` for beliefs, label for episodes, context-assembly for JIT) and the active scope. This rides as an extra `WHERE` term in the grantee-projection builders (§5.3), parameterized by the resolved grant set — never string-built, never agent-authored.

This two-level design keeps `owner_scope` a single, auditable, *unchanged* primitive while category/scope live in dedicated grantee-only builders. **Self-reads (`owner_id == viewer_id`) skip the category/scope predicate entirely** — you have full access to your own substrate.

### 5.3 Owner-traversal vs grantee-projection (two query families)

`graph/queries.py` gains a discipline (not a new enforcement layer): **every personal-overlay read is one of two kinds.**

| Kind | When | Shape | Provenance |
|---|---|---|---|
| **owner-traversal** | `viewer == owner` | free traversal incl. `DERIVED_FROM`, `HAS_OUTCOME`, raw; returns all fields | full chain readable (it's yours) |
| **grantee-projection** | `viewer != owner` | **field-allowlisted** node properties only (§4.4: drops `source_episode_ids`/`corroboration_n`/`subject_id`); no out-traversal past the granted node; carries the category/scope predicate (§5.2) | **stops at the grant** — both the walk and the field set |

The grantee-projection builders are the *only* sanctioned way to read another owner's data. They **cannot** be written to traverse to substrate *or* to return substrate-pointer fields — there is no grantee-facing builder that emits `DERIVED_FROM` or that selects `source_episode_ids`. (A reviewer checks: "does any grantee builder traverse out of, or return a substrate field of, the granted node?" — if yes, it's a bug, caught by §5.4's test and by review.)

🅓 *Open: enforce the owner-vs-grantee split by (a) convention + the fuzz test, or (b) a typed wrapper (`OwnerSession` vs `GranteeSession`) so the projection-and-allowlist discipline is type-checked. **Recommend (b) once it earns its keep** — a `GranteeSession` whose builders structurally can't return provenance neighbors or substrate fields makes the "stop point" un-bypassable by construction, not just by test. For v0 multiplayer, (a) + the fuzz test is sufficient; promote to (b) if the builder surface grows.*

### 5.4 The property-based fuzz test (Stage 7 §7's privacy invariant, made concrete)

**The test that protects rules #4 and #5. It is not invented here — it is specified in Stage 7 §7** ("No-ungranted-node" and "Grant-stop on provenance", both zero-tolerance, pass-rate-must-be-1.0, and explicitly *"deferred to Stage 8, implemented test-first when grants land"*; Decision Log §28 calls for it). Stage 8 is where it is *written*, against the real grant resolver. It runs **both** as a unit test (Stage 7 §8.1) and inside the eval loop (Stage 7 scenario 6 / §2.3), because a leak can be sampling-dependent.

**Coverage depends on §0c.** The invariant "no ungranted node ever returns" is only provable if the test can **enumerate the owned labels** (the §0c manifest). The fuzzer imports that manifest; a new owned-but-unmanifested label is itself a test failure.

**Setup (Hypothesis-driven):**
- Generate a random graph: `M` owners, each with random owned overlay nodes (`:Belief` across random `axis`/`subject_type`, `:Episode`, `:Outcome`, `:Grant`, `:PartyProfile`), `:Dependent` sub-nodes reachable only via `HAS_DEPENDENT`/`WITH`, plus shared world + `:CommonsObservation` nodes.
- Generate a random grant set: random `(grantor, grantee, category, scope, status)` tuples — including `pending`, `revoked`, and self-grants (no-ops).
- Pick a random `viewer_id` (including `"anonymous"`).

**The invariant (the assertions that must never fail):**

> For every overlay node `n` returned by **any** query the access layer can emit for `viewer`, **either** `n.owner_id == viewer` (self) **or** there exists an `active` grant `(n.owner_id → viewer)` whose category covers `n` *by category-kind* — for a `:Belief`, `grant.category == n.axis` **and** (when `n.subject_type == "dependent"`) the grant is over the owner whose `subject_id` it is; for `:Episode`/`:Outcome`, `grant.category == "episode_history"` — **and** whose `scope` admits the active planning context. No other node ever appears.
> **And (provenance stop, §4.4):** no grantee-facing row contains a substrate neighbor (`DERIVED_FROM`/`HAS_OUTCOME` target) **or a substrate-pointer field** (`source_episode_ids`, `corroboration_n`, `subject_id`) of a granted belief.
> **And (Ruby, §2e):** a `:Dependent` appears **only** reachable through an owned/granted owning `:Person` or `:Episode`, **never** standalone, and her capability belief surfaces to a grantee **only** under a `capability` grant over *her owner*.

**What the fuzzer specifically tries to break (adversarial cases):**
- a **pending** grant must yield nothing (status filter);
- a **revoked** grant must yield nothing the instant it flips (resolution recomputed per session);
- a `capability` grant must **never** surface a `preference` node of the same owner (axis filter);
- a `joint_planning`-scoped grant must yield nothing in a **solo** context (scope filter, §4.3);
- a grant to person X must never leak to person Y (grantee filter);
- `"anonymous"` (empty scope) must return **only** unowned world/commons nodes;
- a granted belief must **never** let the viewer reach its `DERIVED_FROM` episodes **or read its `source_episode_ids`/`corroboration_n`** (the provenance stop — *both* cuts);
- a `:Dependent` must only surface via an owned/granted owning node, and only under her owner's `capability` grant — never independently;
- **(write-side, §0a)** a shared/party-Belief or `:Grant` MERGE that omits the owner-scoping clause must be rejected by the write seam — the fuzz test points at the write builders too, not only reads.

**Why property-based, not example-based:** the failure modes are combinatorial (owners × categories × scopes × grant-states × viewer × subject_type). Hand-written examples test the cases you thought of; the danger is the case you didn't. Hypothesis shrinks any counterexample to a minimal reproducer. **This test is the executable form of rules #4/#5** (Stage 7 §7) and rides in CI as a zero-tolerance invariant. It is written *with* the grant resolver, never after.

🅓 *Open: also fuzz the resolver against a **live** Neo4j (integration) vs. only the pure builders (unit). **Recommend both** (Stage 7 §8.1 unit + §8.2 integration) — the pure test proves the builders are scoped; a thin live test proves the driver doesn't bypass them. The pure builders already test DB-free (Stage 2 §queries seam), so the unit layer is cheap; the live layer guards the wiring.*

### 5.5 Why this honors "one shared graph, not federated" (#5, §11)
Enforcement is a *read-time filter over one graph* and grants store no data, so **revocation is real** (nothing was copied) and **divergent feeds are free** (asymmetric grants → asymmetric reachable subgraphs, computed live). The cost — colocated sensitive data — is the accepted trade for a trusted household (§11), with the encryption/federation revisit explicitly deferred to the stranger case. The owned/unowned/**derived** trichotomy (`:CommonsObservation` is severed-and-unowned, §0c/audit M9) is exactly why the §0c manifest matters: three node classes, one enforceable definition of "owned."

---

## 6. The party-composition algorithm

**Concept ✅ (§11): "hikes together" is a computed party — constraints compose conservatively (most-restrictive wins); readiness gates on the *less*-recovered; taste merges by minimizing the bigger disappointment. The *algorithm* is the Stage-8 work (§24 "party preference-merging algorithm").**

> **Precondition (audit M11): the solo readiness filter does not exist yet, and Epic-007 (its contract) is unwritten.** Party readiness composition (§6.2) is *the resolution of the workplan's open "readiness-filter composition (solo + party)" question* — but it cannot be built on a filter that has zero implementation. **The solo readiness filter (Epic-007: parameter shape into the Curator, absent-data degrade path) must exist before party composition.** §6.2 below *specifies the composition*; it does not assume the solo filter is built. Flagged, not assumed away.

A party = a set of members + dependents, each contributing (via T1 grants, §4.2) their `constraint`/`capability`/`taste` beliefs and (via T2 `readiness_today`, opt-in) today's readiness. The party plan is computed in a context that has **all participants' granted conclusions** — and *only* the conclusions (the provenance stop, §4.4, means no one sees anyone's substrate, even mid-party-planning; not even the `corroboration_n` behind a capability).

The three merges map onto the three engine stages (Stage 4) — **each merge happens in the stage that already owns that concern:**

### 6.1 Constraint merge — most-restrictive wins (Curator hard-filter / guardrail)

**Where:** the Curator's hard-constraint filter (Stage 4 §6: "hard filters (deterministic guardrails)"), now fed the *union* of all participants' constraints.

**Rule:** the party's constraint set = the **intersection of what's acceptable to all** = the **union of all hard constraints**. A constraint is a *floor*; combining floors takes the max.
- Ruby is along → off-leash-required trails are out **for the whole party** (her constraint binds everyone; mirrors the existing guardrail "off-leash-required when Ruby's along," Decision Log §4).
- Carter's "no exposed scrambles" (a stated `constraint` belief) removes Old Rag for the party even if Josh loves it.
- Max-difficulty / max-distance constraints take the **minimum** of the maxes (the tightest ceiling); min-anything takes the maximum of the mins.

**Why most-restrictive, no negotiation:** a constraint violation is a *bug*, not a soft loss (§9: "constraints = Verifier filters, violation = bug"; the *hard-constraint filter itself* lives in the Curator per Stage 4 §6 — §9 names the principle, Stage 4 §6 names the placement). You never trade away someone's hard limit for someone else's preference. Deterministic — **no LLM call** (set algebra over typed constraints). Source-or-silence still applies: a constraint binds only if it's a *known* (granted, above-floor) constraint; the party UX **discloses** "planning without Carter's constraints — request access" rather than silently assuming none.

### 6.2 Readiness gate — the less-recovered member (Curator, readiness filter)

**Where:** the readiness filter (Epic-007, Stage 5/6), composed across the party.

**Rule (§11 "gates on the *less*-recovered"):** the party's effective readiness ceiling = **min(readiness) across participants who shared `readiness_today`** (T2, opt-in, `joint_planning`-scoped). The group can't go harder than its least-recovered member is ready for. The gate **caps the suggested effort ceiling**; it does not rank (consistent with "readiness is a filter, not a background default," §10).

**Degrade-and-disclose (Rule #6 — watch data is enrichment, never a dependency):**
- A participant who *didn't* share readiness, has no watch, or a stale reading → the gate **runs without them and says so** ("tuned to the group's recovery; Carter's not included"). Absent data is trivial, never an error (§10).
- If *no one* shared readiness → the filter is simply off; the party plans watch-free (the baseline-by-construction floor, §10). The gate **never blocks** planning — it only tightens the ceiling when data exists. This is the same degrade path Epic-007's solo filter must define (audit M11 / DV-4); party composition reuses it, it does not invent a second one.

**Ruby's readiness:** she has none (no watch) → she contributes to the *capability* gate (her range/heat ceiling, §2) but not the *readiness* gate. Capability is the durable floor; readiness is today's modifier — the two roles stay strictly separate, exactly as the watch design demands (§10).

🅓 *Open: hard cap or strong soft-rank nudge? **Recommend hard cap on the effort ceiling** (safety-adjacent, like the constraint merge) **but never a rank penalty** (#2 — confidence/readiness must not bury trails; it removes too-hard ones, it doesn't down-rank the survivors). Preserves "confidence never penalizes ranking" while letting readiness shrink the candidate set. Resolve jointly with Epic-007's solo definition so solo and party agree.*

### 6.3 Taste merge — minimize the bigger disappointment (Curator, ranking)

**Where:** the Curator's taste-ranking LLM call (Stage 4 §6: "Opus-tier ranking"), now scoring against a *merged* taste objective. This is the one merge that is genuinely *judgment* (a soft loss, §9), so it's the one place an LLM-tier call earns its keep — the other two are deterministic.

**The objective (§11 "minimize the bigger disappointment"):** **not** "maximize average satisfaction" (one person's strong love drags the party onto a trail another mildly hates) and **not** "maximize the minimum at all costs" (pure maximin is paralyzingly bland). The rule is a **regret-minimizing** blend:

> Rank candidates by **minimizing the maximum individual disappointment**, breaking ties by total satisfaction.

- For each candidate trail, estimate each participant's satisfaction from their granted `taste` beliefs (the conclusion only — `{key, value, axis, confidence}`, hedged by `confidence` per #7; never the substrate behind it).
- **Disappointment** = how far below a participant's typical bar this trail falls (would-hate = high; neutral ≈ 0).
- **Score the party as the worst individual disappointment** and **prefer the candidate that minimizes that worst case.** Among ties, prefer higher total satisfaction (the group still gets the better-loved option when no one's hurt either way).

**Why this rule:**
- It protects the **veto-shy** case: a great trail for Josh that Carter would actively dislike scores *worse* than a good-enough trail neither dislikes — the party doesn't sacrifice one member to thrill another. That's the social contract of "hikes together."
- It's **explainable** ("chosen because it's the option no one in the party regrets") — surfaced as the card's *why-it's-here* (Stage 4 Curator output). The honesty primitive (§7) extends to party rationale.
- It **degrades cleanly**: a participant whose taste is unknown/un-granted contributes **0 disappointment** (we can't claim they'd dislike it — source-or-silence on taste, #1/§9 "taste miss = soft loss, not a bug"). The merge never *fabricates* a preference to fill a gap (the watch is a poor preference sensor, #7 — and a missing grant is not a preference at all).

**Confidence interaction (#2 — never penalize rank):** taste beliefs enter the merge *hedged by confidence*, but low confidence **shrinks the estimated disappointment toward neutral** (less sure they'd dislike it → claim less disappointment), it does **not** down-rank the trail. Uncertainty makes the merge *more permissive*, never punitive — consistent with "confidence shapes how honestly we show a trail, not whether it ranks" (§7).

🅓 *Open: leximin (recurse into the second-worst after fixing the worst) vs. single-level worst-case + total-satisfaction tiebreak. **Recommend single-level for v0** (cheaper, explainable, good enough for parties of 2–4); promote to full leximin only if real party sizes/feedback show the tiebreak misbehaving. The merge is an LLM-scored ranking, so the rule lives in the prompt + a deterministic post-sort, not a hardcoded optimizer — tunable against the Stage-7 eval.*

### 6.4 The three merges as one pass

| Merge | Stage | Determinism | Rule | Failure mode if violated |
|---|---|---|---|---|
| Constraint | Curator hard-filter (guardrail) | deterministic (set algebra) | most-restrictive wins (union of floors) | **bug** (someone's hard limit broken) |
| Readiness | readiness filter (Epic-007) | deterministic (min) | gate on the less-recovered; degrade-and-disclose | unsafe over-reach (recoverable member overextended) |
| Taste | Curator rank (LLM) | judgment | minimize the bigger disappointment | **soft loss** (a member quietly disappointed) |

This mirrors the engine's existing hard/soft split (Decision Log §9: "constraints = Verifier filters / taste = Curator ranking"; the Curator runs the *hard-constraint filter* per Stage 4 §6) — **the party algorithm reuses the single-person engine's stages, fed merged inputs.** No new engine; multiplayer is the same Scout→Verifier→Curator pipeline run over a *composed* party object (the "party as a reusable editable object," §4 Console). The composition is the only new code — and it must be fed by the **grantee-projection** reads (§5.3), so no participant's substrate enters even mid-merge.

---

## 7. Sharing UX (request-approve, tiers, revoke) — design-level

*Detailed flows are Stage 10 (T5); Stage 8 fixes the mechanism the UX must express.*

- **Belief store doubles as the sharing dashboard** (§9, §19 surface 5): "what I've learned about you," each belief showing *who it's shared with* and a per-category toggle. Sharing is *visible from the data*, not a buried settings screen.
- **Request → approve** (§4.5): a member requests a category; the grantor sees a calm, non-nagging prompt (anti-engagement stance, §19) with the *exact tier* ("Carter requests: your capability + taste — T1, joint-planning only"). Approve/decline; declined leaves no trace beyond the audit stamp.
- **Tiers shown honestly:** T1 = "what we hike together with," T2 = "your trip history (explicit)," T3 = "locked." The UI must make "you are sharing the *conclusion*, not your biometrics — not even the number of hikes behind it" legible — the provenance-stop (§4.4) is a *trust feature*: "Carter sees that you're strong on climbs; she can't see the hikes behind it, or how many."
- **Revoke = one tap, takes effect on the next query** (§4.5). The UI promises and the architecture delivers "revocation is real" (#5) — say so plainly.
- **Anonymous/solo is never disrupted:** none of this appears unless a household has ≥2 members and a grant exists. Single-user and anonymous paths are untouched (#6, §13).

---

## 8. How Stage 8 honors each non-negotiable rule (audit)

| Rule | Honored by |
|---|---|
| #1 source-or-silence (incl. beliefs) | party merges never fabricate a missing constraint/taste; unknown = disclosed gap, not assumed (§6.1, §6.3) |
| #2 confidence never penalizes rank | taste merge: low confidence → toward-neutral disappointment, never down-rank; readiness caps the ceiling, never ranks (§6.2–6.3) |
| #3 graph holds slow data only | `readiness_today`/`location` are live, *not* graph nodes → `location` ungrantable-by-absence; `readiness` shared as a live value scoped to joint planning, gated at context-assembly not by `owner_scope` (§4.2–4.3) |
| #4 access control at query layer | the entire §5 — extends `scopedQuery`/`ScopedSession`, never a parallel path; the fuzz test (Stage 7 §7) is rule #4 executable; **write-path + owned-label manifest closed in §0** |
| #5 private-by-default; conclusion-not-substrate | private until granted (§4.1); the provenance stop is *two cuts* — no out-traversal **and** field-allowlist dropping `source_episode_ids`/`corroboration_n`/`subject_id` (§4.4); revocation real because nothing copied (§5.5) |
| #6 watch data enrichment, never dependency | readiness gate degrades-and-discloses; no-watch party plans on the T1 capability floor (§6.2) |
| #7 provenance+confidence+timestamp; capability≠preference | grant categories = belief axes (structural separation, §4.2); `confidence` + `last_updated_at` travel with granted beliefs, hedged (§4.4) |
| #8 fork the FIT write early | **designed, pending build** — the commons fork **does not exist yet** (audit C1; decision-log §30/§31 ✅ is wrong memory). Grants are orthogonal to commons consent (§9). Stage 8 does not echo "already accreting." |
| #9 no training | party merge is set algebra + a scored ranking prompt; pure orchestration |
| #10 secrets never in repo | auth credentials/JWT secrets in the secrets store (§3.1, audit M6); the graph holds only an opaque `auth_subject` |

---

## 9. What Stage 8 deliberately defers

- **Encryption/federation for the stranger case** (§11) — colocated-graph + read-time-filter accepted for a trusted household; per-owner encryption revisited only when sharing extends beyond trusted people. At-rest posture for a deployed graph (audit m8) records here as a Stage-8 infra decision. ❓ deferred.
- **`location` (T3) sharing** — locked off in v0; needs the native shell's background location (Stage 11) before it's even a capability. ❓ deferred.
- **Multi-owner / household-owned objects** — introduced *narrowly* for joint-planning artifacts when they appear (§2d); the world-layer single-`owner_id` model untouched. The `:OWNS`-edge promotion (Stage 2 §10 #5) is the mechanism if/when needed. ❓ deferred to the joint-planning build.
- **Direct `:Dependent.owner_id`** — v0 scopes Ruby by traversal from her owning `:Person` (§2e); add the property only if a query needs to read `:Dependent` standalone. 🅓
- **Full leximin** taste merge — single-level worst-case for v0; promote against the Stage-7 eval (§6.3). 🅓
- **Typed `GranteeSession`** — convention + fuzz test for v0; promote to a type-enforced projection-and-allowlist seam if the builder surface grows (§5.3). 🅓
- **Auth provider final pick** (Supabase vs Clerk) — both satisfy every requirement; a values call deferred to the Phase-2 login build (§3.2). The auth *contract* (§3.3) is **not** deferred. 🅓
- **Right-to-delete / retention / backup** (audit M7, decision-log §14) — right-to-delete for a member's private graph lands in this stage's privacy surface; designed jointly with the commons-deletion `writer_hash` hook (audit C1) so write + revoke arrive together. ❓ to schedule.

## 10. Open decisions — for Josh's call

| # | Decision | Recommendation |
|---|---|---|
| A | Auth provider | 🔶 **Supabase Auth** (self-hostable, local-first-aligned), Clerk if DX > sovereignty (§3.2) |
| B | Auth contract (`viewer_id` trust) | ✅ **`viewer_id` derives from a verified token, never the request body** — the C3/§0b precondition; not optional (§3.3) |
| C | Grant as node vs. property | ✅ **node** (`:Grant`, itself owner-scoped) — first-class, queryable, auditable, status-flip revocation (§4.1) |
| D | Grant categories | ✅ **belief axes + episode_history/readiness_today/location**; category predicate dispatched by kind (axis / label / JIT), not a universal `axis` (§4.2) |
| E | Scope enforcement layer | ✅ **two gates: `ScopedSession` for visibility, context-assembly for scope** (incl. the only gate for JIT readiness/location) (§4.3) |
| F | Provenance stop mechanism | ✅ **two cuts: no out-traversal AND field-allowlist** dropping `source_episode_ids`/`corroboration_n`/`subject_id` (§4.4) |
| G | Owner/grantee split enforcement | 🔶 **convention + fuzz test now; typed `GranteeSession` later** (§5.3) |
| H | Dependent scoping | ✅ **via owning `:Person` traversal (no `owner_id` on `:Dependent`)**; add the property only if standalone reads appear (§2e) |
| I | Readiness gate hardness | 🔶 **hard cap on effort ceiling, never a rank penalty**; resolve with Epic-007's solo definition (§6.2) |
| J | Taste merge rule | 🔶 **single-level minimize-the-bigger-disappointment + total-satisfaction tiebreak**; full leximin later (§6.3) |
| K | Fuzz test scope | 🔶 **both pure-builder unit + thin live-Neo4j integration; points at write builders too** (§5.4) |
| L | Household as privacy domain | 🔶 **no — roster + grant-target default only; membership ≠ access** (§2c) |

## 11. Next

**Gate first on §0** — the C2 write-seam (0a), the C3 auth contract (0b), and the M9 owned-label manifest (0c) are hard preconditions; the grant model below is untrustworthy until they land. Then the concrete artifacts (Phase 2, needs always-on infra per the workplan): the `:Grant` schema addition + a `graph/migrations/` script (joining the owned-label manifest); the **grant resolver** + **grantee-projection-and-allowlist builders** in `graph/queries.py` (extending the existing seam, not replacing it); the **property-based fuzz test** (`tests/test_access_control.py` / `evals/security.py` — the executable form of Stage 7 §7's two privacy invariants, written test-first); the **party-composition module** (`orchestration/party.py` — constraint set-algebra + readiness min + the taste-merge prompt/post-sort), reusing the Scout→Verifier→Curator stages over a composed party object, fed by grantee-projection reads. **The read seam is purely additive (built right early, Stage 2 §7); the write seam, auth contract, and manifest are the §0 work that makes "additive" true.** Auth provider pick + the sharing UX flows fold into the Phase-2 build and Stage 10 respectively. Epic-007 (solo readiness) is a named prerequisite of §6.2.
