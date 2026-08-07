"""Construcción de grilla cuadrada en UTM (metros)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import box

from config import params_caracterizacion as P


@dataclass
class CeldaUTM:
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
    col_off: int
    row_off: int
    height_px: int
    width_px: int
    area_km2: float
    geometry: object


def _huso_tile(nombre: str) -> int:
    return int(nombre[:2])


def construir_grilla_utm_tile(
    tile_geom_4326,
    tile_name: str,
    rect_side: int,
) -> list[CeldaUTM]:
    """Genera celdas cuadradas en el UTM nativo del tile."""
    huso = _huso_tile(tile_name)
    epsg = P.UTM_EPSG[huso]
    crs = f"EPSG:{epsg}"
    lado = float(P.LADO_M[rect_side])
    n_px = rect_side * P.CHIP_PX
    grid_mode = "homogeneo" if rect_side <= 2 else "mixto"
    ox, oy = P.ORIGEN_MALLA_XY[huso]

    tile_utm = (
        gpd.GeoDataFrame(geometry=[tile_geom_4326], crs="EPSG:4326")
        .to_crs(epsg)
        .geometry.iloc[0]
    )
    minx, miny, maxx, maxy = tile_utm.bounds

    c0 = int(math.floor((minx - ox) / lado))
    c1 = int(math.ceil((maxx - ox) / lado))
    r0 = int(math.floor((miny - oy) / lado))
    r1 = int(math.ceil((maxy - oy) / lado))

    celdas: list[CeldaUTM] = []
    for ri, r in enumerate(range(r0, r1)):
        for ci, c in enumerate(range(c0, c1)):
            x0 = ox + c * lado
            y0 = oy + r * lado
            geom = box(x0, y0, x0 + lado, y0 + lado)
            if not geom.intersects(tile_utm):
                continue
            inter = geom.intersection(tile_utm)
            if inter.is_empty or inter.area / geom.area < 0.999:
                continue
            grid_id = f"{tile_name}_{rect_side}x{rect_side}_c{ci:03d}_r{ri:03d}"
            celdas.append(
                CeldaUTM(
                    grid_id=grid_id,
                    rect_id=grid_id,
                    rect_side=rect_side,
                    rect_m=lado,
                    chip_px=P.CHIP_PX,
                    chip_m=float(P.CHIP_PX * P.PIXEL_M),
                    n_chips_base=rect_side * rect_side,
                    col_idx=ci,
                    row_idx=ri,
                    grid_mode=grid_mode,
                    mgrs_dom=tile_name,
                    utm_zone=huso,
                    utm_epsg=crs,
                    col_off=c,
                    row_off=r,
                    height_px=n_px,
                    width_px=n_px,
                    area_km2=lado * lado / 1e6,
                    geometry=geom,
                )
            )
    return celdas
