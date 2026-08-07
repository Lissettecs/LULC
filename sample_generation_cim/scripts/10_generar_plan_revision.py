#!/usr/bin/env python3
"""
10 — Deriva años de revisión (rev_year1/2/3) sobre una selección existente.

No recaracteriza ni reselecciona. Escribe salidas en un subdirectorio nuevo.

Uso:
  python scripts/10_generar_plan_revision.py --seleccion 20260727_1340
  python scripts/10_generar_plan_revision.py --seleccion /ruta/a/02_seleccion/TAG
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_plan_revision as P
from plan_revision.exportar import ejecutar_plan_revision


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Genera plan de años de revisión sobre selección SSL4EO v02",
    )
    p.add_argument(
        "--seleccion",
        default=P.SEL_RUN_TAG,
        help="Tag o ruta de corrida en 02_seleccion/",
    )
    p.add_argument(
        "--timestamp",
        default=None,
        help="Sufijo del directorio plan_revision_{timestamp} (default: ahora)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directorio de salida explícito (opcional)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    dest = ejecutar_plan_revision(
        args.seleccion,
        timestamp=args.timestamp,
        out_dir=args.out_dir,
    )
    print(f"Reporte: {dest / 'reporte_plan_revision.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
