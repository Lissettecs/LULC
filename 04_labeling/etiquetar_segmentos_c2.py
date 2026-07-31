#!/usr/bin/env python3
"""
Etiqueta segmentos SLIC+RAG con MapBiomas Collection 2.

Por segmento calcula:
  clase_moda, pureza (%), clase_2, pureza_2 (%), n_clases, area_px, tiene_protegida

Entrada: salida de LULC/segmentacion (labels.tif + segments.gpkg opcional).
Salida: GPKG etiquetado + CSV + summary.json (sobrescribe si --force).

Uso (prueba 18GXA):
  python etiquetar_segmentos_c2.py --prueba-tile 18GXA --force
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.clases_c2 import CLASES_TIER_PROTEGIDO, C2_NODATA  # noqa: E402
from io_landcover import leer_landcover_alineado  # noqa: E402
from stats_c2 import calcular_stats_c2, stats_a_dataframe  # noqa: E402

DEFAULT_SEGMENTACION = Path("/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015")
DEFAULT_OUTPUT = Path("/home/lserey/mapbiomas_land/prod/labeling_slic_rev2015")
DEFAULT_LANDCOVER_DIR = Path("/home/lserey/mapbiomas_land/ancillary_data/landcover_col2")
LANDCOVER_TEMPLATE = "classification_{year}.tif"


def buscar_corrida_rect(rect_dir: Path) -> tuple[Path, Path | None]:
    """Encuentra labels.tif y gpkg de segmentos en un directorio de rectángulo."""
    labels = sorted(rect_dir.glob("*_slic_ragp*_labels.tif"))
    if not labels:
        labels = sorted(rect_dir.glob("*_labels.tif"))
    if not labels:
        raise FileNotFoundError(f"Sin raster de segmentos en {rect_dir}")
    gpkg = sorted(rect_dir.glob("*_slic_ragp*_segments.gpkg"))
    if not gpkg:
        gpkg = sorted(rect_dir.glob("*_segments.gpkg"))
    return labels[-1], (gpkg[-1] if gpkg else None)


def iter_rect_dirs(segmentacion_dir: Path, prueba_tile: str | None, grid_id: str | None):
    if grid_id:
        for p in segmentacion_dir.rglob(grid_id):
            if p.is_dir():
                yield p
        return
    if prueba_tile:
        tile = prueba_tile.upper()
        base = segmentacion_dir / tile
        if not base.is_dir():
            raise FileNotFoundError(f"Sin corridas en {base}")
        for d in sorted(base.iterdir()):
            if d.is_dir():
                yield d
        return
    for tile_dir in sorted(segmentacion_dir.iterdir()):
        if not tile_dir.is_dir() or tile_dir.name.startswith("."):
            continue
        for d in sorted(tile_dir.iterdir()):
            if d.is_dir():
                yield d


def procesar_rectangulo(
    rect_dir: Path,
    landcover_path: Path,
    out_root: Path,
    force: bool,
) -> dict:
    labels_path, seg_gpkg_path = buscar_corrida_rect(rect_dir)
    grid_id = rect_dir.name
    tile = rect_dir.parent.name
    out_dir = out_root / tile / grid_id
    out_dir.mkdir(parents=True, exist_ok=True)

    out_gpkg = out_dir / f"{grid_id}_labeled_segments.gpkg"
    out_csv = out_dir / f"{grid_id}_labeled_segments.csv"
    out_summary = out_dir / f"{grid_id}_labeling_summary.json"

    if out_gpkg.is_file() and not force:
        return {"grid_id": grid_id, "status": "skip", "output": str(out_gpkg)}

    with rasterio.open(labels_path) as src:
        segments = src.read(1)
        profile = src.profile.copy()

    c2 = leer_landcover_alineado(landcover_path, profile)
    stats = calcular_stats_c2(segments, c2, C2_NODATA, CLASES_TIER_PROTEGIDO)
    df_stats = stats_a_dataframe(stats)

    if seg_gpkg_path and seg_gpkg_path.is_file():
        gdf_geom = gpd.read_file(seg_gpkg_path)
        if "grid_id" in gdf_geom.columns:
            gdf_geom = gdf_geom.drop(columns=["grid_id"])
        # Una fila por segment_id (poligonización puede partir un id en varias geometrías)
        geom_cols = [c for c in gdf_geom.columns if c != "geometry" and c != "segment_id"]
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
    gdf.to_file(out_gpkg, driver="GPKG")
    df_stats.to_csv(out_csv, index=False)

    n_prot = int(df_stats["tiene_protegida"].sum())
    n_limpios = int((df_stats["pureza"] >= 95).sum())
    n_frontera = int(
        ((df_stats["pureza"] >= 45) & (df_stats["pureza"] < 55) & (df_stats["pureza_2"] >= 40)).sum()
    )

    summary = {
        "grid_id": grid_id,
        "tile": tile,
        "labels_raster": str(labels_path),
        "landcover_raster": str(landcover_path),
        "n_segments": int(len(df_stats)),
        "n_tiene_protegida": n_prot,
        "n_pureza_ge_95": n_limpios,
        "n_frontera_aprox_50_50": n_frontera,
        "clases_tier_protegido": sorted(CLASES_TIER_PROTEGIDO),
        "c2_nodata": sorted(C2_NODATA),
        "labeled_gpkg": str(out_gpkg),
        "labeled_csv": str(out_csv),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["status"] = "ok"
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Etiquetado C2 por segmento SLIC+RAG.")
    p.add_argument("--segmentacion-dir", type=Path, default=DEFAULT_SEGMENTACION)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--landcover-dir", type=Path, default=DEFAULT_LANDCOVER_DIR)
    p.add_argument("--year", type=int, default=2015)
    p.add_argument("--prueba-tile", type=str, default=None)
    p.add_argument("--grid-id", type=str, default=None)
    p.add_argument("--force", action="store_true", help="Sobrescribir salidas existentes")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    lc_path = args.landcover_dir / LANDCOVER_TEMPLATE.format(year=args.year)
    if not lc_path.is_file():
        raise FileNotFoundError(lc_path)

    rect_dirs = list(iter_rect_dirs(args.segmentacion_dir, args.prueba_tile, args.grid_id))
    if not rect_dirs:
        raise ValueError("No se encontraron directorios de rectángulo")

    print(f"Etiquetando {len(rect_dirs)} rectángulo(s) · landcover={lc_path.name}")
    resultados = []
    errores = []
    for rect_dir in rect_dirs:
        gid = rect_dir.name
        try:
            print(f"  → {gid}…", flush=True)
            res = procesar_rectangulo(rect_dir, lc_path, args.output_dir, args.force)
            if res.get("status") == "skip":
                print("     SKIP (ya existe; use --force)", flush=True)
            else:
                print(
                    f"     OK: {res['n_segments']} segs · "
                    f"protegida={res['n_tiene_protegida']} · "
                    f"pureza≥95%={res['n_pureza_ge_95']}",
                    flush=True,
                )
            resultados.append(res)
        except Exception as exc:
            print(f"     ERROR: {exc}", flush=True)
            errores.append({"grid_id": gid, "error": str(exc)})

    run_path = args.output_dir / f"run_labeling_{args.year}.json"
    run_path.write_text(
        json.dumps(
            {
                "year": args.year,
                "n_ok": sum(1 for r in resultados if r.get("status") != "error"),
                "n_error": len(errores),
                "results": resultados,
                "errors": errores,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResumen → {run_path}")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
