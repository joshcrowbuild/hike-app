# Promise-to-Mechanism Map — Adventure Planner

**Draft — for owner review. This is not legal advice.**

Every material promise in the [Privacy Policy](privacy-policy-draft.md) and [Terms of Service](terms-of-service-draft.md) is listed below with the code, test, or product mechanism that keeps it honest.

Promises marked **[VERIFY]** are not yet backed by shipped code — the scaffold build must make them true before launch. Promises marked **✅ Built** are enforced today.

---

## Privacy promises

| # | Promise | Mechanism | Status |
|---|---|---|---|
| P1 | Private overlay never reaches a cloud model | C4 egress guard — sensitivity routing forces personal context to local/server-side processing; cloud model receives only corpus + live overlays. Tested in `tests/test_overlay_egress.py`. | ✅ Built & tested |
| P2 | No model training on user data | Architectural: no training pipeline exists; cloud model (Anthropic) receives only un-personalized context. Policy invariant (Rule #9, CLAUDE.md). | ✅ Built (structural) |
| P3 | Data never sold or shared for advertising | Product decision — no ad SDK, no analytics SDK, no data broker integration exists in the codebase. | ✅ Built (structural) |
| P4 | No biometric streams stored | v1 architecture stores pace/GPS/duration only; HR/HRV/SpO2 are read transiently for the capability floor, never persisted. Epic 044 AC-5.3 defers biometric archive with no named consumer. | ✅ Built |
| P5 | No client analytics, tracking, or ad identifiers | No analytics SDK present in the frontend. No fingerprinting code. | ✅ Built (structural) |
| P6 | Immediate hard delete of personal data | Delete endpoint removes all personal-overlay nodes (Beliefs, Context, Persona, UserProfile) and Episode records from Neo4j in one request. | **[VERIFY]** — being built in the ToS/deletion scaffold |
| P7 | Auth record deleted within 30 days of account deletion | Supabase `deleted_at` flag + 30-day retention, then hard-delete per Supabase's lifecycle. | **[VERIFY]** — depends on Supabase deletion API wiring |
| P8 | Backups age out within 30 days | Neo4j Aura daily snapshots have a retention window ≤ 7 days on Free tier; 30-day outer bound documented to accommodate paid tiers. | ✅ Aura-managed |
| P9 | Operational logs contain no PII | Log scrubbing confirmed in security review (2026-07-12): no user IDs, no IPs, no GPS in operational logs. | ✅ Built & reviewed |
| P10 | Operational logs rotated within 90 days | Log rotation policy on Render. | **[VERIFY]** — confirm Render's log retention settings |
| P11 | Commons contribution is opt-in, default OFF | `commons_opt_in` flag on `:Person` node, default `false`. Settings → Privacy toggle. Epic 010. | ✅ Built |
| P12 | Commons observations are de-identified (endpoint-trim) | First/last 250m of GPS track stripped before commons write. Tested: startpoint/endpoint distance > 250m from raw. | ✅ Built & tested |
| P13 | Commons observations are de-identified (capability-band) | Raw `pace_on_grade` replaced with 4 coarse bands (easy / easy-moderate / moderate / strenuous). Raw value never on commons node. | ✅ Built & tested |
| P14 | Commons observations are de-identified (writer-hash) | `HMAC(secret_salt, member_id)` — deterministic, non-reversible. Stored as a property, not a graph edge. No stored mapping from hash to person. | ✅ Built & tested |
| P15 | No graph path from commons observation to person | `:CommonsObservation` has zero relationships to `:Person`, `:Episode`, or `:Outcome`. CI test verifies no path of any length exists. | ✅ Built & tested |
| P16 | Commons revocable (forward) | Toggling off stops future forks; below-k observations removed. | ✅ Built (Epic 010) |
| P17 | Salt destroyed on account deletion | Writer-hash salt stored in private overlay (Neo4j); destroyed on account deletion, severing any theoretical link. | **[VERIFY]** — depends on deletion scaffold |
| P18 | k-anonymity threshold before publication | No statistic published until k contributors have contributed. k value is a Stage-9 design decision. | **[VERIFY]** — designed, k value unset, no read path yet exposes commons |
| P19 | Dependent data excluded from commons | Dependent (e.g., pet) data never enters the commons pipeline. | ✅ Built (T6-8 decision, Epic 010) |
| P20 | Self-serve data export (JSON + GPX) | Export endpoint in Settings → Data → Export. | **[VERIFY]** — being built in the ToS/deletion scaffold |
| P21 | Supabase holds no app data | Supabase stores only auth metadata (email, hashed password, session tokens). All app data is in Neo4j. | ✅ Built (architectural) |
| P22 | Access control enforced at query layer | Every Cypher query carries `owner_scope` / `viewer_id`. Adversarial pentest (31 attacks) confirmed. CI falsifiability tests. | ✅ Built & tested |

---

## Terms of Service promises

| # | Promise | Mechanism | Status |
|---|---|---|---|
| T1 | Verdicts are advisory only | Product invariant (CLAUDE.md Rule #4: "the tool scores, the human decides"). Go/marginal/no-go is a computed advisory, never a guarantee. | ✅ Built (structural) |
| T2 | User owns their data; no license beyond serving them | No data pipeline exports or relicenses user data. Commons contribution is separate, opt-in, de-identified. | ✅ Built (structural) |
| T3 | Account deletion is immediate and permanent | Same as P6 — hard delete of all personal data in one request. | **[VERIFY]** — being built in the ToS/deletion scaffold |
| T4 | Opportunity to export before termination | Export endpoint must exist and be accessible before any forced termination. | **[VERIFY]** — depends on export endpoint |
| T5 | Sources displayed with attribution | OSM: "© OpenStreetMap contributors" + ODbL link on all surfaces showing OSM-derived data. Government sources attributed per their requirements. Attribution is a first-class UI honesty primitive. | ✅ Built |
| T6 | Closed beta / invite-only access | No public sign-up endpoint. Access via owner + household invites only. | **[VERIFY]** — depends on managed auth (Epic 043) |
| T7 | 18+ age requirement | UI states age requirement at sign-up; self-declaration (standard for non-COPPA apps, no children's data collected). | **[VERIFY]** — depends on managed auth (Epic 043) |
| T8 | Every fact carries a source and timestamp | Source-or-silence invariant (CLAUDE.md Rule #1). Verifier enforces: unsourced → flagged, never fabricated. | ✅ Built & tested |

---

## Summary

| Status | Count |
|---|---|
| ✅ Built & enforced | 22 |
| **[VERIFY]** — being built or unset | 8 |

### The eight promises the scaffold build must make true

1. **P6 / T3** — Immediate hard-delete endpoint
2. **P7** — Supabase auth record deletion wiring
3. **P10** — Confirm Render log rotation ≤ 90 days
4. **P17** — Salt destruction on account deletion
5. **P18** — k-anonymity threshold value and enforcement
6. **P20 / T4** — Self-serve export endpoint (JSON + GPX)
7. **T6** — Invite-only sign-up enforcement (managed auth)
8. **T7** — 18+ age gate at sign-up (managed auth)

---

*This document is a draft prepared for owner review. It is not legal advice.*
