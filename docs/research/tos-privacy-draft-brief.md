# ToS & Privacy Policy Draft Brief — from the §49 positions

> **How to run this:** open this repo in Antigravity and tell the agent:
> *"Read and execute the brief in `docs/research/tos-privacy-draft-brief.md`. Draft the policy documents as a PR — plain-language, grounded in this project's decided positions. No code."*
> This file is the instruction set. Everything below is addressed to the executing agent.

---

You are a privacy-minded product-counsel writer drafting the **first Terms of Service and Privacy Policy** for a private, single-user (pre-multiplayer) hiking trip planner. This is a *drafting* task grounded entirely in already-decided positions — not a legal-strategy exploration and not code. The output is human-readable policy text plus a short mapping of each promise to the mechanism that keeps it honest, shipped as a PR. **You are not a lawyer and must say so; this is a review-ready draft for the owner to take to counsel, not legal advice.**

## The decided positions you are drafting from (do not re-open these)

Read `docs/decision-log.md` **§49** (data-rights & policy positions) as the source of truth, plus §47 (Supabase auth adopted) and Epic 010 (the commons consent substrate). The settled positions:

- **Deletion:** immediate hard delete of the personal overlay + episodes on request; commons contributions revoked via writer-hash; backups age out within 30 days.
- **Biometrics:** v1 stores **no heart-rate/biometric streams** — pace, GPS, and duration only.
- **Sign-ups:** closed — owner + household invites only (a "private beta" posture); account holders 18+.
- **Commons:** contribution of de-identified observations is **opt-in, default OFF**; contributions are born-severed (no identity edge) and revocable by writer-hash.
- **No analytics/tracking** beyond scrubbed operational logs; **no ads; data is never sold.**
- **Subprocessors:** Vercel (frontend hosting), Render (API), Neo4j Aura (graph DB), Supabase (auth only), Anthropic (the model that composes answers) — name each with its role.
- **The private overlay never reaches a cloud model** — stated as a promise (it is enforced in code and tested; the C4 egress guard).
- **Verdicts are advisory** — the app informs; hiking decisions and their risk are the user's.
- **Export:** self-serve, machine-readable (JSON for beliefs/episodes + GPX for tracks).

## Ground yourself in what the app actually does (so promises match reality)

- `docs/vision.md` + `CLAUDE.md` non-negotiables — the source-or-silence / private-by-default / anti-engagement / no-model-training character the policy voice must reflect (Rule #9: **no model training** — the policy must say data is used only to serve the user's own answers, never to train models).
- `docs/research/t6-licensing-consent.md` — the OSM/ODbL obligations for any commons data (attribution + share-alike posture); the privacy policy's commons section must be consistent with it.
- `docs/research/auth-provider-decision-brief.md` — what Supabase does (identity only; no RLS; the DB is unused for app data) so the subprocessor description is accurate, not boilerplate.
- Epic 010 (`docs/epics/epic-010-commons-fork-write.md`) — how a commons observation is de-identified (endpoint-trimmed, writer-hash, capability-banded) so the "what we share and how it's severed" description is true to the mechanism.

## Voice

Plain language, calm, honest — the same character as the product (a trusted expert friend who only tells the truth). Short sentences. No dark patterns, no scare tactics, no manufactured reassurance. Where a right has a limit, state the limit plainly. Never claim a protection the code doesn't provide — if you're unsure whether a promise is backed, mark it **[VERIFY]** rather than assert it.

## Deliverable — one PR adding two documents

Add `docs/legal/terms-of-service-draft.md` and `docs/legal/privacy-policy-draft.md` (create `docs/legal/`), plus a one-line pointer in `docs/README.md`'s doc map if appropriate. Keep `make docs-lint` green.

**Privacy Policy** — cover, each in plain language: what data is collected (and explicitly what is **not** — no biometrics, no tracking/analytics, no ad identifiers); why each item is collected; where it lives (the named subprocessors + their roles); the "private overlay never reaches a cloud model" promise; the commons opt-in (default OFF, de-identified, revocable) and its ODbL posture; the data-rights section (access, export in JSON+GPX, immediate hard delete + 30-day backup aging, commons revocation by writer-hash); no-model-training; retention; how to exercise each right; who to contact; how changes are communicated.

**Terms of Service** — cover: the private-beta / invite-only + 18+ eligibility; acceptable use; the **advisory-only safety disclaimer** (verdicts and conditions are informational; the user owns their hiking decisions and assumes the risk; the app is not a substitute for judgment, official sources, or emergency services) written prominently but calmly; data ownership (the user owns their data; the app claims no license to it beyond serving them and, only on opt-in, the severed commons contribution); the OSM/ODbL attribution the corpus carries; disclaimers/limitation-of-liability appropriate to a free personal-use beta; termination + what deletion does; governing-law **[VERIFY — owner to set jurisdiction]**.

**Promise-to-mechanism map** (a short appendix in each doc, or a third small file `docs/legal/promise-mechanism-map.md`): a table binding each material promise to the code/mechanism that keeps it honest (e.g. "overlay never reaches cloud model → C4 egress guard, `tests/test_overlay_egress.py`"; "immediate hard delete → [VERIFY: the delete endpoint is being built in the ToS/export-deletion scaffold, not yet shipped"; "commons revocation → writer-hash, Epic 010"). Mark every promise whose mechanism is **not yet built** with **[VERIFY]** so the owner and the scaffold-builder know exactly which promises the code must catch up to before launch.

Mark the PR **"FOR OWNER REVIEW — policy draft, take to counsel; not legal advice."** Follow `AGENTS.md` PR hygiene; `make docs-lint` green.

Bar: the owner can read these in ten minutes, see exactly which promises are already true vs. which the scaffold build must make true, and hand a coherent draft to a lawyer without starting from a blank page.
