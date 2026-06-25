# GitHub Repo Hygiene

This repo enforces part of its workflow in version-controlled files and part of it in GitHub repository settings.

## Current decision

GitHub-native branch protection and rulesets are **deferred for now**.

Reason:

- the repo is staying private
- the current GitHub plan does not expose branch protection/rulesets for this repository

Until that changes, treat the protections below as the **target policy** and use the manual fallback in this document.

## Enforced in-repo

- CI workflow: `.github/workflows/ci.yml`
- Dependency updates: `.github/dependabot.yml`
- PR template: `.github/PULL_REQUEST_TEMPLATE.md`
- Code owner baseline: `.github/CODEOWNERS`
- Agent operating contract: `AGENTS.md`
- Product and process context: `CLAUDE.md`

## Manual fallback while branch protection is unavailable

Use this process on `main` and on any shared integration branch:

- merge by PR, not by blind direct push
- require a green CI run before merge
- require at least one human review before merge
- use `CODEOWNERS` and the PR template on every non-trivial change
- do not merge with unresolved review comments
- do not merge if `make check` fails locally
- prefer small, atomic PRs so manual review stays trustworthy

## Configure once in GitHub

Apply these settings to `main` and to any shared integration branch that is actively receiving PRs.

### Branch protection / ruleset

- Require a pull request before merging
- Require at least 1 approval
- Dismiss stale approvals when new commits are pushed
- Require review from code owners
- Require conversation resolution before merging
- Require status checks to pass before merging
- Restrict force pushes
- Prevent branch deletion

### Required status checks

Require these checks:

- `workflow-lint`
- `format-check`
- `lint`
- `typecheck`
- `test`

If GitHub shows the matrix-expanded names instead of bare job names, select the exact names shown by the first successful CI run.

### Recommended merge settings

- Prefer squash merge for small, atomic PRs
- Disable merge commits if you want a cleaner history
- Keep rebase merge optional; use it only when it matches the branch workflow

## Pull request expectations

Every PR should:

- represent one logical change
- explain why the change exists
- link the relevant epic, story, AC, or design doc
- call out any merge-sensitive seams touched
- report what validation was run

## Multi-agent branch discipline

When parallel coding agents are active:

- protect `main`
- protect the current shared integration branch
- do not require protection on every short-lived personal branch
- prefer PRs into the shared integration branch first, then merge integration into `main`

## Operating note

GitHub settings cannot be fully enforced from repo files alone. This runbook exists so the repo policy is visible, reviewable, and easy to re-apply if the repository is recreated or settings drift.
