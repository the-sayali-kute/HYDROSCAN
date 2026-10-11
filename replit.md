# HydroScan AI

A local-first environmental intelligence app for transparent screening of aligned Sentinel-2-style river imagery, with explicit synthetic demonstration mode.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the Flask API service on the workflow-provided port
- `pnpm --filter @workspace/hydroscan-ai run dev` — run the React/Vite interface on its workflow-provided port
- `pnpm --filter @workspace/hydroscan-ai run typecheck` — check the web artifact
- `pnpm --filter @workspace/api-spec run codegen` — regenerate typed API hooks and Zod schemas after OpenAPI edits
- `uv run python artifacts/hydroscan-ai/backend/app.py` — start the Flask API from the workspace root when running manually
- `uv run python -m unittest discover -s artifacts/hydroscan-ai/backend/tests -v` — run backend tests
- `pnpm run typecheck` — check the TypeScript workspace
- Python uploads and generated outputs live in `artifacts/hydroscan-ai/data/` and are ignored by Git and deployments

## Stack

- Frontend: React, Vite, TypeScript, Tailwind CSS
- API: Python Flask
- Raster analysis: NumPy, Rasterio, SciPy, Matplotlib, Pandas
- Local persistence and reports: SQLite and ReportLab
- API contract and generated client: OpenAPI, Orval, Zod, React Query

## Where things live

- `artifacts/hydroscan-ai/src/` — dashboard, explorer, history, results, map, methodology, health UI
- `artifacts/hydroscan-ai/backend/app.py` — Flask API routes and validation
- `artifacts/hydroscan-ai/backend/processing.py` — raster loading, NDWI, masks, anomaly statistics, image layers
- `artifacts/hydroscan-ai/backend/storage.py` — SQLite analysis history
- `artifacts/hydroscan-ai/backend/reports.py` — PDF output
- `artifacts/hydroscan-ai/backend/tests/` — Python unit and route tests
- `lib/api-spec/openapi.yaml` — source API contract
- `artifacts/hydroscan-ai/README.md` — local setup and project guide
- `artifacts/hydroscan-ai/docs/` — methodology, walkthrough, and viva preparation

## Architecture decisions

- SQLite keeps this student project local-first and avoids requiring a managed database.
- The generated Replit API service workflow launches Flask so the requested Python analysis stack is the actual runtime backend.
- Uploaded bands must match in size, CRS, and transform; there is no implicit resampling.
- Demonstration arrays are synthetic and have no geospatial reference; their metrics never represent observations.
- Robust spectral scores provide inspection priority only; there is no pollution classifier or unsupported accuracy claim.

## Product

Users can create clearly labeled demos or upload aligned band GeoTIFFs, inspect RGB/NDWI/masks, change the NDWI threshold, review robust spectral outliers, view only justified geographic locations, compare compatible dated scenes, reopen saved analyses, and download PDF/CSV reports.

## User preferences

- Keep synthetic values distinct from uploaded satellite observations.
- Do not describe candidate water masks as verified river boundaries or anomaly priorities as confirmed pollution measurements.
- No paid APIs, datasets, hosting, or AI API keys for core features.

## Gotchas

- Re-run API code generation after changing `lib/api-spec/openapi.yaml`.
- Start both the API Server and web workflows for the full app preview.
- Keep source rasters and generated data under the ignored app data directory.
- Trend comparisons require two distinct dated satellite records with identical grid, area label, and threshold.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
