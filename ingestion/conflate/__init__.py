"""Conflation — match the same real-world trail across sources (Stage 3 §5).

OSM is the geometry spine; agency sources (USFS/NPS/USGS) match onto it. `match`
scores candidate pairs and buckets them auto-accept / review / no-match. The
matching algorithm is pure and tested on synthetic geometries here; the empirical
threshold calibration (and OSM-Merge-vs-custom) is settled when the spike runs on
real data (network-bound). See spikes/conflation/ and docs/research/
stage-3-corpus-pipeline.md §5.
"""
