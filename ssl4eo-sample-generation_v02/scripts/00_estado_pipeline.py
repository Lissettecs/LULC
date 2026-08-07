#!/usr/bin/env python3
"""
00 — Estado del pipeline v02.

Muestra corridas existentes y completitud de tiles / consolidación / selección.
No escribe datos.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_caracterizacion as PC
from config import params_seleccion as PS


def _estado_caracterizacion() -> None:
    root = PC.OUT_ROOT
    print("\n=== 01 CARACTERIZACIÓN ===")
    if not root.is_dir():
        print("  (sin corridas)")
        return
    for run in sorted(root.iterdir()):
        if not run.is_dir():
            continue
        por_tile = run / "por_tile"
        n_parcial = len(list(por_tile.glob("*.parquet"))) if por_tile.is_dir() else 0
        consol = list((run / "consolidado").glob("*.gpkg")) if (run / "consolidado").is_dir() else []
        print(f"  {run.name}: {n_parcial} parciales | {len(consol)} consolidados")


def _estado_seleccion() -> None:
    root = PS.OUT_ROOT
    print("\n=== 02 SELECCIÓN ===")
    if not root.is_dir():
        print("  (sin corridas)")
        return
    for run in sorted(root.iterdir()):
        if not run.is_dir():
            continue
        nac = run / "seleccion_nacional.gpkg"
        print(f"  {run.name}: {'OK' if nac.is_file() else 'incompleta'}")


def main() -> int:
    print("Pipeline SSL4EO v02 — estado")
    _estado_caracterizacion()
    _estado_seleccion()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
