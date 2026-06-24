#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida un GeoPackage QA antes de publicar una version en GEE."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.qa_fields import validate_gdf  # noqa: E402

DEFAULT_GPKG = Path("/home/lserey/mapbiomas_land/prod/labels/annual/annual_samples.gpkg")
DEFAULT_LAYER = "annual_samples"


def parse_args():
    p = argparse.ArgumentParser(description="Valida cobertura QA y taxonomia antes de exportar version GEE.")
    p.add_argument("--gpkg", type=Path, default=DEFAULT_GPKG)
    p.add_argument("--layer", default=DEFAULT_LAYER)
    p.add_argument("--fail-on-warnings", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.gpkg.exists():
        raise FileNotFoundError(f"No existe GeoPackage: {args.gpkg}")

    gdf = gpd.read_file(args.gpkg, layer=args.layer)
    ok, msgs = validate_gdf(gdf)

    print(f"Validando: {args.gpkg} [{args.layer}] ({len(gdf)} features)")
    if not msgs:
        print("OK: sin problemas detectados.")
    else:
        for m in msgs:
            print(m)

    if not ok:
        return 1
    if args.fail_on_warnings and any(m.startswith("ADVERTENCIA:") for m in msgs):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
