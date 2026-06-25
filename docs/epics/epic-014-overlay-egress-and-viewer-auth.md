# Epic 014 — Private-overlay egress + viewer-auth hardening

**Status:** DEFINED
**Phase:** 1 (Personal Intelligence) — **urgent** (remediates gap-audit C3 + C4)
**Spec refs:** decision-log §13 (auth boundary = shared/private boundary, `docs/decision-log.md:131`) · `docs/research/decision-log-additions-proposed.md` §28 (access invariant / ScopedSession, line 240) · §29 (engine / provider / cost / sensitivity routing) · §40 (C3, C4) · `docs/research/architecture-gap-audit-2026-06.md` · Rule #4 · Rule #5

---

## Capability statement

The one pipeline that today carries private-overlay data — the personalized taste-ranking call wired by Epic 003 (shipped) — is made **structurally** unable to leak. Personal context (beliefs, capability profile, prior visits) can never reach a cloud provider regardless of config, and `viewer_id` can never be honored unless it arrived from an authenticated caller — so the access seam (Rule #4) is backed by a real identity (Rule #5) rather than a client-supplied string.

## Architectural context

**Builds on:** the working privacy seam in `orchestration/providers/registry.py` (`resolve(role, settings, *, touches_private_overlay=False)` — additions §37, which forces the local provider whenever the flag is set and returns a `Resolution` with `forced_local=True`); Epic 003 `orchestration/context_assembly.py` (assembles the private-context block via `assemble_context(...)`) and `engine.plan()` / `engine.build_runtime()` (the call site that injects it as `profile=`); the `api/` layer (`PlanRequest.viewer_id` default `"anonymous"` in `api/schemas.py`, `app.plan` in `api/app.py`).

**Enables:** safe operation of `ADVENTURE_PROVIDER_JUDGMENT=anthropic` (the documented "yardstick" mode, §29) without overlay egress; Stage 7 memory-on/memory-off evals under cloud judges; the eventual full auth/identity system (Stage 8) by pinning `build_runtime`'s authentication contract now.

**Does NOT include:** a full auth/identity system — sessions, tokens, login, the grant system (Stage 8). This epic delivers **only** the fail-closed guard, the explicit `build_runtime` contract, and the structural privacy routing of the one overlay-bearing call. *Why:* C3/C4 are LIVE exposures the instant Epic 003 shipped; they must be remediated independently of the much larger identity build, and a fail-closed guard is cheap to add and cheap to remove when real auth lands.

---

## Stories

### S1 — Personalized ranking never egresses overlay to a cloud provider

**Given** a `plan()` call where the assembled `personal_context` is non-empty
**When** the engine resolves the judgment-tier provider for the taste-ranking (`rank_plan` → `rank_ids`) call
**Then** that provider is resolved with `touches_private_overlay=True`, forcing the local provider even when `ADVENTURE_PROVIDER_JUDGMENT=anthropic`

*Why:* Rule #5 requires overlay routing to be structural, not contingent on config being set safely. Today `engine.build_runtime` calls `resolve("extract", settings)` / `resolve("curate", settings)` with **no flag** (both default `False`), and Epic 003 feeds `combined_profile` — which carries the assembled private-context block — into that exact `curate`/judge call via `rank_plan(..., profile=combined_profile) → rank_ids(..., profile=...)`. Under the local-first default the overlay stays on-device, but the moment the judgment tier is set to `anthropic` it egresses to Anthropic with no error and no test failure. The trigger is the **overlay** component (`personal_context`), not `intent.profile` (see AC-1.4).

**AC-1.1:** When `personal_context` is non-empty, the judgment-tier provider used for taste-ranking is resolved with `touches_private_overlay=True` — assert via the resolution's `forced_local` being `True`, or via the provider instance being `LocalOpenAIProvider`.
**AC-1.2:** With the judgment tier configured `provider="anthropic"` (`ADVENTURE_PROVIDER_JUDGMENT=anthropic`) **and** a non-anonymous viewer whose `personal_context` is non-empty, the provider that `rank_ids` actually receives is `LocalOpenAIProvider`, never `AnthropicProvider`. *(This is the test that FAILS today.)*
**AC-1.3:** A regression guard asserts that the taste-ranking (`curate`) resolution carries `touches_private_overlay=True` (equivalently `forced_local=True`) whenever `personal_context` is non-empty, and **FAILS** if a future change drops the flag at this call site. *Why:* the enforceable, deterministic form of "overlay never reaches the cloud judge" is a check on the resolution at the call site, not an unbounded runtime property — matching the concrete-assertion style of epic-001's ACs.
**AC-1.4:** When `personal_context` is empty (anonymous / no-data path), behavior is unchanged: the judgment tier resolves per config (cloud allowed), since no overlay is present to protect. Note that `combined_profile = intent.profile or (personal_context or None)`, so an `intent.profile`-only request still reaches `rank_ids` — that path is user free-text, **not** overlay substrate, and is correctly not local-forced (consistent with AC-2.3). *Why:* Rule #2 / §29 — the anonymous world + live-conditions product is real and must keep working against the cloud yardstick.

### S2 — `build_runtime` knows whether context is private and threads that decision to the resolve call site

**Given** `engine.build_runtime` (or `plan`) must decide the privacy of the judgment-tier resolution
**When** it resolves the taste-ranking provider
**Then** the privacy decision is passed explicitly to `resolve(...)` — never left at the implicit `touches_private_overlay=False` default

*Why:* C4's root cause is that the privacy guarantee is requested by no one at the only call site that needs it. Because `build_runtime` wires the judge provider but `plan()` is where `personal_context` is assembled, the privacy decision must either **(a)** defer judge resolution until context is known, or **(b)** resolve a local-forced personalized judge up front. A third shape — splitting an anonymous-cloud judge from an always-local personalized judge, the engine selecting the latter whenever overlay context is present — is also acceptable. Whichever shape, the flag must be a deliberate argument, not a default, and the same AC-1.2 / AC-1.3 guarantees must hold.

**AC-2.1:** `resolve(...)` for the taste-ranking (`curate`) role is invoked with an explicit `touches_private_overlay=` argument at every call path that can carry overlay data — verified by test, not by reading the default.
**AC-2.2:** If the personalized judge is resolved inside `plan()` (option a), `build_runtime` no longer silently resolves a cloud `curate` provider that later receives overlay; if resolved in `build_runtime` (option b), it is resolved local-forced and documented as the overlay-carrying judge; if split (option c), the personalized judge is always local and selected whenever overlay context is present.
**AC-2.3:** The fix is scoped to the **overlay-carrying `curate` call only.** The `judge` role (truthfulness eval) shares the `judgment` tier (`ROLE_TIER`: both `curate` and `judge` → `judgment`) but carries no overlay and is left unchanged; the mechanical-tier `extract` (intent parse) is likewise left unchanged — intent free-text is not private-overlay substrate. *Why:* over-forcing local on the `judge`/eval call or the mechanical tier would needlessly degrade the documented cloud yardstick for non-private work. The relevant distinction is overlay-bearing vs. not, **not** mechanical-vs-judgment (the egress risk is precisely that `ADVENTURE_PROVIDER_JUDGMENT=anthropic` flips both judgment-tier roles at once, and only `curate` carries overlay).
**AC-2.4:** A docstring/contract note on the taste-ranking resolution states that this provider may receive assembled personal-overlay context and is therefore privacy-routed.

### S3 — `viewer_id` is honored only from an authenticated caller; fail closed until auth exists

**Given** a `/plan` (or `/episode/{id}/outcome`) request with a `viewer_id` other than `"anonymous"`
**When** no authentication system exists yet (Phase 1, pre-Stage-8)
**Then** the request hard-fails (HTTP 401/403) unless it presents the shared dev secret, and `build_runtime`'s contract documents that `viewer_id` is **already authenticated** by the time it is called

*Why:* Rule #5 + decision-log §13 (`docs/decision-log.md:131`) make the auth boundary == the shared/private boundary. Today `PlanRequest.viewer_id` (default `"anonymous"`, in `api/schemas.py`) flows straight into `build_runtime → scoped_session` with zero authentication (`api/app.py`), so any caller can POST `{"viewer_id":"mem:josh"}` and be scoped to Josh's overlay — now live-relevant because Epic 003 wires Josh's beliefs/episodes over this same endpoint. The `ScopedSession` (the read seam named `scopedQuery(viewer)` in §28/line 240) protects against a forgotten `WHERE` clause, **not** a forged identity; that gap must be closed at the edge.

**AC-3.1:** A `/plan` request with `viewer_id != "anonymous"` and no valid dev secret returns 401 or 403 (not 200, not a scoped feed). *(Test FAILS today — currently returns 200 scoped to the forged id.)*
**AC-3.2:** A `/plan` request with `viewer_id == "anonymous"` succeeds unauthenticated (the anonymous world / live-conditions product stays open).
**AC-3.3:** When the shared dev secret is configured and presented (header, e.g. `X-Dev-Viewer-Secret`), a non-anonymous `viewer_id` is accepted; when the secret is absent from config, non-anonymous requests fail closed regardless of any header. *Why:* fail-closed default — a misconfigured deploy must not silently accept forged identities.
**AC-3.4:** The same guard covers `/episode/{id}/outcome`, whose `viewer_id` is likewise an unauthenticated query param today (`viewer_id: str = "anonymous"` in `api/app.py`).
**AC-3.5:** The dev secret is read via `Settings.from_env()` (e.g. `ADVENTURE_DEV_VIEWER_SECRET`), never hardcoded (Rule #10 / code standards), and is absent by default so the open anonymous path is the only thing that works out-of-the-box.
**AC-3.6:** `build_runtime`'s docstring states its precondition: **"`viewer_id` is already authenticated by the caller; this function does not verify identity."** *Why:* pins the contract so Stage 8 auth slots in at the edge without re-auditing the engine, and so no future caller assumes `build_runtime` authenticates.

---

## Definition of Done

- [ ] All ACs covered by at least one passing test (named per process doc)
- [ ] AC-1.2, AC-1.3, AC-3.1 each demonstrably FAILED before the fix and PASS after (the regression guards)
- [ ] `make check` green (ruff + mypy + pytest) before commit
- [ ] Overlay-carrying taste-ranking (`curate`) resolution passes `touches_private_overlay=True` at every path; the `judge`/eval call (same `judgment` tier, no overlay) and the mechanical/intent resolution are left unchanged
- [ ] `build_runtime` docstring documents the "`viewer_id` is already authenticated" contract
- [ ] Edge guard fails closed: non-anonymous `viewer_id` rejected without the configured dev secret, on both `/plan` and `/episode/{id}/outcome`
- [ ] `ADVENTURE_DEV_VIEWER_SECRET` wired through `Settings.from_env()`, absent by default, documented in `.env.example`
- [ ] The gap-audit (`docs/research/architecture-gap-audit-2026-06.md`) and additions-proposed (`docs/research/decision-log-additions-proposed.md`) docs are committed alongside this epic (they are not yet on the build branch), so the §40 citation and the "mark remediated" step below resolve
- [ ] Targeted self-review agent run (narrow file list: `orchestration/engine.py`, `orchestration/providers/registry.py`, `api/app.py`, `api/schemas.py`); every CRITICAL fixed before commit
- [ ] `docs/research/decision-log-additions-proposed.md` §40 C3 + C4 marked remediated, pointing at this epic (treating §40's `engine.py:191-192` line cite as illustrative, since this epic edits that call site); `docs/epics/README.md` row added
- [ ] Atomic commits (privacy-routing fix · edge auth guard · tests · doc updates), each its own commit

---

**Build-order note:** This epic remediates the **only LIVE exposure** among the gap-audit criticals (C1/Epic 010, C2/Epic 011, C5/Epic 012, C6/Epic 013 are latent or unbuilt; C3/C4 are exploitable now because Epic 003 shipped on the build branch). Do it before any further work that widens the `/plan` surface or enables a cloud judgment tier (`ADVENTURE_PROVIDER_JUDGMENT=anthropic`) in a shared deploy.
