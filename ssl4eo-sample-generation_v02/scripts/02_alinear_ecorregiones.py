#!/usr/bin/env python3
"""
02 — Alinear raster de ecorregiones a la grilla del landcover.

Recorte por ventana (sin reproyectar). Las islas E16/E17 quedan fuera del extent
continental del landcover.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from caracterizacion.alinear import alinear_ecorregiones_a_landcover
from caracterizacion.verificar import verificar_grillas_raster
from config import params_caracterizacion as P
from utilidades import configurar_log


def main() -> int:
    parser = argparse.ArgumentParser(description="Alinear ecorregiones → landcover")
    parser.add_argument("--anio-ref", type=int, default=2016)
    parser.add_argument("--salida", type=Path, default=P.ECO_RASTER)
    parser.add_argument("--forzar", action="store_true", help="Sobrescribir raster alineado")
    args = parser.parse_args()

    logger = configurar_log(P.OUT_ROOT / "_alineacion", "alineacion")
    lulc_ref = P.LULC_DIR / P.LULC_PATRON.format(year=args.anio_ref)

    if args.salida.is_file() and args.forzar:
        args.salida.unlink()

    alinear_ecorregiones_a_landcover(P.ECO_RASTER_ORIGINAL, lulc_ref, args.salida, logger)
    verif = verificar_grillas_raster(args.salida, lulc_ref, logger)
    return 0 if verif.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
