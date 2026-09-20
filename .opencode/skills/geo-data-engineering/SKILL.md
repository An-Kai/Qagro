---
name: geo-data-engineering
description: Acquire, clean, and pipeline geospatial vector data (OSM/Overpass/Geofabrik, GeoParquet/GeoPackage, CRS transforms, validation, batch ETL). Use when adding fields, boundaries, elevators, or any GIS dataset to Qagro. Invoke alongside remote-sensing-analysis for imagery and swe checks when code is delivered.
license: MIT
compatibility: opencode
---

# Geospatial Data Engineering

Purpose: get spatial data into a clean, validated, analysis-ready state with
a repeatable pipeline. Source: https://github.com/muend/geoai-skills
(`geo-data-engineering`, MIT, author Muhammed Enes Duran).

## Format selection

| Format | Use for | Avoid because |
|---|---|---|
| **GeoParquet** | Analysis interchange, big vector, columnar workflows | Not yet readable by some legacy desktop GIS |
| **GeoPackage** | Desktop GIS exchange, multi-layer projects | Slower than Parquet at scale; SQLite locking |
| **FlatGeobuf** | Streaming, HTTP range reads | Single layer |
| **COG** (Cloud-Optimized GeoTIFF) | All raster deliverables | — (make every GeoTIFF a COG) |
| **Zarr/NetCDF** | Multi-dimensional (time × band × y × x) | Overkill for single rasters |
| Shapefile | Only when a legacy tool demands it | 10-char columns, 2 GB cap, encoding chaos |
| CSV + WKT/lon-lat | Simple point exchange | No CRS metadata — document it explicitly |

## Acquisition playbook

- **OpenStreetMap**: small areas → `osmnx`; large extracts → Geofabrik PBF +
  `pyrosm`/`osmium`. Respect tag heterogeneity: always inspect tag value
  distributions before filtering.
- **Buildings/places at scale**: Overture Maps (GeoParquet on S3/Azure,
  query with DuckDB spatial).
- **Satellite/raster**: STAC APIs via `pystac-client` + `odc-stac` — see
  `remote-sensing-analysis` skill.
- **Boundaries**: authoritative national source first (for Qagro: map.iaqmola.kz
  pilot, needs auth); Natural Earth / GADM / geoBoundaries for global work.
- Record every acquisition: source URL, query parameters, retrieval date,
  license. Qagro keeps this in `data/fields/FIELDS_README.md` + `data_card.md`.

## CRS engineering

- Store in EPSG:4326 or source CRS; **analyze** in a projected CRS suited to
  the extent: local UTM zone (`gdf.estimate_utm_crs()`), national grid, or
  equal-area (EPSG:6933/Mollweide) for cross-region area stats.
- Never strip or overwrite a CRS to "fix" misaligned layers — diagnose which
  layer is wrong with a known landmark instead.

## Cleaning pipeline

Standard hygiene pass: drop empty/null geometries, repair invalid ones with
`make_valid`, de-duplicate, reproject, and **print an accounting report** so
silent data loss is impossible. Then: normalize text attributes, coerce dtypes
explicitly, show `value_counts()` of every categorical you will filter on.

## Scale strategies

- **Fits in RAM**: GeoPandas + Shapely 2 vectorized ops with spatial index
  (`sjoin`, `query_bulk`) — never hand-rolled O(n²) loops.
- **Bigger than RAM**: DuckDB `spatial` extension over GeoParquet, or
  `dask-geopandas`. Rasters: windowed reads, chunked xarray + dask.

## Pipeline standards

Idempotent steps with explicit inputs/outputs; checkpoint after expensive stages
in GeoParquet/GPKG; log rows in → out per stage; deterministic ordering before
writing so diffs are meaningful.

## Pitfalls checklist

CSV without declared CRS; shapefile column truncation; encoding mojibake;
mixed Polygon/MultiPolygon in one layer; antimeridian/pole reprojection breaks;
"latest" data with no recorded version/date.

---

## Qagro appendix (project-specific, takes precedence in this repo)

- Fields: `data/fields/akmola_osm_fields.geojson` — 109 real OSM polygons via
  Overpass (`landuse=farmland`, ODbL) + 6 honest demo 1×2 km rectangles with
  `demo:true` (NEVER present demo as OSM). Builder: `src/fields_osm.py`.
  Geofabrik `kazakhstan-latest.osm.pbf` is the offline fallback when Overpass
  rate-limits. Import guide for the official pilot source (map.iaqmola.kz):
  `data/fields/FIELDS_README.md`.
- Elevators: `data/fields/granaries.json` — 12 entries from Qoldau granaries-map,
  coordinates ESTIMATED via OSM, must be refined from the official ХПП registry.
  Never claim survey-grade accuracy.
- Districts: `config/districts.yaml` holds WGS84 centroids (NOT boundaries/fields).
  Area stats need a projected CRS (Kazakhstan UTM 42N) — compute `area_ha` after
  reprojection, never on raw lon/lat degrees.
- API surface: `GET /fields[?district_en=]`, `GET /granaries`, `GET /gis`
  (`src/gis_monitor.py`, Track 1: 1.1 NDVI / 1.2 boundaries+areas / 1.3 fallow /
  1.4 loss). Keep responses offline-safe with honest errors.
- License discipline: OSM data → ODbL attribution; keep provenance
  (query, date, license) next to every dataset, per data-sources rule above.
