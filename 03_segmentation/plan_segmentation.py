#!/usr/bin/env python3
"""
Plan SLIC+RAG segmentation: inventory rectangles, mosaics, and run status.

Usage:
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

from config.paths import mosaic_root, output_dir  # noqa: E402
from config.run_refs import GPKG_UTM18, GPKG_UTM19  # noqa: E402
from rectangles import build_plan, filter_plan, save_plan  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Segmentation plan by rev_year1")
    p.add_argument("--rev-year", type=int, default=2015, help="Filter rev_year1 in selection GPKG")
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="Masked mosaic year (default: same as --rev-year)",
    )
    p.add_argument("--mosaic-root", type=Path, default=None, help="Override mosaic root")
    p.add_argument("--output-dir", type=Path, default=None, help="Override segmentation output")
    p.add_argument("--gpkg-utm18", type=Path, default=GPKG_UTM18)
    p.add_argument("--gpkg-utm19", type=Path, default=GPKG_UTM19)
    p.add_argument("--test-tile", type=str, default=None)
    p.add_argument("--grid-id", type=str, default=None)
    p.add_argument(
        "--require-mosaic",
        action="store_true",
        help="Exclude rectangles whose tile has no masked mosaic",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Exclude rectangles with an existing summary.json",
    )
    p.add_argument(
        "--export-plan",
        type=Path,
        default=None,
        help="Export plan JSON (e.g. prod/segmentacion_slic_rev2015/plan_rev2015.json)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    year = args.year if args.year is not None else args.rev_year
    mroot = args.mosaic_root or mosaic_root(year)
    out = args.output_dir or output_dir(year)

    plan = build_plan(
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
    to_run = filter_plan(
        plan,
        require_mosaic=args.require_mosaic,
        skip_existing=args.skip_existing,
    )

    print(f"Segmentation plan rev_year1={args.rev_year} · mosaic year={year}")
    print(f"  Mosaics: {mroot}")
    print(f"  Output:  {out}")
    print(f"  Total rectangles:       {res['n_total']}")
    print(f"  Mosaic available:       {res['n_mosaic_ok']}")
    print(f"  Already processed:      {res['n_already_processed']}")
    print(f"  Ready to run:           {len(to_run)}")
    if res["tiles_missing_mosaic"]:
        print(f"  Tiles missing mosaic:   {', '.join(res['tiles_missing_mosaic'])}")
        for r in plan.missing_mosaic:
            print(f"    - {r.grid_id} ({r.tile})")

    if args.export_plan:
        save_plan(plan, args.export_plan)
        print(f"\nPlan exported → {args.export_plan}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
