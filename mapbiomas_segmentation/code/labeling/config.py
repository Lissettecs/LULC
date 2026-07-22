"""Editable configuration for segment labeling with MapBiomas Collection 2."""

from __future__ import annotations

from pathlib import Path

# --- Cluster data root ---
DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")

# --- Inputs (defaults: 18HYD watershed) ---
SEGMENTS_RASTER = DATA_ROOT / "tile_18HYD_2010/watershed_labels.tif"
C2_RASTER = DATA_ROOT / "landcover_tiles/18HYD_classification_2010.tif"

# --- Subset for calibration (phase 1) ---
SUBSET = True
SUBSET_WINDOW: tuple[int, int, int, int] | None = (0, 0, 2000, 2000)

# --- Thresholds ---
TAU_PURITY: float | None = None
KAPPA_COVERAGE = 0.50
N_MIN_PIXELS = 10
TAU_PERCENTILE = "p75"

# --- Sentinel labels (uint8) ---
LABEL_MIXED = 255
LABEL_NODATA = 254

# --- C2 values treated as no-data ---
C2_NODATA: list[int] = [0]

# --- Outputs ---
OUT_DIR = DATA_ROOT / "labeling"
WRITE_RASTER = False
BACKGROUND_SEGMENT_ID = 0

# --- Batch tiles and methods ---
TILES = ("18HYD", "18FXH", "18GXP", "19HCD", "19JCJ", "19KDU")
METHODS = ("watershed", "slic", "felzenszwalb")
YEAR = 2010
