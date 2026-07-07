"""Runner-level tests for ingestion.ingest_water (the Epic 035 wiring).

The three primitives are already covered by tests/test_osm_water.py; these
pin the runner's own behavior: bbox parsing, dry-run makes no graph import,
and the fetched → loaded flow-through with the water_id/iv convention.
"""

from __future__ import annotations

from unittest import mock

from ingestion.fetch.osm import WaterSource
from ingestion.ingest_water import _load_region_bbox, ingest_water

_SPRING = WaterSource(
    osm_id="node/42",
    water_type="spring",
    name="Lewis Spring",
    lat=38.55,
    lon=-78.28,
    seasonal="yes",
)


def test_load_region_bbox_reads_geojson_order() -> None:
    # regions/*.geojson store [west, south, east, north]; fetch wants (s, w, n, e).
    south, west, north, east = _load_region_bbox("shenandoah-gwj")
    assert south < north and west < east
    assert -90 <= south <= 90 and -180 <= west <= 180


def test_dry_run_fetches_but_never_touches_the_graph() -> None:
    with (
        mock.patch("ingestion.ingest_water.fetch_water", return_value=[_SPRING]) as fetched,
        mock.patch("graph.client.GraphClient") as gc,
    ):
        counts = ingest_water("shenandoah-gwj", dry_run=True)
    assert fetched.called
    assert counts == {"fetched": 1, "loaded": 0}
    gc.assert_not_called()


def test_loads_each_source_with_water_id_and_region_iv() -> None:
    calls: list[tuple] = []

    def fake_load(runner, water_id, **kw):  # noqa: ANN001
        calls.append((water_id, kw))

    session = mock.MagicMock()
    driver = mock.MagicMock()
    driver.session.return_value.__enter__ = mock.Mock(return_value=session)
    driver.session.return_value.__exit__ = mock.Mock(return_value=False)

    with (
        mock.patch("ingestion.ingest_water.fetch_water", return_value=[_SPRING]),
        mock.patch("graph.load.load_water_source", side_effect=fake_load),
        mock.patch("graph.client.GraphClient") as gc_cls,
    ):
        gc_cls.return_value._ensure_driver.return_value = driver
        counts = ingest_water("shenandoah-gwj", dry_run=False)

    assert counts == {"fetched": 1, "loaded": 1}
    assert calls and calls[0][0] == "water:osm:node/42"
    kw = calls[0][1]
    assert kw["water_type"] == "spring"
    assert kw["seasonal"] == "yes"
    assert kw["ingest_version"] == "shenandoah-gwj"
