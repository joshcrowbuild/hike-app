# Plan-reliability lane — verification & closure note

*Closes the roadmap-v12 open item "❓ plan-reliability outcome unverified (branch gone from origin; confirm or re-open)". Verdict: **confirmed shipped — nothing to re-open.***

**Last verified:** 2026-07-11 · **Owner:** build lane (verification note) · **Status:** CLOSED

## What was in question

Roadmap v11 recorded a `claude/plan-reliability` lane "in flight" (driver
transient-retry + liveness, provider transient-retry) after `/plan`
intermittently 500'd on a first-after-idle request. By the v12 reconcile the
branch no longer existed on origin and no merged PR surfaced under that name,
so the outcome was flagged unverified — did the hardening land, or vanish?

## What was found (verified on `main`, 2026-07-11)

**It landed — as PR [#65](https://github.com/joshcrowbuild/hike-app/pull/65)
"Harden /plan against transient graph + provider failures", merged
2026-07-01.** The lane's branch was deleted after merge, and the PR title
doesn't contain "plan-reliability", which is why the v12 search missed it.
Everything roadmap R7 described is present on `main`:

- **Driver liveness/pool config** — `graph/client.py` (`GraphClient._ensure_driver`):
  `max_connection_lifetime=180` (recycled before Aura's ~300s idle close),
  `liveness_check_timeout=30` (ping an idle socket before reuse),
  `connection_acquisition_timeout=30`, `max_transaction_retry_time=15`.
- **Bounded read retry** — `graph/client.py` (`_run_with_retry` +
  `_is_retryable`): the `/plan` read hot path retries up to 3 attempts on
  errors the driver itself marks retryable (`ServiceUnavailable` /
  `SessionExpired` / `TransientError`), each attempt on a fresh session.
  Single autocommit **writes are deliberately not retried** (a post-commit-ack
  death raises a *retryable* error and re-running a non-idempotent owned write
  would double-apply it); atomic batches keep the managed `execute_write`
  retry, whose true lost commit surfaces as non-retryable `IncompleteCommit`.
  This is why the code uses a hand-rolled retry rather than a blind
  `execute_read` swap: the one runner also serves the test harness's world
  writes, and the hand-rolled version replicates the driver's managed-retry
  decision exactly while preserving autocommit semantics.
- **Provider transient retry** — `orchestration/providers/retry.py`
  (`retry_transient`, `is_transient_api_error`): bounded
  exponential-backoff-with-jitter over `{408, 409, 429, 500, 502, 503, 504,
  529}` + connection/timeout errors, honoring a capped `Retry-After`; client
  errors (400/401/403/404/422) surface immediately. Wired into **both**
  adapters (`anthropic_claude.py`, `local_openai.py`), each built with
  `max_retries=0` so the SDK's own retries don't stack.

## Tests that prove it (hermetic, in `make check` on every PR)

- `tests/test_graph_resilience.py` — 8 tests: a stale-connection-shaped
  transient on first read recovers; the retry budget is bounded; a
  non-retryable error is never retried; a single write is never retried; the
  driver is built with the resilience config; the scope merge is untouched.
- `tests/test_provider_retry.py` — 16 tests over the transient classifier,
  backoff bounds, and `Retry-After` handling.
- `tests/test_plan_resilience.py` — 5 end-to-end `/plan` tests: transient
  graph/provider blip → 200; persistent failure → clean typed 500 with a
  correlation id, not a crash.

All pass on `main` as of this note (`make check`: 1368 passed).

## Disposition

The roadmap-v12 ❓ can flip to ✅ on the next PO status pass (this note is the
evidence; the roadmap itself is PO-owned). No code change was needed in this
lane — route behavior untouched.
