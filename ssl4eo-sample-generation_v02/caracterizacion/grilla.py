"""Construcción de rectángulos candidatos por tile MGRS."""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_window
from shapely.geometry import box, mapping

from config import params_caracterizacion as P


UTM_EPSG = {18: 32718, 19: 32719}


@dataclass
class RectCandidato:
    grid_id: str
    rect_id: str
    rect_side: int
    rect_m: float
    chip_px: int
    chip_m: float
    n_chips_base: int
    col_idx: int
    row_idx: int
    grid_mode: str
    mgrs_dom: str
    utm_zone: int
    utm_epsg: str
    row_off: int
    col_off: int
    height_px: int
    width_px: int
    area_km2: float


def cargar_tiles_mgrs(husos: list[int] | None = None) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(P.MGRS_VECTOR)
    campo = P.MGRS_CAMPO_NOMBRE
    gdf = gdf.rename(columns={campo: "tile_name"})
    gdf["utm_zone"] = gdf["tile_name"].str.slice(0, 2).astype(int)
    if husos:
        gdf = gdf[gdf["utm_zone"].isin(husos)]
    return gdf.reset_index(drop=True)


def _huso_desde_tile(nombre: str) -> int:
    return int(nombre[:2])


def construir_rectangulos_tile(
    tile_geom_wgs84,
    tile_name: str,
    rect_side: int,
    ref_transform: rasterio.Affine,
    ref_crs: str,
    ref_width: int,
    ref_height: int,
) -> list[RectCandidato]:
    """Genera celdas en píxeles nativos, contenidas en la intersección tile ∩ raster."""
    chip_px = P.CHIP_PX
    rect_px = rect_side * chip_px
    grid_mode = "homogeneo" if rect_side <= 2 else "mixto"
    utm_zone = _huso_desde_tile(tile_name)

    tile_gdf = gpd.GeoDataFrame([{"tile_name": tile_name}], geometry=[tile_geom_wgs84], crs="EPSG:4326")
    tile_native = tile_gdf.to_crs(ref_crs)
    tile_geom = tile_native.geometry.iloc[0]

    ref_path = P.LULC_DIR / P.LULC_PATRON.format(year=P.START_YEAR)
    with rasterio.open(ref_path) as src:
        from rasterio.features import geometry_mask

        # Ventana acotada al tile — NO rasterizar sobre el mosaico nacional completo
        win = geometry_window(src, [mapping(tile_geom)], pad_x=0, pad_y=0)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        col_base = int(win.col_off)
        row_base = int(win.row_off)
        win_w = int(win.width)
        win_h = int(win.height)
        win_transform = src.window_transform(win)
        mask = ~geometry_mask([mapping(tile_geom)], (win_h, win_w), win_transform, invert=True)
        rows, cols = np.where(mask)
        if rows.size == 0:
            return []
        r0, r1 = row_base + int(rows.min()), row_base + int(rows.max()) + 1
        c0, c1 = col_base + int(cols.min()), col_base + int(cols.max()) + 1

    # Anclar a grilla de rect_px desde esquina superior izquierda del tile en píxeles
    r0 = r0 - (r0 % rect_px)
    c0 = c0 - (c0 % rect_px)

    rects: list[RectCandidato] = []
    n_rows = (r1 - r0) // rect_px
    n_cols = (c1 - c0) // rect_px
    chip_m = chip_px * P.PIXEL_M
    rect_m = rect_px * P.PIXEL_M

    for ri in range(n_rows):
        for ci in range(n_cols):
            row_off = r0 + ri * rect_px
            col_off = c0 + ci * rect_px
            if row_off + rect_px > ref_height or col_off + rect_px > ref_width:
                continue
            # Geometría del rectángulo en CRS nativo
            x0, y0 = ref_transform * (col_off, row_off)
            x1, y1 = ref_transform * (col_off + rect_px, row_off + rect_px)
            xmin, xmax = min(x0, x1), max(x0, x1)
            ymin, ymax = min(y0, y1), max(y0, y1)
            geom = box(xmin, ymin, xmax, ymax)
            if not geom.intersects(tile_geom):
                continue
            inter = geom.intersection(tile_geom)
            if inter.is_empty:
                continue
            if inter.area / geom.area < 0.999:
                continue
            grid_id = f"{tile_name}_{rect_side}x{rect_side}_c{ci:03d}_r{ri:03d}"
            rects.append(
                RectCandidato(
                    grid_id=grid_id,
                    rect_id=grid_id,
                    rect_side=rect_side,
                    rect_m=float(rect_m),
                    chip_px=chip_px,
                    chip_m=float(chip_m),
                    n_chips_base=rect_side * rect_side,
                    col_idx=ci,
                    row_idx=ri,
                    grid_mode=grid_mode,
                    mgrs_dom=tile_name,
                    utm_zone=utm_zone,
                    utm_epsg=f"EPSG:{UTM_EPSG.get(utm_zone, 32718)}",
                    row_off=row_off,
                    col_off=col_off,
                    height_px=rect_px,
                    width_px=rect_px,
                    area_km2=inter.area / 1e6 if _es_metrico(ref_crs) else _area_km2_aprox(ref_transform, rect_px),
                )
            )
    return rects


def _es_metrico(crs: str) -> bool:
    return crs and not crs.endswith("4326")


def _area_km2_aprox(transform: rasterio.Affine, px: int) -> float:
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    lat = transform.f
    lon = transform.c
    lon2, _ = transform * (px, 0)
    _, lat2 = transform * (0, px)
    _, _, w = geod.inv(lon, lat, lon2, lat)
    _, _, h = geod.inv(lon, lat, lon, lat2)
    return abs(w * h) / 1e6


def rects_a_dataframe(rects: list[RectCandidato], crs: str) -> pd.DataFrame:
    if not rects:
        return pd.DataFrame()
    rows = []
    for r in rects:
        rows.append({k: v for k, v in r.__dict__.items() if k not in ("row_off", "col_off", "height_px", "width_px")})
    return pd.DataFrame(rows)
