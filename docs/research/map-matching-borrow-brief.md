# Map-Matching Borrow Brief — bind imported GPX tracks to corpus trails

> **How to run this:** open this repo in Antigravity and tell the agent:
> *"Read and execute the brief in `docs/research/map-matching-borrow-brief.md`. This is a research + recommendation spike — deliver a borrow plan as a PR, no product code."*
> This file is the instruction set. Everything below is addressed to the executing research agent.

---

You are a senior geospatial engineer running a **borrow-or-build research spike**, not a feature build. The output is a decision-grade recommendation the team can act on — modeled on the CoMaps borrow program (`docs/research/comaps-borrow-plan.md`): survey real OSS implementations, verify each claim against source, and hand back a ranked, licensed, portable borrow plan. Ship it as a PR that adds one research doc. **Write no product code.**

## The problem you are solving

Epic 044 (history import) imports the owner's years of GPX/FIT activity tracks and must produce `been_on` beliefs — the edge that says "this person has hiked this specific trail." That requires **map-matching**: snapping a noisy consumer-GPS track onto the specific corpus trail node(s) it actually followed. This is Open Decision #10 and the named "hard sub-problem" of B003. If it's unsolved, the import runs but produces **zero** `been_on` edges, and Epic 006 (novelty) stays blocked after Phase C "completes." Your job is to make the build decision unavoidable and well-grounded.

## Non-negotiable constraints (grade every option against these)

1. **Source-or-silence on the binding itself (CLAUDE.md Rule #1 + #7).** A match is an *inference*, never a stated fact. Every produced `been_on` must carry provenance + a **calibrated match confidence** + timestamp. A low-confidence snap must be expressible as "likely *Old Rag Loop* — low confidence, GPS sparse", never silently asserted. An option that gives a binary match with no confidence is a poor fit — say so.
2. **Never-blocks fallback is mandatory (Epic 044 AC-3.2).** When confidence is below threshold, the track is preserved as a **free-floating Episode with geometry** and matched opportunistically later. The recommended design must degrade to this, never drop the trip.
3. **Local-first / private (Rule, Epic 044 S5).** Matching runs in the local import pipeline over the private overlay; nothing leaves for a cloud service. Prefer options runnable fully offline against our own trail graph. A hosted map-matching API (e.g. a paid cloud endpoint) is disqualified for the private path — note it only as a comparison point.
4. **Portable license.** Apache-2.0 / MIT / BSD preferred; document each candidate's license and any viral risk exactly as the CoMaps plan does. A GPL core that would infect the pipeline is a veto — flag it.
5. **Python-pipeline fit.** The import is Python (see `ingestion/gpx_reader.py`, `ingestion/elevation.py`). Prefer a Python library or a clean-to-port algorithm; a C++-only engine requiring a service is a heavier lift — weigh it honestly.

## Ground yourself in our actual substrate (read before recommending)

- `docs/strategy/path-to-complete.md` — Phase C §"Map-matching is a first-class sub-task", the CDP-20 topology-integrity note, and **Open Decision #10** (verbatim the decision you're informing).
- `docs/epics/epic-044-history-import.md` — S3 (the ACs your recommendation must satisfy) + S6 (quality gates the matcher's output feeds).
- `ingestion/gpx_reader.py` — how a track is already parsed (dedupe, <2pt-drop, timestamp-derived flags): the matcher's input.
- `graph/queries.py` (search `geom_wkt` / `route_geom_wkt`) — how corpus trail geometry is stored: **per-segment `Segment.geom_wkt` + a precomputed `route_geom_wkt` per trail (WKT LineStrings)**. This is the network you snap to. Note there is no built routing graph/topology layer yet — the CDP-20 topology gate is future; say what the matcher needs that doesn't exist.
- `docs/research/trail-connectivity-loops.md` — the existing connectivity research (B010); reconcile with it, don't duplicate.
- `docs/research/comaps-borrow-plan.md` — the format + rigor bar to match.

## What to survey (at least these; add others you find)

- **Newson–Krumm (2009) HMM snap-to-network** — the rigorous reference CDP-20 names; who implements it in Python.
- **Valhalla Meili** (map-matching mode) — algorithm, license, Python-invocability, service-vs-lib reality.
- **FMM (Fast Map Matching)** — HMM + precomputed, Python bindings, license, network-format needs.
- **leuven.mapmatching** / **mappymatch** (or current equivalents) — pure-Python HMM matchers, maturity, license.
- Any GraphHopper / OSRM matching mode — for completeness, noting the service constraint against constraint #3.

For each: algorithm summary, exactly how the match confidence comes out (this is load-bearing for Rule #1 — an HMM's per-point probability is a gift here; say how to surface it), license, Python/offline fit, what network format it demands vs. our WKT-LineString-per-segment reality (and the conversion cost), maturity/maintenance, and the veto risks.

## Deliverable — one PR adding `docs/research/map-matching-borrow-plan.md`

Add it to the `docs/research/README.md` index (keep `make docs-lint` green). Contents, in order:
1. **The decision framed** — restate Open Decision #10 and the two branches (rigorous HMM snap now vs. free-floating fallback first, snap later) with the cost/benefit of each against the Milestone-1 exit criteria.
2. **Candidate comparison table** — the surveyed options against the 5 constraints + confidence-extraction + network-conversion cost, each cell adversarially verified against source/docs (cite).
3. **Recommendation** — borrow / port / defer, with the specific library or algorithm, the license, and *why* it best satisfies source-or-silence + never-blocks + local-first. Include the honest **minimum-viable path**: what's the smallest thing that produces *some* confidence-carrying `been_on` edges without the full HMM, so Epic 006 can unblock early.
4. **Confidence model** — concretely how a raw matcher score becomes our calibrated `been_on` confidence (freshness/authority/corroboration framing per Rule #7), including where the "likely X — low confidence" threshold sits and how the fallback boundary is chosen.
5. **Integration sketch** — where it plugs into `ingestion/gpx_reader.py` → a new matcher module → the scoped `been_on` write; what corpus-side prep (a routable topology from the WKT segments?) is prerequisite, and whether that overlaps the CDP-20 topology gate (reuse, don't rebuild).
6. **Risks & vetoes** — licenses, the "runs but produces zero matches" failure mode and how the recommendation prevents it, and any option explicitly rejected with the reason.

Mark the PR **"FOR PO REVIEW — borrow decision, no product code."** Follow `AGENTS.md` PR hygiene; small commits; `make docs-lint` green.

Bar: reading your doc, the PO can pick a branch of Open Decision #10 and a Builder can start Epic 044 S3 the next day without re-researching anything.
