#!/usr/bin/env python3
"""
06 — Presupuesto de selección (punto de control, dry-run).

Imprime universo local, modos y cuotas por ecorregión. No escribe selección final.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_seleccion as P
from seleccion.presencia import cargar_matriz_presencia, imprimir_universo, universo_local
from seleccion.presupuesto import repartir_presupuesto, validar_presupuesto_global


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run presupuesto de selección")
    parser.add_argument("--matriz", type=Path, default=P.MATRIZ_PRESENCIA)
    parser.add_argument("--eco", type=int, action="append", dest="ecos")
    args = parser.parse_args()

    if not args.matriz.is_file():
        print(f"ERROR: matriz de presencia no encontrada: {args.matriz}", file=sys.stderr)
        return 1

    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("presupuesto")

    matriz = cargar_matriz_presencia(args.matriz)
    ecos = args.ecos or P.ECORREGIONES
    validar_presupuesto_global(len(ecos), logger)

    for eco_id in ecos:
        u = universo_local(eco_id, matriz, logger)
        imprimir_universo(eco_id, u, logger)

    cuotas = repartir_presupuesto(matriz, logger)
    print("\n── Resumen cuotas (primeras 20 filas) ──")
    print(cuotas.head(20).to_string(index=False))
    print(f"\nTotal filas cuota: {len(cuotas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
