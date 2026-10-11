"""Flask API for the HydroScan AI local-first raster analysis application."""

from __future__ import annotations

import csv
import io
import logging
import math
import shutil
import uuid
from datetime import date, datetime, timezone
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from processing import (
    DEFAULT_THRESHOLD,
    PUBLIC_ASSETS,
    AnalysisInputError,
    analyze_bands,
    load_band_files,
    make_demo_bands,
)
from reports import build_pdf_report
from storage import data_root, get_analysis, initialize, list_analyses, save_analysis

API_PREFIX = "/api"
ALLOWED_BANDS = ("blue", "green", "red", "nir")
SUMMARY_FIELDS = (
    "id",
    "mode",
    "areaLabel",
    "observationDate",
    "createdAt",
    "threshold",
    "validPixelPercent",
    "waterCoveragePercent",
    "candidateWaterPixels",
    "validPixels",
    "totalPixels",
    "anomalyCount",
    "dataQualityNote",
    "reportId",
)
DEPENDENCIES = {
    "flask": "Flask",
    "numpy": "numpy",
    "rasterio": "rasterio",
    "Pillow": "Pillow",
    "matplotlib": "matplotlib",
    "pandas": "pandas",
    "scikit-learn": "scikit-learn",
    "scipy": "scipy",
    "reportlab": "reportlab",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("hydroscan")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid_analysis_id(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _run_dir(analysis_id: str) -> Path:
    if not _valid_analysis_id(analysis_id):
        raise AnalysisInputError("Invalid analysis ID.")
    return data_root() / "runs" / analysis_id


def _public_analysis(stored: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in stored.items() if not key.startswith("_")}
    directory = _run_dir(stored["id"])
    asset_files = stored.get("_assetFiles", {})
    asset_names = {
        "rgb": "rgb.png",
        "ndwi": "ndwi.png",
        "mask": "mask.png",
        "rawMask": "mask-raw.png",
        "comparison": "comparison.png",
    }
    result["assets"] = {
        key: (
            f"{API_PREFIX}/analyses/{stored['id']}/assets/{filename}"
            if filename in PUBLIC_ASSETS and (directory / "assets" / filename).is_file()
            else ""
        )
        for key, filename in asset_names.items()
        if asset_files.get(key) == filename
    }
    return result


def _summary(analysis: dict[str, Any]) -> dict[str, Any]:
    return {field: analysis.get(field) for field in SUMMARY_FIELDS}


def _analysis_or_404(analysis_id: str) -> dict[str, Any] | None:
    if not _valid_analysis_id(analysis_id):
        return None
    return get_analysis(analysis_id)


def _parse_threshold(value: Any) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError) as error:
        raise AnalysisInputError("Provide a numeric NDWI threshold between -1 and 1.") from error
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise AnalysisInputError("The NDWI threshold must be between -1 and 1.")
    return threshold


def _create_analysis(
    *,
    mode: str,
    threshold: float,
    area_label: str,
    observation_date: str | None,
) -> dict[str, Any]:
    analysis_id = str(uuid.uuid4())
    analysis_dir = _run_dir(analysis_id)
    source_dir = analysis_dir / "source"
    output_dir = analysis_dir / "assets"
    source_dir.mkdir(parents=True, exist_ok=False)
    seed = int(analysis_id.replace("-", "")[:8], 16)

    try:
        if mode == "demonstration":
            bands, valid, metadata = make_demo_bands(seed)
            source_files: dict[str, str] = {}
        else:
            source_files = {}
            for band in ALLOWED_BANDS:
                uploaded = request.files.get(band)
                if uploaded is None or not uploaded.filename:
                    raise AnalysisInputError(f"Choose a GeoTIFF file for the {band.upper()} band.")
                if Path(uploaded.filename).suffix.lower() not in {".tif", ".tiff"}:
                    raise AnalysisInputError(f"The {band.upper()} band must be a .tif or .tiff file.")
                saved = source_dir / f"{band}.tif"
                uploaded.save(saved)
                source_files[band] = str(saved)
            bands, valid, metadata = load_band_files(source_files)

        result = analyze_bands(
            bands,
            valid,
            metadata,
            threshold=threshold,
            mode=mode,
            area_label=area_label,
            observation_date=observation_date,
            output_dir=output_dir,
        )
        result.update(
            {
                "id": analysis_id,
                "reportId": f"HYDRO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{analysis_id[:8].upper()}",
                "createdAt": _iso_now(),
                "_demoSeed": seed if mode == "demonstration" else None,
                "_sourceFiles": source_files,
                "_assetFiles": {
                    "rgb": "rgb.png",
                    "ndwi": "ndwi.png",
                    "mask": "mask.png",
                    "rawMask": "mask-raw.png",
                    "comparison": "comparison.png",
                },
            }
        )
        build_pdf_report(result, analysis_dir)
        save_analysis(result)
        return result
    except Exception:
        shutil.rmtree(analysis_dir, ignore_errors=True)
        raise


def _recalculate_analysis(stored: dict[str, Any], threshold: float) -> dict[str, Any]:
    analysis_dir = _run_dir(stored["id"])
    if stored["mode"] == "demonstration":
        bands, valid, metadata = make_demo_bands(int(stored["_demoSeed"]))
    else:
        source_files = stored.get("_sourceFiles") or {}
        if not all(Path(source_files.get(name, "")).is_file() for name in ALLOWED_BANDS):
            raise AnalysisInputError(
                "The source raster files for this saved analysis are missing. Re-upload the four bands to recalculate it."
            )
        bands, valid, metadata = load_band_files(source_files)

    updated = analyze_bands(
        bands,
        valid,
        metadata,
        threshold=threshold,
        mode=stored["mode"],
        area_label=stored["areaLabel"],
        observation_date=stored.get("observationDate"),
        output_dir=analysis_dir / "assets",
    )
    for field in ("id", "reportId", "createdAt", "_demoSeed", "_sourceFiles", "_assetFiles"):
        if field in stored:
            updated[field] = stored[field]
    build_pdf_report(updated, analysis_dir)
    save_analysis(updated)
    return updated


def _trend_summary(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for item in analyses:
        signature = item.get("gridSignature")
        observation_date = item.get("observationDate")
        if item.get("mode") != "satellite" or not signature or not observation_date:
            continue
        key = (signature, float(item["threshold"]), item["areaLabel"])
        groups.setdefault(key, []).append(item)

    comparable: list[dict[str, Any]] = []
    for group in groups.values():
        unique_dates: dict[str, dict[str, Any]] = {}
        for item in sorted(group, key=lambda entry: entry["createdAt"]):
            unique_dates[item["observationDate"]] = item
        candidate = list(unique_dates.values())
        if len(candidate) > len(comparable):
            comparable = candidate

    comparable.sort(key=lambda item: item["observationDate"])
    points = [
        {
            "observationDate": item["observationDate"],
            "waterCoveragePercent": item["waterCoveragePercent"],
            "analysisId": item["id"],
        }
        for item in comparable
    ]
    if len(points) < 2:
        return {
            "available": False,
            "message": "Historical comparison needs at least two distinct, dated satellite analyses on the same grid, area label, and NDWI threshold. Demonstration data is excluded.",
            "observations": [],
        }
    return {
        "available": True,
        "message": "Showing distinct dated observations with matching raster grid, area label, and threshold. Seasonal, cloud, and sensor effects still require review.",
        "observations": points,
    }


def create_app() -> Flask:
    application = Flask(__name__)
    application.config["MAX_CONTENT_LENGTH"] = 320 * 1024 * 1024
    initialize()

    @application.get(f"{API_PREFIX}/healthz")
    def health_check():
        return jsonify({"status": "ok"})

    @application.get(f"{API_PREFIX}/overview")
    def overview():
        analyses = list_analyses()
        real = [
            item
            for item in analyses
            if item.get("mode") == "satellite" and item.get("observationDate")
        ]
        real.sort(key=lambda item: (item["observationDate"], item["createdAt"]), reverse=True)
        trends = _trend_summary(analyses)
        return jsonify(
            {
                "analysisCount": len(analyses),
                "latestAnalysis": _summary(analyses[0]) if analyses else None,
                "latestRealObservation": _summary(real[0]) if real else None,
                "compatibleDatedObservations": len(trends["observations"]),
                "totalFlaggedRegions": sum(int(item.get("anomalyCount", 0)) for item in analyses),
                "dataModeLabel": "Synthetic demonstration" if analyses and analyses[0]["mode"] == "demonstration" else ("Uploaded satellite bands" if analyses else "No analyses yet"),
            }
        )

    @application.get(f"{API_PREFIX}/analyses")
    def analyses_list():
        return jsonify([_summary(item) for item in list_analyses()])

    @application.post(f"{API_PREFIX}/analyses")
    def analyses_create():
        mode_input = request.form.get("mode", "demo").strip().lower()
        if mode_input not in {"demo", "upload"}:
            raise AnalysisInputError("Choose either demonstration mode or upload mode.")
        threshold = _parse_threshold(request.form.get("ndwiThreshold", DEFAULT_THRESHOLD))
        area_label = request.form.get("areaLabel", "").strip()
        if len(area_label) > 120:
            raise AnalysisInputError("The study-area label must be 120 characters or fewer.")
        if mode_input == "demo":
            analysis = _create_analysis(
                mode="demonstration",
                threshold=threshold,
                area_label=area_label or "Godavari River near Nashik — synthetic demo",
                observation_date=None,
            )
        else:
            supplied_date = request.form.get("observationDate", "").strip()
            if supplied_date:
                try:
                    date.fromisoformat(supplied_date)
                except ValueError as error:
                    raise AnalysisInputError("Observation date must use YYYY-MM-DD format.") from error
            analysis = _create_analysis(
                mode="satellite",
                threshold=threshold,
                area_label=area_label or "Study area not specified",
                observation_date=supplied_date or None,
            )
        return jsonify(_public_analysis(analysis)), 201

    @application.get(f"{API_PREFIX}/analyses/<analysis_id>")
    def analysis_detail(analysis_id: str):
        result = _analysis_or_404(analysis_id)
        if result is None:
            return jsonify({"error": "Analysis not found."}), 404
        return jsonify(_public_analysis(result))

    @application.patch(f"{API_PREFIX}/analyses/<analysis_id>/threshold")
    def analysis_threshold(analysis_id: str):
        result = _analysis_or_404(analysis_id)
        if result is None:
            return jsonify({"error": "Analysis not found."}), 404
        payload = request.get_json(silent=True) or {}
        threshold = _parse_threshold(payload.get("threshold"))
        return jsonify(_public_analysis(_recalculate_analysis(result, threshold)))

    @application.get(f"{API_PREFIX}/analyses/<analysis_id>/assets/<asset_name>")
    def analysis_asset(analysis_id: str, asset_name: str):
        if asset_name not in PUBLIC_ASSETS:
            return jsonify({"error": "Unknown analysis image."}), 404
        result = _analysis_or_404(analysis_id)
        if result is None:
            return jsonify({"error": "Analysis not found."}), 404
        path = _run_dir(analysis_id) / "assets" / asset_name
        if not path.is_file():
            return jsonify({"error": "This analysis image is no longer available."}), 404
        return send_file(path, mimetype="image/png", conditional=True)

    @application.get(f"{API_PREFIX}/analyses/<analysis_id>/export.csv")
    def analysis_csv(analysis_id: str):
        result = _analysis_or_404(analysis_id)
        if result is None:
            return jsonify({"error": "Analysis not found."}), 404
        metric_rows = [
            {"record_type": "metric", "metric": "ndwi_threshold", "value": result["threshold"]},
            {"record_type": "metric", "metric": "candidate_water_pixels", "value": result["candidateWaterPixels"]},
            {"record_type": "metric", "metric": "candidate_coverage_percent", "value": result["waterCoveragePercent"]},
            {"record_type": "metric", "metric": "valid_pixel_percent", "value": result["validPixelPercent"]},
            {"record_type": "metric", "metric": "anomaly_regions", "value": result["anomalyCount"]},
        ]
        anomaly_rows = [
            {
                "record_type": "anomaly",
                "region_id": region["id"],
                "priority": region["priority"],
                "score": region["score"],
                "pixels": region["pixels"],
                "row": region["row"],
                "column": region["column"],
                "latitude": region["coordinates"][0] if region.get("coordinates") else "",
                "longitude": region["coordinates"][1] if region.get("coordinates") else "",
                "explanation": region["explanation"],
            }
            for region in result.get("anomalies", [])
        ]
        table = pd.DataFrame(metric_rows + anomaly_rows).fillna("")
        output = io.StringIO()
        table.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
        response = application.response_class(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="hydroscan-{analysis_id[:8]}.csv"'},
        )
        return response

    @application.get(f"{API_PREFIX}/analyses/<analysis_id>/report.pdf")
    def analysis_report(analysis_id: str):
        result = _analysis_or_404(analysis_id)
        if result is None:
            return jsonify({"error": "Analysis not found."}), 404
        path = _run_dir(analysis_id) / "report.pdf"
        if not path.is_file():
            return jsonify({"error": "The saved PDF report is no longer available."}), 404
        return send_file(
            path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"hydroscan-{analysis_id[:8]}.pdf",
            conditional=True,
        )

    @application.get(f"{API_PREFIX}/trends")
    def trends():
        return jsonify(_trend_summary(list_analyses()))

    @application.get(f"{API_PREFIX}/system-health")
    def system_health():
        dependencies = []
        for module_name, distribution_name in DEPENDENCIES.items():
            try:
                version = package_metadata.version(distribution_name)
                available = True
            except package_metadata.PackageNotFoundError:
                version = None
                available = False
            dependencies.append(
                {"name": distribution_name, "available": available, "version": version}
            )
        root = data_root()
        storage_available = root.is_dir() and root.stat().st_mode & 0o222 != 0
        ready = storage_available and all(item["available"] for item in dependencies)
        return jsonify(
            {
                "status": "ready" if ready else "degraded",
                "storageAvailable": storage_available,
                "dependencies": dependencies,
                "message": "Local processing and analysis storage are available."
                if ready
                else "One or more processing dependencies or the local storage directory are unavailable.",
            }
        )

    @application.errorhandler(AnalysisInputError)
    def invalid_analysis_input(error: AnalysisInputError):
        return jsonify({"error": str(error)}), 400

    @application.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return jsonify({"error": error.description}), error.code

    @application.errorhandler(Exception)
    def unexpected_error(error: Exception):
        logger.exception("Unhandled HydroScan API error", exc_info=error)
        return jsonify({"error": "The analysis could not be completed. Check the input files and local server logs."}), 500

    return application


app = create_app()

if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
