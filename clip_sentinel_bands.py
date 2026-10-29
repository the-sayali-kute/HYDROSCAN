
from pathlib import Path
import rasterio
from rasterio.warp import transform
from rasterio.windows import Window

# Folder containing the original Sentinel-2 JP2 bands
input_folder = Path(
    r"D:\S2A_MSIL2A_20260604T053241_N0512_R105_T43QCC_20260604T090112.SAFE\GRANULE\L2A_T43QCC_A057188_20260604T053243\IMG_DATA\R10m"
)

# New folder for clipped files
output_folder = Path(r"D:\HydroScan-AI\HydroScan_clipped")
output_folder.mkdir(parents=True, exist_ok=True)

# Approximate Godavari monitoring location near Hanuman Ghat, Nashik
longitude = 73.78367
latitude = 20.00910

# Convert location from latitude/longitude to the raster CRS
with rasterio.open(next(input_folder.glob("*_B02_10m.jp2"))) as src:
    eastings, northings = transform(
        "EPSG:4326", src.crs, [longitude], [latitude]
    )
    center_x = eastings[0]
    center_y = northings[0]

    crop_size = 512
    col_start = round((center_x - src.bounds.left) / 10) - crop_size // 2
    row_start = round((src.bounds.top - center_y) / 10) - crop_size // 2

    window = Window(col_start, row_start, crop_size, crop_size)

    # Confirm crop is inside the original image
    if (
        col_start < 0
        or row_start < 0
        or col_start + crop_size > src.width
        or row_start + crop_size > src.height
    ):
        raise ValueError("Crop falls outside the satellite image.")

    print("Crop center in raster coordinates:", center_x, center_y)
    print("Crop window:", window)

# Process all four bands using the exact same window
for band in ["B02", "B03", "B04", "B08"]:
    matches = list(input_folder.glob(f"*_{band}_10m.jp2"))

    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one {band} JP2 file, found {len(matches)}."
        )

    input_file = matches[0]
    output_file = output_folder / f"{band}_clip.tif"

    with rasterio.open(input_file) as src:
        data = src.read(window=window)

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            width=crop_size,
            height=crop_size,
            transform=src.window_transform(window),
            compress="deflate",
            tiled=True
        )

        with rasterio.open(output_file, "w", **profile) as dst:
            dst.write(data)

    print(f"Saved: {output_file}")

print("\nAll four bands clipped successfully.")
print("Output folder:", output_folder)
