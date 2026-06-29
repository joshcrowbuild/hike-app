# Managed Auth Provider — Decision Brief

*The next gating decision after CDP-01. Resolves [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md) Open Decision #4; unblocks all of Phase C (auth + episodes + history import).*

**Last verified:** 2026-06-29 · **Owner:** vision-PM · **Status:** `ACTIVE` — recommendation for PO sign-off

> One-line recommendation: **adopt Supabase Auth.** It satisfies all four hard requirements, is the only managed option whose self-host + own-your-data posture matches the app's local-first / private-by-default ethos, and its single weakness (dev-only built-in email) is *already neutralized* because Phase B commits to an external transactional-email substrate regardless of auth choice.

---

## The decision & what it unblocks

Today every non-anonymous request trusts a free-text `viewer_id` gated by **one shared static dev-secret** (`api/app.py:96` `_authorize_viewer`; `viewer_id == "anonymous"` short-circuits to the open world, else the request must present `X-Dev-Viewer-Secret`). That `viewer_id` then flows verbatim into `ScopedSession` (`graph/client.py:49`), which injects `$viewer_id`/`$granted_ids` into every Cypher read/write. The provider's job is to replace the shared secret with a **verified per-user identity** — nothing more. This is the pivot the whole personal-intelligence machinery waits on (Phase C / Milestone 1 "the loop is real").

## Hard requirements (grade strictly against these)

1. **Replace the shared dev-secret** — issue a verifiable per-user token a FastAPI backend can verify on each request (JWKS → stable subject claim → `viewer_id`), with no per-request round-trip.
2. **Preserve anonymous browsing as a first-class product** — auth gates *only* the private overlay; the open world + live conditions stays un-gated. The provider must not impose a global auth-wall; the backend keeps per-route control.
3. **Non-deferrable transactional email** — password-reset/recovery **and** the data-rights export both physically need it. The question is whether the provider *sends production email itself* or forces a bring-your-own ESP.
4. **Integrate cleanly with the existing grant layer** — supply only the verified `viewer_id`; the household grant model already lives in `ScopedSession`/`owner_scope`. Minimal coupling; no pressure to move authorization into the IdP.

> **Explicit non-criterion — do not grade IdPs on this.** *Revoke-on-next-view* is a property of the grant layer we **already built** (`ScopedSession` re-reads `granted_ids` per request), **not** an IdP feature. Likewise org/RBAC/fine-grained-authorization are out of scope and already owned. Grading any provider up or down for these would be a category error.

## Comparison (adversarially verified, 2026-06)

