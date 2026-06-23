# Live API Verification — 2026-06-23

Verified against real endpoints on 2026-06-23 from terminal.

---

## USGS Water Data OGC API

**Base:** `https://api.waterdata.usgs.gov/ogcapi/v0/`

### Monitoring-locations collection

```
GET /collections/monitoring-locations/items?bbox={w,s,e,n}&limit=50&f=json
```

**Status:** 200 ✓  
**Confirmed field names (from live response):**

| Field | Value (example) | Notes |
|---|---|---|
| `monitoring_location_name` | `"EAST BRANCH NAKED CREEK AT PARK NEAR JOLLIETT, VA"` | Use this for display |
| `monitoring_location_number` | `"01629113"` | Site ID for second call |
| `id` | `"USGS-01629113"` | Alternative feature ID |
| `agency_code` | `"USGS"` | |
| `site_type` | `"Stream"` | |
| `geometry.type` | `"Point"` | |

**Previous code (wrong):** used `props.get("name")` and `props.get("id")` — neither existed.  
**Fix:** updated to `monitoring_location_name` and `monitoring_location_number`.

### Discharge (second call)

The OGC `latest-continuous` and `latest-daily` collections returned 400 for
the tested query parameters (the correct filter params are not yet documented).
**Bridge approach (until OGC discharge endpoint is clarified):** use legacy
`waterservices.usgs.gov/nwis/iv/?format=json&sites={site_id}&parameterCd=00060`.

**Legacy endpoint confirmed working:** returns `value.timeSeries[0].values[0].value[-1].value`
as the latest discharge reading in cfs.

**Migration target:** Q1 2027 (per Stage 1 §27 decision). Update to OGC when
`latest-continuous/items?monitoringLocationNumber={id}&parameterCode=00060` is confirmed.

---

## NWS api.weather.gov

```
GET /points/{lat},{lon}
→ response.properties.forecast  (forecast URL, e.g. /gridpoints/LWX/55,50/forecast)
GET {forecast_url}
→ response.properties.periods[0]
```

**Status:** 200 ✓ (both hops)  
**Confirmed field names (from live response):**

| Field | Value (example) | Notes |
|---|---|---|
| `number` | `1` | Period number |
| `name` | `"Tonight"` | Period name |
| `temperature` | `61` | Integer |
| `temperatureUnit` | `"F"` | |
| `shortForecast` | `"Mostly Clear"` | |
| `windSpeed` | `"2 to 7 mph"` | |
| `startTime` | `"2026-06-23T18:00:00-04:00"` | |

**Verdict:** `nws.py` field names were correct. No changes needed.  
**User-Agent format:** `adventure-planner/0.1 joshcrow1193@gmail.com` — accepted ✓

---

## USFS EDW ArcGIS REST

**URL tested:** `https://apps.fs.usda.gov/arcgis/rest/services/EDW/EDW_TrailNFSTrails_01/MapServer/0/query`  
**Status:** 403 Forbidden  
**Alternate `arcx` subdomain:** Service not found (404 in body)

**Conclusion:** The USFS EDW ArcGIS FeatureServer is not publicly accessible without
USFS network credentials. This is a known limitation of the USFS data access policy.

**Workaround implemented:** `ingestion/fetch/usfs.py` switched to file-based loading.

**Bulk download (230 MB, publicly available):**
```
curl -L -o data/usfs/S_USA.TrailNFS_Publish.zip \
  https://data.fs.usda.gov/geodata/edw/edw_resources/shp/S_USA.TrailNFS_Publish.zip
cd data/usfs && unzip S_USA.TrailNFS_Publish.zip
ogr2ogr -f GeoJSON trails.geojson S_USA.TrailNFS_Publish.shp -t_srs EPSG:4326
```

**Expected field names (from USFS EDW schema documentation):**
- `TRAIL_NAME` — trail name (primary)
- `TRAIL_NO` — trail number (reference key, e.g. "1", "440")
- `GIS_MILES` — length in miles
- `TRAIL_USE` — allowed use codes (e.g. "HIKING", "HORSES")

---

## NPS Trails ArcGIS

**URL:** `https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/NPS_Trails_Public/FeatureServer/0/query`  
**Status:** Not verified in this session (URL from public NPS open data catalog; `nps.py` marks it pending live confirm)  
**Field names (expected from NPS layer schema):**
- `TRLNAME` — trail name
- `OBJECTID` — feature id
- `TRLUSE` — allowed use

**Action:** Verify on first run; the fetcher falls back gracefully to `[]` on non-200.

---

## Summary of adapter changes

| File | Change |
|---|---|
| `orchestration/adapters/usgs_water.py` | Fixed field names; added discharge via legacy WaterServices |
| `orchestration/adapters/nws.py` | No changes (confirmed correct) |
| `ingestion/fetch/usfs.py` | Switched from ArcGIS REST to local file (403 blocked) |
