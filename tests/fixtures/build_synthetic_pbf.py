"""Generator for the committed synthetic OSM PBF fixture (Epic 036 S5, AC-5.1).

Builds `tests/fixtures/synthetic_trails.osm.pbf` with `osmium.SimpleWriter`
(BSD-2-Clause, ships with pyosmium — no GPL `osmium-tool` involved). This is
the fixture's build recipe for provenance + reproducibility, not a runtime test
dependency: `tests/test_osm_pbf_parity.py` reads the committed binary directly.
`write_pbf` is also imported by that test file to build small ad hoc PBFs for
non-parity unit tests (bbox clip, geometry resolution) without touching the
committed fixture.

Coordinate discipline (binding, see epic AC-5.1): every node uses a short-decimal
(<=5 dp) lon/lat literal, matched byte-for-byte against the equivalent Overpass
`_osm_element`-style mock built in the test file. pyosmium round-trips node
locations through libosmium's int32 1e-7 fixed-point quantization + `WKTFactory`
decimal formatting, while the Overpass path keeps full float64 — matched
short-decimal inputs keep both representations equal after that round-trip.

Regenerate the committed fixture with:
  python tests/fixtures/build_synthetic_pbf.py
"""

from __future__ import annotations

from pathlib import Path

import osmium

FIXTURE_PATH = Path(__file__).resolve().parent / "synthetic_trails.osm.pbf"

# (way_id, tags, [(node_id, lon, lat), ...])
WaySpec = tuple[int, dict[str, str], list[tuple[int, float, float]]]

# The five ways AC-5.1 requires: (a) named trail-worthy path with sac_scale +
# surface + access, (b) named track, (c) named footway (3 vertices — avoids the
# is_trail_worthy 2-vertex footway drop, which is a DIFFERENT rule than the ones
# under test here), (d) UNNAMED path (dropped), (e) residential (dropped).
WAYS: list[WaySpec] = [
    (
        101,
        {
            "highway": "path",
            "name": "Old Rag Ridge Trail",
            "sac_scale": "alpine_hiking",
            "surface": "ground",
            "access": "yes",
        },
        [(1, -78.28, 38.55), (2, -78.27, 38.56)],
    ),
    (
        102,
        {"highway": "track", "name": "Compton Gap Road"},
        [(3, -78.30, 38.60), (4, -78.29, 38.61)],
    ),
    (
        103,
        {"highway": "footway", "name": "Timber Hollow Connector"},
        [(5, -78.20, 38.50), (6, -78.21, 38.51), (7, -78.22, 38.52)],
    ),
    (
        104,
        {"highway": "path"},  # unnamed — must be dropped by both transports
        [(8, -78.10, 38.40), (9, -78.11, 38.41)],
    ),
    (
        105,
        {"highway": "residential", "name": "Random Residential Street"},
        [(10, -78.00, 38.30), (11, -78.01, 38.31)],
    ),
]


def write_pbf(path: Path, ways: list[WaySpec]) -> None:
    """Write `ways` (and their constituent nodes) to a fresh `.osm.pbf` at `path`."""
    if path.exists():
        path.unlink()
    writer = osmium.SimpleWriter(str(path))
    try:
        seen_nodes: set[int] = set()
        for _way_id, _tags, nodes in ways:
            for node_id, lon, lat in nodes:
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                writer.add_node(osmium.osm.mutable.Node(id=node_id, location=(lon, lat), tags={}))
        for way_id, tags, nodes in ways:
            writer.add_way(
                osmium.osm.mutable.Way(id=way_id, nodes=[n[0] for n in nodes], tags=tags)
            )
    finally:
        writer.close()


def build_synthetic_trails(path: Path = FIXTURE_PATH) -> None:
    write_pbf(path, WAYS)


if __name__ == "__main__":
    build_synthetic_trails()
    print(f"wrote {FIXTURE_PATH}")
