#!/usr/bin/env python3
"""Recorta y reproyecta Col2 nacional a la grilla UTM de un tile (referencia = segmentos)."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

DEFAULT_NATIONAL = Path("/home/lserey/mapbiomas_land/ancillary_data/landcover_col2")
DEFAULT_OUT_DIR = Path("/home/lserey/mapbiomas_land/test/image_segmentation/landcover_tiles")


def prepare_tile(
    national_raster: Path,
    reference_raster: Path,
    output_path: Path,
    *,
    band: int = 1,
    overwrite: bool = False,
) -> Path:
    if output_path.is_file() and not overwrite:
        print(f"[OK] Ya existe: {output_path}")
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(reference_raster) as ref:
        dst_profile = ref.profile.copy()
        dst_height = ref.height
        dst_width = ref.width
        dst_transform = ref.transform
        dst_crs = ref.crs

    dst = np.zeros((dst_height, dst_width), dtype=np.uint8)

    with rasterio.open(national_raster) as src:
        reproject(
            source=rasterio.band(src, band),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
        )

    dst_profile.update({"dtype": "uint8", "count": 1, "nodata": 0, "compress": "deflate"})

    with rasterio.open(output_path, "w", **dst_profile) as out:
        out.write(dst, 1)

    with rasterio.open(output_path) as chk:
        vals = np.unique(chk.read(1))
        print(
            f"[OK] {output_path.name}: {chk.width}×{chk.height} "
            f"CRS={chk.crs} · {len(vals)} valores únicos"
        )
    return output_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preparar landcover per-tile alineado a referencia UTM.")
    p.add_argument("--tile", required=True)
    p.add_argument("--year", type=int, default=2015)
    p.add_argument("--national-dir", type=Path, default=DEFAULT_NATIONAL)
    p.add_argument("--reference-raster", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    tile = args.tile.upper()
    national = args.national_dir / f"classification_{args.year}.tif"
    if not national.is_file():
        print(f"[ERROR] No existe: {national}")
        return 1

    ref = args.reference_raster
    if ref is None:
        ref = args.output_dir / f"{tile}_classification_2010.tif"
    if not ref.is_file():
        candidatos = sorted(
            Path("/home/lserey/mapbiomas_land/test/image_segmentation").glob(
                f"seg_*/seg_{tile}_2010*.tif"
            )
        )
        if candidatos:
            ref = candidatos[0]
        else:
            print(f"[ERROR] Sin raster referencia para grilla: {tile}")
            return 1

    out = args.output_dir / f"{tile}_classification_{args.year}.tif"
    print(f"[INFO] Nacional: {national}")
    print(f"[INFO] Referencia: {ref}")
    prepare_tile(national, ref, out, overwrite=args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
