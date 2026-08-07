#!/usr/bin/env python
"""03 — Abre una corrida y escribe la lista de cartas a caracterizar.

La lista es el índice del array de tareas: la tarea N procesa la carta de la
línea N. Deja además la marca de corrida activa para que 04 y 05 la encuentren
sin pasarles --run-dir.

Uso:
    python scripts/03_generar_lista_cartas.py
    python scripts/03_generar_lista_cartas.py --run-tag prueba_norte --carta SI-19-Z-B
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config import params_caracterizacion as PC  # noqa: E402
from grilla.construir import cargar_grilla  # noqa: E402
from utilidades import (  # noqa: E402
    configurar_log,
    escribir_summary,
    git_hash,
    resolver_run_dir,
    versiones_paquetes,
)

MARCA = REPO_ROOT / ".ultima_corrida_caract"


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara la corrida de caracterización")
    ap.add_argument("--run-tag", default=PC.RUN_TAG or None)
    ap.add_argument("--resume", action=argparse.BooleanOptionalAction, default=PC.RESUME,
                    help="Permite reabrir una corrida existente; --no-resume exige que sea nueva")
    ap.add_argument("--carta", action="append", dest="cartas",
                    help="Restringe la corrida a estas cartas; repetible")
    args = ap.parse_args()

    run_dir = resolver_run_dir(PC.OUT_ROOT, args.run_tag, args.resume)
    logger = configurar_log(run_dir, "caracterizacion")

    cartas = sorted(cargar_grilla(PC.CELDAS_PX[0])["cim_name"].unique())
    if args.cartas:
        pedidas = set(args.cartas)
        faltan = pedidas - set(cartas)
        if faltan:
            logger.error("Cartas inexistentes en la grilla: %s", ", ".join(sorted(faltan)))
            return 1
        cartas = [c for c in cartas if c in pedidas]

    lista = run_dir / "cartas.txt"
    lista.write_text("\n".join(cartas) + "\n")
    MARCA.write_text(str(run_dir) + "\n")

    escribir_summary(run_dir, {
        "run_dir": str(run_dir),
        "n_cartas": len(cartas),
        "celdas_px": PC.CELDAS_PX,
        "anios": [PC.START_YEAR, PC.END_YEAR],
        "stats_bloque_px": PC.STATS_BLOQUE_PX,
        "versiones": versiones_paquetes(),
        "git_hash": git_hash(),
    }, "summary_corrida.json")

    logger.info("Corrida %s: %d cartas x %s px", run_dir.name, len(cartas), PC.CELDAS_PX)
    print(f"\nrun_dir : {run_dir}")
    print(f"cartas  : {lista}  ({len(cartas)} líneas)")
    print(f"\nPara caracterizar todas en serie:")
    print(f"  while read c; do python scripts/04_caracterizar_carta.py --carta $c; done < {lista}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
