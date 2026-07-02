"""Ad-hoc region trail-count probe (safety check for a new-region ingest).

Prints CanonicalTrail counts grouped by which region an ingest_version belongs
to, plus a sample of names for the region passed as argv[1]. Read-only.
"""

from __future__ import annotations

import sys

from graph.client import GraphClient
from orchestration.config import Settings


def main() -> None:
    focus = sys.argv[1] if len(sys.argv) > 1 else None
    s = Settings.from_env()
    gc = GraphClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    try:
        with gc._ensure_driver().session() as session:
            rows = session.run(
                "MATCH (t:CanonicalTrail) RETURN t.ingest_version AS iv, count(*) AS n ORDER BY iv"
            ).data()
            print("=== CanonicalTrail counts by ingest_version ===")
            total = 0
            for r in rows:
                print(f"  {r['iv']!r}: {r['n']}")
                total += r["n"]
            print(f"  TOTAL: {total}")
            if focus:
                names = session.run(
                    "MATCH (t:CanonicalTrail) "
                    "WHERE t.ingest_version = $rid OR t.ingest_version STARTS WITH $pref "
                    "RETURN t.name AS name ORDER BY name",
                    rid=focus,
                    pref=f"{focus}-",
                ).data()
                print(f"\n=== {focus}: {len(names)} trails ===")
                for r in names:
                    print(f"  {r['name']}")
    finally:
        gc.close()


if __name__ == "__main__":
    main()
