#!/usr/bin/env python3
"""Apply graph/schema.cypher to ANY Neo4j (local bolt **or** cloud Aura).

The `make schema` target execs `cypher-shell` *inside the local docker
container*, so it can only reach a local Neo4j — it ignores `NEO4J_URI` and
cannot target Aura. This script applies the same schema to whatever
`NEO4J_URI` points at (so it works for `neo4j+s://…databases.neo4j.io` too),
using the Python driver. Each statement runs in its own implicit transaction
(DDL and data writes may not share a transaction on Neo4j 5.x/Aura).

Idempotent: the schema is `MERGE` / `CREATE … IF NOT EXISTS` throughout, so a
re-run is a no-op. Reads NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD from the
environment, loading `.env` first if present.

Usage:
  python scripts/apply_schema.py            # apply to $NEO4J_URI
  python scripts/apply_schema.py --dry-run  # parse + list statements, no connect
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "graph" / "schema.cypher"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file (only keys not already set)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def split_statements(cypher: str) -> list[str]:
    """Split a multi-statement Cypher file on top-level `;`, honoring string
    literals (' and ") and comments (// line, /* */ block) so a `;` inside a
    string or comment never splits a statement."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(cypher)
    in_s = in_d = in_line = in_block = False
    while i < n:
        c = cypher[i]
        nxt = cypher[i + 1] if i + 1 < n else ""
        if in_line:
            buf.append(c)
            if c == "\n":
                in_line = False
        elif in_block:
            buf.append(c)
            if c == "*" and nxt == "/":
                buf.append(nxt)
                i += 1
                in_block = False
        elif in_s:
            buf.append(c)
            if c == "\\" and nxt:  # escaped char inside '...'
                buf.append(nxt)
                i += 1
            elif c == "'":
                in_s = False
        elif in_d:
            buf.append(c)
            if c == "\\" and nxt:  # escaped char inside "..."
                buf.append(nxt)
                i += 1
            elif c == '"':
                in_d = False
        else:
            if c == "/" and nxt == "/":
                in_line = True
                buf.append(c)
            elif c == "/" and nxt == "*":
                in_block = True
                buf.append(c)
            elif c == "'":
                in_s = True
                buf.append(c)
            elif c == '"':
                in_d = True
                buf.append(c)
            elif c == ";":
                stmt = _strip(("".join(buf)))
                if stmt:
                    out.append(stmt)
                buf = []
            else:
                buf.append(c)
        i += 1
    tail = _strip("".join(buf))
    if tail:
        out.append(tail)
    return out


def _strip(stmt: str) -> str:
    """Drop // line-comments and surrounding whitespace; keep the executable body."""
    keep: list[str] = []
    for line in stmt.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        # trailing inline // comment (outside strings — schema has none, kept simple)
        keep.append(line)
    return "\n".join(keep).strip()


def _summary(stmt: str) -> str:
    one = " ".join(stmt.split())
    return one[:72] + ("…" if len(one) > 72 else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply graph/schema.cypher to $NEO4J_URI")
    ap.add_argument(
        "--dry-run", action="store_true", help="parse + list statements; do not connect"
    )
    args = ap.parse_args()

    load_dotenv(ENV_PATH)
    statements = split_statements(SCHEMA_PATH.read_text())
    print(f"Parsed {len(statements)} statements from {SCHEMA_PATH}")

    if args.dry_run:
        for idx, st in enumerate(statements, 1):
            print(f"  [{idx:>2}] {_summary(st)}")
        print("\nDRY RUN — nothing applied.")
        return 0

    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "")
    if not uri or not pw:
        print("ERROR: NEO4J_URI and NEO4J_PASSWORD must be set (.env or env).", file=sys.stderr)
        return 2
    scheme = uri.split(":", 1)[0]
    print(f"Target: {scheme}://…  user={user}")

    # Cloud Aura (neo4j+s://) presents a cert the default SSL context may not chain
    # to a trusted root; point it at certifi so strict TLS verification succeeds.
    # Harmless for a local bolt:// instance. Set before the driver builds its context.
    if not os.environ.get("SSL_CERT_FILE"):
        try:
            import certifi

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            pass

    import neo4j

    driver = neo4j.GraphDatabase.driver(uri, auth=(user, pw))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # fail loud — no point applying half a schema
        print(
            f"ERROR: cannot reach Neo4j at {scheme}://… — {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "  → If this is Aura Free, resume the instance in the console first.", file=sys.stderr
        )
        driver.close()
        return 3

    applied = 0
    try:
        for idx, st in enumerate(statements, 1):
            try:
                driver.execute_query(st)  # own implicit tx per statement
                applied += 1
                print(f"  ✓ [{idx:>2}/{len(statements)}] {_summary(st)}")
            except Exception as exc:
                print(f"  ✗ [{idx:>2}/{len(statements)}] {_summary(st)}", file=sys.stderr)
                print(f"      {type(exc).__name__}: {exc}", file=sys.stderr)
                return 4
    finally:
        driver.close()

    print(f"\nApplied {applied}/{len(statements)} statements to {scheme}://… (idempotent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
