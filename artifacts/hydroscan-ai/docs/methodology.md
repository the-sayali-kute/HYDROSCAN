# HydroScan AI methodology

## Processing workflow

1. Select demo mode or upload four GeoTIFF bands. Demo data is generated deterministically, has no real geolocation, and is labeled as synthetic throughout the interface and exports.
2. Validate the band files. Each must be a readable, single-band GeoTIFF. Width, height, CRS, and affine transform must match exactly. The application rejects mismatches instead of silently resampling.
3. Mark a pixel valid only when all four uploaded band values are finite and not masked as nodata.
4. Calculate NDWI and a configurable threshold mask.
5. Remove small eight-connected components from the candidate mask and retain the raw mask for comparison.
6. Calculate robust per-band outlier scores across mutually valid pixels and group connected candidate outliers into review regions.
7. Render the RGB composite, NDWI, raw and cleaned masks, and side-by-side comparison at the source grid.
8. Save metadata in local SQLite and create a PDF report and CSV table.

## NDWI

For green reflectance `G` and near-infrared reflectance `NIR`:

```text
NDWI = (G - NIR) / (G + NIR)
```

The implementation treats non-finite values and denominators whose absolute value is at most `1e-10` as invalid. A valid pixel is a candidate when `NDWI >= threshold`; the default threshold is `0.15`, configurable from `-1` through `1`.

The cleaned mask removes eight-connected candidate components smaller than `max(3, floor(valid_pixel_count × 0.00001))` pixels. This is a simple noise filter, not a hydrological boundary extraction algorithm. The raw candidate mask remains available so users can compare what the filter removed.

The reported candidate coverage is:

```text
100 × cleaned candidate-water pixels / mutually valid pixels
```

It is not the proportion of the real river's water area unless the raster was independently validated and the study extent is appropriate.

## RGB visualization

The red, green, and blue inputs are displayed as an RGB composite. Each channel uses a separate 2nd-to-98th percentile display stretch over valid pixels. That stretch changes visualization brightness only; it does not modify source arrays used by the index or anomaly calculation.

## Spectral anomaly priorities

For each band, the service calculates the median and median absolute deviation (MAD) across valid pixels. If MAD is effectively zero, the interquartile range divided by `1.349` is tried, then standard deviation. The per-pixel absolute robust score is:

```text
robust_z = 0.6745 × |pixel_value - band_median| / robust_scale
pixel_score = maximum robust_z over Blue, Green, Red, and NIR
```

Pixels with a maximum score of at least `3.5` are grouped using eight-connected components; components smaller than `max(5, floor(valid_pixel_count × 0.00001))` pixels are not shown. A region's displayed score is its mean pixel score. Priority labels are Low below `4.5`, Moderate from `4.5` to below `6.0`, and High at `6.0` or above.

The score is a transparent within-scene statistical outlier measure, not a calibrated confidence, machine-learning prediction, toxicity indicator, pollution probability, or cause attribution. The explanation states which band had the largest contribution at a region's peak pixel.

## Geolocation and comparison

The service uses only the GeoTIFF CRS and affine transform. A geographic location is calculated only when both are usable and can be transformed to WGS84. Otherwise it reports raster row/column and does not invent coordinates. Demo rasters never receive a CRS or location.

Trend comparison excludes demo runs and requires at least two distinct user-supplied dates with an identical raster grid, area label, and threshold. The values are not seasonally, atmospherically, or sensor normalized. Date-to-date differences can reflect clouds, season, acquisition conditions, or processing and are not forecasts.

## Data quality and limitations

- Valid-pixel coverage is calculated from the shared valid mask for all four input bands.
- The app does not infer a cloud mask. Cloud or haze pixels can be valid raster measurements and can affect NDWI and outlier scores.
- Input filenames and metadata do not independently prove a Sentinel-2 source or observation date.
- NDWI can be affected by shadows, built surfaces, vegetation, turbidity, and nearby land cover.
- An anomaly is not a confirmed contamination event; no pollution labels or performance metrics are fabricated.
- A candidate mask must not be presented as a verified river boundary without independent validation.
- Reports recommend cloud-masked imagery, consistent multitemporal review, and independent field or authoritative water-quality measurements.

## Future improvements

Accept and validate Sentinel-2 scene classification/quality bands; provide explicit cloud-mask controls; add windowed processing for full-scene GeoTIFFs; support verified shoreline boundaries; compare independent field measurements; and validate any future predictive model on genuine labeled data with a held-out evaluation procedure.
