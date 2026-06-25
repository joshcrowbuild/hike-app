# Contributing

Thanks for contributing to Adventure Planner.

This repo currently relies on a mix of version-controlled automation and manual review discipline. Start here before opening a PR.

## Read first

- `AGENTS.md` — repo operating rules, merge-risk discipline, and Git/PR hygiene
- `CLAUDE.md` — product invariants, architecture, and development process
- `docs/process/development-process.md` — epic → story → AC → tests → code → review workflow
- `docs/process/github-repo-hygiene.md` — CI, PR expectations, and the current manual fallback while GitHub-native branch protection is unavailable

## Local setup

Prereqs:

- Python 3.11+
- Docker
- a local `.env` created from `.env.example`

Typical setup:

```sh
cp .env.example .env
make install-dev
make check
make db-up && make schema
```

Run `make help` for the full command list.

## Working agreement

- Start each session with `git status --short --branch`.
- Keep each PR to one logical change.
- Keep diffs small, reviewable, and reversible.
- Update docs when contracts or workflows change.
- Inspect tests and immediate call sites before changing a shared contract.

When multiple agents or branches are active, prefer isolated work in:

- `.github/`
- docs
- tests
- leaf modules

Treat these as merge-sensitive seams:

- `api/`
- `graph/schema.cypher`
- `orchestration/engine.py`
- `orchestration/belief_update.py`
- ingestion pipeline entrypoints

If you touch one of those seams, inspect likely consumers first and call out the merge risk in your PR.

## Validation

Use the repo targets directly:

- `make format-check`
- `make lint`
- `make typecheck`
- `make test`
- `make check`

`make check` must pass before handoff or merge.

## Pull request expectations

- Use `.github/PULL_REQUEST_TEMPLATE.md`.
- Link the relevant epic, story, AC, or design doc.
- Explain why the change exists.
- Report what validation was run.
- Call out any shared or merge-sensitive seams touched.
- Do not merge with unresolved review comments or failing CI.

## Manual fallback while branch protection is unavailable

This repo is currently private on a GitHub plan that does not expose branch protection or rulesets here.

Until that changes:

- merge by PR, not by blind direct push
- require a green CI run before merge
- require at least one human review before merge
- use `CODEOWNERS` and the PR template for non-trivial changes
- prefer small, atomic PRs so manual review remains trustworthy