| Axis | **Supabase Auth** | **Clerk** | **Auth0** | **Roll-your-own** |
|---|---|---|---|---|
| **1. Verify token → `viewer_id`** | ✅ Asymmetric JWT (default on new projects since 2025-10) + public JWKS + stable UUID `sub`; pure-PyJWT, no SDK needed | ✅ RS256 + JWKS + first-party Python SDK; stable `sub` (`user_…`) | ✅ RS256 + per-tenant JWKS + official `auth0-api-python`; stable `sub` | ✅ Your own HS256 + PyJWT (now FastAPI's recommended lib; `python-jose` abandoned); `sub` = your PK |
| **2. Anonymous browsing** | ✅ Token API, per-route; never an auth-wall | ✅ Opt-in per route | ✅ Redirect fires only when you call it | ✅ First-class by construction (no IdP to fight) |
| **3. Transactional email** | ⚠️ Built-in is **dev-only** (2/hr, refuses non-team recipients, "not for production") → **must wire external ESP** | ✅ **Sends prod email itself** from your domain over dedicated IPs — no ESP needed | ⚠️ Built-in is **dev-only** (fixed `no-reply@auth0user.net`, 10/min, throttle-on-bounce) → **must wire external SMTP** | ❌ **None at all** — you own the entire ESP + deliverability surface |
| **4. Grant-layer coupling** | ✅ Take `sub` only; ignore RLS — authz stays in your layer | ✅ Take `sub` only; ignore Orgs/RBAC/FGA | ✅ Take `sub` only; ignore RBAC/Orgs/FGA | ✅ Single verified-id handoff; zero pressure |
| **Self-host / residency / ethos** | ✅ **Apache-2.0, self-hostable (GoTrue)**; EU region + DPA; you own the Postgres | ❌ Closed SaaS, **no self-host**; identity PII + email leave your infra | ❌ Closed US SaaS, no self-host; residency only at enterprise tier | ✅ **Strongest** — everything on your infra; only egress is the recipient address to the ESP |
| **Exit / lock-in** | ✅ Lowest among managed — export bcrypt hashes yourself via SQL | 🔶 Moderate — CSV export incl. hashes, but frontend coupling | 🔶 Moderate — hash export needs a **support ticket** | ✅ Zero — you never handed the data out |
| **Cost ≤1k MAU** | $0 (50k MAU free; free projects pause after ~1wk idle — $25/mo Pro removes it) | $0 (50k MRU free; $25/mo Pro removes branding) | $0 (25k MAU free; first paid step $35/mo, steep per-MAU growth) | $0 licensing + ESP (Resend free 3k/mo) + **your time forever** |

## The reasoning

- **The email axis is the only real separator among the managed options — and it's neutralized here.** Clerk's one decisive advantage is that it sends production email itself; Supabase and Auth0 both force an external ESP. But the path-to-complete **already commits to a transactional-email substrate in Phase B** (auth recovery *and* the data-rights export depend on it independently of any auth choice — it's a `B→C` blocker in the table-stakes matrix). So "wire Resend/SES" is a line item we are building anyway. Clerk's email edge therefore buys nothing it doesn't also cost on the ethos axis.
- **The ethos axis is where this app is unusual.** A private-by-default, local-first, source-or-silence utility putting its *identity substrate* in a closed US SaaS (Clerk/Auth0) is a genuine philosophical tension — the personal overlay can stay local, but account PII and outbound email would not. Supabase's **Apache-2.0 self-hostable GoTrue** is the only managed option that lets the identity store run on our own infra and gives a real exit (own the Postgres, export the hashes yourself). That matches the project's stated character.
- **Roll-your-own has the best ethos and zero lock-in, but loses on the burden it creates.** Auth is the canonical "don't roll your own" domain, and the 2026 library stack is thinning (`python-jose` abandoned, `passlib` unmaintained/breaks on 3.13, `fastapi-users` in maintenance mode). It converts a tiny vendor relationship into a permanent security commitment (JWT revocation, refresh rotation, account-enumeration safety, breach response) on a one/two-person project that needs to ship. **Self-hosted Supabase captures ~80% of the local-first benefit without owning the auth security surface** — the sweet spot.
- **Auth0 is dominated.** Same dev-only-email trap as Supabase, but worse residency (no self-host, enterprise-gated regions), worse exit (hash export by support ticket), steeper cost growth. Nothing it does, Supabase doesn't do better for this app. **Not recommended.**

## Recommendation

**Adopt Supabase Auth**, created with **asymmetric signing keys**, verified in FastAPI with **PyJWT against the public JWKS** (`/auth/v1/.well-known/jwks.json`), mapping the stable UUID `sub` → `viewer_id`. Deliberately **do not use Supabase RLS** — authorization stays entirely in `ScopedSession`/the grant layer. Treat **external transactional email (Resend or SES)** as a Phase-B prerequisite line item (already committed) that doubles as the data-rights-export sender. Keep the **Apache-2.0 self-host path as a standing residency/exit hedge**.

*If PO weights managed-email convenience above the local-first ethos, Clerk is the fallback; if PO wants maximal control and accepts the maintenance burden, roll-your-own is viable. Auth0 is not recommended.*

## Integration shape (the only coupling)

Replace `_authorize_viewer` (`api/app.py:96`): on a non-anonymous request, verify the Bearer JWT against the cached JWKS, extract `sub` as `viewer_id`, and hand it to `scoped_session(viewer_id)` exactly as today. The `anonymous` short-circuit stays untouched, so anonymous browsing is preserved by construction. The grant layer, `owner_scope`, and revoke-on-next-view are **unchanged** — they were never the IdP's job.

---

*Provenance: an adversarially-verified provider sweep (4 options × the 4 hard requirements + ethos/exit/cost), each load-bearing claim — especially the dev-vs-production email distinction — checked against the providers' current docs. Supersedes the Open-Decision-#4 stub in the path-to-complete once signed off.*
