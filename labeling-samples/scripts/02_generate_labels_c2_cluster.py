#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.mask import mask
from shapely.geometry import shape, mapping
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from mb_labels.sample_paths import (  # noqa: E402
    DEFAULT_LANDCOVER_DIR,
    DEFAULT_PLAN_NAME,
    discover_selection_geojsons,
    infer_grid_tag,
    infer_selection_crs,
    infer_utm_zone,
    resolve_plan_path,
)
from mb_labels.raster_io import safe_grid_filename, write_geotiff  # noqa: E402
from mb_labels.taxonomy import is_transversal_rectangle  # noqa: E402
from mb_labels.field_names import (  # noqa: E402
    DISSOLVE_KEYS,
    class_attrs,
    rect_plan_attrs,
    rename_geodataframe_columns,
)
from mb_labels.qa_fields import init_qa_defaults  # noqa: E402
from mb_labels.gee_export import (  # noqa: E402
    DEFAULT_GEE_ASSET_BASE,
    DEFAULT_EE_PROJECT,
    build_asset_id,
    export_gdf_to_asset,
    local_gee_path,
)

DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")
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
    files = discover_selection_geojsons(samples_dir)
    if not files:
        raise FileNotFoundError(
            f"No se encontraron rectángulos en {samples_dir / 'final_samples'} "
            f"ni en layout legacy {samples_dir}"
        )
    frames = []
    for f in files:
        print(f"Leyendo rectángulos: {f}")
        gdf = gpd.read_file(f)
        if gdf.crs is None:
            gdf = gdf.set_crs(infer_selection_crs(f))
        if "grid_id" not in gdf.columns:
            raise ValueError(f"No existe grid_id en {f}")
        gdf = gdf.copy()
        gdf["grid_id"] = gdf["grid_id"].astype(str)
        gdf["source_rectangles"] = str(f.relative_to(samples_dir))
        gdf["grid_tag"] = infer_grid_tag(f)
        gdf["utm_zone"] = infer_utm_zone(f)
        frames.append(gdf.to_crs("EPSG:4326"))
    out = pd.concat(frames, ignore_index=True)
    out = gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
    if out["grid_id"].duplicated().any():
        dup = out.loc[out["grid_id"].duplicated(keep=False), "grid_id"].unique()
        raise ValueError(f"grid_id duplicados en rectángulos. Ejemplos: {dup[:10]}")
    return out

