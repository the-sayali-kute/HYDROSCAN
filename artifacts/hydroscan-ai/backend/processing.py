"""Transparent raster calculations used by the HydroScan Flask service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as reproject_coordinates
from rasterio.warp import transform_bounds as reproject_bounds
from scipy import ndimage

MAX_PIXELS = 12_000_000
DEFAULT_THRESHOLD = 0.15
ANOMALY_ROBUST_Z_THRESHOLD = 3.5
BAND_ORDER = ("blue", "green", "red", "nir")
PUBLIC_ASSETS = {
    "rgb.png": "rgb.png",
    "ndwi.png": "ndwi.png",
    "mask.png": "mask.png",
    "mask-raw.png": "mask-raw.png",
    "comparison.png": "comparison.png",
}
LIMITATIONS = [
    "NDWI is an index-based candidate mask, not a verified river boundary. Shadows, built surfaces, vegetation, turbidity, and other surface conditions can affect it.",
    "Spectral anomaly priorities flag unusual band patterns for inspection; they are not confirmed water-quality measurements, pollution levels, or source locations.",
    "No cloud mask is inferred from RGB/NIR bands. Nodata and invalid values are excluded, but clouds and haze may remain.",
    "Satellite provenance is not independently verified. Uploaded files are treated as user-provided raster bands.",
    "A single dated observation cannot establish a historical trend or predict future conditions.",
]


class AnalysisInputError(ValueError):
    """Raised when user-provided band inputs cannot be analyzed safely."""


def _affine_signature(transform: Any) -> tuple[float, ...]:
    return tuple(round(float(value), 12) for value in transform)


def load_band_files(paths: dict[str, str | Path]) -> tuple[dict[str, np.ndarray], np.ndarray, dict[str, Any]]:
    """Read four aligned, single-band rasters without resampling any input."""
    missing = [name for name in BAND_ORDER if name not in paths]
    if missing:
        raise AnalysisInputError(f"Missing required bands: {', '.join(missing)}.")

    arrays: dict[str, np.ndarray] = {}
    band_metadata: list[dict[str, Any]] = []
    reference: dict[str, Any] | None = None

    for name in BAND_ORDER:
        path = Path(paths[name])
        if path.suffix.lower() not in {".tif", ".tiff"}:
            raise AnalysisInputError(f"The {name.upper()} band must be a GeoTIFF (.tif or .tiff).")
        try:
            dataset = rasterio.open(path)
        except (rasterio.errors.RasterioError, OSError) as error:
            raise AnalysisInputError(f"Could not read the {name.upper()} GeoTIFF: {error}") from error

        with dataset:
            if dataset.count != 1:
                raise AnalysisInputError(
                    f"The {name.upper()} file contains {dataset.count} bands. Upload a single-band raster for each band."
                )
            if dataset.width * dataset.height > MAX_PIXELS:
                raise AnalysisInputError(
                    f"The {name.upper()} raster has more than {MAX_PIXELS:,} pixels. Clip all four bands to the same study-area extent before upload."
                )

            current = {
                "width": dataset.width,
                "height": dataset.height,
                "crs": dataset.crs,
                "transform": dataset.transform,
            }
            if reference is None:
                reference = current
            elif (
                current["width"] != reference["width"]
                or current["height"] != reference["height"]
                or current["crs"] != reference["crs"]
                or current["transform"] != reference["transform"]
            ):
                raise AnalysisInputError(
                    "The four bands are not on the same grid. Their dimensions, coordinate reference system, and affine transform must match exactly; HydroScan does not resample or align bands."
                )

            values = dataset.read(1, masked=True).astype(np.float32).filled(np.nan)
            arrays[name] = values
            resolution_x, resolution_y = dataset.res
            band_metadata.append(
                {
                    "name": name.upper(),
                    "width": dataset.width,
                    "height": dataset.height,
                    "dtype": dataset.dtypes[0],
                    "crs": str(dataset.crs) if dataset.crs else None,
                    "resolutionX": abs(float(resolution_x)) if np.isfinite(resolution_x) else None,
                    "resolutionY": abs(float(resolution_y)) if np.isfinite(resolution_y) else None,
                }
            )

    if reference is None:
        raise AnalysisInputError("No readable band files were provided.")

    valid = np.logical_and.reduce([np.isfinite(arrays[name]) for name in BAND_ORDER])
    if int(valid.sum()) < 16:
        raise AnalysisInputError("The bands contain fewer than 16 mutually valid pixels.")

    crs = reference["crs"]
    transform = reference["transform"]
    georeferenced = bool(
        crs
        and isinstance(crs, CRS)
        and transform
        and transform != rasterio.Affine.identity()
        and abs(transform.determinant) > 1e-15
    )
    grid_signature = json.dumps(
        {
            "width": reference["width"],
            "height": reference["height"],
            "crs": crs.to_string() if crs else None,
            "transform": _affine_signature(transform),
        },
        sort_keys=True,
    )
    metadata = {
        "width": reference["width"],
        "height": reference["height"],
        "crs": crs.to_string() if crs else None,
        "transform": transform,
        "georeferenced": georeferenced,
        "geographicBounds": None,
        "gridSignature": grid_signature,
        "bands": band_metadata,
    }
    if georeferenced:
        try:
            metadata["geographicBounds"] = list(
                reproject_bounds(
                    crs,
                    "EPSG:4326",
                    *rasterio.transform.array_bounds(
                        reference["height"], reference["width"], transform
                    ),
                    densify_pts=21,
                )
            )
        except (ValueError, rasterio.errors.RasterioError):
            metadata["geographicBounds"] = None
    return arrays, valid, metadata


def make_demo_bands(seed: int = 47) -> tuple[dict[str, np.ndarray], np.ndarray, dict[str, Any]]:
    """Create a reproducible, explicitly synthetic sample; no coordinates are assigned."""
    rng = np.random.default_rng(seed)
    height, width = 256, 256
    rows, columns = np.mgrid[0:height, 0:width]
    across = columns / width
    along = rows / height
    centerline = 0.5 + 0.075 * np.sin(along * np.pi * 3.1) + 0.03 * np.sin(along * np.pi * 8.0)
    water = (np.abs(across - centerline) < 0.095) & (along > 0.03) & (along < 0.98)

    bands = {
        "blue": np.where(water, 0.16, 0.19).astype(np.float32),
        "green": np.where(water, 0.34, 0.17).astype(np.float32),
        "red": np.where(water, 0.10, 0.23).astype(np.float32),
        "nir": np.where(water, 0.055, 0.31).astype(np.float32),
    }
    for name in BAND_ORDER:
        bands[name] += rng.normal(0, 0.006 if name != "nir" else 0.01, (height, width)).astype(np.float32)

    # A bright spectral patch creates a synthetic review candidate, not a pollution label.
    bands["red"][78:91, 172:187] += 0.15
    bands["nir"][78:91, 172:187] += 0.12
    bands["blue"][78:91, 172:187] += 0.04
    valid = np.ones((height, width), dtype=bool)
    valid[20:31, 24:60] = False
    for name in BAND_ORDER:
        bands[name][~valid] = np.nan

    metadata = {
        "width": width,
        "height": height,
        "crs": None,
        "transform": None,
        "georeferenced": False,
        "geographicBounds": None,
        "gridSignature": None,
        "bands": [
            {
                "name": name.upper(),
                "width": width,
                "height": height,
                "dtype": "float32",
                "crs": None,
                "resolutionX": None,
                "resolutionY": None,
            }
            for name in BAND_ORDER
        ],
    }
    return bands, valid, metadata


def _robust_band_scores(bands: dict[str, np.ndarray], valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cube = np.stack([bands[name] for name in BAND_ORDER], axis=-1)
    samples = cube[valid]
    median = np.median(samples, axis=0)
    mad = np.median(np.abs(samples - median), axis=0)
    fallback = np.percentile(samples, 75, axis=0) - np.percentile(samples, 25, axis=0)
    scale = np.where(mad > 1e-9, mad, fallback / 1.349)
    scale = np.where(scale > 1e-9, scale, np.std(samples, axis=0))
    scale = np.where(scale > 1e-9, scale, 1.0)
    scores = np.zeros(cube.shape, dtype=np.float32)
    scores[valid] = (0.6745 * np.abs(cube[valid] - median) / scale).astype(np.float32)
    return np.max(scores, axis=-1), np.argmax(scores, axis=-1)


def _component_filter(mask: np.ndarray, minimum_pixels: int) -> np.ndarray:
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= minimum_pixels
    keep[0] = False
    return keep[labels]


def calculate_ndwi(
    green: np.ndarray, nir: np.ndarray, valid: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return NDWI and its finite, non-zero-denominator validity mask."""
    denominator = green + nir
    computable = valid & np.isfinite(denominator) & (np.abs(denominator) > 1e-10)
    ndwi = np.full(green.shape, np.nan, dtype=np.float32)
    np.divide(green - nir, denominator, out=ndwi, where=computable)
    return ndwi, computable


