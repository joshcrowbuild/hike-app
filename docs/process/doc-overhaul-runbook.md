# Documentation Overhaul Runbook

*A self-contained brief for an unattended ("leave-it-alone-all-day") Claude Code session. Authored by the PM lane (2026-06-26) from a 6-auditor documentation audit. Goal: get the repo's docs to top-tier agentic shape — optimized for **agentic development**, **context freshness** (no "wrong memory"), and **token efficiency**.*

**Repo:** `joshcrowbuild/hike-app` · **Baseline:** `main` @ `725c442` (protected; PRs only, all 6 CI checks required). **Open PRs into:** `main`.
**Read first:** `CLAUDE.md`, `AGENTS.md`, `docs/process/development-process.md`.

---

## Guardrails (non-negotiable)

1. **Docs only.** Touch only `*.md` files + the one new doc-lint script/CI job (Wave 4). Do **not** change `api/`, `graph/`, `orchestration/`, `ingestion/`, `frontend/` source.
2. **PM lane is off-limits.** Do **not** edit `docs/process/roadmap.md` or `docs/workplan.md` — the PM owns those. Treat `roadmap.md` as the live-status **single source of truth (SSOT)** to *link to*, never to copy or restate.
3. **No content loss on archive/dedupe.** "Archive" = `git mv` into `docs/research/archive/` (history preserved, off the live surface), never delete. When de-duplicating a fact, the losing copy becomes a one-line pointer to the SSOT — never a silent deletion of information. If folding decisions (e.g. `decision-log-additions-proposed.md` §32–40 into `decision-log.md`), **preserve every decision**; if unsure whether a section is still live, keep it and flag.
4. **No product/architecture decisions.** This is a docs refactor, not a redesign. If a fact is genuinely ambiguous or two docs *substantively* disagree (not just stale-vs-fresh), STOP that item, leave a `NEEDS-PM:` note in the PR, move on.
5. **One wave = one PR** into `main` (4 PRs total). Atomic commits within. After each, **self-merge once CI is green** (docs are low-risk + reversible; the Wave-4 link-check + doc-lint guard structural breakage). Co-author trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
6. **Order matters — Wave 4 (the lint) goes LAST.** The doc-lint asserts freshness; it can only pass after Waves 1–3 have removed the stale content. Running it earlier reds the build.
7. **Ground truth for freshness:** Phase-1 build is COMPLETE — epics 001–005 and 010–015 are DONE, the personal-intelligence UX shipped, gap-audit C1–C6 + remediation 1C/4M are CLOSED, baseline `main == 725c442`. Anything describing these as pending/unbuilt/"next" is wrong memory — fix it.

---

## Wave 1 — Freshness (stop the wrong-memory bleeding)  ·  PR #1

The audit's highest-priority fixes. Every item is a stale fact in a doc agents actually read.

- **`CLAUDE.md:16` ("Current position")** — the worst offender (always-in-context). It claims "Phase-1 build *started*, Epic 001 DONE, next: 002→003→poller→Valhalla." Replace the whole status detail with **one line**: `**Current position:** Phase-1 build complete; baseline main==725c442. Live status & next work: docs/process/roadmap.md` — making roadmap the SSOT so this line can't rot again.
- **`CLAUDE.md`** — refresh `:38` "frontend TBD" and `:45` frontend phasing (the app UX shipped); soften the "Stack & conventions — SET IN STAGE 0" framing; drop the Garmin-poller-as-"next" framing (Epic 004 DONE). Confirm the `Co-Authored-By` model footer (`:64` currently names "Claude Sonnet 4.6") matches the working model.
- **`README.md:5, :18-19, :22`** — "Status: design complete for Phase 0… no app logic yet", "Most modules are stubs", "Next: build the Phase-0 vertical slice" are all false. Update to "Phase-1 build complete; app UX shipped" or replace with a pointer to `roadmap.md`.
- **`decision-log.md`** — §30/§31 still say the commons fork is "Designed, not built — Epic 010 pending"; Epic 010 is DONE (flip to ✅ built). Strip the "◆ … design complete — next is build" footers (build is done). Fix the header date (`:3` says June 18; sections run through 06-24). §26 "Proposed next step" ("Now in: Stage 2…") is grossly stale.
- **`docs/research/` stale banners** — flip "not built / DESIGN" banners now contradicted by shipped code: `stage-9-commons.md` + `t6-licensing-consent.md` (commons fork built — Epic 010); `stage-8-multiplayer-privacy.md:13` precondition block (its 3 blockers — write seam, viewer auth, overlay egress — are CLOSED by Epics 011/014); `stage-3-corpus-pipeline.md:5` + `stage-4-engine-and-cost.md:5` ("Status: DESIGN" — both built). Prefer a one-line `STATUS: IMPLEMENTED by Epic NNN` badge over deleting the design narrative.

## Wave 2 — Navigation & structure (make the right doc findable)  ·  PR #2

