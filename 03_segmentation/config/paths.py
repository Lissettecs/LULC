"""Year-parameterized paths for masked mosaics and segmentation outputs."""

from __future__ import annotations

import os
from pathlib import Path

MAPBIOMAS_ROOT = Path(os.environ.get("MAPBIOMAS_ROOT", "/home/lserey/mapbiomas_land"))
TMP_ROOT = MAPBIOMAS_ROOT / "tmp"
PROD_ROOT = MAPBIOMAS_ROOT / "prod"

MOSAIC_FILENAME = "TMP-CHILE-{tile}-{year}-SBAND-184B_masked.tif"


def mosaic_root(year: int) -> Path:
    """Root of masked mosaics for a year (e.g. mask_mosaic_2015)."""
    return TMP_ROOT / f"mask_mosaic_{year}"


def output_dir(year: int) -> Path:
    """Segmentation output root for a revision year."""
    return PROD_ROOT / f"segmentacion_slic_rev{year}"


def masked_mosaic_path(mosaic_root_dir: Path, tile: str, year: int) -> Path | None:
    """Path to masked GeoTIFF for a tile, or None if missing."""
    tile_dir = mosaic_root_dir / tile.upper()
    if not tile_dir.is_dir():
        return None
    matches = sorted(tile_dir.glob(MOSAIC_FILENAME.format(tile=tile.upper(), year=year)))
    if len(matches) != 1:
        return None
    return matches[0]


def rect_dir(output_root: Path, tile: str, grid_id: str) -> Path:
    return output_root / tile.upper() / grid_id


def summary_path(output_root: Path, tile: str, grid_id: str) -> Path:
    return rect_dir(output_root, tile, grid_id) / f"{grid_id}_summary.json"
