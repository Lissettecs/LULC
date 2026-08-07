#!/usr/bin/env python3
"""
04 — Caracterizar un tile MGRS.

Uso interactivo / tarea del array SLURM. Escribe por_tile/{TILE}_{side}x{side}.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from caracterizacion.ensamblar import procesar_tile
from caracterizacion.grilla import cargar_tiles_mgrs
from config import params_caracterizacion as P
from utilidades import configurar_log, resolver_run_dir, escribir_summary, git_hash, versiones_paquetes, corrida_caracterizacion_activa


def main() -> int:
    parser = argparse.ArgumentParser(description="Caracterizar grillas de un tile MGRS")
    parser.add_argument("--tile", required=True, help="Nombre tile, ej. 18HYD")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rect-side", type=int, action="append", dest="rect_sides")
    args = parser.parse_args()

    resume = args.resume or P.RESUME
    run_dir = args.run_dir or corrida_caracterizacion_activa() or resolver_run_dir(P.OUT_ROOT, P.RUN_TAG, resume)
    logger = configurar_log(run_dir, "caracterizacion")

    gdf = cargar_tiles_mgrs()
    fila = gdf[gdf["tile_name"] == args.tile]
    if fila.empty:
        logger.error("Tile no encontrado: %s", args.tile)
        return 1

    rect_sides = args.rect_sides or P.RECT_SIDES
    salidas = procesar_tile(args.tile, fila.geometry.iloc[0], run_dir, logger, rect_sides)
    escribir_summary(
        run_dir,
        {
            "tile": args.tile,
            "salidas": [str(s) for s in salidas],
            "versiones": versiones_paquetes(),
            "git_hash": git_hash(),
        },
        f"summary_tile_{args.tile}.json",
    )
    logger.info("Tile %s completado (%d archivos)", args.tile, len(salidas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