def read_plan(samples_dir: Path, plan_name: str) -> pd.DataFrame:
    path = resolve_plan_path(samples_dir, plan_name)
    if not path.exists():
        raise FileNotFoundError(f"No existe el plan: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    for col in ["grid_id", "review_years", "dim_temporal"]:
        if col not in df.columns: raise ValueError(f"El plan no tiene columna {col}")
    df["grid_id"] = df["grid_id"].astype(str)
    if "target_rare_class" not in df.columns: df["target_rare_class"] = ""
    return df

def expand_plan(plan: pd.DataFrame, write_rare_copy: bool, write_transversal_copy: bool) -> pd.DataFrame:
    rows = []
    for _, row in plan.iterrows():
        group = GROUP_MAP.get(str(row.get("dim_temporal", "")).lower().strip(), "otros")
        for year in parse_years(row["review_years"]):
            rec = row.to_dict(); rec["review_year"] = int(year); rec["label_group"] = group; rows.append(rec)
            if write_rare_copy and str(row.get("target_rare_class", "")).strip():
                rec2 = row.to_dict(); rec2["review_year"] = int(year); rec2["label_group"] = "clases_raras"; rows.append(rec2)
            if write_transversal_copy and is_transversal_rectangle(row):
                rec3 = row.to_dict(); rec3["review_year"] = int(year); rec3["label_group"] = "clases_transversales"; rows.append(rec3)
    out = pd.DataFrame(rows)
    if out.empty: raise ValueError("El plan expandido quedó vacío.")
    out["grid_id"] = out["grid_id"].astype(str)
    out["review_year"] = out["review_year"].astype(int)
    return out

def ensure_singlepart(gdf: gpd.GeoDataFrame, *, area_crs: str, rect_area: float) -> gpd.GeoDataFrame:
    """Divide MultiPolygon/MultiLineString en geometrías simples (monoparte)."""
    if gdf.empty:
        return gdf
    gdf = gdf.explode(index_parts=True, ignore_index=True)
    area_geom = gdf.to_crs(area_crs)
    gdf["area_m2"] = area_geom.geometry.area.astype(float)
    gdf["area_ha"] = gdf["area_m2"] / 10000.0
    gdf["rect_a_m2"] = float(rect_area)
    gdf["pct_rect"] = np.where(rect_area > 0, gdf["area_m2"] / rect_area * 100.0, 0.0)
    if "patch_id" not in gdf.columns:
        gdf["patch_id"] = -9999
    needs_patch = gdf["patch_id"].isna() | (gdf["patch_id"] == -9999)
    if needs_patch.any():
        gdf.loc[needs_patch, "patch_id"] = (
            gdf.loc[needs_patch]
            .groupby(list(DISSOLVE_KEYS), dropna=False)
            .cumcount()
            .add(1)
            .astype(int)
        )
    return gdf

def polygonize_rect_year(
    src,
    rect_row: pd.Series,
    rect_geom_raster_crs,
    *,
    output_crs: str,
    area_crs: str,
    min_patch_ha: float,
    connectivity: int,
) -> tuple[gpd.GeoDataFrame, np.ndarray, np.ndarray, object, object]:
    """Vectoriza un rectángulo-año y devuelve GDF + rasters clase/patch (conectividad rook por defecto)."""
    try:
        arr, transform = mask(src, [mapping(rect_geom_raster_crs)], crop=True, filled=False, all_touched=False)
    except ValueError:
        empty = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
        return empty, np.array([]), np.array([]), None, src.crs
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
        empty = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
        return empty, np.array([]), np.array([]), transform, src.crs
    values = values.astype(np.int32)
    class_raster = np.where(valid_mask, values, 0).astype(np.int32)
    patch_raster = np.zeros(values.shape, dtype=np.uint32)
    records = []
    patch_id = 0
    for geom_json, value in shapes(class_raster, mask=valid_mask, transform=transform, connectivity=connectivity):
        class_id = int(value)
        if class_id == 0:
            continue
        patch_id += 1
        geom = shape(geom_json)
        rasterize([(geom, patch_id)], out=patch_raster, transform=transform, fill=0, dtype=np.uint32)
        record = {
            "grid_id": str(rect_row["grid_id"]),
            "rev_year": int(rect_row["review_year"]),
            **class_attrs(class_id),
            "patch_id": patch_id,
            **{k: clean_value(v) for k, v in rect_plan_attrs(rect_row).items()},
            "src_raster": Path(src.name).name,
            "geometry": geom,
        }
        records.append(record)
    if not records:
        empty = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=src.crs)
        return empty, class_raster, patch_raster, transform, src.crs
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=src.crs)
    rect_area = gpd.GeoDataFrame([{"geometry": rect_geom_raster_crs}], geometry="geometry", crs=src.crs).to_crs(area_crs).geometry.area.iloc[0]
    area_geom = gdf.to_crs(area_crs)
    gdf["area_m2"] = area_geom.geometry.area.astype(float)
    gdf["area_ha"] = gdf["area_m2"] / 10000.0
    gdf["rect_a_m2"] = float(rect_area)
    gdf["pct_rect"] = np.where(rect_area > 0, gdf["area_m2"] / rect_area * 100.0, 0.0)
    if min_patch_ha > 0:
        keep = gdf["area_ha"] >= min_patch_ha
        dropped = set(gdf.loc[~keep, "patch_id"].astype(int))
        gdf = gdf[keep].copy()
        if dropped:
            patch_raster[np.isin(patch_raster, list(dropped))] = 0
    if gdf.empty:
        return gdf, class_raster, patch_raster, transform, src.crs
    gdf["patch_id"] = -9999
    gdf = ensure_singlepart(gdf, area_crs=area_crs, rect_area=rect_area)
    return rename_geodataframe_columns(gdf.to_crs(output_crs)), class_raster, patch_raster, transform, src.crs


