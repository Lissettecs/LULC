"""Input validation and raster loading for segment labeling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window


@dataclass(frozen=True)
class RasterPair:
    segments: np.ndarray
    c2: np.ndarray
    transform: rasterio.Affine
    crs: str
    profile: dict


def _read_window(
    path: Path,
    window: Window | None,
) -> tuple[np.ndarray, rasterio.Affine, dict]:
    with rasterio.open(path) as src:
        if window is None:
            data = src.read(1)
            transform = src.transform
        else:
            data = src.read(1, window=window)
            transform = src.window_transform(window)

        profile = src.profile.copy()
        crs = src.crs.to_string() if src.crs else ""
        dtype = src.dtypes[0]

    if not np.issubdtype(np.dtype(dtype), np.integer):
        raise TypeError(f"{path} must be integer dtype, got {dtype}.")

    return data, transform, {"crs": crs, "transform": transform, "dtype": dtype}


def validate_same_grid(
    seg_path: Path,
    c2_path: Path,
    window: Window | None,
) -> None:
    """Abort if segment and C2 rasters are not on the same grid."""
    with rasterio.open(seg_path) as seg_src, rasterio.open(c2_path) as c2_src:
        if seg_src.crs != c2_src.crs:
            raise ValueError(
                f"CRS mismatch: segments={seg_src.crs}, c2={c2_src.crs}. "
                "Resample C2 separately with nearest-neighbor before running."
            )

        if window is None:
            if (seg_src.width, seg_src.height) != (c2_src.width, c2_src.height):
                raise ValueError(
                    f"Shape mismatch: segments=({seg_src.width}, {seg_src.height}), "
                    f"c2=({c2_src.width}, {c2_src.height})."
                )
            if seg_src.transform != c2_src.transform:
                raise ValueError(
                    "Affine transform mismatch between segment and C2 rasters. "
                    "Do not auto-resample; align grids first."
                )
            if seg_src.res != c2_src.res:
                raise ValueError(
                    f"Resolution mismatch: segments={seg_src.res}, c2={c2_src.res}."
                )
        else:
            for src in (seg_src, c2_src):
                if window.col_off + window.width > src.width:
                    raise ValueError(f"Window exceeds width for {src.name}.")
                if window.row_off + window.height > src.height:
                    raise ValueError(f"Window exceeds height for {src.name}.")


def load_raster_pair(
    seg_path: Path,
    c2_path: Path,
    *,
    subset: bool,
    subset_window: tuple[int, int, int, int] | None,
) -> RasterPair:
    """Load aligned segment and C2 arrays with explicit validation."""
    seg_path = seg_path.expanduser().resolve()
    c2_path = c2_path.expanduser().resolve()

    assert seg_path.is_file(), f"Missing segments raster: {seg_path}"
    assert c2_path.is_file(), f"Missing C2 raster: {c2_path}"

    window = None
    if subset:
        if subset_window is None:
            raise ValueError("SUBSET=True requires SUBSET_WINDOW.")
        col_off, row_off, width, height = subset_window
        window = Window(col_off, row_off, width, height)

    validate_same_grid(seg_path, c2_path, window)

    segments, transform, seg_meta = _read_window(seg_path, window)
    c2, c2_transform, c2_meta = _read_window(c2_path, window)

    if transform != c2_transform:
        raise ValueError("Window transforms differ between segment and C2 rasters.")

    return RasterPair(
        segments=segments,
        c2=c2,
        transform=transform,
        crs=seg_meta["crs"],
        profile={"transform": transform, "crs": seg_meta["crs"]},
    )
