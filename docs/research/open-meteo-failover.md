# Open-Meteo — corroboration refusal + availability-failover spec

*A code-grounded spike answering the charter question "can Open-Meteo push live-weather corroboration above 1?" — and, having refused that, fully specifying the honest remainder: an availability-failover adapter and a spread-as-disclosure feature, both gated behind a commercial-license blocker.*

**Last verified:** 2026-07-07 · **Owner:** Epic 037 (spike) · **Status:** `ACTIVE` (resolves the Open-Meteo adoption question; downstream build BLOCKED — see §4)

> Method: read the real adapters/confidence/engine/registry/config on `main` and traced the exact provenance chain from `api.weather.gov` through to Open-Meteo's US model catalog. Findings are grounded in `file:line`; the license terms are quoted from the primary sources listed at the bottom.

## Verdict

**Refuse the corroboration premise; spec the failover.** Open-Meteo's US default forecast is not a second independent origin from NWS — it is the same National Blend of Models (NBM) read twice. Counting it as `corroboration=2` is the exact feed-counting sin vision.md principle 9 forbids. The honest salvageable value is narrower: a **disclosed, non-authoritative, corroboration-pinned-at-1 failover adapter** that closes C6 ("NWS outage → no weather, no swap path"), plus an optional **multi-model spread-as-disclosure** that only ever widens the hedge. Both are fully specified below as future BACKLOG builds — **neither is built in this epic** — and both are blocked on a commercial-license PO decision (§4).

---

## 1. The echo sin

The chartered premise was: adopt Open-Meteo as a second live-weather origin so weather's corroboration axis finally reads `>1`. Tracing both sides of the provenance chain shows this fails the independence governor.

**Our NWS side.** `orchestration/adapters/nws.py:47-49` calls `api.weather.gov/points/{lat},{lon}`, which returns a `forecast` URL; `nws.py:61-65` fetches that URL and takes its first period. Per the NWS API docs (weather-gov.github.io/api/gridpoints), this is the **gridpoint forecast**, which serves **NDFD** (the National Digital Forecast Database). NOAA's own description of NDFD's input, the **NBM (National Blend of Models)**, is that it is *"a blend of both NWS and non-NWS numerical weather prediction model data and post-processed guidance … the starting point for NDFD"* (vlab.noaa.gov/web/mdl/nbm). So the fact NWS already returns is a human-edited blend of **GFS + HRRR + ECMWF + GEM** — not a single raw model run.

**Open-Meteo's US side.** For US coordinates, Open-Meteo's `best_match` and every explicit high-resolution US model it lists (`ncep_gfs_*`, `ncep_hrrr_usl`, and — the load-bearing one — **`ncep_nbm_usl`**) are NOAA products (open-meteo.com/en/docs). `ncep_nbm_usl` **is the exact NBM** that feeds NWS's own gridpoint forecast. Calling Open-Meteo's default US endpoint therefore re-serves the same NOAA numerical guidance NWS is already built on.

**Why counting it is feed-counting (forbidden).** vision.md principle 9 (`docs/vision.md:74`) states: *"Corroboration is the engine, but independence is the governor — count distinct **origin** nodes, not feeds, and never re-ingest our own output as external evidence."* Reading the NBM through NWS and reading the NBM through Open-Meteo are two readings of **one origin**. Counting them as `corroboration=2` would inflate confidence on the single most safety-critical overlay in the product on a false distinct-origin claim — precisely the Curveball/Iraq circular-reporting failure vision.md cites as the cautionary case for this principle.

**Even pinned to a non-NOAA model, it still fails.** Open-Meteo also serves genuinely non-NOAA global models over US coordinates — ECMWF IFS (0.25°/9km), DWD ICON-Global (11km), GEM (Canada), Météo-France ARPEGE (open-meteo.com/en/docs/ecmwf-api). Pinning explicitly to one of these does not rescue the corroboration claim, for two independent reasons:

1. **ECMWF and GEM are already inside the NBM.** NWS's own blend ingests ECMWF and GEM guidance, so a "pinned ECMWF" reading via Open-Meteo *partially echoes* what NWS has already folded in — it is not clean independence, just a smaller echo.
2. **It is model-vs-model, not observation-vs-observation.** `corroboration=2` for a forecast would mean "two models agree," but every numerical weather model — NBM's constituents and ECMWF/ICON/GEM alike — is initialized from the **same WMO GTS observation substrate** (the same radiosondes, satellite radiances, and buoys). Two models agreeing on a shared observation base is categorically weaker evidence than the corpus's own `SAME_AS` corroboration, where NPS and USFS **independently surveyed the same trail on the ground** — two real, physically distinct attestations of a structural fact. Model agreement over a shared observation feed is not what this product means by corroboration.

