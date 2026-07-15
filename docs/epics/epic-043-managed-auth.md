# Epic 043 — Managed auth: Supabase sign-in replaces the shared dev-secret

**Status:** DEFINED
**Phase:** C (Real Intake)
**Spec refs:** [`../research/auth-provider-decision-brief.md`](../research/auth-provider-decision-brief.md) (signed off — decision-log §47) · [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md) Phase C · roadmap R3

---

## Capability statement

A real person signs in with their own account and every request carries a verified per-user identity — replacing the single shared `X-Dev-Viewer-Secret` — while anonymous browsing of the world + live conditions stays a first-class, un-gated product.

## Architectural context

**Builds on:** Epic 014 (`_authorize_viewer` edge guard) · Epic 011 (`ScopedSession` grant layer)
**Enables:** Epic 042 (manual trip log over HTTP) · Epic 044 (history import) · Phase-C onboarding/settings · retiring H1's residual operator steps
**Does NOT include:** household grants / multiplayer (Phase F) · Supabase RLS (authorization stays entirely in `ScopedSession` — the brief's explicit non-goal) · production ESP wiring (a Phase-B line item; see S4 note) · the CDP-12 Zanzibar grant shape (grant-layer work, later)

---

## Stories

### S1 — Verify a per-user token at the edge

**Given** a request with `Authorization: Bearer <Supabase JWT>`
**When** it reaches `_authorize_viewer`
**Then** the token is verified against the project's public JWKS (PyJWT, asymmetric keys, cached) and the stable UUID `sub` becomes `viewer_id`, handed to `scoped_session()` exactly as today

**AC-1.1:** valid token → viewer-scoped request proceeds; `sub` is the only claim trusted for identity
**AC-1.2:** missing/expired/garbage token on a non-anonymous path → 403, fail-closed
**AC-1.3:** JWKS is cached (no per-request fetch); an unknown `kid` triggers exactly one refetch (key rotation) then fails closed
**AC-1.4:** `ScopedSession`, `owner_scope`, and revoke-on-next-view are untouched — the diff lives at the edge only

### S2 — Anonymous browsing preserved by construction

**Given** no credentials at all
**When** anonymous `/plan`, `/search`, or `/trail/*` is called
**Then** it serves exactly as today

**AC-2.1:** regression test asserts anonymous `/plan` returns 200 with zero credentials (the DoD requirement path-to-complete names explicitly)
**AC-2.2:** no global auth-wall — auth is asserted per-route, only where the private overlay is touched

### S3 — Retire the shared dev-secret

**AC-3.1:** the `X-Dev-Viewer-Secret` path is removed (or hard-gated out of production builds); production accepts only anonymous or a verified JWT
**AC-3.2:** frontend `httpPlanner` stops injecting the secret and sends the Supabase session token instead
**AC-3.3:** operator steps listed in the PR body: unset `VITE_DEV_VIEWER_SECRET` on Vercel + retire the Render secret (closes the H1 tail)

### S4 — Sign-in surface (calm)

**AC-4.1:** sign-in/sign-out via `supabase-js`; session persists across reloads
**AC-4.2:** the UI never nags — sign-in is offered where a private action needs it (save / log a trip), never as a gate on browsing
**AC-4.3:** v1 email posture documented: Supabase's built-in email is dev-tier (team recipients only) — acceptable for the single-user phase because the owner *is* the team; the external ESP stays the Phase-B line item

### S5 — First authenticated write: episode creation over HTTP

**Given** a signed-in user
**When** they submit a planned/completed trip
**Then** an authed `POST /episode` wires `queries.upsert_episode` (today batch-only) behind the verified identity, creating a real Episode owned by that viewer

**AC-5.1:** the Episode lands via the scoped-write seam (Epic 011) — no new write path
**AC-5.2:** anonymous or forged/expired-token requests → 403
**AC-5.3:** this endpoint is the write path Epic 042's manual log rides on

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (incl. the anonymous-`/plan` regression)
- [ ] `make check` green
- [ ] Live verification: sign in on the hosted app; an authed write lands in Aura under the verified `sub`; anonymous browsing still serves
- [ ] Targeted review agent run; CRITICALs fixed
