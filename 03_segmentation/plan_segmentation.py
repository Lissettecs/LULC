#!/usr/bin/env python3
"""
Plan de segmentación SLIC+RAG: inventario de rectángulos, mosaicos y estado de corrida.

Uso:
  python plan_segmentation.py --rev-year 2015
  python plan_segmentation.py --rev-year 2015 --require-mosaic
  python plan_segmentation.py --rev-year 2015 --export-plan plan_rev2015.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.mosaic_presets import resolve_mosaic_root  # noqa: E402
from config.paths import output_dir  # noqa: E402
from config.run_refs import GPKG_UTM18, GPKG_UTM19  # noqa: E402
from rectangles import construir_plan, filtrar_plan, guardar_plan  # noqa: E402


def parsear_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plan de segmentación por rev_year")
    p.add_argument(
        "--rev-year",
        type=int,
        default=2015,
        help="Filtrar por año de revisión en el GPKG de selección",
    )
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="Año del mosaico enmascarado (default: igual a --rev-year)",
    )
    p.add_argument(
        "--mosaic-kind",
        type=str,
        default=None,
        help="Preset de mosaico: 184_mask_water | 11b (env MOSAIC_KIND)",
    )
    p.add_argument("--mosaic-root", type=Path, default=None, help="Sobrescribir raíz de mosaicos")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Sobrescribir directorio de salida de segmentación",
    )
    p.add_argument("--gpkg-utm18", type=Path, default=GPKG_UTM18, help="GPKG huso 18 (fallback)")
    p.add_argument("--gpkg-utm19", type=Path, default=GPKG_UTM19, help="GPKG huso 19 (fallback)")
    p.add_argument("--test-tile", type=str, default=None, help="Filtrar por tile")
    p.add_argument("--grid-id", type=str, default=None, help="Filtrar por grid_id")
    p.add_argument(
        "--require-mosaic",
        action="store_true",
        help="Excluir rectángulos cuyo tile no tenga mosaico enmascarado",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Excluir rectángulos que ya tienen summary.json",
    )
    p.add_argument(
        "--export-plan",
        type=Path,
        default=None,
        help="Exportar plan JSON (p.ej. prod/03_segmentation_cim/2015/plan_rev2015.json)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parsear_args(argv)
    year = args.year if args.year is not None else args.rev_year
    mroot, mosaic_kind = resolve_mosaic_root(
        mosaic_root=args.mosaic_root,
        mosaic_kind=args.mosaic_kind,
        year=year,
    )
    out = args.output_dir or output_dir(year)
    print(f"Plan · mosaic_kind={mosaic_kind} · mosaic_root={mroot}")

    plan = construir_plan(
        rev_year=args.rev_year,
        year=year,
        mosaic_root_dir=mroot,
        output_root=out,
        gpkg_utm18=args.gpkg_utm18,
        gpkg_utm19=args.gpkg_utm19,
        test_tile=args.test_tile,
        grid_id=args.grid_id,
    )
    res = plan.summary()
    to_run = filtrar_plan(
        plan,
        require_mosaic=args.require_mosaic,
        skip_existing=args.skip_existing,
    )

    print(f"Plan de segmentación rev_year={args.rev_year} · mosaico year={year}")
    print(f"  Mosaicos: {mroot}")
    print(f"  Salida:   {out}")
    print(f"  Total rectángulos:      {res['n_total']}")
    print(f"  Con mosaico:            {res['n_mosaic_ok']}")
    print(f"  Ya procesados:          {res['n_already_processed']}")
    print(f"  Listos para correr:     {len(to_run)}")
    if res["tiles_missing_mosaic"]:
        print(f"  Tiles sin mosaico:       {', '.join(res['tiles_missing_mosaic'])}")
        for r in plan.missing_mosaic:
            print(f"    - {r.grid_id} ({r.tile})")

    if args.export_plan:
        guardar_plan(plan, args.export_plan)
        print(f"\nPlan exportado → {args.export_plan}")

    return 0


parse_args = parsear_args


if __name__ == "__main__":
    raise SystemExit(main())
