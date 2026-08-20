#!/usr/bin/env python3
"""
Etiqueta segmentos SLIC+RAG con MapBiomas Collection 2.

Entrada:  prod/03_segmentation_cim/{year}/{tile}/{grid_id}/
Salida:   prod/04_labeling_cim/{year}/{tile}/{grid_id}/

Uso:
  python label_segments_c2.py --year 2015
  python label_segments_c2.py --grid-id SI-19-Y-A_2x2_c009_r002 --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import rasterio

_STAGE = Path(__file__).resolve().parent
_PIPELINE = _STAGE.parent
sys.path.insert(0, str(_PIPELINE))
sys.path.insert(0, str(_STAGE))  # stage config/c2_classes before pipeline config/

from config.c2_classes import CLASES_TIER_PROTEGIDO, C2_NODATA  # noqa: E402

import importlib.util

_paths_spec = importlib.util.spec_from_file_location(
    "pipeline_paths", _PIPELINE / "config" / "paths.py"
)
_paths_mod = importlib.util.module_from_spec(_paths_spec)
assert _paths_spec.loader is not None
_paths_spec.loader.exec_module(_paths_mod)
labeling_dir = _paths_mod.labeling_dir
landcover_path = _paths_mod.landcover_path
segmentation_dir = _paths_mod.segmentation_dir
from io_landcover import read_aligned_landcover  # noqa: E402
from stats_c2 import compute_c2_stats, stats_to_dataframe  # noqa: E402

_SKIP_DIR_NAMES = frozenset({"logs", "consolidado", "work"})


def _tiene_summary(rect_dir: Path, year: int | None = None) -> bool:
    if year is not None:
        year_summ = rect_dir / f"{rect_dir.name}_{year}_summary.json"
        if year_summ.is_file():
            return True
    return bool(list(rect_dir.glob(f"{rect_dir.name}_*_summary.json"))) or bool(
        list(rect_dir.glob(f"{rect_dir.name}_summary.json"))
    )


def encontrar_corrida_rect(rect_dir: Path, year: int | None = None) -> tuple[Path, Path | None]:
    """Resuelve raster de labels y segments.gpkg (CIM year-aware o legacy)."""
    labels: list[Path] = []
    if year is not None:
        labels = sorted(rect_dir.glob(f"*_{year}_slic_ragp*_labels.tif"))
        if not labels:
            labels = sorted(rect_dir.glob(f"*_{year}_*_labels.tif"))
    if not labels:
        labels = sorted(rect_dir.glob("*_slic_ragp*_labels.tif"))
    if not labels:
        labels = sorted(rect_dir.glob("*_labels.tif"))
    if not labels:
        raise FileNotFoundError(f"Sin raster de segmentos en {rect_dir}")

    gpkg: list[Path] = []
    if year is not None:
        gpkg = sorted(rect_dir.glob(f"*_{year}_segments.gpkg"))
    if not gpkg:
        gpkg = sorted(rect_dir.glob("*_slic_ragp*_segments.gpkg"))
    if not gpkg:
        gpkg = sorted(rect_dir.glob("*_segments.gpkg"))
    return labels[-1], (gpkg[-1] if gpkg else None)


def iterar_dirs_rect(
    segmentation_root: Path,
    test_tile: str | None,
    grid_id: str | None,
    year: int | None = None,
):
    if grid_id:
        for p in segmentation_root.rglob(grid_id):
            if p.is_dir() and p.name == grid_id and _tiene_summary(p, year):
                yield p
        return
    if test_tile:
        tile = test_tile.upper()
        base = segmentation_root / tile
        if not base.is_dir():
            raise FileNotFoundError(f"Sin corridas bajo {base}")
        for d in sorted(base.iterdir()):
            if d.is_dir() and _tiene_summary(d, year):
                yield d
        return
    for tile_dir in sorted(segmentation_root.iterdir()):
        if not tile_dir.is_dir() or tile_dir.name.startswith(".") or tile_dir.name in _SKIP_DIR_NAMES:
            continue
        for d in sorted(tile_dir.iterdir()):
            if d.is_dir() and _tiene_summary(d, year):
                yield d


def procesar_rectangulo(
    rect_dir: Path,
    lc_path: Path,
    out_root: Path,
    year: int,
    force: bool,
) -> dict:
    labels_path, seg_gpkg_path = encontrar_corrida_rect(rect_dir, year)
    grid_id = rect_dir.name
    tile = rect_dir.parent.name
    out_dir = out_root / tile / grid_id
    out_dir.mkdir(parents=True, exist_ok=True)

    out_gpkg = out_dir / f"{grid_id}_{year}_labeled_segments.gpkg"
    out_csv = out_dir / f"{grid_id}_{year}_labeled_segments.csv"
    out_summary = out_dir / f"{grid_id}_{year}_labeling_summary.json"

    # Retrocompat: skip si ya existe naming legacy sin year
    legacy_gpkg = out_dir / f"{grid_id}_labeled_segments.gpkg"
    if (out_gpkg.is_file() or legacy_gpkg.is_file()) and not force:
        return {
            "grid_id": grid_id,
            "status": "skip",
            "output": str(out_gpkg if out_gpkg.is_file() else legacy_gpkg),
        }

    with rasterio.open(labels_path) as src:
        segments = src.read(1)
        profile = src.profile.copy()

    c2 = read_aligned_landcover(lc_path, profile)
    stats = compute_c2_stats(segments, c2, C2_NODATA, CLASES_TIER_PROTEGIDO)
    df_stats = stats_to_dataframe(stats)

    if seg_gpkg_path and seg_gpkg_path.is_file():
        gdf_geom = gpd.read_file(seg_gpkg_path)
        if "grid_id" in gdf_geom.columns:
            gdf_geom = gdf_geom.drop(columns=["grid_id"])
        geom_cols = [c for c in gdf_geom.columns if c not in ("geometry", "segment_id")]
        gdf_geom = (
            gdf_geom.dissolve(by="segment_id", aggfunc="first", as_index=False)
            if geom_cols
            else gdf_geom.dissolve(by="segment_id", as_index=False)
        )
        gdf = gdf_geom.merge(df_stats, on="segment_id", how="right")
    else:
        gdf = gpd.GeoDataFrame(df_stats, geometry=None, crs=None)

    if "grid_id" not in gdf.columns:
        gdf.insert(0, "grid_id", grid_id)
    if "rev_year" not in gdf.columns:
        gdf["rev_year"] = year
    gdf.to_file(out_gpkg, driver="GPKG")
    df_stats.to_csv(out_csv, index=False)

    n_prot = int(df_stats["has_protected"].sum())
    n_clean = int((df_stats["proportion"] >= 95).sum())
    n_boundary = int(
        (
            (df_stats["proportion"] >= 45)
            & (df_stats["proportion"] < 55)
            & (df_stats["proportion_2"] >= 40)
        ).sum()
    )

    summary = {
        "grid_id": grid_id,
        "tile": tile,
        "year": year,
        "labels_raster": str(labels_path),
        "segments_gpkg": str(seg_gpkg_path) if seg_gpkg_path else None,
        "landcover_raster": str(lc_path),
        "n_segments": int(len(df_stats)),
        "n_has_protected": n_prot,
        "n_proportion_ge_95": n_clean,
        "n_boundary_approx_50_50": n_boundary,
        "protected_tier_classes": sorted(CLASES_TIER_PROTEGIDO),
        "c2_nodata": sorted(C2_NODATA),
        "labeled_gpkg": str(out_gpkg),
        "labeled_csv": str(out_csv),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["status"] = "ok"
    return summary


# Aliases retrocompatibles
find_rect_run = encontrar_corrida_rect
iter_rect_dirs = iterar_dirs_rect
process_rectangle = procesar_rectangulo


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Etiquetado C2 de segmentos SLIC+RAG.")
    p.add_argument(
        "--year",
        type=int,
        default=int(os.environ.get("YEAR", os.environ.get("REV_YEAR", "2015"))),
    )
    p.add_argument("--segmentation-dir", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--landcover-path", type=Path, default=None)
    p.add_argument("--test-tile", type=str, default=None, help="Solo un tile CIM/MGRS")
    p.add_argument("--grid-id", type=str, default=None)
    p.add_argument("--force", action="store_true", help="Sobreescribir salidas existentes")
    p.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Omitir rectángulos ya etiquetados (default: on)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seg_root = args.segmentation_dir or segmentation_dir(args.year)
    out_root = args.output_dir or labeling_dir(args.year)
    lc_path = args.landcover_path or landcover_path(args.year)

    if not lc_path.is_file():
        raise FileNotFoundError(f"Landcover C2 no encontrado: {lc_path}")
    if not seg_root.is_dir():
        raise FileNotFoundError(f"Directorio de segmentación no encontrado: {seg_root}")

    force = args.force
    rect_dirs = list(iterar_dirs_rect(seg_root, args.test_tile, args.grid_id, args.year))
    if not rect_dirs:
        print("Sin rectángulos segmentados para etiquetar.")
        return 0

    print(
        f"Etiquetando {len(rect_dirs)} rectángulo(s) · year={args.year} · "
        f"landcover={lc_path.name}"
    )
    print(f"  seg={seg_root}")
    print(f"  out={out_root}")
    results = []
    errors = []
    for rect_dir in rect_dirs:
        gid = rect_dir.name
        try:
            print(f"  → {gid}…", flush=True)
            res = procesar_rectangulo(rect_dir, lc_path, out_root, year=args.year, force=force)
            if res.get("status") == "skip":
                print("     SKIP (ya existe; use --force)", flush=True)
            else:
                print(
                    f"     OK: {res['n_segments']} segmentos · "
                    f"protegida={res['n_has_protected']} · "
                    f"proporción≥95%={res['n_proportion_ge_95']}",
                    flush=True,
                )
            results.append(res)
        except Exception as exc:
            print(f"     ERROR: {exc}", flush=True)
            errors.append({"grid_id": gid, "error": str(exc)})

    out_root.mkdir(parents=True, exist_ok=True)
    run_path = out_root / f"run_labeling_{args.year}.json"
    run_path.write_text(
        json.dumps(
            {
                "year": args.year,
                "segmentation_dir": str(seg_root),
                "output_dir": str(out_root),
                "landcover": str(lc_path),
                "n_ok": sum(1 for r in results if r.get("status") == "ok"),
                "n_skip": sum(1 for r in results if r.get("status") == "skip"),
                "n_error": len(errors),
                "results": results,
                "errors": errors,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResumen → {run_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
