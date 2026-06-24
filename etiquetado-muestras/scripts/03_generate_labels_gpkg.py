#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera GeoPackages de etiquetas C2 desde los rasters sieved pre-extraídos.

Lee los mosaicos anuales sieved en prod/labels/raster/{grupo}/{zona}/{year}.tif,
recorta por rectángulo de muestra, poligoniza, enriquece con taxonomía y metadatos
del plan, y escribe un GeoPackage por grupo y zona UTM en prod/labels/vector/{grupo}/{zona}/.

Salida:
  prod/labels/
  ├── raster/
  │   ├── annual/UTM18/{year}.tif
  │   └── annual/UTM19/{year}.tif
  └── vector/
      ├── annual/UTM18/annual_samples_UTM18.gpkg
      └── annual/UTM19/annual_samples_UTM19.gpkg

Los GeoPackages se mantienen en la CRS nativa UTM del rectángulo, coherente
con la proyección usada por SSL4EO-L.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from rasterio.mask import mask as raster_mask
from shapely.geometry import mapping, shape
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from mb_labels.taxonomy import lookup_taxonomy  # noqa: E402
from mb_labels.sample_paths import (  # noqa: E402
    DEFAULT_SAMPLES_DIR,
    discover_selection_geojsons,
    infer_selection_crs,
    infer_utm_zone,
    resolve_plan_path,
)

DEFAULT_LABELS_DIR = Path("/home/lserey/mapbiomas_land/prod/labels")

UTM_CRS = {"UTM18": "EPSG:32718", "UTM19": "EPSG:32719"}
GROUP_MAP = {"anual": "anuales", "estable": "estables", "transicion": "transiciones"}
ALL_GROUPS = ["anuales", "estables", "transiciones", "clases_raras"]
GROUP_FOLDER_MAP = {
    "anuales": "annual",
    "estables": "stable",
    "transiciones": "transition",
    "clases_raras": "rare_classes",
}
GPKG_NAME_MAP = {
    "anuales": "annual_samples",
    "estables": "stable_samples",
    "transiciones": "transition_samples",
    "clases_raras": "rare_class_samples",
}


def parse_years(value) -> list[int]:
    if pd.isna(value):
        return []
    return sorted(set(int(float(p.strip())) for p in str(value).split(",") if p.strip()))


def clean_value(value):
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def load_plan(samples_dir: Path, plan_name: str) -> pd.DataFrame:
    path = resolve_plan_path(samples_dir, plan_name)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["grid_id"] = df["grid_id"].astype(str)
    if "target_rare_class" not in df.columns:
        df["target_rare_class"] = ""
    return df


def expand_plan(plan: pd.DataFrame, write_rare_copy: bool) -> pd.DataFrame:
    rows = []
    for _, row in plan.iterrows():
        group = GROUP_MAP.get(str(row.get("dim_temporal", "")).lower().strip(), "otros")
        for year in parse_years(row["review_years"]):
            rows.append({**row.to_dict(), "review_year": int(year), "label_group": group})
            if write_rare_copy and str(row.get("target_rare_class", "")).strip():
                rows.append({**row.to_dict(), "review_year": int(year), "label_group": "clases_raras"})
    out = pd.DataFrame(rows)
    out["grid_id"] = out["grid_id"].astype(str)
    out["review_year"] = out["review_year"].astype(int)
    return out


def build_grid_zone(samples_dir: Path) -> dict[str, str]:
    """Mapea grid_id → zona UTM ('UTM18' o 'UTM19') usando la estructura real de final_samples."""
    grid_zone: dict[str, str] = {}
    for f in discover_selection_geojsons(samples_dir):
        zone = infer_utm_zone(f)   # "UTM18" o "UTM19"
        gdf = gpd.read_file(f, columns=["grid_id"])
        for gid in gdf["grid_id"].astype(str):
            grid_zone[gid] = zone
    return grid_zone


def build_rects_by_zone(samples_dir: Path) -> dict[str, gpd.GeoDataFrame]:
    """Rectángulos de muestra por zona UTM (homogeneo + mixto combinados)."""
    frames: dict[str, list[gpd.GeoDataFrame]] = {}
    for f in discover_selection_geojsons(samples_dir):
        zone = infer_utm_zone(f)
        crs = infer_selection_crs(f)
        gdf = gpd.read_file(f, columns=["grid_id", "geometry"])
        gdf = gdf.set_crs(crs) if gdf.crs is None else gdf.to_crs(crs)
        gdf["grid_id"] = gdf["grid_id"].astype(str)
        frames.setdefault(zone, []).append(gdf)
    return {
        zone: gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), geometry="geometry", crs=gdfs[0].crs)
        for zone, gdfs in frames.items()
    }


def resolve_year_tif(tif_dir: Path, grid_id: str, year: int) -> Path | None:
    year_path = tif_dir / f"{year}.tif"
    if year_path.exists():
        return year_path
    legacy = tif_dir / f"{grid_id}_{year}.tif"
    if legacy.exists():
        return legacy
    return None


