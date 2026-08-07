#!/usr/bin/env python
"""04 — Caracteriza una carta CIM, para cada tamaño de celda.

Es la unidad de paralelización: se puede lanzar una por tarea de un array. Cada
carta lee su ventana una sola vez y escribe por_carta/{CARTA}_{escala}.parquet.

Uso:
    python scripts/04_caracterizar_carta.py --carta SI-19-Z-B
    python scripts/04_caracterizar_carta.py --indice 7      # línea 7 de cartas.txt
    python scripts/04_caracterizar_carta.py --carta SI-19-Z-B --escala 2x2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from caracterizacion.ensamblar import procesar_carta  # noqa: E402
from config import params_caracterizacion as PC  # noqa: E402
from config import params_grilla as PG  # noqa: E402
from utilidades import (  # noqa: E402
    agregar_auditoria,
    configurar_log,
    corrida_caracterizacion_activa,
    resolver_run_dir,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Caracteriza una carta CIM")
    ap.add_argument("--carta")
    ap.add_argument("--indice", type=int, help="Línea (1-based) de cartas.txt")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--escala", action="append", dest="escalas",
                    help="'2x2', '3x3' o el lado en píxeles; repetible")
    ap.add_argument("--resume", action=argparse.BooleanOptionalAction, default=PC.RESUME,
                    help="Omite cartas ya escritas; --no-resume las recalcula")
    args = ap.parse_args()

    run_dir = (
        args.run_dir
        or corrida_caracterizacion_activa()
        or resolver_run_dir(PC.OUT_ROOT, PC.RUN_TAG, args.resume)
    )
    logger = configurar_log(run_dir, "caracterizacion")

    carta = args.carta
    if carta is None:
        if args.indice is None:
            logger.error("Indique --carta o --indice")
            return 1
        lineas = (run_dir / "cartas.txt").read_text().split()
        if not 1 <= args.indice <= len(lineas):
            logger.error("Índice %d fuera de rango (1..%d)", args.indice, len(lineas))
            return 1
        carta = lineas[args.indice - 1]

    celdas_px = (
        [PG.desde_etiqueta(e) for e in args.escalas] if args.escalas else PC.CELDAS_PX
    )
    for celda_px in celdas_px:
        escala = PG.etiqueta(celda_px)
        t0 = time.time()
        try:
            salida = procesar_carta(carta, celda_px, run_dir, logger, args.resume)
            estado = "ok" if salida else "vacio"
        except Exception as exc:  # se audita y se sigue con el resto
            logger.exception("[%s %s] error: %s", carta, escala, exc)
            estado, salida = "error", None
        agregar_auditoria(run_dir, {
            "unidad": f"{carta}_{escala}",
            "carta": carta,
            "escala": escala,
            "celda_px": celda_px,
            "estado": estado,
            "salida": str(salida) if salida else "",
            "segundos": round(time.time() - t0, 2),
        })
        if estado == "error":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
