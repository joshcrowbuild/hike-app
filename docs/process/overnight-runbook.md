# Overnight Build Runbook

*A self-contained brief for an unattended Claude Code session. Authored by the PM lane (2026-06-26) from an AC-level readiness audit. Every item below is verified buildable from trunk **without product decisions** — if you hit one anyway, STOP that item and leave a note (see Guardrails).*

**Trunk:** `claude/vigilant-bohr-yzdcyh`. **Open PRs into:** `claude/vigilant-bohr-yzdcyh`.
**Read first:** `CLAUDE.md` (rules + standards), `AGENTS.md` (repo/Git hygiene), `docs/process/development-process.md` (epic→story→AC→test→review).

---

## Guardrails (non-negotiable)

1. **Stay in scope.** Build only the four items below. Do **not** start anything in "Out of scope" — those need human design.
2. **No product decisions.** If an item turns out to need a choice not written in its epic/spec (a threshold, a vocabulary, a UX behavior), STOP that item, commit what's safely done, and write a one-paragraph `BLOCKED:` note in the PR describing the missing decision. Move to the next item.
3. **TDD + atomic commits.** One AC → at least one test, written first. One logical change → one commit (see CLAUDE.md "atomic commits"). Co-author trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
4. **`make check` green before every commit** (`ruff format --check` + ruff + mypy + pytest). No exceptions.
5. **One branch + one PR per work item**, into `claude/vigilant-bohr-yzdcyh`. After coding an epic, run a **targeted self-review agent** (narrow file list + the specific rules to check) and fix CRITICALs before the PR — do NOT run `/code-review ultra` for these routine epics (CLAUDE.md).
6. **Lane boundaries.** Touch only the dirs each item names. Do not touch `frontend/`. Do not edit another epic's spec.
7. **Pull before push.** Other lanes may merge while you work; rebase (don't merge) onto trunk if you fall behind.

---

## The batch (do in this order)

Each item is independently completable; the order is chosen so shared scaffolding (the live-Neo4j fixture from item 2) is available to item 3's end-to-end DoD.

### 1 · Close Epic 002 — Outcome card endpoint  ·  size S  ·  `tests/` `docs/epics/`
Feature is built and live on trunk (PR #9 fixed the write-seam CRITICAL); it just isn't legitimately DONE. Per the audit:
- Add the missing per-AC tests in `tests/test_outcome.py`: **AC-1.1** (Outcome MERGE `eid` == path `episode_id`), **AC-2.2** (`(e)-[:HAS_OUTCOME]->(o)` direction), **AC-2.3** (explicit single-transaction/atomicity assertion), **AC-5.2** (belief `key=='stated_preference'` and `value==` raw `delta_answer`); extend `test_s5_ac1` to assert `confirmed_by_user==true`.
- Add an endpoint test (TestClient, like `tests/test_viewer_auth.py`) for **AC-4.3**: the belief-queue drain runs as a `BackgroundTask` *after* the response, not synchronously.
- Verify `orchestration.belief_update` drain no-ops safely on the all-None preference-marker `UpdateTask` (`outcome.py:131-139`); add a regression test if not already safe.
- Reconcile **AC-4.1** wording to the implemented/tested behavior (enqueue only for `overall>=2`) — a one-line doc tweak, not a behavior change.
- Tick every DoD box; flip status IN_PROGRESS→DONE in `epic-002-outcome-card-endpoint.md` **and** the `README.md` row.
**DoD:** all 002 ACs have a test; `make check` green; status DONE in both docs.

### 2 · Epic 015 — CI Neo4j integration  ·  size M  ·  `tests/` `pyproject.toml` `.github/workflows/ci.yml` `Makefile`
Build exactly to `docs/epics/epic-015-ci-neo4j-integration.md` (decisions already ratified there: **separate required `integration` job**, read+write isolation + a falsifiability check, `@pytest.mark.neo4j` marker, schema applied via the bolt driver, `neo4j:5-community` service with `NEO4J_AUTH=neo4j/testpassword`).
- Register the `neo4j` marker; make `make test` run `-m "not neo4j"` so the 4 fast legs stay DB-free.
- Build the live fixture (driver-applied `graph/schema.cypher`; `DETACH DELETE` between tests).
- Read-isolation (S3) incl. the **AC-3.3 falsifiability** test; write-isolation (S4) via `assert_scoped_write`.
- Add the required `integration` job to `ci.yml` installing `.[dev,graph]` and running `pytest -m neo4j`.
**DoD:** epic-015 DoD; the new job green in CI; targeted review confirms AC-3.3 fails if the scope guard is bypassed.

### 3 · Close Epic 003 — Context assembly + the `Episode.date` fix (R6/M1)  ·  size S–M  ·  `graph/` `ingestion/` `tests/` `docs/epics/`
`orchestration/context_assembly.py` is on trunk; the load-bearing gap is **AC-3.2** (`e.date > date()-duration('P18M')`) returning nothing because `Episode.date` is never written.
- Thread the already-parsed `FITSummary.start_time` into the Episode write: add `e.date = date($start_date)` to `graph/queries.py` `upsert_episode` and pass it from `ingestion/ingest_episode.py`; set `PhysicalProfile.last_episode_at`.
- Add a test that a date-filtered retrieval returns the just-ingested episode (mark it `neo4j` and reuse item 2's fixture for the E2E DoD; cover the other ACs DB-free with the fake-session pattern already used in `tests/test_context_assembly.py`).
- Confirm the ~26 ACs each have a test; tick DoD; flip status IN_PROGRESS→DONE in both docs.
**DoD:** epic-003 DoD incl. the seeded-Josh E2E (`plan()` produces a context-enriched Curator call); `make check` green.

### 4 · Reconcile design-branch docs → trunk (R4)  ·  size S  ·  `docs/` only
Bring the 13 net-new docs from `origin/claude/web-design-parallel` onto trunk by **selective path checkout — NOT a branch merge** (trunk is ahead; a merge would regress DONE epics to DEFINED).
- `git checkout origin/claude/web-design-parallel -- <the 13 paths>` (epics 006 & 009; `parallel-integration-runbook`, `design-system-v0.1`, `home-curation-prototype-spec-v0.2/v0.3`, `integrated-remediation-review-2026-06`, `novelty-filter-spec`, `outcome-card-ux`, `stage-7-eval-methodology`, `stage-8-multiplayer-privacy`, `t6-licensing-consent`, `ui-brief-v0.2`). **Exclude** `frontend/**` and any incidental code edits on that branch.
- README **union** rule: keep trunk's DONE/IN_PROGRESS statuses; ADD design's epic-006 and epic-009 rows with links; point row 004 at `epic-004-device-integration-seam.md`; mark row 005 SUPERSEDED (folded into 013).
- `decision-log.md`: add design's §20 design-system ratification WITHOUT clobbering trunk's §30/§31 commons demotion (different regions, 3-way mergeable).
**DoD:** all 13 paths on trunk; README internal links resolve; no `✅` regressions on the commons-fork lines (the Epic-010 S1 doc-lint guard stays green).

---

## Out of scope — do NOT attempt (these need human design first)

- **Epic 006 (novelty filter)** — blocked: the `been_on` belief **producer doesn't exist** (no code, no epic) and several semantics are undecided. Reconciling its spec (item 4) is fine; **building it is not**.
- **Epic 007 (readiness filter)** — no epic exists; the readiness→difficulty mapping is **safety-adjacent** and undecided. Do not invent it.
- **Epic 008 (API tests)** — ready to build, but its epic-with-ACs hasn't been written/ratified yet. Skip until it's DEFINED.
- **Garmin always-on poller** — the in-process poller is already DONE (Epic 004); the always-on deployment is gated on the host decision (R7) + live secrets.
- **Anything touching `frontend/`** — UI lane.

---

## When done
Open one PR per item into `claude/vigilant-bohr-yzdcyh` with a short body (what/why/DoD-state). Leave any `BLOCKED:` notes prominent. The PM lane will reconcile `docs/process/roadmap.md` against what landed.
