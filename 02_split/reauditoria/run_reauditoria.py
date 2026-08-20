#!/usr/bin/env python3
"""
Reauditoría de métricas de una corrida de selección ya existente.

No recalcula selección ni caracterización. Solo lee CSV/GPKG y escribe
tablas + informe en 02_seleccion/<tag>/reauditoria_{timestamp}/.

Uso:
  python reauditoria/run_reauditoria.py \\
      --seleccion 20260724_1357 \\
      --caracterizacion 20260724_1056
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd

from config import params_seleccion as P
from reauditoria.cobertura import (
    auditoria_cobertura_corregida,
    cargar_candidatos_2x2,
    cargar_matriz,
    cargar_seleccion,
)
from reauditoria.geometrias import diagnostico_geometrias
from reauditoria.informe import generar_informe
from reauditoria.presupuesto import desambiguar_presupuesto, estado_deficit
from reauditoria.tests_offline import evaluar_tests
from utilidades import git_hash, versiones_paquetes


def main() -> int:
    parser = argparse.ArgumentParser(description="Reauditoría de métricas (sin recalcular selección)")
    parser.add_argument("--seleccion", required=True, help="TAG bajo 02_seleccion/")
    parser.add_argument("--caracterizacion", required=True, help="TAG bajo 01_caracterizacion/")
    parser.add_argument(
        "--matriz",
        type=Path,
        default=P.MATRIZ_PRESENCIA,
        help="CSV clase × ecorregión",
    )
    args = parser.parse_args()

    sel_dir = P.OUT_ROOT / args.seleccion
    car_dir = P.DATA_ROOT / "01_caracterizacion" / args.caracterizacion
    if not sel_dir.is_dir():
        print(f"ERROR: no existe {sel_dir}", file=sys.stderr)
        return 1
    if not car_dir.is_dir():
        print(f"ERROR: no existe {car_dir}", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = sel_dir / f"reauditoria_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("reauditoria")
    logger.info("Salida: %s", out_dir)
    logger.info("Selección (solo lectura): %s", sel_dir)
    logger.info("Caracterización (solo lectura): %s", car_dir)

    # ── Cargas ──
    seleccion = cargar_seleccion(sel_dir)
    logger.info("Rectángulos seleccionados: %d", len(seleccion))
    candidatos = cargar_candidatos_2x2(car_dir)
    logger.info("Candidatos 2x2: %d", len(candidatos))
    matriz = cargar_matriz(args.matriz)
    presupuesto = None
    for nom in ("presupuesto_por_ecorregion.csv", "universo_por_ecorregion.csv"):
        p = sel_dir / nom
        if p.is_file():
            presupuesto = pd.read_csv(p)
            break

    # ── A. Cobertura ──
    logger.info("A — Cobertura alcanzable / absoluta / ratio_fuentes…")
    aud, ratio_df = auditoria_cobertura_corregida(seleccion, candidatos, matriz, presupuesto)
    aud.to_csv(out_dir / "auditoria_cobertura_celdas_corregida.csv", index=False)
    ratio_df.to_csv(out_dir / "ratio_fuentes_por_celda.csv", index=False)
    n_sobre = int((pd.to_numeric(aud["pct_cubierto_alcanzable"], errors="coerce").fillna(0) > 1.0001).sum())
    if n_sobre:
        logger.error("A.1: %d celdas con pct_cubierto_alcanzable > 100 %% — error de cálculo", n_sobre)
    else:
        logger.info("A.1 OK: 0 celdas > 100 %%")

    # ── C. Tests offline ──
    logger.info("C — Tests de aceptación offline…")
    tests = evaluar_tests(sel_dir, car_dir, aud_corregida=aud)
    tests.to_csv(out_dir / "resultado_tests.csv", index=False)
    n_falla = int((tests["resultado"] == "FALLA").sum())
    logger.info("Tests: %d fallan / %d total", n_falla, len(tests))

    # ── D. Geometrías ──
    logger.info("D — Diagnóstico de geometrías…")
    geo_df, geo_meta = diagnostico_geometrias(sel_dir)
    geo_df.to_csv(out_dir / "diagnostico_geometrias.csv", index=False)

    # ── E / F. Presupuesto y déficit ──
    logger.info("E — Desambiguar presupuesto no asignado…")
    presup_df, presup_meta = desambiguar_presupuesto(sel_dir)
    if not presup_df.empty:
        presup_df.to_csv(out_dir / "presupuesto_no_asignado_desambiguado.csv", index=False)
    deficit_meta = estado_deficit(sel_dir)
    logger.info("F — Déficit: %s", deficit_meta["estado"])

    solape = None
    if (sel_dir / "auditoria_solape.csv").is_file():
        solape = pd.read_csv(sel_dir / "auditoria_solape.csv")

    # ── Informe ──
    logger.info("Generando informe…")
    md = generar_informe(
        sel_tag=args.seleccion,
        car_tag=args.caracterizacion,
        out_dir=out_dir,
        aud=aud,
        ratio_df=ratio_df,
        tests=tests,
        geo_meta=geo_meta,
        presup_meta=presup_meta,
        presup_df=presup_df,
        deficit_meta=deficit_meta,
        sel_df=seleccion,
        solape=solape,
    )
    informe_path = out_dir / "informe_seleccion_reauditado.md"
    informe_path.write_text(md, encoding="utf-8")

    # ── Summary ──
    raras = aud[aud["modo"].isin(["censo", "refuerzo"])]
    summary = {
        "seleccion": args.seleccion,
        "caracterizacion": args.caracterizacion,
        "reauditoria_dir": str(out_dir),
        "n_rectangulos": int(len(seleccion)),
        "n_celdas_auditadas": int(len(aud)),
        "n_celdas_raras": int(len(raras)),
        "n_cumplen_objetivo_a1": int(raras["cumple_objetivo"].fillna(False).sum()),
        "n_vacias_a1": int((aud["estado"] == "vacia").sum()),
        "n_pct_alcanzable_gt_100": n_sobre,
        "tests": tests[["test_id", "descripcion", "resultado", "valor_obtenido"]].to_dict(orient="records"),
        "n_tests_falla": n_falla,
        "geometrias": geo_meta.get("resumen", {}),
        "presupuesto_no_asignado": presup_meta,
        "deficit": deficit_meta,
        "git_hash": git_hash(),
        "versiones": versiones_paquetes(),
        "timestamp": stamp,
    }
    (out_dir / "summary_reauditoria.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Listo: %s", informe_path)
    print(out_dir)
    return 0 if n_sobre == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
