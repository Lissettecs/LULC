"""Align C2 landcover to the segment raster grid."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject


def read_aligned_landcover(landcover_path: Path, ref_profile: dict) -> np.ndarray:
    height = ref_profile["height"]
    width = ref_profile["width"]
    dest = np.zeros((height, width), dtype=np.int32)

    with rasterio.open(landcover_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.nearest,
            src_nodata=0,
            dst_nodata=0,
        )
    return dest


leer_landcover_alineado = read_aligned_landcover