def write_rect_rasters(
    *,
    labels_dir: Path,
    grid_id: str,
    year: int,
    class_raster: np.ndarray,
    patch_raster: np.ndarray,
    transform,
    crs,
) -> tuple[Path, Path]:
    stem = f"{safe_grid_filename(grid_id)}_{int(year)}"
    classes_path = labels_dir / "raster" / "classes" / f"{stem}_classes.tif"
    labels_path = labels_dir / "raster" / "labels" / f"{stem}_labels.tif"
    write_geotiff(classes_path, class_raster, transform=transform, crs=crs, nodata=0, dtype="int32")
    write_geotiff(labels_path, patch_raster, transform=transform, crs=crs, nodata=0, dtype="uint32")
    return classes_path, labels_path

def resolve_output_paths(group_name: str, args, utm_zone: str | None = None) -> tuple[Path, Path, str, Path]:
    if args.output_gpkg is not None:
        out_gpkg = args.output_gpkg
        out_dir = out_gpkg.parent
        layer = args.output_layer or out_gpkg.stem
        summary = args.summary_csv or (out_dir / f"resumen_{out_gpkg.stem}.csv")
    elif args.product_name:
        out_dir = args.labels_dir
        if args.split_by_utm and utm_zone:
            out_dir = out_dir / utm_zone
        out_gpkg = out_dir / f"{args.product_name}.gpkg"
        layer = args.output_layer or args.product_name
        summary = out_dir / f"resumen_{args.product_name}.csv"
    else:
        out_dir = args.labels_dir / group_name
        if args.split_by_utm and utm_zone:
            out_dir = out_dir / utm_zone
        out_gpkg = out_dir / f"subdivisiones_C2_{group_name}.gpkg"
        layer = f"subdivisiones_C2_{group_name}"
        summary = out_dir / f"resumen_C2_{group_name}.csv"
    return out_dir, out_gpkg, layer, summary


def resolve_gee_targets(group_name: str, args, out_gpkg: Path) -> tuple[str, Path]:
    if args.asset_id:
        asset_id = args.asset_id
    elif args.product_name:
        asset_id = f"{args.gee_asset_base.rstrip('/')}/{args.product_name}"
    else:
        asset_id = build_asset_id(args.gee_asset_base, group_name, group_name)
    if args.local_geojson is not None:
        geojson_path = args.local_geojson
    elif args.product_name:
        geojson_path = args.labels_dir / f"{args.product_name}.geojson"
    else:
        geojson_path = local_gee_path(args.labels_dir, group_name, group_name)
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    return asset_id, geojson_path


def attach_utm_zone(work: pd.DataFrame, rects: gpd.GeoDataFrame) -> pd.DataFrame:
    lookup = rects.set_index("grid_id")["utm_zone"].astype(str).to_dict()
    out = work.copy()
    out["utm_zone"] = out["grid_id"].astype(str).map(lookup)
    missing = out["utm_zone"].isna()
    if missing.any():
        examples = out.loc[missing, "grid_id"].head(5).tolist()
        raise ValueError(f"grid_id sin utm_zone en geometrias. Ejemplos: {examples}")
    return out


