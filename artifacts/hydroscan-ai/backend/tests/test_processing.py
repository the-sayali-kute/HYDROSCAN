from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from processing import (  # noqa: E402
    AnalysisInputError,
    calculate_ndwi,
    load_band_files,
    make_demo_bands,
)


class NdwiTests(unittest.TestCase):
    def test_known_values_and_zero_denominator(self):
        green = np.array([[0.8, 0.1, 0.0]], dtype=np.float32)
        nir = np.array([[0.2, 0.3, 0.0]], dtype=np.float32)
        ndwi, valid = calculate_ndwi(green, nir, np.ones(green.shape, dtype=bool))

        self.assertAlmostEqual(float(ndwi[0, 0]), 0.6, places=6)
        self.assertAlmostEqual(float(ndwi[0, 1]), -0.5, places=6)
        self.assertTrue(valid[0, 0])
        self.assertTrue(valid[0, 1])
        self.assertFalse(valid[0, 2])
        self.assertTrue(np.isnan(ndwi[0, 2]))

    def test_invalid_pixels_stay_invalid(self):
        green = np.array([[0.4, 0.4]], dtype=np.float32)
        nir = np.array([[0.2, 0.2]], dtype=np.float32)
        ndwi, valid = calculate_ndwi(green, nir, np.array([[True, False]]))

        self.assertAlmostEqual(float(ndwi[0, 0]), 1 / 3, places=6)
        self.assertFalse(valid[0, 1])
        self.assertTrue(np.isnan(ndwi[0, 1]))


class RasterValidationTests(unittest.TestCase):
    @staticmethod
    def _write_tiff(path: Path, width: int, height: int, value: float) -> None:
        with rasterio.open(
            path,
            "w",
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

    def test_missing_band_is_rejected(self):
        with self.assertRaisesRegex(AnalysisInputError, "Missing required bands"):
            load_band_files({"green": "green.tif"})

    def test_mismatched_dimensions_are_rejected_without_resampling(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for name, shape in {
                "blue": (8, 8),
                "green": (8, 9),
                "red": (8, 8),
                "nir": (8, 8),
            }.items():
                path = root / f"{name}.tif"
                self._write_tiff(path, width=shape[1], height=shape[0], value=0.2)
                paths[name] = path
            with self.assertRaisesRegex(AnalysisInputError, "same grid"):
                load_band_files(paths)

    def test_demo_data_is_repeatable_and_unreferenced(self):
        first, first_valid, first_metadata = make_demo_bands(seed=123)
        second, _, _ = make_demo_bands(seed=123)

        np.testing.assert_array_equal(first["green"], second["green"])
        self.assertEqual(int(first_valid.sum()), 256 * 256 - 11 * 36)
        self.assertFalse(first_metadata["georeferenced"])
        self.assertIsNone(first_metadata["crs"])


if __name__ == "__main__":
    unittest.main()
