# regions/

Polygon boundaries that scope ingestion (Stage 3 — everything clips to a region
polygon, not a bbox). Each region is an independent unit; expansion = add another
polygon and re-run.

**Pilot region (`shenandoah-gwj`):** the union of **Shenandoah National Park**
(NPS boundary) and **George Washington & Jefferson National Forests** (PAD-US /
USFS boundary), buffered ~2 km so trails crossing the edge aren't truncated.

The boundary `*.geojson` is produced/committed when the Stage-3 pipeline is built
(small enough to track here; bulk corpus extracts stay under the git-ignored
`data/`). See `docs/research/stage-3-corpus-pipeline.md` §2.
