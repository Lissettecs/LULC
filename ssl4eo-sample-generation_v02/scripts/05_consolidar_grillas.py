#!/usr/bin/env python3
"""
05 — Consolidar parciales por tile en GeoPackage por huso y tamaño.

Aborta si falta algún tile listado en tiles.txt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from caracterizacion.ensamblar import consolidar_grillas
from config import params_caracterizacion as P
from utilidades import configurar_log, ultima_corrida, escribir_summary, git_hash, versiones_paquetes, corrida_caracterizacion_activa


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidar grillas caracterizadas")
    parser.add_argument("--run-dir", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir or corrida_caracterizacion_activa() or ultima_corrida(P.OUT_ROOT)
    if run_dir is None:
        print("ERROR: no hay corrida de caracterización", file=sys.stderr)
        return 1

    logger = configurar_log(run_dir, "caracterizacion")
    logger.info("Consolidando corrida: %s", run_dir)

    try:
        salidas = consolidar_grillas(run_dir, logger)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    escribir_summary(
        run_dir,
        {
            "consolidados": [str(s) for s in salidas],
            "versiones": versiones_paquetes(),
            "git_hash": git_hash(),
        },
    )
    logger.info("Consolidación OK (%d archivos)", len(salidas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
