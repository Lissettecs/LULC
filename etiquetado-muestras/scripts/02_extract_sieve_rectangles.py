#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrae cada rectángulo del raster anual C2, aplica filtro sieve para eliminar
parches pequeños (ruido sal-y-pimienta) y guarda el clip como GeoTIFF en la
CRS nativa UTM del rectángulo.

Salida en prod/labels/rectangulos/:
  utm18/{grid_id}_{year}.tif   — proyección EPSG:32718
  utm19/{grid_id}_{year}.tif   — proyección EPSG:32719

El sieve se aplica ANTES de reproyectar para respetar el tamaño de píxel
original del raster fuente.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import sieve
from rasterio.mask import mask as raster_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import mapping
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.sample_paths import (  # noqa: E402
    DEFAULT_LANDCOVER_DIR,
    DEFAULT_SAMPLES_DIR,
    discover_selection_geojsons,
    infer_selection_crs,
    infer_utm_zone,
    resolve_plan_path,
)

DEFAULT_LABELS_DIR = Path("/home/lserey/mapbiomas_land/prod/labels")

UTM_CRS = {"UTM18": "EPSG:32718", "UTM19": "EPSG:32719"}


def parse_years(value) -> list[int]:
    if pd.isna(value):
        return []
    return sorted(set(int(float(p.strip())) for p in str(value).split(",") if p.strip()))


def read_rectangles_by_zone(samples_dir: Path) -> dict[str, gpd.GeoDataFrame]:
    """
    Descubre todos los GeoJSON de selección (nueva estructura final_samples/UTM*/tipo/
    o legacy) y devuelve un dict {zona: GeoDataFrame} en CRS nativa UTM.
    Combina homogeneo_2x2 y mixto_3x3 dentro de cada zona.
    """
    files = discover_selection_geojsons(samples_dir)
    if not files:
        raise FileNotFoundError(f"No se encontraron GeoJSON de selección en {samples_dir}")

    frames: dict[str, list[gpd.GeoDataFrame]] = {}
    for f in files:
        zone = infer_utm_zone(f)          # "UTM18" o "UTM19"
        crs = infer_selection_crs(f)      # "EPSG:32718" o "EPSG:32719"
        gdf = gpd.read_file(f)
        gdf = gdf.set_crs(crs) if gdf.crs is None else gdf.to_crs(crs)
        gdf["grid_id"] = gdf["grid_id"].astype(str)
        gdf["utm_zone"] = zone
        gdf["source_file"] = f.name
        frames.setdefault(zone, []).append(gdf)
        print(f"  {zone}: {len(gdf)} rectángulos ({f.relative_to(samples_dir)})")

    result = {}
    for zone, gdfs in frames.items():
        combined = pd.concat(gdfs, ignore_index=True)
        if combined["grid_id"].duplicated().any():
            dup = combined.loc[combined["grid_id"].duplicated(keep=False), "grid_id"].unique()
            raise ValueError(f"grid_id duplicados en zona {zone}: {dup[:10]}")
        result[zone] = gpd.GeoDataFrame(combined, geometry="geometry", crs=gdfs[0].crs)
    return result


def build_work(samples_dir: Path, plan_name: str, grid_zone: dict[str, str]) -> pd.DataFrame:
    """Expande el plan a pares únicos (grid_id, review_year)."""
    plan = pd.read_csv(resolve_plan_path(samples_dir, plan_name), encoding="utf-8-sig")
    plan["grid_id"] = plan["grid_id"].astype(str)
    rows = []
    for _, row in plan.iterrows():
        for year in parse_years(row["review_years"]):
            rows.append({"grid_id": str(row["grid_id"]), "review_year": int(year)})
    work = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    work["utm_zone"] = work["grid_id"].map(grid_zone)
    missing = work["utm_zone"].isna().sum()
    if missing:
        print(f"ADVERTENCIA: {missing} grid_id sin zona UTM conocida — se omiten.")
    return work.dropna(subset=["utm_zone"])


