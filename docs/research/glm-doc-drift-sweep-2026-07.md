# GLM Doc-Drift / Stale-Memory Sweep (2026-07)

**Status:** DONE ✅
**Owner:** GLM Auditor
**Target:** Factual current-state claims vs. `main`

## Findings: Factual Claim Drift

| Claim as written | Doc : Line | Reality on main (file:line proof) | Verdict | Proposed exact corrected text |
| :--- | :--- | :--- | :--- | :--- |
| **Corroboration is unwired / unexercised:** `engine.py:172` calls `for_fact(fact)` with no corroboration argument... it defaults to 1. | `docs/strategy/path-to-complete.md:32,126,132,278,320` and `docs/research/cdp-01-corroboration-feasibility-spike.md:19` | `orchestration/engine.py:320` has `_corpus_corroboration` which is actively called at line 427. Live facts are pinned at 1 at `engine.py:491` (`for_fact(fact, corroboration=1)`). Corroboration is wired. | **STALE** | Move corroboration from Phase A "needs wiring" to "DONE" in `path-to-complete.md`. Update line refs from `engine.py:172` to `engine.py:491` for the live-fact pin. |
| **Slug collision is unguarded:** `_build_canonical_id` (`pipeline.py:72-83`). Short identical slugs unguarded, sha1 suffix fires only when `len(slug) > 40`, id keeps only `slug[:33]` + a 6-char hash. | `docs/strategy/path-to-complete.md:136,279` and `docs/research/comaps-borrow-plan.md:209` | `ingestion/pipeline.py:130-145` applies an 8-char sha1 suffix unconditionally and keeps `slug[:50]`. The short-slug collision is guarded. | **STALE** | Move the slug-collision substrate audit to the "DONE" section of `path-to-complete.md` (and remove claims it is unguarded). |
| **Phantom Epics / Doc drift fixes still pending:** "Fix the doc drifts NOW — apply_schema 'untracked', epic-index vs roadmap on Maps 016/017, phantom epics 007/008" | `docs/strategy/path-to-complete.md:140,280,362` | `docs/process/roadmap.md:121` states `apply_schema.py` is tracked. Epics 016/017/008 are DONE in both `roadmap.md` and `docs/epics/README.md`. | **STALE** | Remove the follow-ups about fixing these specific doc drifts from `path-to-complete.md`, as they are already completed. |
| **Epic Index Completeness:** (Implicit claim that `docs/epics/README.md` contains all epics) | `docs/epics/README.md` | `docs/epics/epic-026-tag-classification.md` exists and is DONE, but is missing from the table in `docs/epics/README.md`. | **WRONG** | Insert row for 026 (linking `epic-026-tag-classification.md`): `\| 026 \| Classify OSM tags... \| DONE ✅ \| 1 \| Epic 023 \|` |
| **Phantom Epic 008:** Epic 008 is tracked in the index and roadmap as DONE ✅. | `docs/process/roadmap.md:75` and `docs/epics/README.md:14` | The file `docs/epics/epic-008-*.md` does not exist in the repository. | **WRONG** | Either create a stub `epic-008-api-tests.md` file, or note in the index that this work was completed without an epic file. |

## Candidate Gate Improvements (What `doc_lint.py` structurally cannot catch)

1. **Missing epic index rows:** `gen_epic_index.py` only updates rows that *already exist* in the `README.md` table. It does not scan the `docs/epics/` directory for missing `epic-*.md` files (like Epic 026) and add them to the index.
2. **Stale inline file:line references:** Code symbols and line numbers in backticks (e.g., `engine.py:172` or `pipeline.py:72-83`) are not verified. The script cannot catch when functions move (e.g., to `pipeline.py:130`) or change names.
3. **Semantic claim drift:** The script relies on a hardcoded regex denylist for stale claims. It cannot adapt to arbitrary semantic claims like "corroboration is unexercised" or "slugs are unguarded" once the code implementing those features is merged.
4. **Cross-document status mismatches:** The script checks that `docs/epics/README.md` matches individual epic file headers, but it does not cross-check the epic statuses mentioned in `docs/process/roadmap.md` or `docs/strategy/path-to-complete.md`.
5. **Phantom epics:** The script does not verify that epics marked DONE in the index or roadmap actually have corresponding `epic-*.md` files or merged code.
