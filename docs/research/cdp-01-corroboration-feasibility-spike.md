# CDP-01 Feasibility Spike — independence-checked corroboration

*A time-boxed, code-grounded spike answering the highest-leverage open question in the path-to-complete: can we build independence-checked corroboration (count distinct **origins**, not feeds), or does it degrade to honest count-as-1?*

**Last verified:** 2026-06-29 · **Owner:** vision-PM · **Status:** `ACTIVE` (resolves [`../strategy/path-to-complete.md`](../strategy/path-to-complete.md) open decisions #1 + #2)

> Method: read the real engine/verifier/confidence/adapters/graph-schema on `main` and traced where corroboration could ever be >1. External-API origin claims are stated with a confidence note; the load-bearing findings are all grounded in `file:line`.

## The question

CDP-01 (the moat) wants confidence's corroboration axis to count **distinct upstream origins**, never echoing feeds (the Curveball/citogenesis failure). Open decision #1 asked whether our live sources (NWS/USGS/AirNow/FIRMS/RIDB) expose **recoverable distinct-origin metadata** — the "moat-or-relabel" fork.

## Verdict

**The moat is real and recoverable — but its locus is the corpus/graph layer, not the live adapters. The live layer is single-source-by-construction, so its corroboration=1 is *honest*, not the feed-counting sin.** No investment in a live cross-referencing substrate is needed; the work is *connecting* origins we already hold to the confidence function.

## Findings (grounded in code on `main`)

1. **The live path cannot have corroboration >1 today.** The Verifier is break-on-first-success per kind (`orchestration/verifier.py` — "first success wins per kind", `break`), and `orchestration/engine.py:172` computes `for_fact(fact)` over a dict with **exactly one fact per `ConditionKind`**. Each kind maps to one government agency (weather→NWS, water→USGS, air→AirNow, fire→FIRMS, permits→RIDB). Corroboration is pinned at 1 (`orchestration/confidence.py:63,71`) because there is *structurally one source* — we never claim "2 sources", so the axis is **dead weight, not a lie**.
2. **The corpus layer already holds genuine multi-origin corroboration — and it never reaches `for_fact`.** `graph/schema.cypher` models each trail as multiple `:SourceRecord`s joined by `SAME_AS` (OSM + NPS + USFS + USGS_NTD), each a distinct ingest origin with a per-source authority tier (`:Source`). **Counting distinct `SourceRecord.source` per `SAME_AS` cluster = the independence count, available in the graph now.** But corpus facts (existence/geometry/length) don't flow through `for_fact` — only live condition facts do. The one place real corroboration exists is the one place it's never computed.
3. **The pattern is already proven in-repo.** `orchestration/belief_update.py` counts `corroboration_n` with an N=3 promotion threshold for personal beliefs — independence-aware corroboration already ships, just absent from the fact-confidence path.

## Per-source origin metadata (for the day a kind gets a 2nd provider)

| Source | Origin identifier | Recoverable? | Captured today? |
|---|---|---|---|
| **USGS water** | gauge site number (`site_id` / `monitoring_location_number`) | ✅ gold | **Yes** — in the fact `value` (`adapters/usgs_water.py:90-97`; surfaced `present.py:52`) |
| **NWS weather** | forecast office (CWA) + gridpoint (from `/points`) | ✅ yes | No — not stored in the fact |
| **FIRMS fire** | satellite/sensor (MODIS vs VIIRS; Aqua/Terra/Suomi-NPP per detection) | ✅ yes | Partial — keeps `dataset`, drops per-detection satellite (`adapters/firms.py:55`) |
| **AirNow air** | specific EPA monitor | ⚠️ **murky** — AirNow is an *aggregator*; response gives only coarse `reporting_area` (`adapters/airnow.py:67`); two AQI feeds both pulling AirNow share an origin by definition | No |
| **RIDB permits** | single federal source (Recreation.gov) | N/A — single origin, corroboration moot | — |

*Confidence note: USGS/AirNow rows are confirmed in-code; NWS/FIRMS "recoverable" rests on the published API schemas (NWS `/points`→office+grid; FIRMS per-detection satellite) — high-confidence but verify the exact field on capture.*

## What this resolves

- **Open decision #1 (moat-or-relabel):** The moat is **real**. Full distinct-origin recovery exists in the corpus layer (every `SourceRecord` names its origin) and for the point-based live sources (USGS gold; NWS/FIRMS recoverable). The only genuinely hard case is AirNow (an aggregator) → honestly "single aggregated source, counts as 1."
- **Open decision #2 (corroboration honesty):** **Keep the axis and exercise it on corpus facts**, where it's true. Live single-source conditions read "single authoritative source"; corpus facts read the real distinct-origin count. The axis stops being dead weight and never advertises an unexercised capability.
- **Correction to fold into [`../vision.md`](../vision.md):** the vision calls the constant `1` "the exact feed-counting sin the research names." That overstates it — we have *one feed and say so*, we don't count echoes as 2. Honest framing: the corroboration axis is **unexercised** (pinned at 1), and the corpus facts that *do* carry multi-source corroboration never reach `for_fact`. *(Filed as a follow-up edit to vision.md, not made in this PR.)*

## Recommended CDP-01 scope (Phase A) — now grounded

1. **Wire corpus corroboration into `for_fact`** — count distinct `SourceRecord.source` per `SAME_AS` cluster (per-attribute where survivorship differs), pass it as the real `corroboration` arg. This is the moat, and it's a graph read we can already do.
2. **Honestly label live single-source facts** — "single authoritative source," not an implied corroboration; carry the distinct-origin id where we have it.
3. **Capture origin-at-boundary (this *is* CDP-03)** — add NWS office+grid and FIRMS satellite to the fact now, so a future 2nd provider gets the independence check for free. USGS already does this.

**Net:** the moat survives the spike intact and is cheaper than feared — the corpus layer already holds the origins; the work is *connecting* them to confidence, not *recovering* them.
