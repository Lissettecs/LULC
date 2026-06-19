#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from rasterio.mask import mask
from shapely.geometry import shape, mapping
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from mb_labels.taxonomy import lookup_taxonomy  # noqa: E402

DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")
DEFAULT_LANDCOVER_DIR = Path("/home/lserey/mapbiomas_land/landcover_col2")
DEFAULT_LABELS_DIR = Path("/home/lserey/mapbiomas_land/prod/labels")
GROUP_MAP = {"anual": "anuales", "estable": "estables", "transicion": "transiciones"}

def parse_years(value) -> list[int]:
    if pd.isna(value): return []
    return sorted(set(int(float(p.strip())) for p in str(value).split(",") if p.strip()))

def clean_value(value):
    try:
        if pd.isna(value): return ""
    except Exception:
        pass
    if hasattr(value, "item"):
        try: return value.item()
        except Exception: pass
    return value

def read_rectangles(samples_dir: Path) -> gpd.GeoDataFrame:
    files = sorted(samples_dir.glob("seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"))
    if not files:
        raise FileNotFoundError(f"No se encontraron rectángulos en {samples_dir}")
    frames = []
    for f in files:
        print(f"Leyendo rectángulos: {f}")
        gdf = gpd.read_file(f)
        if gdf.crs is None:
            if "UTM18" in f.name.upper(): gdf = gdf.set_crs("EPSG:32718")
            elif "UTM19" in f.name.upper(): gdf = gdf.set_crs("EPSG:32719")
            else: raise ValueError(f"CRS no definido y UTM no inferible en {f}")
        if "grid_id" not in gdf.columns: raise ValueError(f"No existe grid_id en {f}")
        gdf = gdf.copy()
        gdf["grid_id"] = gdf["grid_id"].astype(str)
        gdf["source_rectangles"] = f.name
        frames.append(gdf.to_crs("EPSG:4326"))
    out = pd.concat(frames, ignore_index=True)
    out = gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
    if out["grid_id"].duplicated().any():
        dup = out.loc[out["grid_id"].duplicated(keep=False), "grid_id"].unique()
        raise ValueError(f"grid_id duplicados en rectángulos. Ejemplos: {dup[:10]}")
    return out