def polygonize_tif(
    tif_path: Path,
    utm_crs: str,
    area_crs: str,
    keep_patches: bool,
    clip_geom=None,
) -> gpd.GeoDataFrame:
    with rasterio.open(tif_path) as src:
        nodata = src.nodata or 0
        if clip_geom is not None:
            arr, transform = raster_mask(
                src, [mapping(clip_geom)], crop=True, filled=True,
                all_touched=False, nodata=nodata,
            )
            data = arr[0].astype(np.int32)
        else:
            data = src.read(1).astype(np.int32)
            transform = src.transform
        valid_mask = (data != int(nodata)) & np.isfinite(data)

    if not valid_mask.any():
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=utm_crs)

    records = []
    patch_id = 0
    for geom_json, value in shapes(data, mask=valid_mask.astype(np.uint8), transform=transform, connectivity=4):
        class_id = int(value)
        if class_id == 0:
            continue
        patch_id += 1
        tax = lookup_taxonomy(class_id)
        records.append({
            "class_id": class_id,
            "class_name": tax["class_name"],
            "n1_cd": tax["n1_cd"], "n1_nm": tax["n1_nm"],
            "n2_cd": tax["n2_cd"], "n2_nm": tax["n2_nm"],
            "n3_cd": tax["n3_cd"], "n3_nm": tax["n3_nm"],
            "es_transversal": bool(tax["es_transversal"]),
            "es_critica_n3": bool(tax["es_critica_n3"]),
            "patch_id": patch_id,
            "geometry": shape(geom_json),
        })

    if not records:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=utm_crs)

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=utm_crs)
    gdf["area_m2"] = gdf.to_crs(area_crs).geometry.area.astype(float)
    gdf["area_ha"] = gdf["area_m2"] / 10000.0
    return gdf


def process_group_zone(
    group_name: str,
    zone: str,
    work: pd.DataFrame,
    rects_dir: Path,
    rects_by_zone: dict[str, gpd.GeoDataFrame],
    args,
) -> None:
    utm_crs = UTM_CRS[zone]                         # zone es "UTM18" o "UTM19"
    group_folder = GROUP_FOLDER_MAP.get(group_name, group_name)
    gpkg_base = GPKG_NAME_MAP.get(group_name, group_name)
    out_dir = args.labels_dir / "vector" / group_folder / zone
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"{gpkg_base}_patches" if args.patches else gpkg_base
    out_gpkg = out_dir / f"{suffix}_{zone}.gpkg"
    layer = f"{suffix}_{zone}"

    if out_gpkg.exists() and not args.overwrite:
        print(f"  [{group_name}/{zone}] Ya existe, se omite: {out_gpkg.name}")
        return

    sub = work[(work["label_group"] == group_name) & (work["utm_zone"] == zone)].copy()
    if sub.empty:
        return

    tif_dir = rects_dir / group_folder / zone
    zone_rects = rects_by_zone.get(zone)
    outputs = []

    for _, row in tqdm(sub.iterrows(), total=len(sub), desc=f"{group_name}/{zone}"):
        year = int(row["review_year"])
        grid_id = str(row["grid_id"])
        tif_path = resolve_year_tif(tif_dir, grid_id, year)
        if tif_path is None:
            print(f"ADVERTENCIA: no existe TIF sieved para {grid_id} año {year}")
            continue

        clip_geom = None
        if tif_path.name == f"{year}.tif":
            if zone_rects is None or grid_id not in zone_rects["grid_id"].values:
                print(f"ADVERTENCIA: grid_id sin geometría en {zone}: {grid_id}")
                continue
            clip_geom = zone_rects.set_index("grid_id").loc[grid_id, "geometry"]

        gdf_one = polygonize_tif(
            tif_path, utm_crs, args.area_crs,
            keep_patches=bool(args.patches), clip_geom=clip_geom,
        )
        if gdf_one.empty:
            continue

        # Agregar metadatos del plan
        meta_cols = [
            "grid_id", "review_year", "label_group", "sample_type",
            "dim_temporal", "dim_espacial", "review_rule", "review_priority",
            "review_tier", "review_status", "split", "target_rare_class",
            "lulc_mode_id", "lulc_mode_name", "eco_dom_id", "eco_dom_name",
        ]
        for col in meta_cols:
            if col in row.index:
                gdf_one[col] = clean_value(row[col])
        gdf_one["source_tif"] = tif_path.name
        gdf_one["utm_zone"] = zone
        rect_area = gdf_one.to_crs(args.area_crs).geometry.area.sum()
        gdf_one["rect_area_m2"] = float(gdf_one.to_crs(args.area_crs).dissolve().geometry.area.iloc[0])
        gdf_one["pct_rect"] = np.where(
            gdf_one["rect_area_m2"] > 0,
            gdf_one["area_m2"] / gdf_one["rect_area_m2"] * 100.0,
            0.0,
        )

        if not args.patches:
            dissolve_cols = [
                c for c in [
                    "grid_id", "review_year", "class_id", "class_name",
                    "n1_cd", "n1_nm", "n2_cd", "n2_nm", "n3_cd", "n3_nm",
                    "es_transversal", "es_critica_n3", "sample_type", "dim_temporal",
                    "dim_espacial", "review_rule", "review_priority", "review_tier",
                    "review_status", "split", "target_rare_class", "lulc_mode_id",
                    "lulc_mode_name", "eco_dom_id", "eco_dom_name", "source_tif",
                    "utm_zone", "rect_area_m2",
                ] if c in gdf_one.columns
            ]
            gdf_one = gdf_one.dissolve(by=dissolve_cols, as_index=False)
            gdf_one["area_m2"] = gdf_one.to_crs(args.area_crs).geometry.area.astype(float)
            gdf_one["area_ha"] = gdf_one["area_m2"] / 10000.0
            gdf_one["pct_rect"] = np.where(
                gdf_one["rect_area_m2"] > 0,
                gdf_one["area_m2"] / gdf_one["rect_area_m2"] * 100.0,
                0.0,
            )
            gdf_one["patch_id"] = -9999

        if args.min_patch_ha > 0:
            gdf_one = gdf_one[gdf_one["area_ha"] >= args.min_patch_ha].copy()

        if not gdf_one.empty:
            outputs.append(gdf_one)

    if not outputs:
        print(f"  [{group_name}/{zone}] No se generaron polígonos.")
        return

    out = gpd.GeoDataFrame(pd.concat(outputs, ignore_index=True), geometry="geometry", crs=utm_crs)
    if out_gpkg.exists() and args.overwrite:
        out_gpkg.unlink()
    out.to_file(out_gpkg, layer=layer, driver="GPKG")
    print(f"  [{group_name}/{zone}] Escrito: {out_gpkg} ({len(out)} features)")

    summary = (
        out.groupby(["review_year", "class_id", "class_name"], dropna=False)
        .agg(n_features=("grid_id", "count"), n_grid_id=("grid_id", "nunique"), area_ha=("area_ha", "sum"))
        .reset_index()
    )
    summary["area_ha"] = summary["area_ha"].round(2)
    summary.to_csv(out_dir / f"resumen_{gpkg_base}_{zone}.csv", index=False, encoding="utf-8-sig")


