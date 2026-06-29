# Graph Architecture Patterns (Lens 3) — a technical brief for the architecture/graph lane

**Last verified:** 2026-06-29 · **Owner:** research (architecture lane) · **Status:** `ACTIVE` (design input; nothing here is shipped except where a card says "already in the stack")

> **Method note.** This is the architecture-lane half of a two-doc cross-domain review. It mines *connected-data and graph systems* — Zanzibar/ReBAC, fraud/AML graphs, KG-provenance mechanics, Palantir's entity+access model, graph recommendation, entity resolution, temporal/bitemporal graphs, and spatial routing — for **methods, formal models, architecture patterns, and cautionary failures**, not UX widgets. Each finding is an implementation-oriented *card*: what it is → how it maps to **our** Neo4j schema / access wrapper / commons → adopt vs. adapt → a concrete implementation note → risks. Every load-bearing external claim was verification-checked; cards respect those verdicts and call out the corrections inline. **Source-or-silence applies to this doc too:** where a claim was misattributed or unverified in the upstream research, it is flagged rather than repeated.
>
> **Audience:** the people who own the graph schema, the `scopedQuery` access seam, the Verifier/Curator engine, and the Stage-9 commons. The product/design-facing half of this review lives in **[`cross-domain-pattern-library.md`](cross-domain-pattern-library.md)** (read that for the UX manifestations and the full adopt-queue / pattern-register). This brief assumes you have read **[`stage-2-schema.md`](stage-2-schema.md)** (`SourceRecord`/`SAME_AS` provenance, computed-on-read confidence, the `scopedQuery` seam), **[`stage-8-multiplayer-privacy.md`](stage-8-multiplayer-privacy.md)** (grant model), and **[`stage-9-commons.md`](stage-9-commons.md)** (k-floor, DP posture).

---

## Summary

Eight connected-data domains converge on a small set of architectural moves that map almost one-to-one onto our non-negotiable rules. The headline transfers:

1. **Access control is a graph-traversal problem with a single choke-point, not a Cypher-authoring discipline** (Zanzibar Check + userset rewrites + Palantir marking-propagation). Our `scoped_session` / `owner_scope` seam (`graph/client.py`, `graph/queries.py`) is the right shape; the gap is (a) it has *no real viewer auth* yet (gap-audit C3, Epic 014) and (b) it relies on query authors remembering `owner_scope`, where the mature systems make bypass *architecturally impossible* and make a grant a **stop-point that propagates along provenance edges by default** rather than a thing the engine must remember.

2. **Provenance, confidence, and timestamp belong on the edge, and a property graph gives us RDF-star ergonomics for free** — but the discipline (every user-facing edge carries a non-null `{source, fetched_at, confidence-inputs, role}` bundle, generated *by the fetch wrapper*, never by remember-to-log diligence) is what transfers, not the syntax.

3. **Corroboration must count distinct upstream *origins*, fused by weakest-link, and the engine must never re-ingest its own output** — our shipped `confidence.compute()` currently counts *feeds* (`c = 0.6 + 0.2·(n−1)`), which is exactly the failure mode named across KG-provenance (citogenesis), AML (circular reporting), and genealogy (false corroboration). This is the single highest-leverage change and is **feasibility-gated** (see open question below).

4. **Conflation must be non-destructive, threshold-gated, and guarded against transitive-closure cascade** — the genealogy persona/conclusion split and the AML/ER literature agree: store each source's claim immutably, derive the displayed value separately, merge by *adding reversible edges*, and never let one bad match edge fuse a neighborhood. Our `SAME_AS`-to-`CanonicalTrail` model is already close to this; the live Shenandoah slug-merge (1643→1458) is the canonical risk.

5. **The slow corpus is versioned and auditable; the JIT overlay is governed by a freshness window and never persisted** — bitemporal "as-of" replay + Identity/State node split for the slow corpus; stale-while-revalidate / stale-if-error for overlays; Zanzibar zookies / SpiceDB consistency-spectrum as the formal model for "a revoke takes effect on the grantee's *next* view."

6. **Routing keeps geometry immutable and costs query-time; "no route" is a sourced empty-state** — pgRouting `cost`/`reverse_cost` + `analyzeGraph` integrity gate + HMM snap-to-network as a provenance-bearing inference.

The cautionary half is as load-bearing as the adopt half: the **new-enemy problem** (stale ACL on new content), the **transitive-closure merge cascade** (one bad edge → a mega-node a closure overlay then attaches to), the **Matthew effect** (random walks collapse personalization into popularity), the **frozen-ontology failure** (a stale slow-fact is *worse* than none), and **AML false-positive fatigue** (95–98% — a calm utility cannot afford a noisy safety layer).

**Two things this brief does NOT do, deliberately:** (a) it does not re-rate effort — several upstream "low/medium, extend the shipped primitive" estimates are understated because Confidence and Staleness are *not yet built as components* and there is no verdict layer; treat every confidence/provenance card here as a **net-new build**, not an extension; (b) it does not adopt any severity-palette UX — the criticality/verdict colour question collides with the ratified design-system §7.3 and is out of scope for the architecture lane (it is a §10 design-governance question, flagged in the product-facing doc).

---

## How to read the cards

Each card is tagged **adopt** (take the mechanism largely as-is), **adapt** (take the model, change the substance for our domain), **cautionary** (a failure to design against), or **just-interesting** (reach for only if a measured need appears). The "Maps to our stack" line names the concrete file / schema element / epic. "Risks" is non-optional.

---

# Pattern cards

## Card 1 — Relation tuples + userset rewrites: store minimal grant edges, derive the rest by traversal
**Domain:** Google Zanzibar / ReBAC · **Disposition: adopt (model)** · Rules 4, 5 · Epic 011 (scoped-write), the auth provider (R3), Stage 8

