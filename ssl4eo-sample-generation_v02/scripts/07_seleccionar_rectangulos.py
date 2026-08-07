#!/usr/bin/env python3
"""
07 — Selección de rectángulos por ecorregión.

Requiere consolidado de caracterización y matriz de presencia.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import geopandas as gpd
import pandas as pd

from config import params_caracterizacion as PC
from config import params_seleccion as P
from seleccion.presupuesto import repartir_presupuesto
from seleccion.presencia import cargar_matriz_presencia
from seleccion.selector import ejecutar_seleccion
from utilidades import configurar_log, resolver_run_dir, ultima_corrida, escribir_summary, git_hash, versiones_paquetes


def _cargar_consolidado(grid_run_dir: Path, huso: int, side: int) -> gpd.GeoDataFrame:
    path = grid_run_dir / "consolidado" / f"grilla_utm{huso}_{side}x{side}.gpkg"
    if not path.is_file():
        raise FileNotFoundError(f"Consolidado faltante: {path}")
    gdf = gpd.read_file(path)
    epsg = 32718 if huso == 18 else 32719
    if gdf.crs is None or gdf.crs.to_epsg() != epsg:
        gdf = gdf.to_crs(epsg)
    return gdf


def _unir_husos(partes: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    """Une husos reproyectando a EPSG:32719 solo para procesamiento interno."""
    convertidas = []
    for g in partes:
        if g.crs is None or g.crs.to_epsg() != 32719:
            convertidas.append(g.to_crs(32719))
        else:
            convertidas.append(g)
    return gpd.GeoDataFrame(pd.concat(convertidas, ignore_index=True), crs="EPSG:32719")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seleccionar rectángulos SSL4EO v02")
    parser.add_argument("--grid-run-dir", type=Path, default=None)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    resume = args.resume or P.RESUME
    grid_run = args.grid_run_dir
    if grid_run is None:
        tag = P.GRID_RUN_TAG
        grid_run = PC.OUT_ROOT / tag if tag else ultima_corrida(PC.OUT_ROOT)
    if grid_run is None or not grid_run.is_dir():
        print("ERROR: no hay corrida de caracterización", file=sys.stderr)
        return 1

    run_dir = args.run_dir or resolver_run_dir(P.OUT_ROOT, P.RUN_TAG, resume)
    logger = configurar_log(run_dir, "seleccion")

    if not P.MATRIZ_PRESENCIA.is_file():
        logger.error("Matriz de presencia faltante: %s", P.MATRIZ_PRESENCIA)
        return 1

    matriz = cargar_matriz_presencia(P.MATRIZ_PRESENCIA)
    presupuesto = repartir_presupuesto(matriz, logger)

    hom_parts = [_cargar_consolidado(grid_run, h, 2) for h in P.HUSOS]
    mix_parts = [_cargar_consolidado(grid_run, h, 3) for h in P.HUSOS]
    grilla_hom = _unir_husos(hom_parts)
    grilla_mix = _unir_husos(mix_parts)

    seleccion = ejecutar_seleccion(grilla_hom, grilla_mix, presupuesto, run_dir, logger, matriz=matriz)
    escribir_summary(
        run_dir,
        {
            "grid_run": str(grid_run),
            "n_seleccionados": len(seleccion),
            "presupuesto_segmentos_total": P.PRESUPUESTO_SEGMENTOS_TOTAL,
            "segmentos_por_1000ha": P.SEGMENTOS_POR_1000HA,
            "rendimiento_seg_ok": P.RENDIMIENTO_SEG_OK,
            "versiones": versiones_paquetes(),
            "git_hash": git_hash(),
        },
    )
    logger.info("Selección escrita en %s", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
