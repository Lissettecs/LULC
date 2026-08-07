"""Lectura del ráster 4326 por ventana y remuestreo nearest a malla UTM."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
import geopandas as gpd

from config import params_caracterizacion as P


def _bbox_4326_de_geom_utm(geom_utm, crs_utm: str, pad_deg: float = 0.002):
    g = gpd.GeoSeries([geom_utm], crs=crs_utm).to_crs(4326).iloc[0]
    minx, miny, maxx, maxy = g.bounds
    return (minx - pad_deg, miny - pad_deg, maxx + pad_deg, maxy + pad_deg)


def _ventana_desde_bbox(src: rasterio.DatasetReader, bbox_4326) -> rasterio.windows.Window:
    from rasterio.windows import from_bounds as win_from_bounds

    minx, miny, maxx, maxy = bbox_4326
    win = win_from_bounds(minx, miny, maxx, maxy, transform=src.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    row_off = max(0, int(win.row_off))
    col_off = max(0, int(win.col_off))
    row_end = min(src.height, int(win.row_off + win.height))
    col_end = min(src.width, int(win.col_off + win.width))
    return rasterio.windows.Window(col_off, row_off, col_end - col_off, row_end - row_off)


def remuestrear_a_utm(
    src_arr: np.ndarray,
    src_transform,
    src_crs,
    geom_utm,
    crs_utm: str,
    n_px: int,
    res_m: float = P.PIXEL_M,
) -> tuple[np.ndarray, object]:
    minx, miny, maxx, maxy = geom_utm.bounds
    dst_transform = from_bounds(minx, miny, minx + n_px * res_m, miny + n_px * res_m, n_px, n_px)
    dst = np.zeros((n_px, n_px), dtype=src_arr.dtype)
    reproject(
        source=src_arr,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=crs_utm,
        resampling=Resampling.nearest,
        src_nodata=0,
        dst_nodata=0,
    )
    return dst, dst_transform


def leer_stack_tile_optimizado(
    celdas: list,
    crs_utm: str,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Lee una ventana 4326 por tile y remuestrea cada celda a UTM."""
    if not celdas:
        return {}
    from shapely.ops import unary_union

    union = unary_union([c.geometry for c in celdas])
    bbox = _bbox_4326_de_geom_utm(union, crs_utm, pad_deg=0.005)
    years = range(P.START_YEAR, P.END_YEAR + 1)

    with rasterio.open(P.LULC_DIR / P.LULC_PATRON.format(year=P.START_YEAR)) as ref:
        win = _ventana_desde_bbox(ref, bbox)
        win_transform = ref.window_transform(win)
        src_crs = ref.crs

    stacks_src: list[np.ndarray] = []
    for year in years:
        with rasterio.open(P.LULC_DIR / P.LULC_PATRON.format(year=year)) as src:
            stacks_src.append(src.read(1, window=win))
    with rasterio.open(P.ECO_RASTER) as eco_src:
        eco_src_arr = eco_src.read(1, window=win)

    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for celda in celdas:
        n_px = celda.width_px
        capas = []
        for arr in stacks_src:
            utm, _ = remuestrear_a_utm(arr, win_transform, src_crs, celda.geometry, crs_utm, n_px)
            capas.append(utm)
        eco_utm, _ = remuestrear_a_utm(
            eco_src_arr, win_transform, src_crs, celda.geometry, crs_utm, n_px
        )
        out[celda.grid_id] = (np.stack(capas, axis=0), eco_utm)
    return out