**What it is.** Zanzibar stores permissions as relation tuples `object#relation@user` (verified against the USENIX ATC '19 paper grammar: `⟨object⟩'#'⟨relation⟩'@'⟨user⟩`, with `object ::= namespace':'id`). Most permissions are *not* stored — they are derived by **userset-rewrite** rules: `_this` (stored tuples), `computed_userset` (editor ⇒ viewer on the same object), `tuple_to_userset` (inherit a parent's ACL, e.g. a doc inherits viewer from its folder). A single `Check(object, relation, user) → bool` resolves by walking these rules over the sparse tuple graph. Proven at scale: >2 trillion tuples, >10M qps, p95 Check <10 ms, >99.999% over 3 years (all four figures confirmed against the paper).

**How it maps to our stack.** This *is* Rules 4 + 5, battle-tested. In our overlay a grant is a stored edge; derived access (a household member sees a *shared derived conclusion*; Ruby as a dependent inherits nothing on her own account) is `computed_userset` / `tuple_to_userset`-style derivation, not duplicated edges. Our `owner_scope(var)` clause (`graph/queries.py`) — `(var.owner_id = $viewer_id OR var.owner_id IN $granted_ids)` — is a hand-rolled, flattened userset: `$granted_ids` is the materialized result of a (currently trivial) userset rewrite. The Zanzibar lesson is to keep the grant edges minimal and **derive `$granted_ids` by traversal at session-open**, so the rewrite rules (household membership, purpose-scoped grants, trip co-planning) live in one place rather than being spread across query authors.

**Adopt/adapt.** Adopt the model. When the auth provider (R3) lands, build `$granted_ids` from a userset-rewrite over grant edges rather than a static list; keep the *shape* `owner_scope` already enforces.

**Implementation note.** Today `granted_ids` is passed into `scoped_session(viewer_id, granted_ids)` as a literal sequence (`graph/client.py`). The clean evolution: a `resolve_grants(viewer_id) -> list[str]` that walks `(:Person)-[:GRANTED {purpose, expiry}]->(:Conclusion)` (and household/purpose edges) and returns the flattened set, computed once per scoped session and merged into every query's params exactly as today. This keeps the Check choke-point (Card 2) and lets grant *logic* change without touching a single query builder.

**Risks.** (1) **Userset depth → latency**: deep household/purpose chains can blow the calm-utility budget; instrument grant-chain depth vs. session-open latency before grants nest (Leopard-style transitive-closure precompute is the documented escape hatch — see Card 12, just-interesting). (2) Flattening grants into `$granted_ids` at session-open caches the permission set for the session's life — fine for reads within a request, **unsafe across a revoke** (Card 5).

---

## Card 2 — The Check API as the single authorization choke-point
**Domain:** Zanzibar · **Disposition: adopt** · Rule 4 · access wrapper, Epic 014 (overlay egress + viewer auth), Epic 011

**What it is.** Zanzibar exposes one narrow primitive — `Check` (plus Read/Write/Expand/Watch) — and *all* of Google's services ask only that. Authorization logic lives entirely behind the API, never in client/agent code; that centralization is what makes a uniform consistency + audit model possible and prevents each caller from subtly re-implementing access rules.

**How it maps to our stack.** Rule 4 explicitly forbids access control *in the agent*. Our `ScopedSession` (`graph/client.py`) is the intended choke-point: every personal-overlay read/write merges `$viewer_id`/`$granted_ids`, and `graph/queries.py` carries a guard (`_OWNER_SCOPE_RE`) that *refuses to emit* an owned-label `CREATE` without an `owner_id = $viewer_id` scope clause (AC-1.6, Epic 011). `graph/load.py` even forbids `owner_id`/`granted_ids`/`viewer_id` as raw property names. This is the same architectural stance — make the un-gated query *unconstructible*.

**Adopt/adapt.** Adopt, and harden two known gaps:
- **C3 / Epic 014 — viewer auth is not real yet.** `graph/client.py` documents it: "`viewer_id` is unauthenticated today … a forged `viewer_id` is still a forged write." The choke-point exists but the identity feeding it is asserted, not authenticated. The Check model is worthless without an authenticated principal; Epic 014 is the precondition for Stage 8.
- **Read-side egress.** The write guard is strong; ensure the *read* side has the equivalent — no raw Cypher touching owned labels outside `ScopedSession`. The schema comment (§5) already mandates this; make it a CI lint (scan orchestration + agent layers for direct owned-label `MATCH` outside the wrapper), the Zanzibar "static test" hook.

**Implementation note.** Add a CI check that greps the engine/agent modules for `MATCH (…:Episode|:Belief|:Outcome|:PhysicalProfile|:PartyProfile…)` not routed through `ScopedSession`, mirroring the existing `_OWNER_SCOPE_RE` write guard. Pair it with the adversarial fuzz harness already sketched in the schema (§5: "a property-based test fuzzes `$viewer_id`/`$granted_ids` to assert no ungranted node ever returns").

**Risks.** Authorization leaking into agent code is the exact anti-pattern Check was built to kill; the guard regex covers writes, not reads, so the read-side leak is the live exposure until Epic 014 closes it.

---

## Card 3 — Capture-at-boundary provenance bundle on every edge (RDF-star ergonomics, by construction)
**Domain:** KG provenance (RDF-star / named graphs / PROV-O) · **Disposition: adopt (discipline)** · Rules 1, 7, 3 · Verifier-freshness epic, graph-schema provenance-edge convention, Confidence-v2

**What it is.** The semantic-web community produced three competing mechanics for fact-level metadata: **classic RDF reification** (4 auxiliary triples per fact — now an explicit anti-pattern, confirmed: standard reification is exactly 4 triples per statement, quadrupling size and making provenance queries cumbersome), **named graphs** (group facts under a URI, hang provenance off the graph), and **RDF-star / RDF 1.2 triple terms** (annotate one triple inline: `<<:trail :hasWater :spring>> :confidence 0.7 ; :asOf "…"`). PROV-O gives the canonical `Entity`/`Activity`/`Agent` derivation vocabulary (`wasDerivedFrom`, `wasGeneratedBy`, `wasAttributedTo`).

**How it maps to our stack.** We are on Neo4j — a *property graph* — so **edge properties give us the RDF-star ergonomics natively**: `(t:CanonicalTrail)-[:HAS_WATER_AT {source, confidence_inputs, observed_at, fetched_at, role}]->(s:Spring)`. We already do this for the slow corpus: `SAME_AS` carries `{source, source_id, match_method, matched_on, match_score, reviewed_by, reviewed_at, ingest_version}`; `DERIVED_FROM` ties a `Belief` to its `Episode` (Rule 7 in the schema, §8). The two gaps the KG literature exposes:
- **Role tag is where capability ≠ preference lives.** Our `Belief` carries `axis: "capability"` and `type: "inferred"` (schema §8) — good. Generalize that to a controlled **role enum** on *every* user-facing fact: `LIVE_FETCHED`/observed (USGS, NWS), `CORPUS_DERIVED`, `INFERRED` (watch/taste). An `INFERRED` fact must never render in the register reserved for an `OBSERVED` safety fact (PROV-O's stated-vs-derived distinction made machine-checkable).
- **The live overlay carries no per-fact provenance bundle today** — confidence is computed transiently from `VerifiedFact.confidence_inputs` (`orchestration/confidence.py`), and there is no `content_hash`/`role` on the fetched fact. The fix is to make the **Verifier's fetch wrapper stamp `{source, fetched_at, content_digest, role}` by construction** — provenance generated at the boundary, never by remember-to-log diligence. (Across four upstream domains, after-the-fact provenance entry is the primary error injector; the trustworthy path must be the *only* path.)

**Adopt/adapt.** Adopt the discipline; adapt the vocabulary. Use PROV's verbs as a *tiered starting set*, not a closed ontology, and only capture lineage that has a UX or eval consumer (the frozen-ontology warning, Card 8, applies to over-modeling provenance too).

**Implementation note.** This is a **from-scratch Verifier-layer build**, not a medium extension: grep confirms no `content_hash`/`digest` and no `role`/`observed|inferred|stated` enum on the live path. Define a `ProvenanceBundle` dataclass the live-adapter seam (`source-seams-corpus-and-live.md`, Epic 013) emits alongside every `VerifiedFact`; make a fact lacking a complete bundle *unrenderable* (it must fall to an empty-state, never a bare assertion). The RDF-star analogy is for *ergonomics intuition only* — Neo4j has no triple-term semantics; do not oversell it as free RDF.

**Risks.** (1) Reification-style sidecar nodes per fact would quadruple graph size — **never** model provenance as separate nodes; use edge properties and ensure deleting a fact deletes its annotation atomically (no orphaned provenance). (2) Named-graph contamination: if you batch facts under one provenance grouping (e.g. all facts from one USGS fetch), enforce one-warrant-per-grouping at the write layer, or per-edge confidence silently inherits the wrong source. (3) The LLM normalization step in our provider seam (`extract`/`normalize`/`judge`) is an *inference Activity*, never a source of asserted facts — it must refuse to emit a user-belief without an attached source+timestamp+role (source-or-silence at the boundary).

---

## Card 4 — Composite confidence: store freshness × authority × corroboration separately, fuse only at floor/presentation time
**Domain:** KG uncertainty (Knowledge Vault) + Fellegi-Sunter + Mills evidence analysis · **Disposition: adopt (we already do this; sharpen it)** · Rule 2 · Confidence-v2, Epic 009

**What it is.** Knowledge Vault computes per-fact truth probability by fusing distinct signals into a binary classifier, and uses **"the square root of the number of sources where the extractor extracted this triple"** as the corroboration feature (verified verbatim against the KDD 2014 paper — the sqrt transform explicitly "reduces the effect of very commonly expressed facts"). Fellegi-Sunter record linkage scores a match as a *sum of per-field log-Bayes-factor weights* (m-prob / u-prob) with a **two-threshold band** (match / clerical-review / non-match). Mills' Evidence Analysis weights every fact on three axes (Source authority / Information quality / Evidence relevance) and **down-weights, never discards** a low-weight source.

**How it maps to our stack.** This validates our shipped model almost exactly. `orchestration/confidence.py` already: (a) keeps three axes — `authority` (per-source tier), `freshness` (live/slow/stale), `corroboration` (count); (b) fuses to one `score`; (c) maps score → `level` → `presentation` (`stated`/`hedged`/`flagged`); (d) sets a `floor` (0.4); and (e) is **consumed only by presentation and guardrail-flagging — the Curator's taste ranking never reads it** (Rule 2, enforced by module boundary). The literature's lesson is: the three axes are stored separately and fused *only at presentation/floor time* — which is what keeps confidence orthogonal to desirability. We already honour this; Confidence-v2 should preserve the separation and make the three sub-scores independently inspectable (the two-axis decomposition card in the product doc).

**Adopt/adapt.** Adopt. Two sharpenings:
- The Fellegi-Sunter **two-threshold band** maps onto our `level` boundaries (`high ≥ 0.75`, `medium ≥ 0.5`, `low < 0.5`). The "medium/hedged" band is the *clerical-review region by design* — it should contain a genuine mix of true and false facts. Calibrate the thresholds against acceptable false-state rates, not by feel.
- Mills' "never discard, only down-weight" is precisely Rule 2's "confidence sets a floor + presentation, never penalizes ranking." Keep it.

**Implementation note.** The current corroboration term is the weak point — see Card 11. Today `c = min(1.0, 0.6 + 0.2·(n−1))` where `n` is a raw count (and in `belief_update.py`, `corroboration_n` is a count of source episodes). Knowledge Vault's sqrt-of-source-count is a *better dampening* than our linear term, but the deeper fix is that `n` must count **distinct independent origins**, not feeds/episodes (Card 11).

**Risks.** Calibration: a confidence score can be internally self-consistent yet systematically *miscalibrated* (a fact scored 0.8 is true only 50% of the time). Add a **proper-scoring-rule / Brier / reliability-diagram** metric to Epic 009 — none of the existing eval hooks would catch miscalibration. (Weather-forecast verification and clinical calibration are the formal disciplines here; the upstream synthesis cites the forecasting *ensemble* half but omits the *verification* half that proves a probability honest.)

---

## Card 5 — Zookies / consistency-spectrum: bind every conclusion/grant to the data version it assumed (defeat the new-enemy problem)
**Domain:** Zanzibar zookies / SpiceDB consistency spectrum · **Disposition: adapt** · Rules 7, 3, 2 · Verifier-freshness epic, auth provider (R3), Confidence-v2

**What it is.** A zookie (SpiceDB ZedToken) is an opaque token encoding a snapshot timestamp; a content-change check at write time returns it, it's stored *atomically with the content*, and later checks evaluate at a snapshot **≥ that timestamp** — defeating the **new-enemy problem** (a revocation that happened-before a content change is always observed). SpiceDB generalizes this into a consistency spectrum: `minimize_latency` (cached, fast, risks new-enemy) / `at_least_as_fresh` (≥ a ZedToken) / `at_exact_snapshot` / `fully_consistent` (all four verified against AuthZed docs).

**How it maps to our stack.** Two distinct uses:
- **Access (R3 / Stage 8).** When a member revokes a share, the cached `$granted_ids` from Card 1 must not let a stale snapshot expose content added after the revoke. **Eventual-consistency caching of the access wrapper is unsafe for revocations.** Use `at_least_as_fresh` for anything in the private overlay: the grant edge carries the data-version it was computed against, and the next traversal re-evaluates at ≥ that version. Only the slow public corpus may use a relaxed/cached consistency (`minimize_latency`).
- **Overlay freshness (Verifier).** The consistency spectrum is a ready-made vocabulary for our per-data-type freshness windows: weather/streamflow/AQI want `at_least_as_fresh` (JIT, never stale-cached); the slow corpus tolerates `minimize_latency`. Every overlay-backed verdict carries its source timestamp; past its window the verdict auto-hedges rather than rendering crisp.

**Adopt/adapt.** Adapt the *model* (version-token bound to content/conclusion). We don't need Spanner TrueTime; a monotonic version/timestamp per source-fetch suffices.

**Implementation note.** Add a `data_version` (or reuse `fetched_at` as the token) to derived conclusions and grant edges. On read, the access wrapper compares the grantee's view-time against the grant's version; the Verifier compares the overlay's `fetched_at` against the data-type window. The revoke-then-add adversarial test (revoke a share, add substrate behind it, assert the revoked party never sees the new content) is the falsifier.

**Risks.** The whole guarantee collapses if a revoke is allowed to take effect only on the *next session* rather than the *next view*. The current static-`granted_ids`-per-session model (Card 1) has exactly this hazard — re-resolve grants at sensitive boundaries or shorten session scope around shares.

---

## Card 6 — Marking propagation with explicit stop-points: a grant becomes a label-propagation property
**Domain:** Palantir Foundry markings + lineage · **Disposition: adapt** · Rules 5, 4, 7 · auth provider (R3), Stage 9 commons, provenance-edge model

**What it is.** A Foundry "marking" is a *mandatory* sensitivity label with conjunctive AND-semantics (a user must hold *all* markings to see a resource; even the owner cannot strip one without explicit "Expand Access" — both verified). Markings propagate automatically along file hierarchy **and data-dependency lineage** (any dataset derived from a marked dataset inherits the marking, transitively, through transform logic), and removing an inherited marking requires an explicit `stop_propagating` declaration in the transform — a deliberate, auditable stop-point (verified against the Foundry docs).

**How it maps to our stack.** This is **Rule 5 made mechanical** and the literal model behind "a grant is a stop-point on a provenance edge." A private overlay node's sensitivity should propagate *down* `DERIVED_FROM` edges by default, so a derived belief is at-least-as-protected as its substrate **by construction**, not by the engine remembering to scope it. A grant is then an explicit `stop_propagating` stop-point on exactly one edge: the shared *derived conclusion* loses the marking; the substrate keeps it. This reframes Rule 4: access scoping becomes a label-propagation problem solved below the agent, not a Cypher-authoring discipline.

**Adopt/adapt.** Adapt. Implement as a `sensitivity` property that propagates along `DERIVED_FROM`/derivation edges, with a grant materialized as a stop-point edge property (`stop_propagating: true`) that the traversal honours.

**Implementation note.** This is the schema-level home for the Stage-8 grant model and the Stage-9 commons k-floor: the commons aggregation is "derived from N private observations with a stop-point at the aggregate." Combine with **Purpose-Based Access Control** (Card 7) so the stop-point edge carries `{purpose, justification, expiry}`.

**Risks.** Conjunctive AND-semantics are strict by design — that's the point (fail-closed). The failure to design against is the *implicit* widening: removing a stop-point must be a single visible, logged, auditable act, never a silent side-effect of a re-derivation.

---

## Card 7 — Purpose-Based Access Control: grant to a scoped purpose + recorded justification + expiry, not to a person
**Domain:** Palantir PBAC · **Disposition: adapt** · Rules 5, 4, 7 · auth provider (R3), Stage 8, Stage 9

**What it is.** Instead of granting a user access to data, the user applies for access to a **Purpose** — a container scoped to a goal, "no more, no less" — and *both* the approver and the data owner record a written rationale at grant time, producing an auditable who-what-**why** trail (verified; "no more, no less" is a paraphrase of Palantir's data-minimization language, not a verbatim quote). It solves RBAC's role-sprawl: across many resources, per-person grants make "who can see what and why" unanswerable.

**How it maps to our stack.** Our household model is a web of person-to-person grants that *will* sprawl like RBAC. PBAC reframes a grant from "Alice can see Bob's data" to "Alice, for the purpose of co-planning the July trip, can see Bob's derived readiness conclusion — expires when the trip is done." The recorded justification is the human-readable companion to Rule 7's provenance-on-every-belief: the grant edge itself carries *why it exists*, so the system can later surface stale/over-broad grants.

**Adopt/adapt.** Adapt. Prefer purpose-scoped grants over per-person RBAC from the first grant schema (R3). One household-specific binding constraint (from `stage-8-multiplayer-privacy.md` and open question PR-#4): **one person's trip deadline must never override another's safety floor** — purpose scoping is what keeps a co-planning grant from leaking the grantor's readiness *substrate* while still sharing the *conclusion*.

**Implementation note.** Grant edge shape: `(:Person)-[:GRANTED {purpose, justification, expiry, data_version, stop_propagating: true}]->(:Conclusion)`. A lint query finds purposeless or expired-but-live grants. The product must ship *no* path to a blanket "see all my data" grant.

**Risks.** Justification-as-theatre: a recorded rationale is only auditable if it's meaningful. Don't let it degrade into a required-but-ignored field.

---

## Card 8 — Ontology as a slow semantic layer with a separated kinetic (action) layer; the frozen-ontology failure
**Domain:** Palantir Foundry Ontology · **Disposition: adopt (the split) + cautionary (frozen ontology)** · Rules 3, 1, 7 · graph schema, Epics 006/007, Verifier-freshness, Confidence-v2

**What it is.** Foundry splits a **static** layer (object/property/link types — the slow "digital twin") from a **kinetic** layer (`action types`: governed, schema-defined edits with declared side-effects); mutation happens only through actions. The dominant cautionary lesson (a 1990s auto-lending case, relayed in a *critique* blog — note: this is an opinion-grade, pre-Foundry anecdote, not a Palantir case study): a "complete" ontology went stale within months of a business change, yielding the maxim that **an incomplete ontology isn't just behind, it's *wrong* — and a wrong ontology is more dangerous than none.** Separately, ontologies black-box embedded value-judgments as if neutral.

**How it maps to our stack.** Validates and sharpens our own split: the slow graph (Rule 3) is the static ontology of trails/terrain/regions; JIT overlays (weather/streamflow/AQI/permits) are the kinetic/ephemeral dimension Foundry deliberately keeps *out* of the indexed object store — i.e. **not nodes** (our schema §8 comment is explicit: live-overlay resolution keys are stored, not live values). The deeper transfer is **action-type discipline**: our Curator/Verifier mutations to user-belief nodes should be governed "actions" that *always* stamp provenance+confidence+timestamp (Card 3) and never let an inference enter the graph as a bare fact.

Two concrete hazards this domain proves are costly:
1. **Staleness-as-falsehood.** A trail node asserting "water at mile 6" that was true last season is now *active misinformation*. This is the external, costly proof of CLAUDE.md's "wrong memory is worse than none" — and the reason per-data-type freshness windows (Verifier-freshness epic) must treat an un-refreshed slow fact as **unverified, not standing truth**.
2. **Inference-as-neutral-fact.** Our taste/readiness inferences (Epics 006/007) are encoded judgments about the user; rendering them as flat facts repeats the black-boxing error. Rule 7's "capability ≠ preference" is the antidote — the watch says what the body *can* do, never what the user *wants*. Our `Belief` schema already tags `type: "inferred"` and `confirmed_by_user: false`; honour that distinction in *presentation*, always with an override affordance.

**Adopt/adapt.** Adopt the static/kinetic split (we have it). Treat the frozen-ontology and neutral-fact failures as cautionary design constraints, not optional.

**Risks.** Over-modeling the ontology is itself the frozen-ontology trap — model only what has a consumer, and make slow facts visibly age past their window.

---

## Card 9 — Persona/Conclusion two-tier identity: non-destructive, reversible conflation via evidence edges
**Domain:** Genealogy (GEDCOM-X) + MDM survivorship + ER · **Disposition: adopt** · Rules 1, 7, 5 · conflation pipeline, Confidence-v2; ties to the live slug-merge audit

**What it is.** GEDCOM-X splits identity into two node tiers: a **persona** (`extracted=true`, MUST reference exactly one source — verified verbatim against the spec: "MUST NOT refer to more than one source description … all source references MUST resolve to the same source description") and a **synthesized conclusion** that carries an `evidence: [EvidenceReference]` list pointing back to the personas. "Merging" is *asserting sameness by adding evidence edges over immutable extracts* — additive and reversible. MDM separates **matching** (which records are the same) from **survivorship** (which attribute value wins) via per-attribute rules (source-precedence / most-recent / most-complete / per-attribute trust). FamilySearch's *destructive in-place merge* is the named catastrophe: "seconds to make, hours to untangle," snowballing across generations, often undetectable once the apparent identity has shifted.

**How it maps to our stack.** This is our `SourceRecord` → `SAME_AS` → `CanonicalTrail` model, *exactly*. Each source's claim is already an immutable `SourceRecord` (the persona: `raw_name`, `raw_geom_wkt`, `fetched_at`, one source). The `CanonicalTrail` is the synthesized conclusion, with `SAME_AS` edges as the `EvidenceReference` list (carrying `match_method`, `matched_on`, `match_score`). Per-attribute survivorship is the right model for our best-view cache (`length_source = "NPS"`, `gain_source = "USGS_3DEP"` — schema §4: NPS wins closures, USGS/3DEP wins elevation, OSM wins names). Disagreement should render as a **range** ("~2.7 mi, sources differ: 2.6–2.8"), never a silently-picked number and never a fabricated average.

**Adopt/adapt.** Adopt. We are already close; the gaps are (a) make merges *reversible* (removing a `SAME_AS` edge leaves the `SourceRecord` byte-identical — our MERGE-based ingest supports this, but assert it as an invariant) and (b) render disagreement as a range with both sources cited rather than collapsing to the best-view value silently.

**Implementation note.** The live **Shenandoah slug-merge (1643 → 1458 canonical_ids)** is the concrete instance of this card *and* Card 10's risk: ~185 collapsed ids may be same-trail or collision. Because this is the substrate beneath every downstream confidence claim, the merge-precision audit should be promoted toward **blocking before live-data dogfood** (open question PR-#5): a wrong fuse means a future closure/streamflow overlay attaches to the wrong real-world place.

**Risks.** Precision misses are worse than recall misses for a calm safety utility — a duplicate trail is annoying; a fused trail is *confidently wrong*. See Card 10.

---

## Card 10 — Transitive-closure / connected-components merge cascade (the conflation failure to design against)
**Domain:** ER / AML / genealogy · **Disposition: cautionary** · Rules 1, 2, 3 · conflation pipeline, Epic 009

**What it is.** After pairwise matching, ER systems often cluster by transitive closure / connected components (A~B, B~C ⇒ A=B=C). This boosts recall but **disregards negative classifications**, so a *single* false-positive edge can chain-merge distinct entities into one bloated cluster — precision collapses, and the failure is invisible at the pair level (each edge looked plausible). Verified against the HPI/Draisbach work: "Calculating the transitive closure disregards negative classifications," producing the "black-hole entity." AML adds the quantitative stakes: rule-based monitoring runs at a **95–98% false-positive rate** (confirmed across multiple industry sources; the often-cited "$180B FATF compliance cost" figure is *corroborated in magnitude but misattributed* — it is an industry/IMF estimate, not FATF, and the originally-cited page does not contain it).

**How it maps to our stack.** Our world entities are shared `CanonicalTrail` nodes. If conflation uses naive transitive closure, one bad geometry/name match can fuse two distinct trails into one node — and then live overlays (closures, streamflow, permits) attach to the *wrong* real-world place, delivering confidently-wrong safety information. **This is the highest-stakes failure for a self-verifying safety utility: it corrupts the substrate before confidence is even computed**, defeating source-or-silence at the root.

**Design-against.**
- Gate every merge with an explicit `match_score` threshold (we have it: `so.match_score = 0.88`, `sn.match_score = 0.95`) **plus a degree/size guard** so a shared weak identifier (a common name like "Lost Lake Trail") can't snowball.
- **Cap component size** — refuse to auto-merge into a large cluster; route it to review (our `reviewed_by`/`reviewed_at` fields are the hook).
- Prefer weighted/correlation clustering that respects *negative* evidence over naive connected-components.
- The Fellegi-Sunter **clerical-review band** (Card 4) is the right model: matches in the middle band go to human review, not auto-fuse.

**Risks.** Eval hook (Epic 009): inject a known false-positive match edge between two distinct trails and assert the clustering step does **not** cascade-fuse their neighborhoods; assert no safety overlay attaches to a fused-ambiguous node without a confidence penalty. Falsified the moment one injected bad edge yields a multi-trail mega-node.

---

## Card 11 — Independence-checked corroboration: walk to distinct origins, fuse by weakest-link, never re-ingest your own output
**Domain:** KG citogenesis + AML circular reporting + genealogy false corroboration + ISO 22095 + sensor-fusion covariance · **Disposition: adapt** · Rules 2, 7, 5 · Confidence-v2, Stage 9 k-floor

**What it is.** Real corroboration counts **distinct upstream origins**, not citing feeds. NWS + a weather aggregator sharing one model run = *1* source; two trail reports quoting one ranger = *1*. The failure has many names: **citogenesis** (the engine's own output re-ingested as an external observation), **circular reporting** (Iraq Curveball), **false corroboration** (several APIs reselling one OSM extract). The formal backbone the upstream synthesis under-cited: **sensor-fusion covariance** — fusion theory *proves* correlated measurements must not be treated as independent (the off-diagonal covariance term is exactly the citogenesis governor, as math not anecdote). ISO 22095 chain-of-custody says the **weakest link caps the claim** (fuse by MIN over the provenance chain, not average or feed-count). Mills' evidence analysis requires checking corroborating items are "independently created … or whether all might be tracked back to a common source" (verified verbatim).

**How it maps to our stack.** **This is the single most consequential gap in the shipped code.** `orchestration/confidence.py` computes corroboration as `c = min(1.0, 0.6 + 0.2·(n−1))` where `n` is a raw count; `belief_update.py` recounts `corroboration_n` as a count of source episodes. *That is exactly the feed-counting the literature says to replace.* The fix:
1. Make the corroboration leg count **DISTINCT upstream origins**, computed by a Cypher traversal to origin nodes (walk `SAME_AS`/`DERIVED_FROM` to the originating `Source`/`SourceRecord`), not a count of citing feeds.
2. Fuse the floor by **MIN over the provenance chain** (ISO 22095 weakest-link), not the current additive blend, for the *safety floor* specifically.
3. Add a hard rule that the engine **never re-ingests its own derived output as an external observation** (citogenesis self-loop) — a `role`-tag check (Card 3): a `CORPUS_DERIVED`/`INFERRED` node may not enter the corroboration count as an independent origin.

This is the one capability a graph has that humans cannot do by hand. It also **feeds the Stage-9 commons k-floor** (Card 12 below): counting non-independent parties (one trip re-shared N times) can falsely cross the k threshold, so the same origin-walk governs both corroboration and the commons gate.

**Adopt/adapt.** Adapt — this is a net-new traversal + a rewrite of the corroboration term, not a tweak.

**Risks / feasibility gate (open question PR-#3).** This assumes the graph can resolve each fact to a distinct origin. **Do NWS / USGS / AirNow / RIDB / FIRMS expose enough origin metadata to tell a shared model-run from an independent observation?** If origin is unrecoverable for a source pair, the **safe default is treat-as-shared (conservative: count as 1)**, not treat-as-independent. Until a feasibility spike answers this per-source, the "moat" framing ("their corroborated is our echo") is *conditional* and must be hedged — if origin is unrecoverable for most pairs, CDP-01 degrades to a relabeling exercise. Gate the build on the spike.

---

## Card 12 — k-anonymity-gated commons aggregation, fed by the independence walk
**Domain:** AML community labeling + de-identification + DP composition · **Disposition: adopt (with a known-incomplete caveat)** · Rules 5, 4, 2, 8 · Stage 9 commons read/aggregation half, Epic 010 (write half, shipped)

**What it is.** AML systems score/label communities collectively but only **publish aggregate statistics once the group exceeds a minimum size** — the same construct as a k-anonymity threshold; singleton/tiny components re-identify individuals. WCC produces mostly size-1 components; meaningful signal lives in larger ones.

**How it maps to our stack.** This is the architectural skeleton of the Stage-9 commons *read* half. The write half is shipped (Epic 010): `CommonsObservation` nodes are **born severed** — no `owner_id`, no edge to any `Person`/`Episode`, de-identified at write (schema §6, §8.2). The read half publishes only **derived conclusions** ("most parties found this approach passable in late June") and only when **≥k independent parties** back it, with the k-floor enforced in the *aggregation query* (Rule 4), never the agent. Below k: silence. The independence walk (Card 11) is load-bearing here: counting non-independent parties (one trip re-shared, or the engine's own output) can falsely cross the floor.

**Adopt/adapt.** Adopt the gate. **Caveat the guarantee.** The project's own `stage-9-commons.md` (S9-14) already flags that **k-anonymity is weak under snapshot-differencing / repeated longitudinal release** — DP composition theorems are the formal answer the k-floor alone does not provide. Present the commons read half as k-floor-*plus*-deferred-DP, not as a clean privacy guarantee; the upstream "adopt, clean" framing understates this known-incomplete posture.

**Implementation note.** Enforce the k-floor as a `HAVING count(DISTINCT origin) >= $k` in the aggregation Cypher, where `origin` comes from the Card-11 independence walk, not a raw `CommonsObservation` count. No commons query path may traverse from an aggregate back to a private overlay node (adversarial re-identification test, Epic 009).

**Risks.** Singleton leak; non-independent inflation over the floor; longitudinal snapshot-differencing (the DP gap). All three are eval targets.

---

## Card 13 — Transitive staleness propagation: a conclusion inherits a risk flag when its substrate changes, by edge-walking
**Domain:** Legal citators (KeyCite Overruling Risk) + Palantir lineage · **Disposition: adapt** · Rules 5, 7, 3 · Confidence-v2, Stage 9

**What it is.** When a source a derived belief rests on later changes or is retracted, the conclusion inherits a staleness/risk flag **automatically by walking provenance edges** — even though the conclusion node was never directly re-verified. Only one of three legal citators even attempts this; it catches the silent-stale failure (a confidently-stated derived belief outliving its substrate).

**How it maps to our stack.** This is the same edge-walk that enforces the grant boundary (Card 6) and computes corroboration (Card 11), run in the *invalidation* direction along `DERIVED_FROM`. A `Belief` derived from an `Episode`, or a cached "go" set derived from a now-stale overlay, gets a quiet downgrade flag when its substrate changes — risk surfaces on the *conclusion* without re-deriving it. Our verdict/Curator layer (when built) needs this to avoid caching a "go" set under stale assumptions.

**Adopt/adapt.** Adapt. Implement as a Verifier-cycle pass: when a substrate node is invalidated, flip every derived belief reachable along same-topic `DERIVED_FROM` edges to a risk state within one cycle.

**Risks.** Over-propagation: an irrelevant substrate change should not flag unrelated conclusions — scope the walk by topic/edge-type, or every minor overlay flicker greys the whole feed (the alarm-fatigue trap, distinct from this card's domain but adjacent).

---

## Card 14 — Bitemporal "as-of" replay + Identity/State split: auditable slow corpus, never-persisted overlays
**Domain:** SQL:2011 bitemporal + Neo4j temporal-versioning pattern + CDN SWR/SIE · **Disposition: adapt** · Rules 1, 7, 3, 2 · Verifier-freshness, Epic 009 (replay), slow-corpus ingestion

**What it is.** Bitemporal modeling splits **valid time** (when a fact is true in the world) from **transaction time** (when the system learned it) — SQL:2011 standardizes both, reusing existing date-time columns (verified). Transaction time is append-only → an immutable audit log; corrections *append*, never overwrite. Neo4j has no native versioning, so the community pattern splits each entity into an immutable **Identity node** + time-bounded **State nodes** carrying `from`/`to` (verified against the Neo4j blog; current = `NOT EXISTS(r.to)`, point-in-time = `r.from <= T AND (r.to >= T OR NOT EXISTS(r.to))`). For ephemera, CDN **stale-while-revalidate** (serve stale + async refresh) / **stale-if-error** (serve stale only on origin failure) governs a freshness window and the object *expires* — never becomes durable state (verified; note the precedence rule is Fastly implementation behavior, not RFC 5861).

**How it maps to our stack.** Two halves of Rule 3:
- **Slow corpus → versioned + auditable.** When a user followed a "GO" verdict that later looks wrong, we must reconstruct what live sources said *at the moment of the verdict* (transaction time = when the Verifier fetched; valid time = the real-world window the condition applied to). This is the formal backbone for replay (Epic 009): store a verdict + its source snapshots at T0; an "as-of T0" query must reproduce the original verdict byte-for-byte even after upstream data changes. Our `ingest_version` ("2026-06") and `fetched_at` are the seeds of this; the Identity/State split is the upgrade path when slow facts start changing (a trail reroute, a seasonal closure rule). Crucially, **grants and provenance edges attach to the Identity node, not a transient State**, so re-versioning never orphans a grant (Rule 4/5 anchoring survives).
- **Overlays → freshness window, never persisted.** SWR/SIE is the formal model for the Verifier-freshness epic; the schema §8 comment already mandates "live-overlay resolution keys (NOT live values)."

**Adopt/adapt.** Adapt. Reserve *full* bitemporality for the few fact-types that genuinely get retroactively corrected (a backdated regulation); most slow facts need single-axis valid-time states; overlays need *no* persistence, only a window.

**Risks (the SCD-2 cautionary).** Hand-managed `valid_to` ranges silently produce gaps/overlaps that corrupt time-bounded joins with no error (the IRS in-place-overwrite case destroyed an audit trail). Enforce **at most one open State per Identity** at ingest, make corrections append-only (immutable once superseded), and prefer **idempotent datestamped re-ingest of a region** over surgical range edits (our MERGE-by-`ingest_version` pipeline already leans this way). A bitemporal "as-of" replay that reconstructs a historical verdict purely from its archived snapshot is the Epic 009 falsifier. Reconcile auditability with Rule 3 by persisting an immutable *hashed snapshot of the decision substrate* — without persisting ephemeral data as live graph nodes.

---

## Card 15 — Personalized-PageRank candidate generation + multi-hit boosting over the trail graph; design against the Matthew effect
**Domain:** Pinterest Pixie random walks + RecWalk · **Disposition: adapt + cautionary** · Rules 7, 2, 9 · Epic 006 (novelty/taste), Epic 009

**What it is.** Pixie computes real-time Personalized PageRank by Monte-Carlo random walks with restart (α=0.5) over a bipartite graph, seeded from a weighted query set, ranking nodes by visit count (~60ms, no training). **Multi-hit boosting** combines per-seed visits as `V[p] = (Σ_q √V_q[p])²` (verified verbatim, incl. the 4-4-4-4→64 vs 16-0-0-0→16 example) so an item corroborated by *multiple* seeds outscores one reached the same total from a single seed. **Adaptive early termination** stops once ~2000 distinct nodes are each visited ≥4 times (~84% of full-convergence at ~3× speedup — verified). The defining failure (RecWalk, verified): naive walks "rapidly concentrate towards the central nodes of the graph" — the **Matthew effect** — collapsing personalization into global popularity.

**How it maps to our stack.** Our corpus is already a Neo4j graph of trails/regions/features/terrain. Epic 006's taste/novelty problem *is* "recommend over a connected corpus from a few liked items." Seed a walk from a member's liked/completed trails (`(:Person)-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)`), read candidates off visit counts. It needs no training (Rule 9), the restart probability α is literally the **familiar↔adventurous dial**, and the graph path *is* the provenance of the suggestion (Rule 7). Multi-hit boosting is corroboration scored by topology — but **use it for the confidence/hedge layer, not to penalize a genuinely-good single-source match** (Rule 2 nuance).

**Cautionary (the existential product risk).** For a *calm private utility*, popularity dominance is not a quality dip — it's product death. A walk that keeps surfacing Half Dome / Angels Landing has failed the thesis. The dual risk to Rule 2: confidence must not penalize desirability, but graph *centrality must not covertly inflate it* either. Design against from day one: degree-capping, an explicit novelty term, and keep a "popular nearby" lane **separate and labeled** from the personalized "for you" lane.

**Risks.** Eval hook: measure Spearman rank-correlation between per-user recommendation order and global node degree — alert if > ~0.5 (the upstream synthesis suggests >0.7 as a hard falsifier). Track personalization divergence: two users' top-k should have low overlap. Also pair with a cold-start / sparse-seed empty-state ("not enough to confidently suggest yet") rather than padding the feed (source-or-silence applied to compute).

---

## Card 16 — Routing keeps geometry immutable, costs query-time; "no route" is a sourced empty-state; snap is a probabilistic inference
**Domain:** pgRouting / Valhalla · **Disposition: adopt (integrity gate, cost model) + adopt (HMM snap)** · Rules 1, 3, 7, 2, 6 · Epic 007 (effort floor as cost), Verifier-freshness, Stage 9 commons fork

**What it is.** Three mechanics. (1) **`cost`/`reverse_cost`** decouples an edge's immutable geometry from a swappable, *directional*, query-time cost expression — a ridge that's a green descent and a black ascent is one edge with two costs; a flooded ford is `cost=∞` *for today only* (verified). (2) **Topology integrity gate**: pgRouting can't route on un-noded geometry; `pgr_analyzeGraph` enumerates isolated segments, dead ends (`cnt=1`), gaps (`chk=1`), rings (verified; note "disconnected components" is detected by a *separate* function `pgr_connectedComponents`, and the "silently returns no path" behavior is real but not a doc-quoted sentence). (3) **Snap-to-network** is the Newson-Krumm HMM (Gaussian emission on point-to-segment distance + route-connectivity transition + Viterbi), explicitly degrading as GPS sampling sparsens (verified against the SIGSPATIAL '09 record and Valhalla's Meili implementation) — *not* a nearest-edge lookup.

**How it maps to our stack.** (1) The cost model is the cleanest template for slow-corpus / JIT-overlay: the trail graph (geometry, grade, junctions — our `Segment`/`Junction`/`route_geom_wkt`) is the stable substrate; weather, a flooded ford, snow line, a permit closure, and **Epic 007's effort floor** are all query-time cost *terms*, never persisted graph state. `reverse_cost` maps directly to asymmetric trail difficulty. Epic 007's Body-Battery→effort floor acts as a cost *modifier*, keeping capability (the watch signal) a weighting term distinct from immutable trail facts (Rule 7). **A low-confidence overlay must hedge presentation, not silently inflate cost and reorder candidates.** (2) The integrity gate turns "no route found" (a silent fabrication-by-omission) into a sourced empty-state: "No connected trail path in our data between A and B (segment X isolated; last ingested USFS 2026-05). We won't guess." Connectivity also guards proximity search — a graph-isolated trailhead must never appear in "reachable" results even if euclidean-near. (3) Any time we associate a watch/GPS track with our graph (which trail an `Episode` happened on; snapping a FIT track for the commons fork; resolving a tapped pin), the HMM gives a *confidence* on the snap and a connectivity check — naive nearest-edge teleports points onto a parallel/unreachable trail and then attributes facts to the wrong place (Rule 7: the snap is an inference, capability ≠ a stated fact; Rule 6: degrade-and-disclose for sparse tracks).

**Adopt/adapt.** Adopt the integrity gate and cost model; adopt the HMM snap (gating watch-track influence on Epics 006/007 and the Stage-9 commons fork on snap confidence — a natural k-anonymity-style quality floor).

**Implementation note.** We compute geometry at ingest in Python/Shapely/GDAL and store the graph + WKT in Neo4j (no PostGIS in v0, schema header). The `analyzeGraph`-equivalent must run *in our ingest pipeline* per region; quarantine isolated/dead-end edges from proximity results. The watch-snap HMM-confidence gate should exist **before any watch track influences taste/readiness** (open question PR-#8 — the always-on poller is the deferred R7 piece), to prevent a low-confidence snap silently attributing an outcome to the wrong trail.

**Risks.** Do **not** precompute routing structures (Contraction-Hierarchy-style shortcuts) against ephemeral or per-user costs — CH assumes a static cost function, so any overlay/effort-floor change invalidates the preprocessing and couples the slow corpus to fast data (Rule 3 violation). Any speedup layer is built only over stable topology+geometry; live overlays and effort floors stay query-time terms.

---

# How this lands in our stack

### Rule 4 (access control at the query layer) + Rule 5 (grant = stop-point)
- **Already shipped, right shape:** `ScopedSession` + `owner_scope` + the write-guard regex (Cards 1, 2). The `scopedQuery` seam is the Zanzibar Check choke-point in embryo.
- **Net-new, ordered:** (a) **real viewer auth** (gap-audit C3 / Epic 014) — the choke-point is worthless with a forgeable principal; this is the Stage-8 precondition. (b) **read-side egress lint** mirroring the write guard (Card 2). (c) **userset-rewrite resolution of `$granted_ids`** at session-open (Card 1) when R3 lands. (d) **marking-propagation + stop-points** along `DERIVED_FROM` so Rule 5 is a label-propagation property, not engine memory (Card 6). (e) **Purpose-Based grants** with `{purpose, justification, expiry, data_version}` over per-person RBAC (Card 7). (f) **consistency-token / at_least_as_fresh** on grants so a revoke takes effect on the grantee's *next view*, not next session (Card 5) — the static-`granted_ids`-per-session model has exactly the new-enemy hazard.

### Rule 7 (provenance + confidence + timestamp on every belief; capability ≠ preference)
- **Already shipped:** `SAME_AS` and `DERIVED_FROM` provenance edges; `Belief.{axis, type, confirmed_by_user}`; computed-on-read 3-axis confidence (`orchestration/confidence.py`).
- **Net-new:** (a) a **`ProvenanceBundle` stamped by the Verifier fetch wrapper by construction** — `{source, fetched_at, content_digest, role}` — with `role ∈ {LIVE_FETCHED, CORPUS_DERIVED, INFERRED}` carrying the capability≠preference distinction; a fact without a complete bundle is unrenderable (Card 3). (b) **transitive staleness propagation** so a derived conclusion inherits a risk flag when its substrate changes (Card 13). (c) **bitemporal as-of replay** for past-verdict reproducibility (Card 14, Epic 009).

### Epic 006 (taste/novelty)
- **Personalized-PageRank over the trail graph** seeded from `(:Person)-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)`, α as the familiar↔adventurous dial, multi-hit boosting for topology-corroboration (Card 15). **Mandatory guardrail:** degree-cap + separate "popular" lane + a degree-correlation eval — the Matthew effect is an existential risk for a calm utility, not a quality dip.

### Epic 011 (scoped-write) + the auth provider (R3) + Stage 8
- Epic 011's write guard *is* the Zanzibar "make the un-gated query unconstructible" stance (Card 2). R3 should build on **tuple+userset-rewrite** (Card 1) + **marking-propagation stop-points** (Card 6) + **PBAC** (Card 7) + **consistency tokens** (Card 5). Stage 8 is gated on Epic 014 (real auth) — the household constraint that *one person's deadline must never override another's safety floor* is a purpose-scoping requirement, not an afterthought.

### Stage 9 (commons read/aggregation, k-anonymity)
- **k-floor enforced in the aggregation Cypher** (`HAVING count(DISTINCT origin) >= $k`), fed by the **independence walk** so non-independent parties can't inflate the floor (Cards 11, 12). The write half (Epic 010, `CommonsObservation` born-severed) is shipped. **Caveat:** k-anonymity is known-incomplete under snapshot-differencing (the project's own S9-14); present as k-floor-plus-deferred-DP.

### The conflation pipeline (OSM × USGS × USFS × NPS) — the substrate beneath everything
- Our `SourceRecord`/`SAME_AS`/`CanonicalTrail` model is the genealogy persona/conclusion split (Card 9). **Guard transitive-closure cascade** with threshold + degree/size guards + component-size caps + a human-review band (Card 10). **Promote the Shenandoah slug-merge audit toward blocking** before live-data dogfood — a wrong fuse corrupts the substrate beneath every downstream confidence claim and attaches safety overlays to the wrong place (open question PR-#5).

### The corroboration leg of confidence — the highest-leverage single change, feasibility-gated
- Replace `c = 0.6 + 0.2·(n−1)` (feed-count) with **distinct-origin count via traversal + weakest-link MIN for the safety floor + a no-self-ingest citogenesis rule** (Card 11). **Gate the build on a feasibility spike**: do NWS/USGS/AirNow/RIDB/FIRMS expose recoverable origin metadata? Default to *treat-as-shared* (count as 1) where origin is unrecoverable. The same walk feeds the Stage-9 k-floor.

### Epic 009 (eval harness) — what these cards demand it test
- **Calibration** (Brier / reliability diagram) — no existing hook catches a confidence that is self-consistent yet miscalibrated (Card 4).
- **Adversarial access traversal** (revoke-then-add; non-granted viewer reaches zero substrate) (Cards 1, 5, 6).
- **Conflation cascade injection** (one bad edge must not fuse a neighborhood) (Card 10).
- **As-of replay** (a historical verdict reconstructs from its snapshot) (Card 14).
- **Degree-correlation** (recommendations must not track global popularity) (Card 15).
- **Topology integrity** (every route is node-connected; isolated edges quarantined) (Card 16).
- **Commons re-identification** (no aggregate below k; no path from aggregate to private node) (Card 12).
- **Structure-vs-baseline A/B** — several of these patterns (rich provenance UI, ACH-style framing) may be scaffolding that does not actually debias (Dhami-2024: ACH did *not* reduce confirmation bias). Be prepared to cut patterns the eval shows are decorative.

---

# References

Sources below were verification-checked; where the upstream research misattributed a source or left a figure unverified, the correction is noted inline above and flagged here.

**Zanzibar / ReBAC**
- Pang et al., "Zanzibar: Google's Consistent, Global Authorization System," USENIX ATC 2019. https://www.usenix.org/system/files/atc19-pang.pdf · https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/ *(all four scale/latency figures confirmed against the paper)*
- AuthZed, "Zanzibar" explainer + "New Enemies" + SpiceDB consistency docs. https://authzed.com/zanzibar · https://authzed.com/blog/new-enemies · https://authzed.com/docs/spicedb/concepts/consistency
- OpenFGA authorization concepts. https://openfga.dev/docs/authorization-concepts

**Fraud / AML graph patterns**
- Blumenfeld, "Exploring Fraud Detection with Neo4j GDS, Part 2" (P2P demo; 87.5% lift, SHARED_IDS rule). https://neo4j.com/blog/developer/exploring-fraud-detection-neo4j-graph-data-science-part-2/ *(confirmed)*
- TigerGraph, "Money Laundering Detection — Structuring and Layering" (typology-as-traversal). https://www.tigergraph.com/blog/money-laundering-detection-with-aml-graph-analytics-structuring-and-layering/ *(confirmed)*
- AML false-positive rate (95–98%): RegFyl / Trapets / industry. https://www.regfyl.com/post/how-to-reduce-false-positives-in-aml-transaction-monitoring *(rate confirmed; the "$180B FATF" figure is corroborated in magnitude but misattributed — it is an industry/IMF estimate, not FATF)*

**KG provenance**
- W3C, PROV-O. https://www.w3.org/TR/prov-o/ · RDF 1.2 Concepts (reification reformulated as triple terms). https://www.w3.org/TR/rdf12-concepts/
- Carroll, Bizer, Hayes, Stickler, "Named Graphs, Provenance and Trust," ISWC 2004 (content/warrant separation; trust as consumer-side policy). http://wbsg.informatik.uni-mannheim.de/bizer/SWTSGuide/carroll-ISWC2004.pdf *(confirmed verbatim)*
- Dong et al., "Knowledge Vault," KDD 2014 (sqrt-of-source-count corroboration feature). https://www.cs.ubc.ca/~murphyk/papers/kv-kdd14.pdf *(confirmed verbatim; evidences the corroboration leg specifically, not freshness/authority)*
- RDF reification verbosity / anti-pattern. https://www.w3.org/community/rdf-dev/2022/01/26/provenance-in-rdf-star/

**Palantir entity + access model**
- Foundry: Markings (mandatory, conjunctive AND). https://www.palantir.com/docs/foundry/security/markings · Remove inherited markings (`stop_propagating`/`stop_requiring`). https://www.palantir.com/docs/foundry/building-pipelines/remove-inherited-markings · Ontology overview (static/kinetic). https://www.palantir.com/docs/foundry/ontology/overview *(all confirmed)*
- Purpose-Based Access Control. https://blog.palantir.com/purpose-based-access-controls-at-palantir-f419faa400b3 *(confirmed; "no more, no less" is a paraphrase)*
- Frozen-ontology critique (Vonng, relaying a 1990s pre-Foundry anecdote — opinion-grade, not a Palantir case study). https://blog.vonng.com/en/db/ontology-bullshit/

**Graph recommendation / random walks**
- Eksombatchai et al., "Pixie," WWW 2018 (multi-hit boosting `(Σ√v)²`; early termination 2000/4 at ~84%/3×). https://ar5iv.labs.arxiv.org/html/1711.07601 · https://cs.stanford.edu/people/jure/pubs/pixie-www18.pdf *(confirmed; note 3× = vs fixed-walk-length, distinct from the ~2× early-stopping figure)*
- Nikolakopoulos & Karypis, "RecWalk" (Matthew effect; nearly-uncoupled chains). https://arxiv.org/abs/1909.03579 · https://dl.acm.org/doi/10.1145/3289600.3291016 *(confirmed verbatim)*

**Entity resolution / record linkage**
- Fellegi-Sunter mechanics (additive log-Bayes weights; two-threshold band). https://www.robinlinacre.com/maths_of_fellegi_sunter/ · https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html *(confirmed; additive form assumes conditional independence)*
- Blocking (silent recall loss; multi-pass). https://moj-analytical-services.github.io/splink/demos/tutorials/03_Blocking.html · https://cs.anu.edu.au/people/peter.christen/publications/kdd03-6pages.pdf *(confirmed)*
- MDM survivorship vs matching. https://profisee.com/blog/mdm-survivorship/ *(confirmed; practitioner-consensus, no single standard)*
- Draisbach et al., transitive-closure "disregards negative classifications" / black-hole entity. https://hpi.de/oldsite/fileadmin/user_upload/fachgebiete/naumann/publications/PDFs/2019_draisbach_transforming.pdf · Christophides et al. ER survey, arXiv:1905.06397 *(confirmed; the upstream VLDB/p1506 citation for this point was misattributed — that paper is BrewER and does not contain it)*

**Genealogy data modeling**
- GEDCOM-X conceptual model (persona single-source constraint; evidence references; confidence enum; attribution). https://github.com/FamilySearch/gedcomx/blob/master/specifications/conceptual-model-specification.md *(confirmed verbatim)*
- Mills, "QuickLesson 17: Evidence Analysis Process Map" (three classifications + independent-origin check). https://www.evidenceexplained.com/content/quicklesson-17-evidence-analysis-process-map *(confirmed; framed as a sequential pipeline, not strictly orthogonal axes)*
- FamilySearch, "Merge Duplicates" (destructive-merge cautionary). https://www.familysearch.org/en/blog/familysearch-merge-duplicates *(confirmed verbatim)*

**Temporal / bitemporal / versioned graphs**
- SQL:2011 temporal survey. https://illuminatedcomputing.com/posts/2019/08/sql2011-survey/ · https://wiki.postgresql.org/wiki/SQL2011Temporal *(confirmed)*
- Fowler, "Bitemporal History" (append-only corrections; complexity warning). https://martinfowler.com/articles/bitemporal-history.html *(confirmed verbatim)*
- Lazarevic, "Keeping track of graph changes using temporal versioning" (Neo4j Identity/State pattern). https://medium.com/neo4j/keeping-track-of-graph-changes-using-temporal-versioning-3b0f854536fa *(confirmed)*
- Fastly, stale-while-revalidate / stale-if-error. https://www.fastly.com/documentation/guides/concepts/edge-state/cache/stale/ · RFC 5861. https://httpwg.org/specs/rfc5861.html *(confirmed; precedence rule is Fastly implementation, not RFC)*

**Spatial routing & isochrones**
- pgRouting: `pgr_analyzeGraph` / `pgr_nodeNetwork` / cost-reverse_cost. https://docs.pgrouting.org/3.0/en/pgr_analyzeGraph.html · https://workshop.pgrouting.org/0.6.1/en/chapters/shortest_path.html *(confirmed; "disconnected components" is a separate function `pgr_connectedComponents`)*
- Valhalla isochrone API (Dijkstra-grid contour; Douglas-Peucker artifacts). https://valhalla.github.io/valhalla/api/isochrone/api-reference/ · https://valhalla.github.io/valhalla/thor/isochrones/ *(confirmed; grid cell-size figure lives in engine internals, not the API page)*
- Newson & Krumm, "Hidden Markov Map Matching Through Noise and Sparseness," ACM SIGSPATIAL 2009. https://www.microsoft.com/en-us/research/publication/hidden-markov-map-matching-noise-sparseness/ · https://dl.acm.org/doi/10.1145/1653771.1653818 · Valhalla Meili. https://valhalla.github.io/valhalla/meili/algorithms/ *(confirmed)*
- Contraction Hierarchies (static-cost-function caveat). https://en.wikipedia.org/wiki/Contraction_hierarchies

**Companion doc:** [`cross-domain-pattern-library.md`](cross-domain-pattern-library.md) — the product/design-facing half (adopt-queue CDP-01…20, pattern register PR-01…132, UX manifestations). **Internal anchors:** [`stage-2-schema.md`](stage-2-schema.md), [`stage-8-multiplayer-privacy.md`](stage-8-multiplayer-privacy.md), [`stage-9-commons.md`](stage-9-commons.md), [`stage-4-engine-and-cost.md`](stage-4-engine-and-cost.md), `graph/schema.cypher`, `graph/client.py`, `graph/queries.py`, `orchestration/confidence.py`.
