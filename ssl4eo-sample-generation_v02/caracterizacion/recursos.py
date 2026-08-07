"""Estimación de memoria por tile antes de lanzar el array SLURM."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask, geometry_window
from shapely.geometry import mapping

from config import params_caracterizacion as P


@dataclass
class EstimacionTile:
    tile: str
    ventana_ancho_px: int
    ventana_alto_px: int
    n_rect_2x2: int
    n_rect_3x3: int
    mem_ventana_mb: float
    mem_pico_estimada_mb: float


def _ventana_tile_px(tile_geom, ref_path: str) -> tuple[int, int, int, int]:
    """Retorna col_off, row_off, width, height en píxeles del raster."""
    with rasterio.open(ref_path) as src:
        win = geometry_window(src, [mapping(tile_geom)], pad_x=0, pad_y=0)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        return int(win.col_off), int(win.row_off), int(win.width), int(win.height)


def estimar_tile(tile_name: str, tile_geom) -> EstimacionTile:
    ref = str(P.LULC_DIR / P.LULC_PATRON.format(year=P.START_YEAR))
    col_off, row_off, w, h = _ventana_tile_px(tile_geom, ref)
    n_years = P.END_YEAR - P.START_YEAR + 1

    # stack 30 m int16 + eco int32 + stack_stats + overhead rasterio
    px = w * h
    mem_stack_mb = px * n_years * 2 / 1e6
    mem_eco_mb = px * 4 / 1e6
    mem_stats_mb = px * n_years * 4 / (P.PIXEL_M ** 2) / 1e6  # aprox escala 300 m
    mem_pico = (mem_stack_mb + mem_eco_mb + mem_stats_mb) * 1.5 + 512  # 512 MB base

    from caracterizacion.grilla import construir_rectangulos_tile

    with rasterio.open(ref) as src:
        t, crs = src.transform, src.crs.to_string()
        width, height = src.width, src.height
    n2 = len(construir_rectangulos_tile(tile_geom, tile_name, 2, t, crs, width, height))
    n3 = len(construir_rectangulos_tile(tile_geom, tile_name, 3, t, crs, width, height))

    return EstimacionTile(
        tile=tile_name,
        ventana_ancho_px=w,
        ventana_alto_px=h,
        n_rect_2x2=n2,
        n_rect_3x3=n3,
        mem_ventana_mb=round(mem_stack_mb, 1),
        mem_pico_estimada_mb=round(mem_pico, 1),
    )


def verificar_todos_los_tiles(husos: list[int] | None = None, limite_mb: float = 10_240) -> list[EstimacionTile]:
    from caracterizacion.grilla import cargar_tiles_mgrs

    gdf = cargar_tiles_mgrs(husos)
    estimaciones = [estimar_tile(row.tile_name, row.geometry) for row in gdf.itertuples()]
    return sorted(estimaciones, key=lambda e: e.mem_pico_estimada_mb, reverse=True)


def tiles_sobre_limite(husos: list[int] | None = None, limite_mb: float = 10_240) -> list[EstimacionTile]:
    return [e for e in verificar_todos_los_tiles(husos, limite_mb) if e.mem_pico_estimada_mb > limite_mb]