**Conclusion — correct-by-construction, not a gap.** `orchestration/engine.py:341` (`for_fact(fact, corroboration=1)`) pins every live condition fact at `corroboration=1` by construction: the Verifier is break-on-first-success per `ConditionKind`, so there is structurally one live weather fact per query. This spike confirms that pin is **honest, not a shortfall to close**. The only place `corroboration>1` should ever originate is the corpus layer's distinct-origin count — `orchestration/engine.py:204-230` (`_corpus_corroboration`), which reads the `SAME_AS` cluster's real, independently-surveyed source count. Open-Meteo does not change this. **No code in this repo should ever route a live-weather reading, from any provider, into `_corpus_corroboration` or bump `corroboration` above 1 on its account.**

---

## 2. The honest remainder — spec, not build

Refusing the corroboration premise does not refuse Open-Meteo outright. Two narrower, invariant-respecting uses survive scrutiny. Both are specified here as future one-file/one-config-line builds; **neither ships in this epic** (see the scope fence in the epic file).

### 2.1 Availability-failover adapter (closes C6)

SS-11 (`docs/research/source-seams-corpus-and-live.md:223`) already named an illustrative, license-pending weather fallback slot; SS-6 (`source-seams-corpus-and-live.md:218`) already ships the kind-keyed primary→fallback registry that would carry it. An `OpenMeteoAdapter` as the **secondary** `weather` probe closes C6 ("NWS outage = no weather, no swap path") without touching corroboration at all — it is pure availability, not evidence-stacking.

Modeled directly on `orchestration/adapters/nws.py:98-134`:

| Property | NWS (`nws.py`) | Open-Meteo failover (spec) |
|---|---|---|
| `kind` | `ConditionKind.weather` | `ConditionKind.weather` (same kind — the registry treats this as fallback, not a second kind) |
| `is_keyless` | `True` | `True` (free-tier keyless, subject to the license gate in §4) |
| `supports_region` (`LiveCapabilities.supports_region`, `base.py:90`) | `frozenset({"US"})` (`nws.py:122`) | **global** — Open-Meteo serves worldwide model coverage; hard-coding `{"US"}` here would be a regression from what the source actually offers, and the whole point of a fallback is to cover cases (including future non-US regions) NWS can't |
| `ttl_seconds` | `3600` (`nws.py:106`) | `3600` — matches NWS's cadence so the fallback doesn't over- or under-poll relative to the primary it's standing in for |
| `confidence_inputs["authority"]` | `"tier1_gov"` (`nws.py:94`) | **`"tier2"` or `"derived"`, never `"tier1_gov"`** — per `orchestration/confidence.py:22-32`, `tier1_gov=1.0` vs. `tier2=0.6` / `derived=0.7`. A failover reading must present as honestly less authoritative than the primary government source it's standing in for, not equal to it |
| `disclosures` (`base.py:42`) | *(none needed; primary tier1 source)* | Must carry an entry naming it a **non-authoritative secondary/failover source** — the `disclosures` tuple already exists on `VerifiedFact` for exactly this |

**Wiring (spec only — not performed here):** exactly one entry in `ADAPTER_FACTORIES` (`orchestration/adapters/registry.py:42-50`, e.g. `"open_meteo": OpenMeteoAdapter`) plus one position in `ADVENTURE_LIVE_ADAPTERS` (`orchestration/config.py:89`, parsed at `config.py:182`) placed **after** `nws` — `probes_for` (`registry.py:78-87`) orders primary→fallback strictly by list position, so "after nws" is sufficient to make it the fallback with zero other code change. This is the seam's designed proof: a new source is one adapter file + one config line, zero downstream change.

**Corroboration discipline (hard requirement):** the failover reading MUST be constructed with `corroboration=1`, exactly like every other live fact at `engine.py:338-341` — it is never eligible to route through `_corpus_corroboration`. Two providers answering the `weather` kind is redundancy for availability, not a second attestation for confidence. A future implementer who wires this adapter and is tempted to bump corroboration because "now there are two weather sources" has re-committed the echo sin this doc refuses in §1.

### 2.2 Multi-model spread as an uncertainty disclosure (widens hedge, never a count)