def process_group(group_name, work, rects, args):
    group_rows = work[work["label_group"] == group_name].copy()
    if group_rows.empty:
        return
    utm_zones = sorted(group_rows["utm_zone"].dropna().unique()) if args.split_by_utm else [None]
    for utm_zone in utm_zones:
        zone_rows = group_rows if utm_zone is None else group_rows[group_rows["utm_zone"] == utm_zone].copy()
        zone_label = utm_zone or "ALL"
        out_dir, out_gpkg, layer, summary_csv = resolve_output_paths(group_name, args, utm_zone)
        out_dir.mkdir(parents=True, exist_ok=True)
        if out_gpkg.exists() and not args.overwrite:
            print(f"[{group_name}/{zone_label}] Ya existe y no se sobrescribe: {out_gpkg}")
            continue
        print(f"\n=== Grupo {group_name} | {zone_label}: {len(zone_rows)} rectángulo-año ===")
        print(f"  conectividad: {args.connectivity} (rook=4, queen=8)")
        print(f"  salida GPKG:  {out_gpkg}")
        if args.write_rasters:
            print(f"  salida raster: {out_dir / 'raster'}")
        allowed_ids = set(zone_rows["grid_id"].astype(str))
        rects_zone = rects[rects["grid_id"].astype(str).isin(allowed_ids)]
        outputs = []
        for year, sub_year in zone_rows.groupby("review_year", sort=True):
            raster_path = args.landcover_dir / args.raster_template.format(year=int(year))
            if not raster_path.exists():
                raise FileNotFoundError(f"No existe raster para año {year}: {raster_path}")
            print(f"  Año {year}: {len(sub_year)} rectángulo-año | {raster_path.name}")
            with rasterio.open(raster_path) as src:
                rects_raster = rects_zone.to_crs(src.crs)
                geom_lookup = rects_raster.set_index("grid_id")["geometry"].to_dict()
                for _, row in tqdm(sub_year.iterrows(), total=len(sub_year), desc=f"{group_name}-{zone_label}-{year}"):
                    geom = geom_lookup.get(row["grid_id"])
                    if geom is None:
                        print(f"ADVERTENCIA: grid_id sin geometría: {row['grid_id']}")
                        continue
                    gdf_one, class_raster, patch_raster, transform, raster_crs = polygonize_rect_year(
                        src,
                        row,
                        geom,
                        output_crs=args.output_crs,
                        area_crs=args.area_crs,
                        min_patch_ha=args.min_patch_ha,
                        connectivity=args.connectivity,
                    )
                    if args.write_rasters and class_raster.size:
                        write_rect_rasters(
                            labels_dir=out_dir,
                            grid_id=str(row["grid_id"]),
                            year=int(row["review_year"]),
                            class_raster=class_raster,
                            patch_raster=patch_raster,
                            transform=transform,
                            crs=raster_crs,
                        )
                    if not gdf_one.empty:
                        outputs.append(gdf_one)
        if not outputs:
            print(f"[{group_name}/{zone_label}] No se generaron polígonos.")
            continue
        out = rename_geodataframe_columns(
            gpd.GeoDataFrame(pd.concat(outputs, ignore_index=True), geometry="geometry", crs=args.output_crs)
        )
        out = init_qa_defaults(out)
        if group_name == "clases_transversales":
            if "es_transv" not in out.columns:
                raise ValueError("Falta columna es_transv para filtrar clases_transversales.")
            out = out[out["es_transv"].astype(bool)].copy()
            if out.empty:
                print(f"[{group_name}/{zone_label}] No quedaron poligonos transversales.")
                continue
        if out_gpkg.exists() and args.overwrite:
            out_gpkg.unlink()
        out.to_file(out_gpkg, layer=layer, driver="GPKG")
        print(f"[{group_name}/{zone_label}] Escrito GPKG: {out_gpkg} ({len(out)} polígonos)")
        summary = (
            out.groupby(["rev_year", "class_id", "class_nm"], dropna=False)
            .agg(n_features=("grid_id", "count"), n_grid_id=("grid_id", "nunique"), area_ha=("area_ha", "sum"))
            .reset_index()
        )
        summary["area_ha"] = summary["area_ha"].round(2)
        summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
        if args.export_gee_asset:
            asset_id, geojson_path = resolve_gee_targets(group_name, args, out_gpkg)
            if args.split_by_utm and utm_zone:
                asset_id = f"{asset_id.rstrip('/')}/{utm_zone.lower()}"
                geojson_path = out_dir / f"{geojson_path.stem}_{utm_zone.lower()}{geojson_path.suffix}"
            print(f"[{group_name}/{zone_label}] Exportando a Earth Engine Asset...")
            export_gdf_to_asset(
                out,
                asset_id,
                project=args.gee_project,
                local_geojson=geojson_path,
                overwrite=args.overwrite,
                wait=args.gee_wait,
                force_auth=args.gee_authenticate,
            )

