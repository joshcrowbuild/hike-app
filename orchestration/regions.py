"""Region catalog — reads `regions/*.geojson` so the API can serve region + origin
config to the frontend picker (Phase 2: config-driven origins).

Distinct from `ingestion.pipeline.load_region`: that loader is CLI-bound (`sys.exit`
on a bad `--region`) and returns exactly one ingest-scoped `Region`. This one lists
every region file in the directory and degrades a malformed file to "skip it, log
it" (rule #1) rather than 500ing the endpoint that serves the picker to every
viewer over one bad file. Also independent of `ADVENTURE_REGION` (the ingest-scoped
env var): the graph holds trails from every ingested region at once, so the picker
must offer all of them, not just whichever region a batch job last ingested.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

REGIONS_DIR = Path("regions")


@dataclass(frozen=True)
class OriginInfo:
    key: str
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RegionInfo:
    region_id: str
    label: str
    origins: tuple[OriginInfo, ...]


def _parse_origins(raw: object) -> tuple[OriginInfo, ...]:
    if not isinstance(raw, list):
        return ()
    origins = []
    for o in raw:
        origins.append(
            OriginInfo(
                key=str(o["key"]), label=str(o["label"]), lat=float(o["lat"]), lon=float(o["lon"])
            )
        )
    return tuple(origins)


def list_regions(directory: Path | None = None) -> list[RegionInfo]:
    """Every region under `directory` (default `regions/`) that parses cleanly, in
    filename order. A region with no `origins` array yields an empty tuple (valid —
    a region can predate the picker); a file that fails to parse at all is logged
    and skipped so one bad file can't take down the whole catalog (rule #1)."""
    d = directory or REGIONS_DIR
    out: list[RegionInfo] = []
    for path in sorted(d.glob("*.geojson")):
        try:
            props = json.loads(path.read_text())["properties"]
            out.append(
                RegionInfo(
                    region_id=str(props["region_id"]),
                    label=str(props.get("region_label") or props["name"]),
                    origins=_parse_origins(props.get("origins")),
                )
            )
        except Exception:
            log.exception("skipping malformed region file %s", path)
    return out
