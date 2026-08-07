#!/usr/bin/env python3
"""
07 — Selección de rectángulos por ecorregión sobre la grilla CIM.

Requiere la caracterización consolidada (2x2 y 3x3) y la matriz de presencia.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_caracterizacion as PC
from config import params_seleccion as P
from seleccion.cargar import cargar_parejas
from seleccion.presupuesto import repartir_presupuesto
from seleccion.presencia import cargar_matriz_presencia
from seleccion.selector import ejecutar_seleccion
from utilidades import (
    configurar_log,
    escribir_summary,
    git_hash,
    resolver_run_dir,
    ultima_corrida,
    versiones_paquetes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seleccionar celdas CIM")
    parser.add_argument("--grid-run-dir", type=Path, default=None)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    resume = args.resume or P.RESUME
    grid_run = args.grid_run_dir
    if grid_run is None:
        tag = P.GRID_RUN_TAG
        grid_run = (PC.OUT_ROOT / tag) if tag else ultima_corrida(PC.OUT_ROOT)
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

    grilla_hom, grilla_mix = cargar_parejas(grid_run)
    logger.info(
        "Grillas cargadas: %d celdas 2x2 + %d celdas 3x3 (EPSG:4326)",
        len(grilla_hom), len(grilla_mix),
    )

    seleccion = ejecutar_seleccion(
        grilla_hom, grilla_mix, presupuesto, run_dir, logger, matriz=matriz
    )
    escribir_summary(
        run_dir,
        {
            "grid_run": str(grid_run),
            "n_seleccionados": len(seleccion),
            "presupuesto_segmentos_total": P.PRESUPUESTO_SEGMENTOS_TOTAL,
            "base_cuota": P.BASE_CUOTA,
            "pixel_m": P.PIXEL_M,
            "seg_por_mpx": P.SEG_POR_MPX,
            "celda_px_cuota": P.CELDA_PX_CUOTA,
            "segmentos_por_1000ha": P.SEGMENTOS_POR_1000HA,
            "area_km2_cuota": P.AREA_KM2_CUOTA,
            "rendimiento_seg_ok": P.RENDIMIENTO_SEG_OK,
            "crs_salida": P.CRS_SALIDA,
            "versiones": versiones_paquetes(),
            "git_hash": git_hash(),
        },
    )
    logger.info("Selección escrita en %s", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