def parse_args():
    p = argparse.ArgumentParser(description="Genera subdivisiones C2 en cluster desde GeoTIFF anuales.")
    p.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR)
    p.add_argument("--plan-name", default=DEFAULT_PLAN_NAME)
    p.add_argument(
        "--only-grid-tags",
        nargs="*",
        default=None,
        choices=["homogeneo_2x2", "mixto_3x3"],
        help="Filtra rectángulos por tamaño (carpeta final_samples).",
    )
    p.add_argument("--raster-template", default="classification_{year}.tif")
    p.add_argument("--only-groups", nargs="*", default=None, choices=["anuales", "estables", "transiciones", "clases_raras", "clases_transversales", "otros"])
    p.add_argument("--only-years", nargs="*", type=int, default=None)
    p.add_argument("--max-rows", type=int, default=None,
                   help="Limita filas rectángulo-año tras expandir el plan.")
    p.add_argument("--max-rectangles", type=int, default=None,
                   help="Limita rectángulos únicos (grid_id) antes de procesar.")
    p.add_argument(
        "--only-grid-ids",
        nargs="*",
        default=None,
        help="Procesa solo estos grid_id (espacio-separados).",
    )
    p.add_argument(
        "--grid-ids-file",
        type=Path,
        default=None,
        help="CSV con columna grid_id para filtrar rectángulos.",
    )
    p.add_argument("--min-patch-ha", type=float, default=0.0)
    p.add_argument(
        "--connectivity",
        type=int,
        choices=(4, 8),
        default=4,
        help="Conectividad de parches al vectorizar (4=rook, diagonal separada; 8=queen).",
    )
    p.add_argument(
        "--no-dissolve",
        action="store_true",
        help="Alias legacy: equivale a --connectivity 4 (ya es el default).",
    )
    p.add_argument(
        "--split-by-utm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Escribe un GPKG (y rasters) por zona UTM bajo labels-dir/UTM18|UTM19/.",
    )
    p.add_argument(
        "--write-rasters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Escribe GeoTIFF por rectángulo-año en raster/classes y raster/labels.",
    )
    p.add_argument("--write-rare-copy", action="store_true", help="Crea copia adicional en grupo clases_raras para target_rare_class.")
    p.add_argument("--write-transversal-copy", action="store_true",
                   help="Crea copia en clases_transversales para rectangulos con modal transversal.")
    p.add_argument("--output-crs", default="EPSG:4326")
    p.add_argument("--area-crs", default="EPSG:6933")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--product-name", default=None,
                   help="Nombre de producto: escribe labels-dir/NAME.gpkg (sin subcarpeta de grupo).")
    p.add_argument("--output-gpkg", type=Path, default=None, help="Ruta completa al GeoPackage de salida.")
    p.add_argument("--output-layer", default=None, help="Nombre de capa GPKG (default: stem del gpkg o product-name).")
    p.add_argument("--summary-csv", type=Path, default=None, help="Ruta al CSV resumen.")
    p.add_argument("--asset-id", default=None, help="Asset ID GEE completo (sobreescribe gee-asset-base/product-name).")
    p.add_argument("--local-geojson", type=Path, default=None, help="GeoJSON local de staging para export GEE.")
    p.add_argument("--export-gee-asset", action="store_true",
                   help="Exporta además a Earth Engine Asset bajo SAMPLES_SSL4EO.")
    p.add_argument("--gee-project", default=DEFAULT_EE_PROJECT)
    p.add_argument("--gee-asset-base", default=DEFAULT_GEE_ASSET_BASE,
                   help="Prefijo del asset GEE (carpeta SAMPLES_SSL4EO).")
    p.add_argument("--gee-wait", action="store_true",
                   help="Espera a que termine la tarea de exportación GEE.")
    p.add_argument("--gee-authenticate", action="store_true",
                   help="Fuerza autenticación OAuth de Earth Engine antes de exportar.")
    return p.parse_args()

