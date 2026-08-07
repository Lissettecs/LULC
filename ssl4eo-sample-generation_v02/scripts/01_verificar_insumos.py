#!/usr/bin/env python3
"""
01 — Verificación de insumos (bloqueante).

Comprueba: vector MGRS, 26 rasters landcover, ecorregiones alineadas vs landcover.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from caracterizacion.verificar import (
    metadatos_dict,
    verificar_anios,
    verificar_grillas_raster,
    verificar_mgrs,
)
from config import params_caracterizacion as P
from utilidades import configurar_log, escribir_summary, git_hash, versiones_paquetes


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificar insumos del pipeline v02")
    parser.add_argument("--eco-raster", type=Path, default=P.ECO_RASTER)
    parser.add_argument("--anio-ref", type=int, default=2016)
    args = parser.parse_args()

    log_dir = P.OUT_ROOT / "_verificacion"
    logger = configurar_log(log_dir, "verificacion")

    errores = []
    try:
        verificar_mgrs(P.MGRS_VECTOR, P.MGRS_CAMPO_NOMBRE)
        logger.info("Vector MGRS OK: %s", P.MGRS_VECTOR)
    except (FileNotFoundError, ValueError) as e:
        errores.append(str(e))
        logger.error("%s", e)

    faltantes = verificar_anios(P.LULC_DIR, P.LULC_PATRON, P.START_YEAR, P.END_YEAR)
    if faltantes:
        msg = f"Rasters landcover faltantes: {faltantes}"
        errores.append(msg)
        logger.error(msg)
    else:
        logger.info("26 rasters landcover OK (%d–%d)", P.START_YEAR, P.END_YEAR)

    lulc_ref = P.LULC_DIR / P.LULC_PATRON.format(year=args.anio_ref)
    if not args.eco_raster.is_file():
        errores.append(f"Ecorregiones no encontradas: {args.eco_raster}. Ejecute script 02.")
        logger.error(errores[-1])
    elif not lulc_ref.is_file():
        errores.append(f"Landcover referencia no encontrado: {lulc_ref}")
    else:
        verif = verificar_grillas_raster(args.eco_raster, lulc_ref, logger)
        if not verif.ok:
            errores.append("Grillas incompatibles — ejecute scripts/02_alinear_ecorregiones.py")
        escribir_summary(
            log_dir,
            {
                "verificacion": metadatos_dict(verif),
                "versiones": versiones_paquetes(),
                "git_hash": git_hash(),
            },
        )

    if errores:
        logger.error("Verificación FALLIDA (%d errores)", len(errores))
        return 1
    logger.info("Verificación OK — listo para caracterizar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
