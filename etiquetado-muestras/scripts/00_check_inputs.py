#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
from pathlib import Path
import geopandas as gpd
import pandas as pd

DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")
DEFAULT_LANDCOVER_DIR = Path("/home/lserey/mapbiomas_land/landcover_col2")

def split_years(value) -> list[int]:
    if pd.isna(value):
        return []
    return sorted(set(int(float(p.strip())) for p in str(value).split(",") if p.strip()))

def parse_args():
    p = argparse.ArgumentParser(description="Verifica insumos para etiquetado C2 en cluster.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--raster-template", default="classification_{year}.tif")
    return p.parse_args()

def main() -> int:
    args = parse_args()
    samples = args.samples_dir
    lc_dir = args.landcover_dir
    print("=== CHECK INPUTS ===")
    print(f"samples-dir:   {samples}")
    print(f"landcover-dir: {lc_dir}")
    required = [
        samples / "listado_revision_manual.csv",
        samples / "seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson",
        samples / "seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson",
    ]
    ok = True
    print("\nArchivos requeridos:")
    for f in required:
        exists = f.exists()
        print(f"  {'OK' if exists else 'NO'} {f}")
        ok &= exists
    if not ok:
        return 1
    plan = pd.read_csv(samples / "listado_revision_manual.csv", encoding="utf-8-sig")
    print("\nPlan:")
    print(f"  filas:          {len(plan)}")
    print(f"  grid_id únicos: {plan['grid_id'].nunique()}")
    years = sorted({y for txt in plan["review_years"].dropna() for y in split_years(txt)})
    print(f"  años requeridos ({len(years)}): {years}")
    print("\nRectángulos:")
    rect_ids = []
    for name in ["seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson", "seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson"]:
        path = samples / name
        gdf = gpd.read_file(path)
        print(f"  {name}: {len(gdf)} features | CRS={gdf.crs}")
        rect_ids.extend(gdf["grid_id"].astype(str).tolist())
    print(f"  grid_id únicos en geometrías: {len(set(rect_ids))}")
    missing_geom = sorted(set(plan["grid_id"].astype(str)) - set(rect_ids))
    if missing_geom:
        print(f"\nERROR: {len(missing_geom)} grid_id del plan no tienen geometría.")
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
        print(f"\nERROR: faltan raster para años: {missing_years}")
        ok = False
    print("\nResultado:", "insumos correctos." if ok else "hay problemas en los insumos.")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