def load_requested_grid_ids(args) -> set[str] | None:
    ids: list[str] = []
    if args.only_grid_ids:
        ids.extend(str(x) for x in args.only_grid_ids)
    if args.grid_ids_file is not None:
        path = Path(args.grid_ids_file)
        if not path.exists():
            raise FileNotFoundError(f"No existe grid-ids-file: {path}")
        df = pd.read_csv(path, encoding="utf-8-sig")
        col = "grid_id" if "grid_id" in df.columns else df.columns[0]
        ids.extend(df[col].astype(str).tolist())
    return set(ids) if ids else None


def main() -> int:
    args = parse_args()
    if args.no_dissolve:
        args.connectivity = 4
    print("=== GENERAR ETIQUETAS / SUBDIVISIONES C2 EN CLUSTER ===")
    print(f"samples-dir:   {args.samples_dir}")
    print(f"landcover-dir: {args.landcover_dir}")
    print(f"labels-dir:    {args.labels_dir}")
    print(f"connectivity:  {args.connectivity} ({'rook' if args.connectivity == 4 else 'queen'})")
    print(f"split-by-utm:  {args.split_by_utm}")
    print(f"write-rasters: {args.write_rasters}")
    rects = read_rectangles(args.samples_dir)
    if args.only_grid_tags:
        allowed = set(args.only_grid_tags)
        rects = rects[rects["grid_tag"].isin(allowed)].copy()
        if rects.empty:
            raise ValueError(f"No quedaron rectángulos para grid_tags={sorted(allowed)}")
    plan = read_plan(args.samples_dir, args.plan_name)
    allowed_ids = set(rects["grid_id"].astype(str))
    plan = plan[plan["grid_id"].astype(str).isin(allowed_ids)].copy()
    if plan.empty:
        raise ValueError("El plan no tiene filas compatibles con los rectángulos cargados.")
    work = expand_plan(plan, write_rare_copy=args.write_rare_copy, write_transversal_copy=args.write_transversal_copy)
    if args.only_groups:
        work = work[work["label_group"].isin(args.only_groups)].copy()
    if args.only_years:
        work = work[work["review_year"].isin(args.only_years)].copy()
    requested_ids = load_requested_grid_ids(args)
    if requested_ids:
        work = work[work["grid_id"].astype(str).isin(requested_ids)].copy()
        missing = sorted(requested_ids - set(work["grid_id"].astype(str)))
        if missing:
            print(f"ADVERTENCIA: {len(missing)} grid_id no encontrados en plan/grupo filtrado: {missing[:10]}")
    work = work.sort_values(["label_group", "review_year", "grid_id"]).reset_index(drop=True)
    if args.max_rectangles is not None and args.max_rectangles > 0:
        keep_ids = work["grid_id"].drop_duplicates().head(args.max_rectangles)
        work = work[work["grid_id"].isin(keep_ids)].copy()
    if args.max_rows is not None and args.max_rows > 0:
        work = work.head(args.max_rows).copy()
    work = attach_utm_zone(work, rects)
    if work.empty:
        raise ValueError("No quedan filas para procesar después de filtros.")
    print("\nPlan expandido:")
    print(f"  rectángulo-año: {len(work)}")
    print("  por grupo:")
    print(work["label_group"].value_counts().to_string())
    print("  por UTM:")
    print(work["utm_zone"].value_counts().to_string())
    print("  años:")
    print(sorted(work["review_year"].unique().tolist()))
    for group_name in sorted(work["label_group"].unique()):
        process_group(group_name, work, rects, args)
    print("\nListo.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
