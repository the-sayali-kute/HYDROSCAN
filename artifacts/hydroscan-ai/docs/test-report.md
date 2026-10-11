# HydroScan AI test report

## Executed checks

Build-session date: 2026-10-11.

Command:

```text
uv run --locked python -m unittest discover -s artifacts/hydroscan-ai/backend/tests -v
```

Result: **12 tests passed**.

Coverage:

- Known NDWI values, zero denominators, and invalid-pixel exclusion.
- Deterministic synthetic demo arrays without georeferencing.
- Missing band files and mismatched raster-grid rejection.
- Flask demonstration analysis, saved history, generated PNGs, PDF, and CSV.
- Threshold mutation and recalculated candidate-mask counts.
- Missing-band, invalid-threshold, invalid-TIFF, and incompatible-dimension errors.
- Uploaded GeoTIFF CRS/bounds and same-grid distinct-date comparison.
- Dependency and local-storage health status.
- Unknown analysis IDs return a not-found response.

Command:

```text
pnpm run typecheck
```

Result: **passed** for the shared TypeScript libraries, API server package, HydroScan web artifact, scripts, and mockup artifact.

Command:

```text
pnpm --filter @workspace/hydroscan-ai run build
```

Result: **passed**. Vite produced the static app bundle without requiring an environment-specific port during build. It reports a non-blocking source-map notice and a bundle-size advisory.

## Interpretation

These checks verify code paths on generated arrays and temporary raster files. They do not validate any real Godavari scene, Sentinel-2 provenance, a river boundary, water quality, pollution source, or predictive accuracy. A real project report should be supported by source-scene metadata and independent environmental measurements.

## Visual verification

The empty dashboard was checked in the Replit preview at desktop and mobile viewport sizes after both API and web workflows were restarted. The browser console showed the app connecting without page errors. This verifies the empty-workspace state only; a real uploaded raster is still needed to visually inspect its projected image overlay, and a field reference is required to assess geographic accuracy.
