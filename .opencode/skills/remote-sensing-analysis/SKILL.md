---
name: remote-sensing-analysis
description: Turn satellite/aerial imagery into defensible products (STAC search, Sentinel-2 L2A discipline, cloud masking, NDVI/spectral indices, compositing, SAR basics, spatial validation). Use for Qagro NDVI monitoring, fallow/loss detection, and any Sentinel-2 work. Routes neural methods to geo-deep-learning patterns and archive-scale execution to Earth Engine.
license: MIT
compatibility: opencode
---

# Remote Sensing Analysis

Purpose: turn raw Earth observation imagery into defensible analytical
products. Source: https://github.com/muend/geoai-skills
(`remote-sensing-analysis`, MIT, author Muhammed Enes Duran).

## Data access (STAC-first)

Search via STAC APIs rather than per-provider portals:

```python
import pystac_client
import odc.stac

catalog = pystac_client.Client.open("https://earth-search.aws.element84.com/v1")
items = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[27.0, 38.3, 27.4, 38.6],
    datetime="2025-05-01/2025-09-30",
    query={"eo:cloud_cover": {"lt": 20}},
).item_collection()
ds = odc.stac.load(items, bands=["red", "nir", "scl"], resolution=10, chunks={})
```

Key collections: `sentinel-2-l2a` (10 m optical, surface reflectance),
`landsat-c2-l2` (30 m, 1982→), `sentinel-1-grd` (SAR, weather-independent).
Microsoft Planetary Computer mirrors most (needs `planetary_computer` signing).
Record collection + item IDs + search parameters for reproducibility.

## Processing-level discipline

| Level | Meaning | Analysis-ready? |
|---|---|---|
| L1C / L1TP | Top-of-atmosphere (TOA) | Indices OK-ish; cross-date comparison risky |
| **L2A / L2SP** | Surface reflectance (BOA) | Yes — default choice |
| GRD (SAR) | Detected amplitude | Needs terrain correction + speckle filter |

Always state which level you used. Never mix TOA and BOA scenes in one
composite or time series. Landsat Collection 2 L2 needs scale factors applied
(`reflectance = DN * 0.0000275 - 0.2`).

### The Sentinel-2 baseline discontinuity (25 January 2022, Baseline 04.00)

A constant `BOA_ADD_OFFSET` (−1000) was added to L2A DNs so negative surface
reflectance can be encoded. Two L2A scenes on opposite sides of that date have
DNs 1000 apart — differencing them reads as fake change.

- Read `BOA_ADD_OFFSET` and `QUANTIFICATION_VALUE` from each product's metadata;
  convert with `reflectance = (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE`.
- Record the **processing baseline of every scene**, not just the product level.
- **Do not correct twice**: harmonised collections (Earth Engine
  `COPERNICUS/S2_SR_HARMONIZED`, some commercial mirrors) already shifted
  post-baseline data back. If baseline is undocumented, say the comparison is
  not defensible instead of assuming.

## Cloud and quality masking — before anything else

- Sentinel-2: mask with SCL (drop 3 shadow, 8-9 clouds, 10 cirrus, 11 snow;
  keep 4 vegetation, 5 bare, 6 water, 7 unclassified with care).
- Landsat C2: decode `QA_PIXEL` bitfields. Report % valid pixels per scene;
  below ~60% valid usually deserves exclusion.
- For gap-free products, build seasonal median composites, not single scenes.

## Spectral indices

Compute on surface reflectance, guard division by zero, name bands explicitly
(NIR is B8 on Sentinel-2, B5 on Landsat 8/9):

```python
import numpy as np
import xarray as xr

def normalized_diff(a: xr.DataArray, b: xr.DataArray) -> xr.DataArray:
    return xr.where(a + b == 0, np.nan, (a - b) / (a + b))

ndvi = normalized_diff(ds.nir, ds.red)
```

Guardrails: NDVI thresholds are scene/season-dependent — never hardcode
"NDVI > 0.3 = vegetation" without checking the histogram. Shadows mimic water
in NDWI — cross-check indices against each other and true-color.

## Validation

Validate with a **spatially independent** test set; report per-class F1/IoU plus
confusion matrix (overall accuracy alone hides rare-class failure). Map errors
spatially — misclassification plots reveal terrain-shadow / urban-bare confusion.

## Pitfalls checklist

Mixed TOA/BOA composites; S2 baseline change ignored or double-applied;
20 m→10 m band mixing (B11/B12 natively 20 m); indices on raw DNs; SAR median
in linear units (use dB); train/test pixels from same field (leakage); nodata
edges becoming zeros after reprojection.

---

## Qagro appendix (project-specific, takes precedence in this repo)

- Pipeline: `src/sentinel_ndvi.py` (PC STAC scene search, no key, best-effort,
  Esil/Zerenda demo fields, Jun–Aug 2024–2025, cloud<20%) →
  `data/ndvi/ndvi_timeseries.json` (`{district, date, ndvi_mean|None, scene_id,
  status}`). Honest states: `ndvi_mean` number in [-1,1] (currently 41 real via
  PC TiTiler, Jun+Jul) or `None` + `status: "MISSING"` / `"listed ..."` /
  `"error: ..."` (40 missing — NEVER invent numbers to fill gaps).
- Model contract: `src/features_ndvi.py` does an OPTIONAL join — `ndvi_max`
  enters only with full real-NDVI coverage and zero NaN, else skipped. The yield
  model must always work without NDVI (see `agro-analytics` skill).
- Manual pilot path: Copernicus Browser (https://browser.dataspace.copernicus.eu/)
  / Sentinel Hub for B04/B08 download, `NDVI=(B08−B04)/(B08+B04)` by hand
  (`rasterio` optional, commented in `requirements.txt`), drop seasonal max as
  `ndvi_mean` into `ndvi_timeseries.json` — picked up automatically.
- Cross-check: LandsatLook/USGS for verification; Track 1 mapping:
  1.1 NDVI monitoring, 1.3 fallow (amplitude), 1.4 loss (dead_share) via
  `src/gis_monitor.py` + `GET /gis`.
