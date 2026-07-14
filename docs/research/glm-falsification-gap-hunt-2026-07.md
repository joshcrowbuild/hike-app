# Falsification-Test Gap Hunt — Guard Audit (2026-07)

**Status:** ACTIVE (foreign-model audit of test falsifiability)
**Reviewer:** GLM (foreign-model gap hunt)
**Scope:** Every guard/invariant listed in the GLM prompt: prune ratio, verify_before_prune, scoped-write, viewer-id, rate limiting, secret redaction, eval-gate hard keys, region non-overlap — plus additional guards discovered during the audit.
**Method:** For each guard, ask: *does a test exist that goes RED if the guard were deleted?* If yes, the guard is falsified. If no, it's a gap.

---

## 1. Audit summary

| # | Guard | Location | Falsified? | Gap severity |
|---|-------|----------|-----------|-------------|
| 1 | Prune ratio / collapse gate | `graph/load.py:prune_stale_trails` guard 2, `ingestion/pipeline.py:verify_before_prune` | ✅ YES | — |
| 2 | verify_before_prune (pipeline gate) | `ingestion/pipeline.py:538` | ✅ YES | — |
| 3 | Scoped-write guard | `graph/queries.py:assert_scoped_write` | ✅ YES | — |
| 4 | Viewer-id auth | `api/app.py:_authorize_viewer` | ✅ YES | — |
| 5 | Rate limiting | `api/ratelimit.py:limiter` + `real_client_ip` | ✅ YES (partial) | LOW (no-XFF fallback) |
| 6 | Secret redaction | `orchestration/logsafe.py:SecretUrlRedactionFilter` | ✅ YES | — |
| 7 | Eval-gate hard keys | `evals/replay.py:_hard` + `_REQUIRED_HARD_KEYS` | ✅ YES | — |
| 8 | Region non-overlap | `tests/test_region_files.py:test_region_bboxes_pairwise_disjoint` | ✅ YES | — |
| 9 | NEO4J loopback guard | `tests/conftest.py:_assert_local_neo4j_uri` | ✅ YES | — |
| 10 | Overlay egress | `orchestration/engine.py` privacy routing | ✅ YES | — |
| 11 | Owned-ref safety in prune | `graph/load.py:prune_stale_trails` (2c) | ✅ YES | — |
| 12 | Region separator anchor | `graph/load.py:_REGION_VERSION_PRED` | ✅ YES | — |
| 13 | Empty-ingest guard (min_current) | `graph/load.py:prune_stale_trails` guard 1 | ✅ YES | — |
| 14 | Feed warmer anonymous-only | `api/feed_warmer.py:184` | ✅ YES | — |
| 15 | Feed warmer kill switch | `api/feed_warmer.py:131` | ✅ YES | — |
| 16 | Commons privacy vacuous | `tests/test_commons_privacy.py:test_s5_ac4_privacy_suite_not_vacuous` | ✅ YES | — |
| 17 | No-scenarios check | `evals/run_replay.py:54` | ❌ NO | **HIGH** |
| 18 | Prune ratio env-fallback (garbage) | `graph/load.py:prune_min_ratio()` try/except | ❌ NO | **MEDIUM** |
| 19 | _ANSWERED_STATES complement | `evals/replay.py:480-486` | ❌ NO | **MEDIUM** |
| 20 | Elev coverage env-fallback (garbage) | `ingestion/pipeline.py:_env_float` try/except | ❌ NO | **LOW** |
| 21 | Rate limiter no-XFF fallback | `api/ratelimit.py:real_client_ip` fallback | ❌ NO | **LOW** |

**Result:** 16 guards falsified, 5 gaps found. Top 5 gaps ranked below with test skeletons.

---

## 2. Falsified guards (proof of coverage)

### 2.1 Prune ratio / verify_before_prune

**Guard:** `verify_before_prune` raises `IngestVerificationError` when `n_cur < ratio * pre_load_count`. `prune_stale_trails` guard 2 independently aborts on the same condition.

**Falsification tests:**
- `test_verify_before_prune_aborts_on_collapse` — n_cur=100, pre_load=1500 → expects `IngestVerificationError(match="collapsed")`. If guard deleted, no exception raised → test fails.
- `test_verify_before_prune_aborts_on_half_partial_reingest` — n_cur=700, n_prev=700, pre_load=1500 → expects exception. Tests the collapse-gate correction (pre-load denominator, not post-load n_prev).
- `test_verify_before_prune_run_marker_truncated_ingest_trips` — run-marker mode, n_cur=100 of 1500 → expects exception. Verifies the run-marker keying makes the gate sensitive.
- `test_truncated_ingest_does_not_prune` (neo4j) — end-to-end: truncated ingest leaves prior corpus intact.
- `test_run_marker_truncated_ingest_aborts_via_ratio_guard` (neo4j) — end-to-end with run markers.

