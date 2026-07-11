# Runbook (stub) — Backup / DR for the personal overlay

**Owner:** infra · **Status:** STUB (Phase B) — full version lands in Phase G

The personal overlay (Episodes, Outcomes, Beliefs, PhysicalProfiles — everything
owner-scoped) is the one **irreplaceable** data class in the system: the world
corpus can be re-ingested from OSM/USGS/USFS/NPS and live conditions are never
persisted (rule #3), but a member's logged history cannot be re-derived from
anywhere. Phase B requires this stub to exist **before real overlay data
accrues**; today the overlay holds only mock/seed data for one seeded user, so
the recovery bar is deliberately low — but the moment Phase C's intake opens
(real auth + episode creation + history import), it becomes a hard gate.

## What must be recoverable

| Data class | Recoverable from | Backup priority |
|---|---|---|
| Personal overlay (owner-scoped nodes + edges) | **nothing** — this runbook | critical |
| Commons fork (`:CommonsObservation`, born-severed) | nothing (accretes) | high |
| World corpus (trails, trailheads, SourceRecords) | re-run `make ingest` per region | low |
| Schema / Meta | `graph/schema.cypher` (committed) | none |

## Current posture (verify, don't trust)

- Production graph is Neo4j **Aura** (managed). Aura's own snapshot cadence,
  retention, and export/download options are **tier-dependent and unverified
  from this repo** — confirm them in the Aura console and record the answer
  here before relying on them. *Do not assume the free tier keeps restorable
  snapshots.*
- There is **no application-level export** of the personal overlay yet. The
  Phase B→C data-rights work (GDPR/CCPA export) will create one; that export
  path and this backup path should be the same code, so backup = "run the
  export for every member" and never a second diverging implementation.

## Minimum viable procedure (to flesh out before Phase C exit)

1. **Backup:** a scheduled job exports all owner-scoped nodes/edges per member
   (scoped through `ScopedSession`, rule #4 — never a raw `MATCH (n)` dump) to
   a versioned, encrypted object store. Cadence: daily while volume is small.
2. **Restore drill:** documented steps to replay an export into a fresh graph
   (schema first via `make schema-aura`, then the overlay import, then re-run
   `make ingest` for the world), plus a checklist item proving one member's
   episodes/beliefs round-trip intact.
3. **DR decision record:** RPO/RTO targets (proposal: RPO ≤ 24h, RTO ≤ 1 day —
   a personal utility, not a pager product), where the encrypted exports live,
   and who holds the keys (secrets store, rule #10 — never this repo).

## Out of scope for the stub

Cross-region replication, point-in-time recovery, commons re-aggregation
mechanics, and automated restore testing — all Phase G (`path-to-complete.md`
§Phase G names the full runbook).
