
from pathlib import Path
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from scipy import ndimage

ROOT = Path(r"D:\HydroScan-AI")
BANDS = ROOT / "HydroScan_clipped"
OUTPUT = ROOT / "river_corridor_mask.tif"

# Read the same aligned 512 x 512 satellite crop.
with rasterio.open(BANDS / "B04_clip.tif") as ds:
    red = ds.read(1).astype(np.float32)
    profile = ds.profile.copy()
    transform = ds.transform
    crs = ds.crs

with rasterio.open(BANDS / "B03_clip.tif") as ds:
    green = ds.read(1).astype(np.float32)

with rasterio.open(BANDS / "B02_clip.tif") as ds:
    blue = ds.read(1).astype(np.float32)

def stretch(band):
    lo, hi = np.percentile(band, [2, 98])
    return np.clip((band - lo) / max(hi - lo, 1), 0, 1)

rgb = np.dstack([stretch(red), stretch(green), stretch(blue)])

fig, ax = plt.subplots(figsize=(10, 10))
ax.imshow(rgb, origin="upper")
ax.set_title(
    "Click along the CENTER of the Godavari River, from one end to the other.\n"
    "Click several points along every bend. Press ENTER when finished."
)
ax.set_xlim(-0.5, 511.5)
ax.set_ylim(511.5, -0.5)
ax.set_xlabel("Column (pixel)")
ax.set_ylabel("Row (pixel)")
plt.tight_layout()

print("Click points along the visible river centreline.")
print("Follow the river carefully; press ENTER to finish.")
points = plt.ginput(n=-1, timeout=0)
plt.close(fig)

if len(points) < 2:
    raise SystemExit("Not enough points. Run again and click at least 2 points.")

# Create a line along the manually selected river centreline.
line = np.zeros((512, 512), dtype=bool)
for (x1, y1), (x2, y2) in zip(points[:-1], points[1:]):
    steps = max(int(np.hypot(x2 - x1, y2 - y1)), 1)
    xs = np.rint(np.linspace(x1, x2, steps + 1)).astype(int)
    ys = np.rint(np.linspace(y1, y2, steps + 1)).astype(int)
    inside = (xs >= 0) & (xs < 512) & (ys >= 0) & (ys < 512)
    line[ys[inside], xs[inside]] = True

# Expand the line by 6 pixels (about 60 m on each side at 10 m resolution).
yy, xx = np.ogrid[-6:7, -6:7]
kernel = (xx * xx + yy * yy) <= 36
corridor = ndimage.binary_dilation(line, structure=kernel)

# Save a georeferenced mask: 1 = inside corridor, 0 = outside.
profile.update(
    driver="GTiff",
    count=1,
    dtype="uint8",
    nodata=None,
    compress="lzw"
)

with rasterio.open(OUTPUT, "w", **profile) as dst:
    dst.write(corridor.astype(np.uint8), 1)
    dst.set_band_description(1, "Manually reviewed river corridor: 1=in, 0=out")

print(f"Saved: {OUTPUT}")
print(f"Corridor pixels: {int(corridor.sum())}")
print(f"CRS: {crs}")
print(f"Transform: {transform}")

plt.figure(figsize=(9, 8))
plt.imshow(rgb, origin="upper")
plt.imshow(np.ma.masked_where(~corridor, corridor),
           origin="upper", alpha=0.45, cmap="winter")
plt.title("Review the corridor overlay before using it")
plt.xlim(-0.5, 511.5)
plt.ylim(511.5, -0.5)
plt.show()
