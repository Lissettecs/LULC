#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.gee_export import (  # noqa: E402
    DEFAULT_GEE_ASSET_BASE,
    DEFAULT_EE_PROJECT,
    build_asset_id,
    export_gdf_to_asset,
    local_gee_path,
)

DEFAULT_LABELS_DIR = Path("/home/lserey/mapbiomas_land/prod/labels")
GROUPS = ["anuales", "estables", "transiciones", "clases_raras", "clases_transversales", "otros"]


def parse_args():
    p = argparse.ArgumentParser(
        description="Exporta subdivisiones C2 (GeoPackage) a Earth Engine Asset en SAMPLES_SSL4EO."
    )
    p.add_argument("--labels-dir", type=Path, default=DEFAULT_LABELS_DIR)
    p.add_argument("--group", choices=GROUPS, required=True)
    p.add_argument("--patches", action="store_true", help="Usar capa *_patches en lugar del grupo.")
    p.add_argument("--gee-project", default=DEFAULT_EE_PROJECT)
    p.add_argument("--gee-asset-base", default=DEFAULT_GEE_ASSET_BASE)
    p.add_argument("--asset-id", default=None, help="Asset ID completo (sobreescribe --gee-asset-base).")
    p.add_argument("--gpkg", type=Path, default=None, help="Ruta al GeoPackage de entrada.")
    p.add_argument("--layer", default=None, help="Capa GPKG (default: stem del archivo o subdivisiones_C2_GROUP).")
    p.add_argument("--local-geojson", type=Path, default=None, help="GeoJSON local de staging.")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--authenticate", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    suffix = "patches" if args.patches else args.group
    gpkg = args.gpkg or (args.labels_dir / args.group / f"subdivisiones_C2_{suffix}.gpkg")
    layer = args.layer or (gpkg.stem if args.gpkg else f"subdivisiones_C2_{suffix}")
    if not gpkg.exists():
        raise FileNotFoundError(f"No existe GeoPackage: {gpkg}")

    print(f"Leyendo: {gpkg} [{layer}]")
    gdf = gpd.read_file(gpkg, layer=layer)
    print(f"  features: {len(gdf)}")

    asset_id = args.asset_id or build_asset_id(args.gee_asset_base, args.group, suffix)
    if args.local_geojson is not None:
        geojson_path = args.local_geojson
        geojson_path.parent.mkdir(parents=True, exist_ok=True)
    elif args.gpkg is not None:
        geojson_path = gpkg.with_suffix(".geojson")
    else:
        geojson_path = local_gee_path(args.labels_dir, args.group, suffix)

    export_gdf_to_asset(
        gdf,
        asset_id,
        project=args.gee_project,
        local_geojson=geojson_path,
        overwrite=args.overwrite,
        wait=args.wait,
        force_auth=args.authenticate,
    )
    print(f"\nAsset destino: {asset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
