# Conflation spike

**The single highest de-risk for the lowest effort** (Stage 1 §7 / workplan
Stage 1 spike): pull the *same* few real trails from OSM and an agency source, and
see how hard merging them actually is. The result calibrates two Stage-3
decisions: the conflation match-score **thresholds**, and **adopt OSM Merge vs. a
thin custom matcher**.

## What it does

For a small set of named pilot trails inside a bbox, `conflation_spike.py`:

1. Pulls candidate ways from **OSM** (Overpass) and trail features from an
   **agency** source (USFS EDW by default — adjustable).
2. Normalizes names and, for every cross-source pair, scores **name similarity**
   (fuzzy) and **geometry agreement** (buffer-overlap + Hausdorff distance).
3. Prints a report bucketing pairs into **auto-accept / review / no-match** — the
   shape of that distribution is the answer (mostly clean auto-accepts → custom
   matcher is fine; lots of review → lean on OSM Merge).

## Running it (needs open network — blocked in the Claude sandbox)

```sh
pip install -e ".[ingestion,live]"          # shapely, thefuzz, httpx
python spikes/conflation/conflation_spike.py
```

Endpoints + the trail list + thresholds are constants at the top of the script —
edit them for your pilot area. Be polite to Overpass (low query volume).

## What to look for

- **Auto-accept rate** at name≥85 + strong geometry overlap — high = tractable.
- **The review pile** — eyeball a few: are they genuinely the same trail under
  different names/refs, or false pairs? This sets the thresholds and tells you
  whether human review volume is acceptable at pilot scale.
- **Misses** — trails present in one source but not the other (coverage gaps).

Findings get written back into `docs/decision-log.md` §3 (conflation) and the
Stage-3 doc. The matching algorithm itself lives in (and is unit-tested in)
`ingestion/conflate/match.py` — this script is just the network harness that feeds
it real data, so a run exercises the exact code Stage 3 will use.