**Verdict:** ✅ Strongly falsified. Multiple tests at both unit and integration level.

### 2.2 Scoped-write guard

**Guard:** `assert_scoped_write` raises `UnscopedWriteError` if an owned-label write lacks an owner-scope clause bound to `$viewer_id`.

**Falsification tests:**
- `test_s1_ac6_free_owner_param_does_not_satisfy_guard` — `owner_id = $owner` (≠ `$viewer_id`) → expects `UnscopedWriteError`. If guard deleted, no exception → test fails.
- `test_s3_ac2_every_write_builder_passes_the_guard` — every builder's Cypher passes the guard (positive test, but structural).
- `test_s3_ac4_no_builder_takes_a_free_owner_param` — no builder binds owner to anything but `$viewer_id`.
- `test_s3_ac2_owned_upserts_pin_owner_in_the_merge_key` — upserts pin `owner_id` in MERGE key.

**Verdict:** ✅ Falsified. The negative test (AC6) goes red if the guard is deleted.

### 2.3 Viewer-id auth

**Guard:** `_authorize_viewer` rejects non-anonymous viewer_id without the dev secret. Fails closed when secret is unset.

**Falsification tests:**
- `test_s3_ac1_plan_rejects_forged_viewer_id` — `viewer_id="mem:josh"` with no secret → expects 403. If guard deleted, returns 200 → test fails.
- `test_s3_ac3_dev_secret_accepts_and_fails_closed` — correct secret passes, missing header → 403.
- `test_s3_ac3_fail_closed_when_secret_unset` — secret absent from config → 403 regardless of header.
- `test_s3_ac4_outcome_rejects_forged_viewer_id` — same guard covers the outcome endpoint.

**Verdict:** ✅ Falsified. Multiple negative tests that expect 403.

### 2.4 Rate limiting

**Guard:** `limiter` (slowapi) bounds per-IP request rate. `real_client_ip` keys on the last XFF entry to prevent spoofing.

**Falsification tests:**
- `test_plan_rate_limited_returns_clean_429` — 3rd request → expects 429. If limiter deleted, returns 200 → test fails.
- `test_plan_buckets_are_keyed_per_forwarded_client_ip` — client A exhausted, client B still fresh. If `real_client_ip` deleted (all share one bucket), B would get 429 → test fails.
- `test_plan_bucket_ignores_client_spoofed_xff_prefix` — rotating forged XFF prefix doesn't buy a fresh bucket. If `real_client_ip` used first XFF entry instead of last, rotating prefix would evade → test fails.
- `test_health_rate_limited_returns_429`, `test_outcome_write_endpoint_is_rate_limited` — adjacent endpoints bounded.

