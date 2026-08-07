#!/usr/bin/env python3
"""CLI unificada del pipeline SSL4EO v02."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config.corridas_ref import SEL_RUN_REF

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


def _run_script(script: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(REPO / "scripts" / script)] + (extra or [])
    return subprocess.call(cmd)


def cmd_estado(_args: argparse.Namespace) -> int:
    return _run_script("00_estado_pipeline.py")


def cmd_caracterizar(args: argparse.Namespace) -> int:
    if args.generar_lista_tiles:
        return _run_script("03_generar_lista_tiles.py")
    if args.consolidar:
        extra = ["--run-dir", str(args.run_dir)] if args.run_dir else []
        return _run_script("05_consolidar_grillas.py", extra)
    if not args.tile:
        print("ERROR: indique --tile, --generar-lista-tiles o --consolidar", file=sys.stderr)
        return 1
    extra = ["--tile", args.tile]
    if args.run_dir:
        extra += ["--run-dir", str(args.run_dir)]
    if args.resume:
        extra.append("--resume")
    if args.rect_sides:
        for s in args.rect_sides:
            extra += ["--rect-side", str(s)]
    return _run_script("04_caracterizar_tile.py", extra)


def cmd_seleccionar(args: argparse.Namespace) -> int:
    if args.etapa == "presupuesto":
        extra = []
        if args.eco:
            for e in args.eco:
                extra += ["--eco", str(e)]
        return _run_script("06_presupuesto_seleccion.py", extra)
    extra = []
    if args.grid_run_dir:
        extra += ["--grid-run-dir", str(args.grid_run_dir)]
    if args.run_dir:
        extra += ["--run-dir", str(args.run_dir)]
    if args.resume:
        extra.append("--resume")
    return _run_script("07_seleccionar_rectangulos.py", extra)


def cmd_plan_revision(args: argparse.Namespace) -> int:
    extra = ["--seleccion", args.seleccion]
    if args.timestamp:
        extra += ["--timestamp", args.timestamp]
    if args.out_dir:
        extra += ["--out-dir", str(args.out_dir)]
    return _run_script("10_generar_plan_revision.py", extra)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline SSL4EO v02")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_est = sub.add_parser("estado", help="Estado de corridas")
    p_est.set_defaults(func=cmd_estado)

    p_car = sub.add_parser("caracterizar", help="Caracterización por tile MGRS")
    p_car.add_argument("--tile", type=str, default=None)
    p_car.add_argument("--run-dir", type=Path, default=None)
    p_car.add_argument("--resume", action="store_true")
    p_car.add_argument("--generar-lista-tiles", action="store_true")
    p_car.add_argument("--consolidar", action="store_true")
    p_car.add_argument("--rect-side", type=int, action="append", dest="rect_sides")
    p_car.set_defaults(func=cmd_caracterizar)

    p_sel = sub.add_parser("seleccionar", help="Presupuesto o selección")
    p_sel.add_argument("--etapa", choices=["presupuesto", "seleccion"], default="seleccion")
    p_sel.add_argument("--dry-run", action="store_true", help="Solo presupuesto (etapa presupuesto)")
    p_sel.add_argument("--grid-run-dir", type=Path, default=None)
    p_sel.add_argument("--run-dir", type=Path, default=None)
    p_sel.add_argument("--resume", action="store_true")
    p_sel.add_argument("--eco", type=int, action="append")
    p_sel.set_defaults(func=cmd_seleccionar)

    p_rev = sub.add_parser("plan-revision", help="Deriva años de revisión rev_year*")
    p_rev.add_argument("--seleccion", default=SEL_RUN_REF, help="Tag o ruta de selección")
    p_rev.add_argument("--timestamp", default=None, help="Sufijo plan_revision_{timestamp}")
    p_rev.add_argument("--out-dir", type=Path, default=None)
    p_rev.set_defaults(func=cmd_plan_revision)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