def _stretch(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    output = np.zeros(values.shape, dtype=np.float32)
    if not valid.any():
        return output
    low, high = np.percentile(values[valid], [2, 98])
    if high <= low:
        high = low + 1.0
    output[valid] = np.clip((values[valid] - low) / (high - low), 0.0, 1.0)
    return output


def _write_visualizations(
    bands: dict[str, np.ndarray],
    valid: np.ndarray,
    ndwi: np.ndarray,
    raw_mask: np.ndarray,
    clean_mask: np.ndarray,
    anomaly_score: np.ndarray,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rgb = np.stack(
        [_stretch(bands["red"], valid), _stretch(bands["green"], valid), _stretch(bands["blue"], valid)],
        axis=-1,
    )
    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    ax.imshow(rgb)
    ax.set_title("RGB composite · percentile stretch")
    ax.set_axis_off()
    fig.savefig(output_dir / "rgb.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
    shown = np.ma.masked_where(~valid, ndwi)
    image = ax.imshow(shown, cmap="BrBG", vmin=-1, vmax=1)
    fig.colorbar(image, ax=ax, label="NDWI")
    ax.set_title("Normalized Difference Water Index")
    ax.set_axis_off()
    fig.savefig(output_dir / "ndwi.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    for filename, data, title in (
        ("mask-raw.png", raw_mask, "Raw NDWI candidate mask"),
        ("mask.png", clean_mask, "Connected-component cleaned mask"),
    ):
        fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
        display = np.ma.masked_where(~valid, data.astype(np.float32))
        ax.imshow(display, cmap=matplotlib.colors.ListedColormap(["#eaf2ed", "#14b8a6"]), vmin=0, vmax=1)
        ax.set_title(title)
        ax.set_axis_off()
        fig.savefig(output_dir / filename, dpi=150, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, data, title in (
        (axes[0], raw_mask, "Before component filtering"),
        (axes[1], clean_mask, "After component filtering"),
    ):
        display = np.ma.masked_where(~valid, data.astype(np.float32))
        ax.imshow(display, cmap=matplotlib.colors.ListedColormap(["#eaf2ed", "#14b8a6"]), vmin=0, vmax=1)
        ax.set_title(title)
        ax.set_axis_off()
    fig.suptitle("Candidate water mask comparison")
    fig.savefig(output_dir / "comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def analyze_bands(
    bands: dict[str, np.ndarray],
    valid: np.ndarray,
    metadata: dict[str, Any],
    *,
    threshold: float,
    mode: str,
    area_label: str,
    observation_date: str | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    if not -1.0 <= threshold <= 1.0:
        raise AnalysisInputError("The NDWI threshold must be between -1 and 1.")
    if any(bands[name].shape != valid.shape for name in BAND_ORDER):
        raise AnalysisInputError("Band arrays do not have matching shapes.")
    if int(valid.sum()) < 16:
        raise AnalysisInputError("At least 16 valid pixels are required.")

    ndwi, computable = calculate_ndwi(bands["green"], bands["nir"], valid)
    ndwi_valid = computable & np.isfinite(ndwi)
    raw_mask = ndwi_valid & (ndwi >= threshold)
    minimum_component = max(3, int(valid.sum() * 0.00001))
    clean_mask = _component_filter(raw_mask, minimum_component) & ndwi_valid

    anomaly_score, dominant_band = _robust_band_scores(bands, valid)
    anomaly_candidates = valid & (anomaly_score >= ANOMALY_ROBUST_Z_THRESHOLD)
    anomaly_labels, region_count = ndimage.label(anomaly_candidates, structure=np.ones((3, 3), dtype=np.uint8))
    region_sizes = np.bincount(anomaly_labels.ravel()) if region_count else np.array([0])
    minimum_region = max(5, int(valid.sum() * 0.00001))
    anomalies: list[dict[str, Any]] = []
    region_number = 0
    transform = metadata.get("transform")
    crs = metadata.get("crs")

    for label in range(1, region_count + 1):
        rows, columns = np.where(anomaly_labels == label)
        if len(rows) < minimum_region:
            continue
        region_number += 1
        region_score = float(np.mean(anomaly_score[rows, columns]))
        peak_index = int(np.argmax(anomaly_score[rows, columns]))
        peak_row, peak_column = int(rows[peak_index]), int(columns[peak_index])
        band_index = int(dominant_band[peak_row, peak_column])
        if region_score >= 6.0:
            priority = "high"
        elif region_score >= 4.5:
            priority = "moderate"
        else:
            priority = "low"

        coordinates = None
        location_type = "pixel"
        if metadata.get("georeferenced") and transform is not None and crs:
            x, y = transform * (float(np.mean(columns)) + 0.5, float(np.mean(rows)) + 0.5)
            try:
                longitude, latitude = reproject_coordinates(crs, "EPSG:4326", [x], [y])
                coordinates = [float(latitude[0]), float(longitude[0])]
                location_type = "geographic"
            except (ValueError, rasterio.errors.RasterioError):
                coordinates = None

        explanation = (
            f"Connected region of {len(rows):,} pixels exceeded the robust spectral outlier threshold "
            f"({ANOMALY_ROBUST_Z_THRESHOLD:g}); {BAND_ORDER[band_index].upper()} contributed the largest deviation at its peak pixel. "
            f"Mean robust score: {region_score:.2f}. This is an inspection priority, not a pollution finding."
        )
        anomalies.append(
            {
                "id": f"R{region_number:03d}",
                "priority": priority,
                "score": round(region_score, 3),
                "pixels": int(len(rows)),
                "row": peak_row,
                "column": peak_column,
                "explanation": explanation,
                "locationType": location_type,
                "coordinates": coordinates,
            }
        )
    anomalies.sort(key=lambda item: item["score"], reverse=True)
    anomalies = anomalies[:100]

    total_pixels = int(valid.size)
    valid_pixels = int(valid.sum())
    water_pixels = int(clean_mask.sum())
    valid_percent = 100.0 * valid_pixels / total_pixels if total_pixels else 0.0
    water_percent = 100.0 * water_pixels / valid_pixels if valid_pixels else 0.0
    if mode == "demonstration":
        quality_note = "Synthetic demonstration: all values are calculated from generated sample arrays and do not describe river conditions."
    elif valid_percent < 70:
        quality_note = f"Only {valid_percent:.1f}% of pixels were valid after nodata checks; inspect coverage before interpretation. No cloud mask was supplied."
    elif valid_percent < 95:
        quality_note = f"{valid_percent:.1f}% of pixels were valid after nodata checks. No cloud mask was supplied."
    else:
        quality_note = f"{valid_percent:.1f}% of pixels were valid after nodata checks. No cloud mask was supplied."

    output_path = Path(output_dir)
    _write_visualizations(bands, valid, ndwi, raw_mask, clean_mask, anomaly_score, output_path)
    return {
        "mode": mode,
        "areaLabel": area_label or "Study area not specified",
        "observationDate": observation_date,
        "threshold": float(threshold),
        "validPixelPercent": round(valid_percent, 3),
        "waterCoveragePercent": round(water_percent, 3),
        "candidateWaterPixels": water_pixels,
        "rawCandidateWaterPixels": int(raw_mask.sum()),
        "validPixels": valid_pixels,
        "totalPixels": total_pixels,
        "anomalyCount": len(anomalies),
        "dataQualityNote": quality_note,
        "sourceLabel": (
            "Synthetic demonstration data" if mode == "demonstration" else "User-uploaded raster bands (provenance not independently verified)"
        ),
        "width": int(metadata["width"]),
        "height": int(metadata["height"]),
        "crs": metadata.get("crs"),
        "georeferenced": bool(metadata.get("georeferenced")),
        "geographicBounds": metadata.get("geographicBounds"),
        "gridSignature": metadata.get("gridSignature"),
        "bands": metadata["bands"],
        "anomalies": anomalies,
        "limitations": list(LIMITATIONS),
        "thresholdMethod": {
            "mask": "NDWI >= configured threshold; NDWI = (Green - NIR) / (Green + NIR).",
            "cleaning": f"8-connected components smaller than {minimum_component} pixels are removed.",
            "anomalies": f"Per-band median/MAD robust z-scores; a pixel is a candidate at max absolute robust z >= {ANOMALY_ROBUST_Z_THRESHOLD:g}.",
            "priority": "Low < 4.5, Moderate 4.5–5.99, High >= 6.0 mean robust score. These are triage categories only.",
        },
        "assets": {},
    }
