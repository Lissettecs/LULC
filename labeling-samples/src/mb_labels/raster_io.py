#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GeoTIFF helpers for label generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine


def write_geotiff(
    path: Path,
    data: np.ndarray,
    *,
    transform: Affine,
    crs,
    nodata: int | float | None = 0,
    dtype: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if dtype is None:
        dtype = data.dtype.name
    profile = {
        "driver": "GTiff",
        "height": int(data.shape[0]),
        "width": int(data.shape[1]),
        "count": 1,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(dtype), 1)


def safe_grid_filename(grid_id: str) -> str:
    return grid_id.replace("/", "_").replace("\\", "_")