def extract_and_sieve(
    src: rasterio.DatasetReader,
    geom_raster_crs,
    dst_crs: str,
    sieve_size: int,
    nodata: int = 0,
) -> tuple[np.ndarray, rasterio.transform.Affine] | None:
    """
    Recorta el raster al rectángulo, aplica sieve en CRS original y
    reproyecta al CRS destino UTM.
    Devuelve (array 2D int32, transform) o None si el recorte está vacío.
    """
    try:
        arr, transform = raster_mask(
            src, [mapping(geom_raster_crs)], crop=True, filled=True,
            all_touched=False, nodata=nodata,
        )
    except ValueError:
        return None

    data = arr[0].astype(np.int32)

    if sieve_size > 0:
        # sieve elimina parches de píxeles contiguos con menos de sieve_size píxeles
        data = sieve(data, size=sieve_size, connectivity=4)

    src_height, src_width = data.shape
    src_bounds = rasterio.transform.array_bounds(src_height, src_width, transform)

    if src.crs.to_epsg() == int(dst_crs.split(":")[1]):
        # Ya en la CRS destino: no hace falta reproyectar
        return data, transform

    dst_transform, dst_width, dst_height = calculate_default_transform(
        src.crs, dst_crs, src_width, src_height, *src_bounds
    )
    dst_data = np.full((dst_height, dst_width), nodata, dtype=np.int32)
    reproject(
        source=data,
        destination=dst_data,
        src_transform=transform,
        src_crs=src.crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
        src_nodata=nodata,
        dst_nodata=nodata,
    )
    return dst_data, dst_transform


def parse_args():
    p = argparse.ArgumentParser(
        description="Extrae rectángulos con filtro sieve, separados por zona UTM."
    )
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR)
    p.add_argument("--plan-name", default="listado_revision_manual.csv")
    p.add_argument("--raster-template", default="classification_{year}.tif")
    p.add_argument(
        "--sieve-size", type=int, default=9,
        help="Tamaño mínimo de parche en píxeles para el filtro sieve (0 = desactivar).",
    )
    p.add_argument("--only-years", nargs="*", type=int, default=None)
    p.add_argument("--only-zones", nargs="*", choices=["utm18", "utm19"], default=None)
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=== EXTRAER RECTÁNGULOS CON FILTRO SIEVE ===")
    print(f"samples-dir:   {args.samples_dir}")
    print(f"landcover-dir: {args.landcover_dir}")
    print(f"labels-dir:    {args.labels_dir}")
    print(f"sieve-size:    {args.sieve_size} px")

    print("\nLeyendo rectángulos por zona UTM:")
    rects_by_zone = read_rectangles_by_zone(args.samples_dir)

    grid_zone = {
        gid: zone
        for zone, gdf in rects_by_zone.items()
        for gid in gdf["grid_id"]
    }
    work = build_work(args.samples_dir, args.plan_name, grid_zone)

    if args.only_years:
        work = work[work["review_year"].isin(args.only_years)].copy()
    if args.only_zones:
        work = work[work["utm_zone"].isin([z.upper() for z in args.only_zones])].copy()
    if args.max_rows:
        work = work.head(args.max_rows).copy()

    print(f"\nPares a procesar: {len(work)}")
    print(work["utm_zone"].value_counts().to_string())

    out_base = args.labels_dir / "rectangulos"
    for zone in rects_by_zone:
        (out_base / zone).mkdir(parents=True, exist_ok=True)

    n_written = n_skip = n_empty = 0

    for year, sub_year in work.groupby("review_year", sort=True):
        raster_path = args.landcover_dir / args.raster_template.format(year=int(year))
        if not raster_path.exists():
            print(f"ADVERTENCIA: no existe raster para año {year}: {raster_path}")
            continue
        print(f"\nAño {year}: {len(sub_year)} rectángulos | {raster_path.name}")

        with rasterio.open(raster_path) as src:
            for _, row in tqdm(sub_year.iterrows(), total=len(sub_year), desc=f"año {year}"):
                zone = row["utm_zone"]   # "UTM18" o "UTM19"
                gid = row["grid_id"]
                out_path = out_base / zone / f"{gid}_{year}.tif"

                if out_path.exists() and not args.overwrite:
                    n_skip += 1
                    continue

                zone_crs = UTM_CRS[zone]
                geom_utm = rects_by_zone[zone].set_index("grid_id").loc[gid, "geometry"]
                geom_raster = (
                    gpd.GeoDataFrame([{"geometry": geom_utm}], crs=zone_crs)
                    .to_crs(src.crs)
                    .geometry.iloc[0]
                )

                result = extract_and_sieve(
                    src, geom_raster, zone_crs,
                    sieve_size=args.sieve_size, nodata=0,
                )
                if result is None:
                    n_empty += 1
                    continue

                dst_data, dst_transform = result
                profile = {
                    "driver": "GTiff",
                    "dtype": "int32",
                    "crs": zone_crs,
                    "transform": dst_transform,
                    "width": dst_data.shape[1],
                    "height": dst_data.shape[0],
                    "count": 1,
                    "nodata": 0,
                    "compress": "lzw",
                    "tiled": False,
                }
                with rasterio.open(out_path, "w", **profile) as dst:
                    dst.write(dst_data, 1)
                n_written += 1

    print(f"\nResultado: escritos={n_written} | saltados={n_skip} | vacíos={n_empty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