**Verdict:** ✅ Falsified (partial — the no-XFF fallback path is untested, see gap #5).

### 2.5 Secret redaction

**Guard:** `SecretUrlRedactionFilter` masks API keys in httpx log lines before any handler sees them.

**Falsification tests:**
- `test_firms_map_key_in_url_path_never_reaches_a_handler` — FIRMS_MAP_KEY in URL path → not in any handler message. If filter deleted, key appears → test fails.
- `test_airnow_api_key_query_param_never_reaches_a_handler` — API_KEY in query param → not in messages.
- `test_root_handlers_carry_the_filter_for_child_logger_records` — httpcore.http11 records also masked.
- `test_filter_is_not_stacked_on_repeated_setup` — no duplicate filters on repeated `setup_logging`.

**Verdict:** ✅ Falsified. Tests assert the secret string does NOT appear in output.

### 2.6 Eval-gate hard keys

**Guard:** `_hard()` in `evals/replay.py` validates that `expected.json`'s `hard` block has exactly `_REQUIRED_HARD_KEYS` — no more, no less. Prevents vacuous passes from missing/typoed keys.

**Falsification tests:**
- `test_typoed_expectation_key_is_rejected_not_vacuously_green` — `must_blocked` (typo of `must_be_blocked`) → expects `ValueError(match="must_be_blocked")`. If validation deleted, typoed key passes silently → no ValueError → test fails.
- `test_unknown_condition_kind_reds_fidelity_not_a_traceback` — bad kind name → red criterion, not crash.
- `test_gutted_corpus_fails_surfaced_expected` — empty corpus → `surfaced_expected` failure.

**Verdict:** ✅ Falsified. The typo test goes red if the key validation is deleted.

### 2.7 Region non-overlap

**Guard:** `test_region_bboxes_pairwise_disjoint` — the test IS the guard. It checks every pair of region bboxes for positive-area overlap.

**Falsification tests:** The guard is self-falsifying: if the assertion were deleted, the test would pass trivially (but then the guard wouldn't exist). The test is run in CI on every PR.

**Verdict:** ✅ Falsified (tautologically — the test is the guard).

### 2.8 NEO4J loopback guard

**Guard:** `_assert_local_neo4j_uri` refuses non-loopback / Aura TLS schemes.

**Falsification tests:**
- `test_rejects_the_uri_shape_that_wiped_production` — `neo4j+s://...` → expects `pytest.fail.Exception`. If guard deleted, no fail → test fails.
- `test_rejects_every_non_local_uri_shape` — parametrized: all remote schemes + non-loopback hosts + empty string.
- `test_near_miss_opt_in_values_do_not_bypass` — `true`, `1`, `yes` don't bypass; only the exact ugly string does.

**Verdict:** ✅ Falsified. Comprehensive negative tests.

### 2.9–2.16 Remaining falsified guards

| Guard | Key falsification test | How it goes red |
|-------|----------------------|-----------------|
| Overlay egress | `test_overlay_egress.py` AC-1.2 | Overlay-carrying call uses `LocalOpenAIProvider`, not cloud → if routing deleted, cloud provider used → assertion fails |
| Owned-ref safety | `test_owned_referenced_trail_survives_prune` | `outcome.protected == 1` → if skip deleted, protected=0, trail pruned |
| Region separator anchor | `test_prune_stale_trails_prefix_is_separator_anchored` | Cypher contains `STARTS WITH $prefix` with `-` boundary → if bare `STARTS WITH $region_id`, shen prunes shenandoah |
| Empty-ingest guard | `test_empty_ingest_still_noops` | n_cur=0 → no delete fires → if guard deleted, all nodes wiped |
| Feed warmer anonymous-only | `test_feed_warmer.py:69` | `assert viewer_id == "anonymous"` → if production code changed, assertion fails |
| Feed warmer kill switch | `test_disabled_feed_cache_disables_the_warmer` | Disabled cache → warmer doesn't run → if check deleted, warmer runs |
| Commons privacy vacuous | `test_s5_ac4_privacy_suite_not_vacuous` | Privacy test count > 0 → if tests deleted, count drops to 0 → goes red |
| Cross-region prune isolation | `test_region_scope_protects_other_regions` | Prune of region A doesn't touch region B → if scope deleted, B's nodes pruned |

---

## 3. Gap report (ranked)

### Gap 1 — HIGH: No-scenarios check in `run_replay.py`

**Guard:** `evals/run_replay.py:54`:
```python
raise SystemExit("no scenarios found under evals/scenarios/ — the gate has no teeth")
```

**What it prevents:** An empty scenario directory silently passing as a green eval gate — the ultimate vacuous pass. If someone accidentally deletes or gitignores the scenario directory, the gate should fail loudly, not report "0 scenarios, 0 failures, all green."

**Why no test goes red:** No test calls `run_replay` with an empty scenario directory and asserts `SystemExit`. If the `raise SystemExit` line were deleted, the script would silently produce an empty report, and no test would catch it.

**Test skeleton:**
```python
# tests/test_eval_replay.py

import subprocess, sys, tempfile, pathlib

def test_empty_scenario_directory_aborts_not_vacuously_green(tmp_path):
    """If evals/scenarios/ is empty, run_replay must SystemExit, not silently pass."""
    empty_dir = tmp_path / "empty_scenarios"
    empty_dir.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "evals.run_replay", "--scenarios-dir", str(empty_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "no scenarios" in result.stderr.lower() or "gate has no teeth" in result.stderr.lower()
```

**Note:** The `--scenarios-dir` flag may not exist yet — the test skeleton assumes it or a monkeypatchable entry point. Alternatively, test the function directly if `run_replay` exposes a callable API.

---

### Gap 2 — MEDIUM: Prune ratio env-fallback on garbage value

**Guard:** `graph/load.py:prune_min_ratio()`:
```python
try:
    return float(raw)
except ValueError:
    log.warning(...)
    return _DEFAULT_PRUNE_MIN_RATIO
```

**What it prevents:** A malformed `ADVENTURE_PRUNE_MIN_RATIO` env value (e.g. `"half"` or `"0,5"`) silently disabling the data-safety gate. Without the fallback, `float("half")` raises `ValueError` and the pipeline crashes — loud, but the guard's *safe-default* contract is broken. The docstring says "a bad knob must never silently disable this data-safety gate."

**Why no test goes red:** `test_verify_before_prune_ratio_env_configurable` tests `ADVENTURE_PRUNE_MIN_RATIO=0.1` (valid float). No test sets it to a non-float string and asserts the fallback to 0.5. If the try/except were deleted, the valid-value test would still pass; only the garbage case would crash.

**Test skeleton:**
```python
# tests/test_pipeline.py

def test_prune_min_ratio_falls_back_safe_on_garbage_env(monkeypatch):
    """A non-float ADVENTURE_PRUNE_MIN_RATIO must fall back to the default, not crash."""
    from graph.load import prune_min_ratio, _DEFAULT_PRUNE_MIN_RATIO
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "not-a-number")
    assert prune_min_ratio() == _DEFAULT_PRUNE_MIN_RATIO

def test_prune_min_ratio_falls_back_safe_on_empty_env(monkeypatch):
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "")
    assert prune_min_ratio() == _DEFAULT_PRUNE_MIN_RATIO
```

---

### Gap 3 — MEDIUM: `_ANSWERED_STATES` complement check

**Guard:** `evals/replay.py:480-486`:
```python
if want in _ANSWERED_STATES and not answered:
    violations.append(...)
if want not in _ANSWERED_STATES and answered:
    violations.append(...)
```

**What it prevents:** An answered condition state (`present`, `stale_degraded`, `no_hazard`, `no_data`) appearing without source attribution, or an unanswered state carrying a fabricated source. This is the source-or-silence invariant enforced in the eval gate.

**Why no test goes red:** No test tampers with a scenario's expected condition states to inject an answered state without source (or vice versa) and asserts the violation is caught. If the complement check were deleted, a scenario with `present` but no source would pass silently — the exact fabrication the invariant prevents.

**Test skeleton:**
```python
# tests/test_eval_replay.py

def test_answered_state_without_source_is_caught():
    """An answered condition state (present/no_hazard/etc.) carrying no source
    must be flagged as a violation — source-or-silence in the eval gate."""
    from evals.replay import check_condition_states, _ANSWERED_STATES, ReplayScenario
    # Build a minimal scenario with a 'present' state that lacks source
    # (tamper with a nominal scenario's expected condition states)
    nominal = _by_name("nominal-old-rag")
    hard = dict(nominal.expected["hard"])
    # Inject a 'present' state with no source_prefix — should be caught
    hard["conditions"] = {"air_quality": "present"}  # answered but no source
    tampered = dataclasses.replace(nominal, expected={**nominal.expected, "hard": hard})
    result = evaluate_scenario(tampered, n=1)
    assert not result.passed
    assert "condition_states" in result.failures or "fact_fidelity" in result.failures

def test_unanswered_state_with_source_is_caught():
    """An unanswered state carrying a source must be flagged — fabricated attribution."""
    nominal = _by_name("nominal-old-rag")
    hard = dict(nominal.expected["hard"])
    # Inject an unanswered state (e.g. 'not_fetched') WITH a source — should be caught
    hard["conditions"] = {"air_quality": "not_fetched:source=NWS"}
    tampered = dataclasses.replace(nominal, expected={**nominal.expected, "hard": hard})
    result = evaluate_scenario(tampered, n=1)
    assert not result.passed
```

---

### Gap 4 — LOW: Elevation coverage env-fallback on garbage value

**Guard:** `ingestion/pipeline.py:_env_float()`:
```python
try:
    return float(raw)
except ValueError:
    log.warning(...)
    return default
```

**What it prevents:** A malformed `ADVENTURE_ELEV_MIN_COVERAGE` env value crashing the pipeline instead of falling back to the default 0.8.

**Why no test goes red:** `test_verify_before_prune_elev_coverage_env_configurable` tests `ADVENTURE_ELEV_MIN_COVERAGE=0.6` (valid). No test sets it to garbage and asserts the fallback.

**Test skeleton:**
```python
# tests/test_pipeline.py

def test_env_float_falls_back_safe_on_garbage(monkeypatch):
    """A non-float env value must fall back to the default, not crash."""
    from ingestion.pipeline import _env_float
    monkeypatch.setenv("ADVENTURE_ELEV_MIN_COVERAGE", "eighty-percent")
    assert _env_float("ADVENTURE_ELEV_MIN_COVERAGE", 0.8) == 0.8

def test_env_float_falls_back_safe_on_empty(monkeypatch):
    monkeypatch.setenv("ADVENTURE_ELEV_MIN_COVERAGE", "")
    assert _env_float("ADVENTURE_ELEV_MIN_COVERAGE", 0.8) == 0.8
```

---

### Gap 5 — LOW: Rate limiter no-XFF fallback

**Guard:** `api/ratelimit.py:real_client_ip()`:
```python
forwarded_for = request.headers.get("x-forwarded-for")
if forwarded_for:
    candidate = forwarded_for.split(",")[-1].strip()
    if candidate:
        return candidate
return get_remote_address(request)  # fallback: no XFF → raw client host
```

**What it prevents:** A direct connection (no proxy, no XFF header) crashing because `real_client_ip` has no fallback path. Without the `return get_remote_address(request)` fallback, a `None` return would break slowapi's key function contract.

**Why no test goes red:** All rate-limit tests use `proxied_client` (which sets XFF headers) or `client` (TestClient, which has a default remote address). No test specifically sends a request with NO XFF header through the `proxied_client` and verifies the fallback to `get_remote_address`. If the fallback line were deleted, the function would return `None` for no-XFF requests, but the existing tests all provide XFF, so none would go red.

**Test skeleton:**
```python
# tests/test_api_ratelimit.py

def test_real_client_ip_falls_back_when_no_xff_header():
    """Without an X-Forwarded-For header, real_client_ip must fall back to
    the raw client address, not return None or crash."""
    from api.ratelimit import real_client_ip
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {}  # no X-Forwarded-For
    request.client.host = "192.0.2.1"
    assert real_client_ip(request) == "192.0.2.1"

def test_real_client_ip_falls_back_on_empty_xff():
    request = MagicMock()
    request.headers = {"x-forwarded-for": ""}
    request.client.host = "192.0.2.2"
    assert real_client_ip(request) == "192.0.2.2"
```

---

## 4. Additional observations

### 4.1 Guards not in the original prompt but falsified

The audit discovered additional guards with strong falsification coverage:

- **Region separator anchor** — prevents `shen` from pruning `shenandoah` via a bare `STARTS WITH`. Falsified by `test_prune_stale_trails_prefix_is_separator_anchored`.
- **Owned-ref safety** — prevents pruning trails referenced by live Episodes. Falsified by `test_owned_referenced_trail_survives_prune` (asserts `protected == 1`).
- **Cross-region prune isolation** — pruning region A doesn't touch region B. Falsified by `test_region_scope_protects_other_regions`.
- **Empty-ingest guard** — `n_cur < min_current` prevents wiping on empty ingest. Falsified by `test_empty_ingest_still_noops`.
- **Feed warmer kill switch** — disabled cache stops the warmer. Falsified by `test_disabled_feed_cache_disables_the_warmer`.
- **Commons privacy vacuous** — meta-test ensures the privacy suite itself isn't vacuous. Falsified by `test_s5_ac4_privacy_suite_not_vacuous`.

### 4.2 Test quality observations

The existing falsification tests are high quality:
- They test the **negative** case (guard rejects/blocks/aborts), not just the positive path.
- They use **specific matchers** (`match="collapsed"`, `match="must_be_blocked"`) that verify the guard's reasoning, not just that *some* error occurred.
- The NEO4J loopback guard tests include **near-miss parametrization** (`true`, `1`, `yes` don't bypass) — exceptional rigor.
- The rate-limit XFF tests verify both **evasion** (rotating prefix) and **poisoning** (reusing someone else's prefix) attack vectors.

### 4.3 The `prune_min_ratio` / `_env_float` pattern

Both `prune_min_ratio()` and `_env_float()` share the same safe-fallback pattern: try `float(raw)`, except `ValueError`, return default. This is the correct design (a bad knob should never disable a safety gate), but neither has a falsification test for the garbage-input path. The gap is low-severity because deleting the try/except would produce a **loud crash** (ValueError), not a **silent bypass** — but the safe-default contract should still be falsified.

---

## 5. Recommendations

1. **Add the 5 test skeletons** above to close the gaps. Estimated effort: ~1 hour total.
2. **Priority order:** Gap 1 (HIGH) → Gaps 2+3 (MEDIUM) → Gaps 4+5 (LOW).
3. **Gap 1 is highest priority** because an empty eval scenario directory silently passing is the exact vacuous-pass failure mode the gate was built to prevent. The irony of a vacuous-pass guard itself passing vacuously is worth closing.
4. **Gaps 2+4** share the same pattern (env-float fallback) and could be closed with a single parametrized test covering both `prune_min_ratio()` and `_env_float()`.
5. **Gap 3** requires understanding the `check_condition_states` function's interface, which may need a small test harness to construct a `PlannedBatch` with tampered condition states.