def parse_args():
    p = argparse.ArgumentParser(
        description="Genera GeoPackages C2 desde rasters sieved, por grupo y zona UTM."
    )
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR)
    p.add_argument("--plan-name", default="listado_revision_manual.csv")
    p.add_argument(
        "--only-groups", nargs="*", default=None,
        choices=ALL_GROUPS + ["otros"],
    )
    p.add_argument("--only-zones", nargs="*", choices=["utm18", "utm19"], default=None)
    p.add_argument("--only-years", nargs="*", type=int, default=None)
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--min-patch-ha", type=float, default=0.0)
    p.add_argument("--patches", action="store_true", help="Conserva parches individuales sin disolver.")
    p.add_argument("--write-rare-copy", action="store_true")
    p.add_argument("--area-crs", default="EPSG:6933", help="CRS para cálculo de áreas (igual-área).")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=== GENERAR GEOPACKAGES C2 POR GRUPO Y ZONA UTM ===")
    print(f"samples-dir: {args.samples_dir}")
    print(f"labels-dir:  {args.labels_dir}")

    grid_zone = build_grid_zone(args.samples_dir)
    rects_by_zone = build_rects_by_zone(args.samples_dir)
    plan = load_plan(args.samples_dir, args.plan_name)
    work = expand_plan(plan, write_rare_copy=args.write_rare_copy)
    work["utm_zone"] = work["grid_id"].map(grid_zone)
    work = work.dropna(subset=["utm_zone"])

    if args.only_years:
        work = work[work["review_year"].isin(args.only_years)].copy()
    if args.only_groups:
        work = work[work["label_group"].isin(args.only_groups)].copy()
    if args.only_zones:
        zones = []
        for z in args.only_zones:
            z = z.upper()
            if not z.startswith("UTM"):
                z = f"UTM{z}"
            zones.append(z)
        work = work[work["utm_zone"].isin(zones)].copy()
    if args.max_rows:
        work = work.head(args.max_rows).copy()

    if work.empty:
        raise ValueError("No quedan filas para procesar después de filtros.")

    print(f"\nPlan expandido: {len(work)} rectángulo-año")
    print("Por grupo:")
    print(work["label_group"].value_counts().to_string())
    print("Por zona:")
    print(work["utm_zone"].value_counts().to_string())

    rects_dir = args.labels_dir / "raster"
    active_groups = sorted(work["label_group"].unique())
    active_zones = sorted(work["utm_zone"].unique())

    for group_name in active_groups:
        print(f"\n=== Grupo: {group_name} ===")
        for zone in active_zones:
            process_group_zone(group_name, zone, work, rects_dir, rects_by_zone, args)

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