def read_plan(samples_dir: Path, plan_name: str) -> pd.DataFrame:
    path = samples_dir / plan_name
    if not path.exists(): raise FileNotFoundError(f"No existe el plan: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    for col in ["grid_id", "review_years", "dim_temporal"]:
        if col not in df.columns: raise ValueError(f"El plan no tiene columna {col}")
    df["grid_id"] = df["grid_id"].astype(str)
    if "target_rare_class" not in df.columns: df["target_rare_class"] = ""
    return df

def expand_plan(plan: pd.DataFrame, write_rare_copy: bool) -> pd.DataFrame:
    rows = []
    for _, row in plan.iterrows():
        group = GROUP_MAP.get(str(row.get("dim_temporal", "")).lower().strip(), "otros")
        for year in parse_years(row["review_years"]):
            rec = row.to_dict(); rec["review_year"] = int(year); rec["label_group"] = group; rows.append(rec)
            if write_rare_copy and str(row.get("target_rare_class", "")).strip():
                rec2 = row.to_dict(); rec2["review_year"] = int(year); rec2["label_group"] = "clases_raras"; rows.append(rec2)
    out = pd.DataFrame(rows)
    if out.empty: raise ValueError("El plan expandido quedó vacío.")
    out["grid_id"] = out["grid_id"].astype(str)
    out["review_year"] = out["review_year"].astype(int)
    return out

def polygonize_rect_year(src, rect_row: pd.Series, rect_geom_raster_crs, *, output_crs: str, area_crs: str, min_patch_ha: float, keep_patches: bool) -> gpd.GeoDataFrame:
    try:
        arr, transform = mask(src, [mapping(rect_geom_raster_crs)], crop=True, filled=False, all_touched=False)
    except ValueError:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
    data = arr[0]
    if np.ma.isMaskedArray(data):
        valid_mask = ~data.mask
        values = data.filled(0)
    else:
        valid_mask = np.ones(data.shape, dtype=bool)
        values = data
    if src.nodata is not None:
        valid_mask = valid_mask & (values != src.nodata)
    valid_mask = valid_mask & np.isfinite(values)
    if not valid_mask.any():
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
    values = values.astype(np.int32)
    records = []
    patch_id = 0
    for geom_json, value in shapes(values, mask=valid_mask, transform=transform, connectivity=4):
        class_id = int(value)
        if class_id == 0: continue
        patch_id += 1
        tax = lookup_taxonomy(class_id)
        records.append({
            "grid_id": rect_row["grid_id"], "review_year": int(rect_row["review_year"]),
            "class_id": class_id, "class_name": tax["class_name"],
            "n1_cd": tax["n1_cd"], "n1_nm": tax["n1_nm"], "n2_cd": tax["n2_cd"], "n2_nm": tax["n2_nm"],
            "n3_cd": tax["n3_cd"], "n3_nm": tax["n3_nm"], "es_transversal": bool(tax["es_transversal"]), "es_critica_n3": bool(tax["es_critica_n3"]),
            "patch_id": patch_id, "sample_type": clean_value(rect_row.get("sample_type", "")), "dim_temporal": clean_value(rect_row.get("dim_temporal", "")),
            "dim_espacial": clean_value(rect_row.get("dim_espacial", "")), "review_rule": clean_value(rect_row.get("review_rule", "")),
            "review_priority": clean_value(rect_row.get("review_priority", "")), "review_tier": clean_value(rect_row.get("review_tier", "")),
            "review_status": clean_value(rect_row.get("review_status", "")), "split": clean_value(rect_row.get("split", "")),
            "target_rare_class": clean_value(rect_row.get("target_rare_class", "")), "lulc_mode_id": clean_value(rect_row.get("lulc_mode_id", "")),
            "lulc_mode_name": clean_value(rect_row.get("lulc_mode_name", "")), "eco_dom_id": clean_value(rect_row.get("eco_dom_id", "")),
            "eco_dom_name": clean_value(rect_row.get("eco_dom_name", "")), "source_raster": Path(src.name).name, "geometry": shape(geom_json),
        })
    if not records:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=src.crs)
    rect_area = gpd.GeoDataFrame([{"geometry": rect_geom_raster_crs}], geometry="geometry", crs=src.crs).to_crs(area_crs).geometry.area.iloc[0]
    area_geom = gdf.to_crs(area_crs)
    gdf["area_m2"] = area_geom.geometry.area.astype(float)
    gdf["area_ha"] = gdf["area_m2"] / 10000.0
    gdf["rect_area_m2"] = float(rect_area)
    gdf["pct_rect"] = np.where(rect_area > 0, gdf["area_m2"] / rect_area * 100.0, 0.0)
    if min_patch_ha > 0:
        gdf = gdf[gdf["area_ha"] >= min_patch_ha].copy()
    if gdf.empty: return gdf
    if not keep_patches:
        group_cols = [c for c in ["grid_id", "review_year", "class_id", "class_name", "n1_cd", "n1_nm", "n2_cd", "n2_nm", "n3_cd", "n3_nm", "es_transversal", "es_critica_n3", "sample_type", "dim_temporal", "dim_espacial", "review_rule", "review_priority", "review_tier", "review_status", "split", "target_rare_class", "lulc_mode_id", "lulc_mode_name", "eco_dom_id", "eco_dom_name", "source_raster"] if c in gdf.columns]
        gdf = gdf.dissolve(by=group_cols, as_index=False)
        area_geom = gdf.to_crs(area_crs)
        gdf["area_m2"] = area_geom.geometry.area.astype(float)
        gdf["area_ha"] = gdf["area_m2"] / 10000.0
        gdf["rect_area_m2"] = float(rect_area)
        gdf["pct_rect"] = np.where(rect_area > 0, gdf["area_m2"] / rect_area * 100.0, 0.0)
        gdf["patch_id"] = -9999
    return gdf.to_crs(output_crs)

