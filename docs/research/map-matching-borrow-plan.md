# Map-Matching Borrow Plan — The History-Import Binder

**Synthesis of the map-matching borrow-or-build research spike (Epic 044 S3 / Open Decision #10)**

**Status:** `RESOLVED` — Open Decision #10 adopted 2026-07-14 with corrections (decision-log §50). PO ran an independent verification; the borrow choice and MVP-first sequencing held, with three corrections folded in below (marked **[PO-CORRECTED]**).

---

## 0. PO verification corrections (2026-07-14)

An independent PO pass verified the load-bearing claims against source and the live schema. Results:

- **Verified:** Leuven is Apache-2.0 + HMM-with-non-emitting-states; the topology premise is real (grep confirms no `:Junction`/`CONNECTS_TO`/`been_on` in `graph/schema.cypher` — the rigorous HMM genuinely needs a connectivity layer we haven't built).
- **[PO-CORRECTED] FMM license:** the table below says MIT; FMM is in fact **Apache-2.0** (verified at github.com/cyang-kth/fmm). Both permissive, so the veto/borrow calculus is unchanged — but the cell was wrong.
- **[PO-CORRECTED] Problem framing:** this is **trajectory-to-polyline similarity**, not classic road-network map-matching. Road map-matching (the HMM's purpose) reconstructs which of *many connected edges* a vehicle drove over a dense graph; our task is matching a track to *one of ~2,600 named trail polylines*. The buffer approach is therefore **the right primary method for the common single-trail case**, not a lesser stopgap.
- **[PO-CORRECTED] Confidence model:** §4's "all buffer matches capped at low confidence" is wrong for the single-named-trail case. A **directed Hausdorff / Fréchet** similarity gives a principled, topology-free confidence *gradient* — a track covering 98% of a trail's line within tolerance, same direction, is legitimately **high** confidence with no HMM. Reserve "low confidence, hedged" for partial/ambiguous coverage; reserve the Leuven HMM for the genuinely hard case (a single track spanning multiple connected trails), where topology earns its cost. Capping everything at hedged needlessly weakens the `been_on` signal the novelty filter (§48) consumes.
- **Maintenance note:** Leuven's last release is 1.1.4 (Dec 2022); FMM's last commit ~2020. Treat Leuven as a **vendored port** (Apache-2.0 permits it) and confirm it runs clean on Python 3.11 before adopting it as a live dependency.

The sections below are the original spike output; read them through the corrections above.

---

## 1. The decision framed

Epic 044 (history import) depends on mapping noisy consumer GPX tracks to the trail graph to produce `been_on` edges, unblocking Epic 006 (novelty). This is **Open Decision #10**. The two branches of the decision are:

1. **Rigorous HMM snap now:** Build the full Newson-Krumm Hidden Markov Model (HMM) up front. It provides high-accuracy matching and robust per-point probability (confidence), but requires network topology (routing graph) which we do not yet have, risking a long build cycle that keeps Epic 006 blocked.
2. **Free-floating fallback first, snap later (MVP):** Start with a simple spatial buffer (bounding-box/radius) to generate low-confidence matches. Any ambiguity falls back to preserving the trip as a free-floating Episode with geometry. This unblocks the pipeline immediately and satisfies the Phase C criteria, deferring the rigorous HMM to Phase E when the topology gate (CDP-20) provides the network.

**Cost/Benefit against Milestone 1:** The Milestone 1 exit criteria require that the loop is real—a user imports history, produces *some* `been_on` beliefs, and gets an honestly-personalized answer. A rigorous HMM now provides high yield but costs weeks of prerequisite topology work. The MVP + fallback yields fewer `been_on` edges initially but ships the pipeline end-to-end, unlocking novelty early while respecting source-or-silence (a low-confidence match is explicitly hedged).

---

## 2. Candidate comparison table

| Candidate | Algorithm | Source/Silence (Confidence) | Local-First / Python Fit | License | Network / Format Needs | Veto Risks / Notes |
|---|---|---|---|---|---|---|
| **LeuvenMapMatching** | HMM (Newson-Krumm base) | **Excellent:** Exposes full Viterbi state probabilities per match for direct confidence extraction. | Pure Python, runs offline. Perfect for `gpx_reader.py`. | Apache-2.0 | Generic graph (can build from our WKT endpoints). | None. Most transparent for confidence extraction. |
| **FMM (Fast Map Matching)** / **fastmm** | HMM + UBODT precompute | **Moderate:** Returns match geometry but obscures probabilistic confidence behind C++ core. | C++ core with Python API (`fastmm` is simpler). | MIT | Shapefile or OSM network (needs heavy precomputation). | Requires C++ build or precomputed UBODT index. |
| **Valhalla Meili** | HMM | **Moderate:** High quality, but returns HTTP JSON attributes; internal HMM probabilities are abstracted. | C++ engine. Python usage requires running a local Docker service. | MIT | Valhalla `.pbf` tiles. | **Vetoed for private pipeline:** Requires standing up a routing service container. |
| **Mappymatch** (NREL) | LCSS / Wrappers | **Poor:** Acts as a wrapper for OSRM/Valhalla; LCSS alone lacks probabilistic confidence. | Python wrapper. | BSD-3 | Graph or external service. | Often delegates to external services (violates local-first without Docker overhead). |
| **GraphHopper / OSRM** | HMM | **Poor:** Full routing engines. Confidence is opaque. | Java/C++ services. | Apache/BSD | Heavy routing graph generation. | **Vetoed for private pipeline:** Requires standing up a routing service container. |

---

## 3. Recommendation

**Verdict: PORT/BORROW `LeuvenMapMatching` (Apache-2.0), but DEFER the full HMM until the topology gate exists.**

**Why LeuvenMapMatching:** It is pure Python (satisfies constraint #5 and #3), runs fully offline against local WKT geometries, and, crucially, exposes the underlying HMM Viterbi probabilities (satisfying Rule #1 source-or-silence). It allows us to build the match confidence from the probabilistic math of the HMM itself.

**The Minimum-Viable Path (MVP) to unblock Epic 006:**
To unblock Epic 006 immediately without waiting for the full topology noding pass, we recommend an MVP spatial-buffer matcher:
1. Simplify the GPX track (Epic 031 reader tolerance).
2. Buffer the track by 30 meters and intersect with `CanonicalTrail` geometries.
3. If >85% of the track points snap to a single unambiguous trail, emit a `been_on` belief with **low confidence**.
4. If ambiguous or below threshold, invoke the **never-blocks fallback**: store as a free-floating Episode with `geom_wkt`, to be upgraded by the HMM later.

---

## 4. Confidence model

Rule #1 and Rule #7 dictate that a match is an inference. Under the full HMM (LeuvenMapMatching), confidence is calibrated from the Viterbi state probabilities:
*   **Probability > 0.90:** High confidence. ("Confirmed match.")
*   **Probability 0.60 – 0.90:** Low confidence. The threshold for the "likely *[Trail]* — low confidence, GPS sparse" hedge.
*   **Probability < 0.60 (or ambiguity):** Below threshold. The track triggers the fallback to a free-floating Episode.

Under the MVP buffer approach, **all** successful matches are capped at the "low confidence" tier (`authority_tier=3`, explicitly hedged) because spatial buffering lacks topological rigor.

---

## 5. Integration sketch

1. **Input:** `ingestion/gpx_reader.py` parses the GPX and applies tolerance cleaning (removing <2-pt segments, deduplicating).
2. **Matcher Module:** A new `ingestion/map_matcher.py` receives the cleaned polyline.
   *   *Phase C MVP:* Queries the Neo4j spatial index for bounding-box intersections, applies the Shapely buffer, and determines if a low-confidence match exists.
   *   *Phase E Full HMM:* Reads the `:Junction` / `CONNECTS_TO` topology graph (prerequisite: Layer-1 topology from `docs/research/trail-connectivity-loops.md`), instantiates the LeuvenMapMatching graph, and runs the Viterbi decoding.
3. **Write Path:** The result passes to the scoped-write layer (`graph/queries.py` `upsert_episode`). If matched, it writes the `been_on` edge with the computed confidence and `provenance:"import"`. If unmatched, it writes the Episode with `geom_wkt`.

**Prerequisite overlap:** The full HMM depends entirely on the O(n) endpoint-quantize pass described in the Trail Connectivity research (B010). Reusing that topology gate prevents rebuilding the spatial graph twice.

---

## 6. Risks & vetoes

*   **Vetoed: Valhalla Meili & GraphHopper.** These are heavy C++/Java routing engines that require standing up a service. They violate the local-first Python pipeline constraint and obscure the probabilistic confidence needed for source-or-silence.
*   **Risk: "Runs but produces zero matches."** If the MVP is too strict, all tracks fall back to free-floating Episodes. We mitigate this by tuning the spatial buffer threshold on a small test set (e.g., the owner's archive) before declaring the pipeline complete, ensuring Epic 006 is genuinely unblocked.
*   **License Risk:** LeuvenMapMatching is Apache-2.0, completely safe for our use.