- **New `docs/README.md`** — the top-level doc map. A `read-this-for-task-that` router table (≥5 rows: *check status*→roadmap.md; *add/close a feature*→epics/README.md→the epic file; *touch schema*→graph/ + decision-log §28; *how to commit/review*→development-process.md; *understand a stage*→research/README.md) + an explicit **always-load vs load-on-demand** split + a one-line declaration of each SSOT (status→roadmap; per-epic→epics/README; decisions→decision-log; plan→workplan).
- **New `docs/research/README.md`** — an index for the 25+ research docs: a `stage → file → one-line purpose → STATUS badge` table (`ACTIVE` / `IMPLEMENTED-by-Epic-NNN` / `SUPERSEDED` / `ARCHIVED`). This kills the "guess-and-sample 27 files" problem.
- **Wire the orphans into `CLAUDE.md`** — its "Canonical design docs (read on demand)" list omits `docs/process/roadmap.md` (the live dashboard — add it, marked SSOT for status), the two `docs/README.md`/`research/README.md` maps, and (optionally) the runbooks. The freshest doc must be findable from root.
- **Per-doc headers** — add a one-line `STATUS: … · Read this when: …` header to each research doc so agents skip irrelevancies cheaply.

## Wave 3 — Dedupe & archive (token efficiency)  ·  PR #3

- **Create `docs/research/archive/` and `git mv` the closed history into it** (~115KB / ~29K tokens off the live surface): `architecture-gap-audit-2026-06.md`, `self-review-2026-06.md`, `integrated-remediation-review-2026-06.md`, `conflation-review-2026-06.md`, `api-verification-2026-06.md`. Add a 2-line `archive/README.md` ("Closed point-in-time audits; findings actioned & shipped; kept for provenance").
- **`decision-log-additions-proposed.md`** — it proposes folding §32–40 into `decision-log.md` (which still stops at §31). **Fold the still-live decisions into `decision-log.md` first**, then `git mv` the proposal to `archive/`. Do not lose a decision.
- **Archive superseded design specs** → `archive/`: `home-curation-prototype-spec-v0.2.md` (superseded by v0.3, per v0.3:55), and the now-fully-implemented seam specs `device-integration-seam.md` (Epic 004) + `source-seams-corpus-and-live.md` (Epics 012/013) — *or* leave in place with an `IMPLEMENTED-by-Epic` badge if you judge them still useful reference. Archive `ui-brief-v0.2.md` if superseded by the shipped design-system/ux-assembly docs.
- **Collapse `CONTRIBUTING.md` → `AGENTS.md`** — it's ~80% a restatement (session start, seams, validation, PR rules). Reduce CONTRIBUTING to a thin human-facing pointer to AGENTS.md + development-process.md.
- **Single-source the duplicated facts** (losing copy → pointer): architecture-in-one-breath (`README.md:10-11` → link to `CLAUDE.md`); git/PR hygiene (canonical = `development-process.md`; trim the copies in `CLAUDE.md:52-87`, `AGENTS.md`, `CONTRIBUTING`); the merge-seam list (one home); the local-setup command block (→ `make help`); the T1–T7 thread tracker (state lives in `roadmap.md` — PM lane; `epics/README.md:23-25` and `workplan.md` keep only the *definitions*/pointer).
- **Do NOT** trim the DONE-epic story/AC bodies — they're the spec history, lazy-loaded, low cost. Leave them.

## Wave 4 — Anti-drift enforcement (make it stick)  ·  PR #4  *(LAST — needs Waves 1–3 done first)*

- **Generate the epic index from epic headers.** A small `scripts/gen_epic_index.py` that reads each `docs/epics/epic-*.md` `**Status:**`/`**Phase:**`/`Depends:` header and rewrites the `docs/epics/README.md` table. Kills the #1 drift source (epic status in 4 places).
- **CI doc-lint** — a new `docs-lint` job in `.github/workflows/ci.yml` (and `scripts/doc_lint.py`) that **fails the build** on:
  1. **Epic index out of sync** — run `gen_epic_index.py --check` (generated table ≠ committed table → fail).
  2. **Known stale markers** — grep the live doc surface (excluding `archive/`) for a denylist of strings that are now wrong: e.g. `Epic 010 pending`, `no app logic yet`, `Phase-1 build started`, `claude/vigilant-bohr-yzdcyh` as an *active* branch ref, `Designed, not built` on a shipped epic. (Keep the denylist in `scripts/doc_lint.py`, commented with why each is banned.)
  3. **Broken internal links** — every relative `*.md` link resolves to an existing file (this is also what makes autonomous doc-merging safe).
- Add the `docs-lint` job to the **required status checks** note in `docs/process/github-repo-hygiene.md` (and flag the PM to add it to branch protection).
- **Uniform freshness stamp** — add `**Last verified:** <date> · **Owner:** <lane>` to the top of each *live* status-bearing doc (not the archived ones).

---

## Out of scope / do NOT touch
- `docs/process/roadmap.md` + `docs/workplan.md` (PM lane — link to roadmap as the status SSOT).
- Any `api/ graph/ orchestration/ ingestion/ frontend/` source.
- The DONE-epic AC bodies (leave as spec history).
- Trimming `CLAUDE.md`'s 10 non-negotiable rules — load-bearing invariants, keep as-is.

## When done
4 PRs merged into `main` (one per wave, CI green incl. the new `docs-lint`). Leave any `NEEDS-PM:` notes prominent. The result: a lean always-load hot path, a findable doc map, the ~115KB of closed history archived, single-source facts, and a CI gate that fails on wrong memory. The PM will reconcile `roadmap.md` + retire this runbook to `archive/` once it's executed.