def process_group(group_name, work, rects, args):
    out_dir = args.labels_dir / group_name
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "patches" if args.patches else group_name
    out_gpkg = out_dir / f"subdivisiones_C2_{suffix}.gpkg"
    layer = f"subdivisiones_C2_{suffix}"
    if out_gpkg.exists() and not args.overwrite:
        print(f"[{group_name}] Ya existe y no se sobrescribe: {out_gpkg}")
        return
    group_rows = work[work["label_group"] == group_name].copy()
    if group_rows.empty: return
    print(f"\n=== Grupo {group_name}: {len(group_rows)} rectángulo-año ===")
    outputs = []
    for year, sub_year in group_rows.groupby("review_year", sort=True):
        raster_path = args.landcover_dir / args.raster_template.format(year=int(year))
        if not raster_path.exists(): raise FileNotFoundError(f"No existe raster para año {year}: {raster_path}")
        print(f"  Año {year}: {len(sub_year)} rectángulo-año | {raster_path.name}")
        with rasterio.open(raster_path) as src:
            rects_raster = rects.to_crs(src.crs)
            geom_lookup = rects_raster.set_index("grid_id")["geometry"].to_dict()
            for _, row in tqdm(sub_year.iterrows(), total=len(sub_year), desc=f"{group_name}-{year}"):
                geom = geom_lookup.get(row["grid_id"])
                if geom is None:
                    print(f"ADVERTENCIA: grid_id sin geometría: {row['grid_id']}")
                    continue
                gdf_one = polygonize_rect_year(src, row, geom, output_crs=args.output_crs, area_crs=args.area_crs, min_patch_ha=args.min_patch_ha, keep_patches=bool(args.patches))
                if not gdf_one.empty: outputs.append(gdf_one)
    if not outputs:
        print(f"[{group_name}] No se generaron polígonos.")
        return
    out = gpd.GeoDataFrame(pd.concat(outputs, ignore_index=True), geometry="geometry", crs=args.output_crs)
    if out_gpkg.exists() and args.overwrite: out_gpkg.unlink()
    out.to_file(out_gpkg, layer=layer, driver="GPKG")
    print(f"[{group_name}] Escrito: {out_gpkg}")
    summary = out.groupby(["review_year", "class_id", "class_name"], dropna=False).agg(n_features=("grid_id", "count"), n_grid_id=("grid_id", "nunique"), area_ha=("area_ha", "sum")).reset_index()
    summary["area_ha"] = summary["area_ha"].round(2)
    summary.to_csv(out_dir / f"resumen_C2_{group_name}.csv", index=False, encoding="utf-8-sig")

def parse_args():
    p = argparse.ArgumentParser(description="Genera subdivisiones C2 en cluster desde GeoTIFF anuales.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR)
    p.add_argument("--plan-name", default="listado_revision_manual.csv")
    p.add_argument("--raster-template", default="classification_{year}.tif")
    p.add_argument("--only-groups", nargs="*", default=None, choices=["anuales", "estables", "transiciones", "clases_raras", "otros"])
    p.add_argument("--only-years", nargs="*", type=int, default=None)
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--min-patch-ha", type=float, default=0.0)
    p.add_argument("--patches", action="store_true", help="Conserva parches individuales. Por defecto disuelve por clase.")
    p.add_argument("--write-rare-copy", action="store_true", help="Crea copia adicional en grupo clases_raras para target_rare_class.")
    p.add_argument("--output-crs", default="EPSG:4326")
    p.add_argument("--area-crs", default="EPSG:6933")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()

def main() -> int:
    args = parse_args()
    print("=== GENERAR ETIQUETAS / SUBDIVISIONES C2 EN CLUSTER ===")
    print(f"samples-dir:   {args.samples_dir}")
    print(f"landcover-dir: {args.landcover_dir}")
    print(f"labels-dir:    {args.labels_dir}")
    rects = read_rectangles(args.samples_dir)
    plan = read_plan(args.samples_dir, args.plan_name)
    work = expand_plan(plan, write_rare_copy=args.write_rare_copy)
    if args.only_years: work = work[work["review_year"].isin(args.only_years)].copy()
    work = work.sort_values(["label_group", "review_year", "grid_id"]).reset_index(drop=True)
    if args.max_rows is not None and args.max_rows > 0: work = work.head(args.max_rows).copy()
    if args.only_groups: work = work[work["label_group"].isin(args.only_groups)].copy()
    if work.empty: raise ValueError("No quedan filas para procesar después de filtros.")
    print("\nPlan expandido:")
    print(f"  rectángulo-año: {len(work)}")
    print("  por grupo:")
    print(work["label_group"].value_counts().to_string())
    print("  años:")
    print(sorted(work["review_year"].unique().tolist()))
    for group_name in sorted(work["label_group"].unique()):
        process_group(group_name, work, rects, args)
    print("\nListo.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
