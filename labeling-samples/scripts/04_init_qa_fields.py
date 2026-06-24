#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inicializa o actualiza campos QA en un GeoPackage existente (sin re-polygonizar)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.field_names import rename_geodataframe_columns  # noqa: E402
from mb_labels.qa_fields import compute_cov_rect, compute_lbl_id, ensure_poly_uid, init_qa_defaults  # noqa: E402

DEFAULT_GPKG = Path("/home/lserey/mapbiomas_land/prod/labels/annual/annual_samples.gpkg")
DEFAULT_LAYER = "annual_samples"


def parse_args():
    p = argparse.ArgumentParser(description="Backfill poly_uid y campos QA en GeoPackage de etiquetas.")
    p.add_argument("--gpkg", type=Path, default=DEFAULT_GPKG)
    p.add_argument("--layer", default=DEFAULT_LAYER)
    p.add_argument("--output-gpkg", type=Path, default=None, help="Si se omite, sobrescribe --gpkg.")
    p.add_argument("--output-layer", default=None)
    p.add_argument("--overwrite", action="store_true", help="Reescribir archivo de salida.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.gpkg.exists():
        raise FileNotFoundError(f"No existe GeoPackage: {args.gpkg}")

    out_gpkg = args.output_gpkg or args.gpkg
    out_layer = args.output_layer or args.layer
    if out_gpkg.exists() and out_gpkg.resolve() != args.gpkg.resolve() and not args.overwrite:
        raise FileExistsError(f"Ya existe {out_gpkg}; use --overwrite")

    print(f"Leyendo: {args.gpkg} [{args.layer}]")
    gdf = gpd.read_file(args.gpkg, layer=args.layer)
    print(f"  features: {len(gdf)}")

    gdf = rename_geodataframe_columns(gdf)
    gdf = init_qa_defaults(gdf)
    gdf["lbl_id"] = compute_lbl_id(gdf)
    gdf["cov_rect"] = compute_cov_rect(gdf)

    if out_gpkg.exists() and args.overwrite:
        out_gpkg.unlink()

    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_gpkg, layer=out_layer, driver="GPKG")
    print(f"Escrito: {out_gpkg} [{out_layer}]")
    print(f"  poly_uid: {gdf['poly_uid'].nunique()} unicos")
    print(f"  columnas QA: rect_qa, poly_qa, qa_scope, corr_id, err_type, lbl_id, cov_rect, qa_ver")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
