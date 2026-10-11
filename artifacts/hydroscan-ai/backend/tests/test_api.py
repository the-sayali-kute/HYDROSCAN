from __future__ import annotations

import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

TEST_DATA = tempfile.TemporaryDirectory(prefix="hydroscan-test-")
os.environ["HYDROSCAN_DATA_DIR"] = TEST_DATA.name
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402


class AnalysisApiTests(unittest.TestCase):
    def setUp(self):
        self.test_data = tempfile.TemporaryDirectory(prefix="hydroscan-case-")
        os.environ["HYDROSCAN_DATA_DIR"] = self.test_data.name
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.test_data.cleanup()

    @staticmethod
    def _tiff_bytes(value: float, width: int = 32, height: int = 32) -> bytes:
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="GTiff",
                width=width,
                height=height,
                count=1,
                dtype="float32",
                crs="EPSG:32643",
                transform=from_origin(500000, 2200000, 10, 10),
                nodata=-9999,
            ) as dataset:
                dataset.write(np.full((height, width), value, dtype=np.float32), 1)
            return memory_file.read()

    def _upload_data(self, observation_date: str, green_width: int = 32):
        band_values = {"blue": 0.1, "green": 0.3, "red": 0.15, "nir": 0.1}
        data = {
            "mode": "upload",
            "areaLabel": "Test grid",
            "observationDate": observation_date,
            "ndwiThreshold": "0.15",
        }
        for name, value in band_values.items():
            width = green_width if name == "green" else 32
            data[name] = (BytesIO(self._tiff_bytes(value, width=width)), f"{name}.tif")
        return data

    def test_demo_history_assets_exports_and_report(self):
        created = self.client.post(
            "/api/analyses",
            data={"mode": "demo", "ndwiThreshold": "0.15"},
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        analysis = created.get_json()
        self.assertEqual(analysis["mode"], "demonstration")
        self.assertIsNone(analysis["observationDate"])
        self.assertIn("Synthetic", analysis["dataQualityNote"])
        self.assertIsNone(analysis["crs"])
        self.assertTrue(all(item["locationType"] == "pixel" for item in analysis["anomalies"]))

        for asset in ("rgb", "ndwi", "mask", "rawMask", "comparison"):
            self.assertTrue(analysis["assets"][asset])
            image_response = self.client.get(analysis["assets"][asset])
            self.assertEqual(image_response.status_code, 200)
            self.assertEqual(image_response.mimetype, "image/png")
            image_response.close()

        report = self.client.get(f"/api/analyses/{analysis['id']}/report.pdf")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.mimetype, "application/pdf")
        self.assertTrue(report.data.startswith(b"%PDF"))
        report.close()

        csv_response = self.client.get(f"/api/analyses/{analysis['id']}/export.csv")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(b"candidate_water_pixels", csv_response.data)
        csv_response.close()

        history = self.client.get("/api/analyses")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.get_json()[0]["id"], analysis["id"])

        overview = self.client.get("/api/overview").get_json()
        self.assertEqual(overview["analysisCount"], 1)
        self.assertEqual(overview["latestRealObservation"], None)
        self.assertEqual(overview["compatibleDatedObservations"], 0)

    def test_threshold_change_recalculates_mask(self):
        created = self.client.post("/api/analyses", data={"mode": "demo", "ndwiThreshold": "-0.25"})
        self.assertEqual(created.status_code, 201, created.get_json())
        analysis = created.get_json()

        updated = self.client.patch(
            f"/api/analyses/{analysis['id']}/threshold",
            json={"threshold": 0.7},
        )
        self.assertEqual(updated.status_code, 200, updated.get_json())
        result = updated.get_json()
        self.assertEqual(result["threshold"], 0.7)
        self.assertLess(result["candidateWaterPixels"], analysis["candidateWaterPixels"])

    def test_invalid_upload_and_threshold_are_reported(self):
        missing_bands = self.client.post("/api/analyses", data={"mode": "upload"})
        self.assertEqual(missing_bands.status_code, 400)
        self.assertIn("BLUE", missing_bands.get_json()["error"])

        invalid_threshold = self.client.post(
            "/api/analyses",
            data={"mode": "demo", "ndwiThreshold": "2"},
        )
        self.assertEqual(invalid_threshold.status_code, 400)
        self.assertIn("between -1 and 1", invalid_threshold.get_json()["error"])

    def test_uploaded_bands_keep_georeferencing_and_enable_compatible_trends(self):
        first = self.client.post(
            "/api/analyses",
            data=self._upload_data("2024-01-15"),
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 201, first.get_json())
        first_analysis = first.get_json()
        self.assertEqual(first_analysis["mode"], "satellite")
        self.assertTrue(first_analysis["georeferenced"])
        self.assertEqual(len(first_analysis["geographicBounds"]), 4)
        self.assertEqual(first_analysis["anomalies"], [])

        second = self.client.post(
            "/api/analyses",
            data=self._upload_data("2024-02-15"),
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 201, second.get_json())

        trends = self.client.get("/api/trends").get_json()
        self.assertTrue(trends["available"])
        self.assertEqual(
            [item["observationDate"] for item in trends["observations"]],
            ["2024-01-15", "2024-02-15"],
        )

    def test_invalid_tiff_and_mismatched_uploads_are_rejected(self):
        mismatch = self.client.post(
            "/api/analyses",
            data=self._upload_data("2024-01-15", green_width=33),
            content_type="multipart/form-data",
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("same grid", mismatch.get_json()["error"])

        invalid_data = self._upload_data("2024-01-15")
        invalid_data["blue"] = (BytesIO(b"not a GeoTIFF"), "blue.tif")
        invalid = self.client.post(
            "/api/analyses",
            data=invalid_data,
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("Could not read", invalid.get_json()["error"])
        self.assertEqual(self.client.get("/api/analyses").get_json(), [])

    def test_deleted_assets_and_unknown_analysis_are_handled(self):
        missing = self.client.get("/api/analyses/8fa2ca1f-955f-4075-94a0-71dd328a6dd4")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["error"], "Analysis not found.")

    def test_system_health_lists_real_dependencies(self):
        health = self.client.get("/api/system-health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ready")
        names = {item["name"] for item in health.get_json()["dependencies"]}
        self.assertIn("Flask", names)
        self.assertIn("rasterio", names)


if __name__ == "__main__":
    unittest.main()
