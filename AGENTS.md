# AGENTS.md — Adventure Planner

This file is the tool-agnostic operating contract for coding agents working in this repo.

**Last verified:** 2026-06-26 · **Owner:** docs

Read it together with `CLAUDE.md`:
- `AGENTS.md` = session startup, merge-risk discipline, repo hygiene
- `CLAUDE.md` = product invariants, architecture, development process

## Start every session
1. Run `git status --short --branch` and confirm the target branch.
2. Verify whether the working tree is clean before making changes.
3. Read only the docs needed for the task; do not reload the entire design set by default.
4. Inspect the tests and immediate call sites before changing a shared contract.

## Work selection when parallel branches are active
- Prefer isolated changes in `.github/`, docs, tests, or leaf modules when multiple agents may be active.
- Avoid broad refactors or opportunistic cleanup while shared integration work is in flight.
- Treat central seams as merge-sensitive: `api/`, `graph/schema.cypher`, `orchestration/engine.py`, `orchestration/belief_update.py`, and ingestion pipeline entrypoints.
- If you touch a merge-sensitive seam, inspect likely consumers first and call out the risk in the PR.

## Git and PR hygiene
- Commit/PR discipline is canonical in [`docs/process/development-process.md`](docs/process/development-process.md): one logical change per PR; small, reviewable, reversible diffs; `make check` before handoff; the PR template (summary/why/scope/validation/merge-risk); never merge with failing CI or unresolved comments.
- Branch from `main`; open PRs into `main`. `main` is **branch-protected** — PRs only, all required CI checks must pass, no force-push/delete (see [`docs/process/github-repo-hygiene.md`](docs/process/github-repo-hygiene.md)).

## Review discipline
- Link the relevant epic, story, acceptance criteria, or design doc.
- Update docs when contracts or workflows change.
- Prefer targeted review for narrow changes; use broad review only for cross-cutting work.

## Safety rules
- Never commit secrets, generated credentials, or `.env` contents.
- Do not invent APIs, data sources, or product behavior that the repo/docs do not support.
- Do not delete or rewrite process docs unless the replacement is strictly better and aligned with current practice.
