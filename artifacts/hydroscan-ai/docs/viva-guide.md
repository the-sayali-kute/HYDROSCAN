# HydroScan AI viva preparation

## One-minute project explanation

HydroScan AI is a local-first application that helps a student inspect four aligned satellite raster bands. It validates the raster grid, calculates NDWI candidate water pixels, filters small connected components, and finds relative spectral outliers using median/MAD robust scores. It saves the analysis locally and creates visualizations, a CSV, and a PDF. The results are preliminary screening indicators only: they do not confirm a river boundary or water pollution.

## Module walkthrough

- `backend/app.py`: Flask endpoints, upload checks, history access, threshold recalculation, download routes, and health status.
- `backend/processing.py`: GeoTIFF validation, NDWI, mask cleanup, robust anomaly scoring, map coordinates, and PNG layers.
- `backend/storage.py`: SQLite persistence for analysis metadata and calculated results.
- `backend/reports.py`: PDF report with metadata, calculated values, visuals, flagged regions, and limitations.
- `src/`: React/Vite screens that call the typed API and show results.
- `lib/api-spec/openapi.yaml`: API contract from which the generated TypeScript and Zod helpers are produced.
- `backend/tests/`: small-array formula tests, GeoTIFF validation tests, and Flask route tests.

## Likely questions and answers

### What is NDWI?

NDWI is `(Green - NIR) / (Green + NIR)`. Water often reflects green light more strongly than near-infrared light, so the normalized difference can help find water-like pixels. A threshold turns that continuous index into a candidate mask.

### Why is the denominator checked?

If `Green + NIR` is zero or nearly zero, the ratio is undefined or unstable. The app marks that pixel invalid rather than allowing infinity or a misleading number into the mask.

### Why are all bands required to have the same grid?

Pixel-wise formulas compare values at the same location. If dimensions, CRS, or affine transform differ, pixels may refer to different places. This app rejects such inputs rather than silently resampling them.

### Does a candidate pixel prove that it is river water?

No. NDWI can confuse water with shadows and other land-surface conditions. The result is explicitly called a candidate mask and needs independent boundary validation.

### Does a high-priority anomaly mean pollution?

No. It means a connected region has band values that are statistically unusual relative to the same raster under the stated robust-score method. It is a queue for inspection, not a measured contaminant or confirmed pollution event.

### Why use median and MAD?

The median and median absolute deviation are less sensitive to a small number of extreme pixels than a mean and standard deviation. The fallback to interquartile range or standard deviation handles bands whose MAD is zero.

### What is the role of the threshold?

The threshold determines which valid pixels satisfy `NDWI >= threshold`. Raising the threshold is stricter and typically reduces the candidate mask; the user can change it and compare raw and cleaned masks.

### Why doesn't the application use an AI model to predict pollution?

There are no verified historical labels, field measurements, or validation data supplied. Training on invented labels or reporting invented accuracy would be misleading. The project uses transparent screening statistics instead.

### When can it show a historical trend?

Only after at least two genuinely distinct, dated uploaded analyses match in raster grid, area label, and threshold. Even then, cloud, season, atmospheric effects, and sensor differences can confound the comparison. It is descriptive, not predictive.

### Why might the map show pixels instead of latitude and longitude?

An uploaded raster may not contain a usable CRS or affine transform. In that case, exact geographic placement cannot be justified; the app uses row and column and leaves coordinates blank.

### Where is history stored?

Analysis metadata and derived results are stored in a local SQLite database. Uploaded TIFF copies, visualizations, and reports are stored beside that database under the app's ignored `data/` directory.

## Demonstration checklist

1. Open the dashboard and point out whether the current data is synthetic or uploaded.
2. Run the synthetic demo; show the NDWI layer and raw/cleaned mask comparison.
3. Change the NDWI threshold and explain why the candidate-pixel count changes.
4. Open a flagged spectral region and explain its score and dominant band contribution.
5. Show that the demo has pixel positions only and no observation date or map coordinates.
6. Download the PDF and CSV, then reopen the run from history.
7. Open the methodology and health screens and state the cloud-mask and validation limitations.
8. For a real-data demonstration, use four single-band GeoTIFFs with a matching grid and record a date only if verified from the source.
