# Epic 015 — CI Neo4j integration (live owner-isolation guardrail)

**Status:** DEFINED
**Phase:** 1 (Personal Intelligence) — thread T1 (infra/CI) · T2 (access control)
**Spec refs:** roadmap R2 · decision-log §17 (security/privacy tests) · Rule #4 (access control at the query layer) · Epic 011 (scoped-write seam)

---

## Capability statement
The access-control invariant — Rule #4, "`scopedQuery(viewer)` is the only path to owned data; no ungranted node ever returns" — is proven **end-to-end against a real Neo4j in CI**, on a separate required job, so an owner-clause regression **fails the build** instead of merging silently.

## Architectural context
**Builds on:** Epic 011 (`graph/client.py` `ScopedSession.run`/`run_write`/`execute_write`; `graph/queries.py` `assert_scoped_write`, `owner_scope`) and the Epic 010/002/003 owned-node writers (Episode/Belief/Outcome/PhysicalProfile).
**Enables:** a trustworthy merge gate for every future owned-node read/write (multiplayer Stage 8 makes this consequential); a live-Neo4j fixture that downstream E2E tests (e.g. Epic 003's seeded-Josh DoD) can reuse.
**Does NOT include:** changing any access-control code (the seam already landed); the always-on poller; per-PR DB requirement on the existing fast legs (they stay DB-free).

**Why this is needed (the gap it closes):** today the scope guard runs in CI only as *unit* tests with a fake, duck-typed session asserting on Cypher strings — **no test round-trips a real Neo4j driver + real Cypher**. So the invariant has never been proven against the actual database. This epic adds that proof, isolated so the fast legs stay quick.

**Design decisions (ratified 2026-06-26):**
- **Enforcement:** a **separate, required `integration` job** (not advisory, not folded into the `test` leg).
- **Invariant asserted:** read isolation + write isolation + a **falsifiability** check (an unscoped query *does* leak, proving the scoped one earns its keep).
- **Bootstrap/auth:** schema applied via the bolt driver in a fixture (not `docker compose exec`, which a GitHub `services:` container can't use); service `neo4j:5-community` with `NEO4J_AUTH=neo4j/testpassword`; everything gated behind a registered `@pytest.mark.neo4j` marker.

---

## Stories

### S1 — Marker isolates DB tests; fast legs stay green and DB-free

**Given** the existing 4 matrix legs (format-check/lint/typecheck/test) install only `.[dev]` (no neo4j driver)
**When** the `neo4j` marker and the default deselect are added
**Then** the existing suite is unchanged and the DB tests run only where a database is present.

**AC-1.1:** A `neo4j` marker is registered under `[tool.pytest.ini_options] markers` in `pyproject.toml` (no "unknown marker" warning under `-W error`).
**AC-1.2:** `make test` runs `pytest -q -m "not neo4j"`; the existing DB-free tests stay green and collect **zero** `neo4j`-marked tests.
**AC-1.3:** The integration leg **fails loudly** (readable connection error), never passes as "0 tests", when `pytest -m neo4j` runs with no reachable database — i.e. a missing service is a red build, not a silent no-op.

### S2 — Live-Neo4j fixture: schema bootstrap + per-test isolation

**Given** a reachable `neo4j:5-community` service and `NEO4J_URI/USER/PASSWORD` env
**When** the integration tests run
**Then** the schema is applied via the driver and each test starts from a clean graph.

**AC-2.1:** A session-scoped fixture builds a real `GraphClient(uri, user, password)` from env and applies `graph/schema.cypher` over the bolt driver (statement-split on `;`), **not** via `docker compose exec`/`cypher-shell`.
**AC-2.2:** A function-scoped fixture clears the graph (`MATCH (n) DETACH DELETE n`) before each test so tests are independent and order-free.
**AC-2.3:** The fixture is `@pytest.mark.neo4j` and is the **only** place a test opens a live driver connection.

### S3 — Read isolation (Rule #4)

**Given** members A and B each owning an `:Episode`/`:Belief`/`:PhysicalProfile` (distinct `owner_id`)
**When** A reads owned data through `scoped_session(A).run(<a graph.queries owned-read builder>)`
**Then** A sees only A's nodes.

**AC-3.1:** A's scoped read returns A's owned nodes.
**AC-3.2:** The same scoped read returns **none** of B's owned nodes.
**AC-3.3 (falsifiability):** An **unscoped** read of the same label returns **both** A's and B's nodes — demonstrating the scope clause is what provides isolation (this test fails if `owner_scope`/the WHERE clause is removed).

### S4 — Write isolation (Rule #4 extended — Epic 011)

**Given** member A's scoped write session
**When** A writes owned nodes, and when A attempts to write a node carrying B's `owner_id`
**Then** A can only create/own its own nodes and can never write B's.

**AC-4.1:** A's `run_write`/`execute_write` of an owned node persists it with `owner_id == A` (round-tripped and read back).
**AC-4.2:** A statement that would MERGE/SET an owned node without an A-scoped owner clause is **rejected by `assert_scoped_write`** (raises), so no cross-owner write reaches the DB.
**AC-4.3:** After A's writes, `scoped_session(B).run(...)` cannot see A's newly written owned nodes.

### S5 — Required `integration` CI job

**Given** the CI workflow
**When** a PR or push runs
**Then** the owner-isolation tests run against a real Neo4j and gate the merge.

**AC-5.1:** A new `integration` job in `.github/workflows/ci.yml` runs a `neo4j:5-community` service with `NEO4J_AUTH=neo4j/testpassword` and waits for health (service `--health-cmd` or a bolt wait-loop) before tests.
**AC-5.2:** The job installs `.[dev,graph]` (so the `neo4j` driver is present — the default `test` leg deliberately does not) and runs `pytest -m neo4j` with `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j`, `NEO4J_PASSWORD=testpassword`.
**AC-5.3:** The job is **required** (no `continue-on-error`); a failing owner-isolation test fails the workflow.
**AC-5.4:** The existing matrix legs (format-check/lint/typecheck/test) are unchanged and remain DB-free.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (the integration tests + an assertion that `make test` collects 0 `neo4j` tests).
- [ ] `make check` green locally (DB-free) **and** the new `integration` job green in CI against the service.
- [ ] Targeted review: confirm AC-3.3 genuinely **fails** if `owner_scope`/`assert_scoped_write` is bypassed (the guardrail is real, not a tautology).
- [ ] Committed atomically: marker+make · fixture · read-isolation tests · write-isolation tests · `ci.yml` job — each its own commit.
- [ ] Pushed; status → DONE ✅; `docs/epics/README.md` row updated.
