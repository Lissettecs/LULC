#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera GeoPackages de etiquetas C2 desde los rasters sieved pre-extraídos.

Lee los clips en prod/labels/rectangulos/{utm_zone}/{grid_id}_{year}.tif,
poligoniza, enriquece con taxonomía y metadatos del plan, y escribe un
GeoPackage por grupo y zona UTM en prod/labels/{grupo}/{utm_zone}/.

Salida:
  prod/labels/
  ├── anuales/
  │   ├── utm18/subdivisiones_C2_anuales_utm18.gpkg
  │   └── utm19/subdivisiones_C2_anuales_utm19.gpkg
  ├── estables/   utm18/ utm19/
  ├── transiciones/ utm18/ utm19/
  └── clases_raras/ utm18/ utm19/

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
from shapely.geometry import shape
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from mb_labels.taxonomy import lookup_taxonomy  # noqa: E402

DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")
DEFAULT_LABELS_DIR = Path("/home/lserey/mapbiomas_land/prod/labels")

UTM_CRS = {"utm18": "EPSG:32718", "utm19": "EPSG:32719"}
GROUP_MAP = {"anual": "anuales", "estable": "estables", "transicion": "transiciones"}
ALL_GROUPS = ["anuales", "estables", "transiciones", "clases_raras"]


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
    path = samples_dir / plan_name
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
    grid_zone: dict[str, str] = {}
    for f in sorted(samples_dir.glob("seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson")):
        name_upper = f.name.upper()
        if "UTM18" in name_upper:
            zone = "utm18"
        elif "UTM19" in name_upper:
            zone = "utm19"
        else:
            continue
        gdf = gpd.read_file(f, columns=["grid_id"])
        for gid in gdf["grid_id"].astype(str):
            grid_zone[gid] = zone
    return grid_zone


def polygonize_tif(tif_path: Path, utm_crs: str, area_crs: str, keep_patches: bool) -> gpd.GeoDataFrame:
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(np.int32)
        transform = src.transform
        nodata = src.nodata or 0
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


def process_group_zone(group_name: str, zone: str, work: pd.DataFrame, rects_dir: Path, args) -> None:
    utm_crs = UTM_CRS[zone]
    out_dir = args.labels_dir / group_name / zone
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = "patches" if args.patches else group_name
    out_gpkg = out_dir / f"subdivisiones_C2_{suffix}_{zone}.gpkg"
    layer = f"subdivisiones_C2_{suffix}_{zone}"

    if out_gpkg.exists() and not args.overwrite:
        print(f"  [{group_name}/{zone}] Ya existe, se omite: {out_gpkg.name}")
        return

    sub = work[(work["label_group"] == group_name) & (work["utm_zone"] == zone)].copy()
    if sub.empty:
        return

    tif_dir = rects_dir / zone
    outputs = []

    for _, row in tqdm(sub.iterrows(), total=len(sub), desc=f"{group_name}/{zone}"):
        tif_path = tif_dir / f"{row['grid_id']}_{row['review_year']}.tif"
        if not tif_path.exists():
            print(f"ADVERTENCIA: no existe TIF sieved: {tif_path}")
            continue

        gdf_one = polygonize_tif(tif_path, utm_crs, args.area_crs, keep_patches=bool(args.patches))
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
    summary.to_csv(out_dir / f"resumen_C2_{group_name}_{zone}.csv", index=False, encoding="utf-8-sig")


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
    plan = load_plan(args.samples_dir, args.plan_name)
    work = expand_plan(plan, write_rare_copy=args.write_rare_copy)
    work["utm_zone"] = work["grid_id"].map(grid_zone)
    work = work.dropna(subset=["utm_zone"])

    if args.only_years:
        work = work[work["review_year"].isin(args.only_years)].copy()
    if args.only_groups:
        work = work[work["label_group"].isin(args.only_groups)].copy()
    if args.only_zones:
        work = work[work["utm_zone"].isin(args.only_zones)].copy()
    if args.max_rows:
        work = work.head(args.max_rows).copy()

    if work.empty:
        raise ValueError("No quedan filas para procesar después de filtros.")

    print(f"\nPlan expandido: {len(work)} rectángulo-año")
    print("Por grupo:")
    print(work["label_group"].value_counts().to_string())
    print("Por zona:")
    print(work["utm_zone"].value_counts().to_string())

    rects_dir = args.labels_dir / "rectangulos"
    active_groups = sorted(work["label_group"].unique())
    active_zones = sorted(work["utm_zone"].unique())

    for group_name in active_groups:
        print(f"\n=== Grupo: {group_name} ===")
        for zone in active_zones:
            process_group_zone(group_name, zone, work, rects_dir, args)

    print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
