#!/usr/bin/env python
"""05 — Consolida los parquet por carta en un GeoPackage nacional por tamaño de celda.

Uso:
    python scripts/05_consolidar.py
    python scripts/05_consolidar.py --escala 2x2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from caracterizacion.ensamblar import consolidar, resumen_consolidado  # noqa: E402
from config import params_caracterizacion as PC  # noqa: E402
from config import params_grilla as PG  # noqa: E402
from utilidades import (  # noqa: E402
    configurar_log,
    corrida_caracterizacion_activa,
    escribir_summary,
    git_hash,
    versiones_paquetes,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Consolida la caracterización")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--escala", action="append", dest="escalas",
                    help="'2x2', '3x3' o el lado en píxeles; repetible")
    args = ap.parse_args()

    run_dir = args.run_dir or corrida_caracterizacion_activa()
    if run_dir is None:
        print("No hay corrida activa. Ejecute scripts/03_generar_lista_cartas.py")
        return 1
    logger = configurar_log(run_dir, "caracterizacion")

    celdas_px = (
        [PG.desde_etiqueta(e) for e in args.escalas] if args.escalas else PC.CELDAS_PX
    )
    resumenes = {}
    for celda_px in celdas_px:
        escala = PG.etiqueta(celda_px)
        gpkg, csv = consolidar(celda_px, run_dir, logger)
        res = resumen_consolidado(celda_px, run_dir)
        resumenes[escala] = res

        print(f"\n=== Grilla {escala} ({celda_px} px) ===")
        for k in ("n_celdas", "n_cartas", "n_columnas",
                  "n_celdas_con_area_valida", "n_celdas_sin_area_valida",
                  "suma_pct_min", "suma_pct_max", "celdas_suma_fuera_de_rango",
                  "valid_area_pct_min", "valid_area_pct_media",
                  "celdas_valid_area_bajo_1pct", "area_ha_total", "area_valida_ha_total",
                  "ha_por_pixel_min", "ha_por_pixel_max",
                  "transition_pct_media", "stable_mode_pct_media"):
            print(f"  {k}: {res[k]}")
        print(f"  clases presentes: {res['clases_presentes']}")
        print(f"  ecorregiones    : {res['ecorregiones']}")
        print(f"  -> {gpkg}")
        print(f"  -> {csv}")

    escribir_summary(run_dir, {
        "run_dir": str(run_dir),
        "resumenes": resumenes,
        "versiones": versiones_paquetes(),
        "git_hash": git_hash(),
    }, "summary_consolidado.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
