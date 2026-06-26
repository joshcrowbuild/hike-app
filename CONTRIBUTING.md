# Contributing

Adventure Planner is built by coding agents under a tight operating contract. Before opening a PR, read:

- **[`AGENTS.md`](AGENTS.md)** — the operating contract: session startup, merge-risk discipline, Git/PR hygiene.
- **[`CLAUDE.md`](CLAUDE.md)** — product invariants, the non-negotiable rules, architecture, and stack.
- **[`docs/process/development-process.md`](docs/process/development-process.md)** — the full workflow (epic → story → AC → tests → code → review) plus the canonical commit/PR and code standards.
- **[`docs/process/github-repo-hygiene.md`](docs/process/github-repo-hygiene.md)** — CI checks, branch protection, and merge policy.

Quick start: `cp .env.example .env` → `make install-dev` → `make check` → `make db-up && make schema`. Run `make help` for all targets. Secrets live only in `.env` (git-ignored), never in the repo (CLAUDE.md Rule #10).
