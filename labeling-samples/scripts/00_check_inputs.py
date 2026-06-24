#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.sample_paths import (  # noqa: E402
    DEFAULT_LANDCOVER_DIR,
    DEFAULT_PLAN_NAME,
    DEFAULT_SAMPLES_DIR,
    discover_selection_geojsons,
    resolve_plan_path,
)



def split_years(value) -> list[int]:
    if pd.isna(value):
        return []
    return sorted(set(int(float(p.strip())) for p in str(value).split(",") if p.strip()))


def parse_args():
    p = argparse.ArgumentParser(description="Verifica insumos para etiquetado C2 en cluster.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--plan-name", default=DEFAULT_PLAN_NAME)
    p.add_argument("--raster-template", default="classification_{year}.tif")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    samples = args.samples_dir
    lc_dir = args.landcover_dir
    plan_path = resolve_plan_path(samples, args.plan_name)
    rect_files = discover_selection_geojsons(samples)

    print("=== CHECK INPUTS ===")
    print(f"samples-dir:   {samples}")
    print(f"landcover-dir: {lc_dir}")
    print(f"plan:          {plan_path}")

    ok = True
    print("\nPlan de revision:")
    if plan_path.exists():
        print(f"  OK {plan_path}")
    else:
        print(f"  NO {plan_path}")
        ok = False

    print("\nRectangulos seleccionados:")
    if not rect_files:
        print(f"  NO se encontraron GeoJSON en {samples / 'final_samples'} ni layout legacy")
        ok = False
    rect_ids: list[str] = []
    for path in rect_files:
        gdf = gpd.read_file(path)
        print(f"  OK {path.relative_to(samples)}: {len(gdf)} features | CRS={gdf.crs}")
        if "grid_id" not in gdf.columns:
            print(f"  ERROR: falta grid_id en {path}")
            ok = False
        else:
            rect_ids.extend(gdf["grid_id"].astype(str).tolist())

    if not ok:
        return 1

    plan = pd.read_csv(plan_path, encoding="utf-8-sig")
    print("\nPlan:")
    print(f"  filas:          {len(plan)}")
    print(f"  grid_id unicos: {plan['grid_id'].nunique()}")
    years = sorted({y for txt in plan["review_years"].dropna() for y in split_years(txt)})
    print(f"  anos requeridos ({len(years)}): {years}")
    print(f"  grid_id unicos en geometrias: {len(set(rect_ids))}")
    missing_geom = sorted(set(plan["grid_id"].astype(str)) - set(rect_ids))
    if missing_geom:
        print(f"\nERROR: {len(missing_geom)} grid_id del plan no tienen geometria.")
        print(missing_geom[:20])
        ok = False

    print("\nLandcovers C2:")
    missing_years = []
    for year in years:
        tif = lc_dir / args.raster_template.format(year=year)
        if not tif.exists():
            missing_years.append(year)
            print(f"  NO {year}: {tif}")
        else:
            print(f"  OK {year}: {tif.name}")
    if missing_years:
        print(f"\nERROR: faltan raster para anos: {missing_years}")
        ok = False

    print("\nResultado:", "insumos correctos." if ok else "hay problemas en los insumos.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