The genuinely novel, invariant-aligned idea: when NWS(NBM) and a pinned non-NOAA model (e.g. ECMWF-via-Open-Meteo) **disagree** on a forecast value (the brief's example: afternoon-storm probability-of-precipitation), that disagreement is real signal — just not corroboration.

- **Where it attaches:** the `VerifiedFact.disclosures` tuple (`base.py:42`) — the same field the failover adapter uses in §2.1 — never the `corroboration=` argument of `for_fact`/`compute` (`orchestration/confidence.py:52-79`).
- **The asymmetry (binding):** **agreement between models never inflates confidence or corroboration** — two models sharing one observation substrate agreeing tells us nothing beyond what NWS alone already says. **Disagreement only ever lowers presentation** (widens the hedge — moves `presentation` from `stated` toward `hedged`/`flagged`, per `Confidence.presentation` at `confidence.py:44-49`). This is the exact **inverse** of the echo sin: instead of two readings of one thing inflating confidence, two independent forecasts of the same event honestly *lower* it when they diverge. It is also a clean fit for pillar 4's two-axis discipline (never fuse the quality axis and the ranking axis) and pillar 1's honesty primitives (source-or-silence; an inference never poses as a stated fact).
- **Status:** PO-adjudication-pending, not built this epic. It depends on the exact same license clearance as §2.1 (a pinned ECMWF/ICON/GEM call is still an Open-Meteo API call).

---

## 3. Integration seam (verified against the current repo, unchanged by this epic)

- **Contract.** `orchestration/adapters/base.py` — `VerifiedFact` (`base.py:33-42`, `disclosures` tuple at `:42`), `LiveAdapter` ABC (`base.py:108-145`, `capabilities()`/`probe()`/`health()`/`from_config()`), `health_from_status` (`base.py:93-105`, already maps `429 → rate_limited`, so Open-Meteo's documented keyless rate limits are handled by the existing backoff with zero new code).
- **Registry.** `ADAPTER_FACTORIES` (`registry.py:42-50`) is the single name→class map; `enabled_adapters` (`registry.py:53-68`) self-drops any adapter whose `from_config` returns `None` (absent credential — the deliberate `| None` self-drop asymmetry, SS-10); `probes_for` (`registry.py:78-87`) groups by `kind` and orders primary→fallback by list position, gated by `supports_region`.
- **Corroboration path (proven untouched by this epic — see AC-5.1 in the epic file).** `engine.py:341` (`for_fact(fact, corroboration=1)`) for every live fact; `_corpus_corroboration` (`engine.py:204-230`) reads `corroboration` only from the corpus `SAME_AS` cluster via `queries.trail_source_corroboration`. Nothing in this spec touches either.
- **Config (proven untouched).** `nws_user_agent` (`config.py:79`), `live_adapters` (`config.py:89`), `ADVENTURE_LIVE_ADAPTERS` parsing (`config.py:182`) are read-only references here, not edits.

---

## 4. License gate (binding — the reason this is a spike, not a build)

Screened per the §18 open-data/license discipline SS-11 named as a precondition.

- **Data license: CC-BY 4.0** (open-meteo.com/en/terms). Attribution required — already satisfied by the existing `VerifiedFact.source` stamping pattern every adapter uses. No blocker here.
- **Server source code: AGPLv3.** This only bites a project that **self-hosts and redistributes** Open-Meteo's server. This spec calls the **hosted HTTP API** exclusively — AGPL never touches this repo. **No Open-Meteo source is or will be vendored/ported/cloned into this repo; there is no `repos/open-meteo` checkout in this spike.**
- **BLOCKER — commercial use.** Open-Meteo's free tier is explicitly **non-commercial only** ("You may only use the free API services for non-commercial purposes," open-meteo.com/en/terms), keyless, rate-limited to **600/min · 5,000/hour · 10,000/day · 300,000/month**. A shipping product with auth and households is a commercial use under those terms. **A real build requires either a paid Open-Meteo subscription (Standard/Pro/Enterprise) or a self-hosted instance of their (AGPLv3) server** — the self-host path would need its own separate hosting decision and would still call it over HTTP, never vendoring the AGPL code into this repo.

**This is a PO decision, not a lane default**, and is the precise reason Epic 037 is scoped as a spike: the chartered reason to adopt (corroboration) is refused on invariant grounds (§1), and the salvageable value (§2) cannot be built until this license question is adjudicated. See the epic file's "Build status" section for the binding statement.

---

## 5. Risks

- **Echo sin recurrence (highest).** Any future contributor who wires the failover adapter (§2.1) and is tempted to "count the second weather feed" reintroduces false confidence on the most safety-critical overlay in the product. Mitigated by the hard-coded `corroboration=1` requirement in §2.1 and the AC-5.1 `git diff` proof in the epic file.
- **Commercial license.** Shipping this on the free tier for an authenticated, multi-household product violates Open-Meteo's ToS outright — not a gray area.
- **Coarse independence even where genuine.** The one truly non-NOAA, high-value comparison model (DWD ICON-Global / ECMWF) runs at 9-11km resolution — coarse for a single mountain trailhead point. A spread-as-disclosure signal (§2.2) is directional guidance, not a precise divergence measurement.
- **Model-ID churn.** Open-Meteo's named model IDs (`ncep_*`, the ECMWF-API model set) are a live product surface and can change. Any future implementation must pin explicit model IDs rather than relying on `best_match`, and should not assume today's `ncep_nbm_usl` naming is permanent.

---

## Sources

open-meteo.com/en/terms · open-meteo.com/en/docs · open-meteo.com/en/docs/ecmwf-api · vlab.noaa.gov/web/mdl/nbm · weather-gov.github.io/api/gridpoints
