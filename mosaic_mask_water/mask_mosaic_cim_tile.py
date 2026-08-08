#!/usr/bin/env python3
"""Mask a CIM harmonized 184-band mosaic (GEE shards) with water/glacier ancillary rasters.

Stitches shard GeoTIFFs into one output mosaic per CIM tile, warps national ancillary
layers to the mosaic grid, and writes nodata where water or glacier is present.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Compression
from rasterio.transform import Affine, rowcol
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window


MASK_NODATA = 0
OUTPUT_NODATA = -9999.0
SHARD_SUFFIX_RE = re.compile(r"(\d{10})-(\d{10})\.tif$")
TILE_IN_NAME_RE = re.compile(r"^CHILE-([^-]+-[^-]+-[^-]+-[^-]+)-(\d{4})-")


def parse_args() -> argparse.Namespace:
    base = Path("/home/lserey/mapbiomas_land")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tile",
        required=True,
        help="CIM grid id, e.g. SE-19-V-D",
    )
    parser.add_argument("--year", type=int, default=2015, help="Mosaic/ancillary year")
    parser.add_argument(
        "--mosaic-root",
        type=Path,
        default=base / "mosaic_184bands",
    )
    parser.add_argument(
        "--ancillary-root",
        type=Path,
        default=base / "ancillary_data",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=base / "mosaic_184bands_mask_water",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep warped masks and exclude raster in the work directory",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class ShardInfo:
    path: Path
    window: Window


def shard_paths(mosaic_root: Path, tile: str, year: int) -> list[Path]:
    tile_dir = mosaic_root / str(year)
    pattern = f"CHILE-{tile}-{year}-*.tif"
    paths = sorted(p for p in tile_dir.glob(pattern) if SHARD_SUFFIX_RE.search(p.name))
    if not paths:
        raise FileNotFoundError(f"No shard GeoTIFFs for tile {tile} in {tile_dir}")
    return paths


def ancillary_paths(ancillary_root: Path, year: int) -> tuple[Path, Path]:
    glacier = ancillary_root / "glacier_col1" / f"{year}_annual_glacier_surface.tif"
    water = ancillary_root / "water_col1" / f"{year}_water_water_surface.tif"
    for path in (glacier, water):
        if not path.is_file():
            raise FileNotFoundError(path)
    return glacier, water


def merged_profile_from_shards(shards: list[Path]) -> tuple[dict, list[ShardInfo]]:
    bounds = []
    with rasterio.open(shards[0]) as ref:
        res = ref.res[0]
        crs = ref.crs
        count = ref.count
        dtype = ref.dtypes[0]

    for shard in shards:
        with rasterio.open(shard) as ds:
            bounds.append(ds.bounds)

    west = min(b.left for b in bounds)
    geo_south = min(b.top for b in bounds)
    transform = Affine(res, 0, west, 0, res, geo_south)

    shard_infos: list[ShardInfo] = []
    width = 0
    height = 0
    for shard in shards:
        with rasterio.open(shard) as ds:
            b = ds.bounds
            row0, col0 = rowcol(transform, b.left, b.top)
            window = Window(col0, row0, ds.width, ds.height)
            width = max(width, int(window.col_off + window.width))
            height = max(height, int(window.row_off + window.height))
            shard_infos.append(ShardInfo(path=shard, window=window))

    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": count,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "compress": Compression.deflate.value,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "nodata": OUTPUT_NODATA,
        "BIGTIFF": "YES",
    }
    return profile, shard_infos


def output_mosaic_path(output_root: Path, tile: str, year: int, shards: list[Path]) -> Path:
    stem = shards[0].name
    stem = SHARD_SUFFIX_RE.sub("", stem)
    if not stem.endswith(".tif"):
        stem += ".tif"
    return output_root / str(year) / stem.replace(".tif", "_masked.tif")


def mosaic_profile(ref_profile: dict) -> dict:
    return ref_profile.copy()


def warp_binary_to_mosaic(src_path: Path, ref_profile: dict, out_path: Path) -> dict:
    mask_profile = ref_profile.copy()
    mask_profile.update(count=1, dtype="uint8", nodata=MASK_NODATA, compress=Compression.deflate.value)

    with rasterio.open(src_path) as src:
        with rasterio.open(out_path, "w", **mask_profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref_profile["transform"],
                dst_crs=ref_profile["crs"],
                src_nodata=MASK_NODATA,
                dst_nodata=MASK_NODATA,
                resampling=Resampling.nearest,
            )

    with rasterio.open(out_path) as ds:
        data = ds.read(1)
        ones = int(np.sum(data == 1))
        zeros = int(np.sum(data == 0))
        other = int(data.size - ones - zeros)
        return {
            "path": str(out_path),
            "pixels_1": ones,
            "pixels_0": zeros,
            "pixels_other": other,
            "fraction_1": ones / data.size,
        }


def build_exclude_mask(glacier_path: Path, water_path: Path, out_path: Path, ref_profile: dict) -> dict:
    mask_profile = ref_profile.copy()
    mask_profile.update(count=1, dtype="uint8", nodata=MASK_NODATA, compress=Compression.deflate.value)

    with rasterio.open(glacier_path) as glacier, rasterio.open(water_path) as water:
        g = glacier.read(1)
        w = water.read(1)
        exclude = ((g == 1) | (w == 1)).astype(np.uint8)
        with rasterio.open(out_path, "w", **mask_profile) as dst:
            dst.write(exclude, 1)

    ones = int(np.sum(exclude == 1))
    return {
        "path": str(out_path),
        "pixels_1": ones,
        "fraction_1": ones / exclude.size,
    }


def apply_mask_to_shards(
    shard_infos: list[ShardInfo],
    exclude_path: Path,
    mosaic_out: Path,
    ref_profile: dict,
) -> dict:
    masked_pixels = 0
    total_pixels = ref_profile["width"] * ref_profile["height"]

    with rasterio.open(exclude_path) as exclude_src:
        with rasterio.open(mosaic_out, "w", **ref_profile) as dst:
            for shard in shard_infos:
                with rasterio.open(shard.path) as src:
                    if src.count != ref_profile["count"]:
                        raise ValueError(f"Band count mismatch in {shard.path}")

                    for _, window in src.block_windows(1):
                        out_window = Window(
                            shard.window.col_off + window.col_off,
                            shard.window.row_off + window.row_off,
                            window.width,
                            window.height,
                        )
                        exclude = exclude_src.read(1, window=out_window) == 1
                        if exclude.any():
                            masked_pixels += int(exclude.sum())

                        for band in range(1, src.count + 1):
                            data = src.read(band, window=window)
                            if exclude.any():
                                data = data.copy()
                                data[exclude] = OUTPUT_NODATA
                            dst.write(data, band, window=out_window)

    return {
        "path": str(mosaic_out),
        "masked_pixels": masked_pixels,
        "total_pixels": total_pixels,
        "masked_fraction": masked_pixels / total_pixels,
        "band_count": ref_profile["count"],
        "output_nodata": OUTPUT_NODATA,
        "shard_count": len(shard_infos),
    }


def list_tiles(mosaic_root: Path, year: int) -> list[str]:
    tile_dir = mosaic_root / str(year)
    tiles: set[str] = set()
    for path in tile_dir.glob("CHILE-*-*.tif"):
        match = TILE_IN_NAME_RE.match(path.name)
        if match and int(match.group(2)) == year and SHARD_SUFFIX_RE.search(path.name):
            tiles.add(match.group(1))
    return sorted(tiles)


def main() -> int:
    args = parse_args()
    work_dir = args.output_root / "work" / args.tile
    work_dir.mkdir(parents=True, exist_ok=True)
    args.output_root.joinpath(str(args.year)).mkdir(parents=True, exist_ok=True)

    shards = shard_paths(args.mosaic_root, args.tile, args.year)
    mosaic_out = output_mosaic_path(args.output_root, args.tile, args.year, shards)
    summary_path = work_dir / "mask_summary.json"

    if summary_path.is_file() and mosaic_out.is_file():
        print(f"[SKIP] {args.tile} already masked ({mosaic_out})")
        return 0

    glacier_src, water_src = ancillary_paths(args.ancillary_root, args.year)
    glacier_on_mosaic = work_dir / f"glacier_{args.year}_on_mosaic.tif"
    water_on_mosaic = work_dir / f"water_{args.year}_on_mosaic.tif"
    exclude_mask = work_dir / "exclude_water_glacier.tif"

    print(f"[INFO] Tile         : {args.tile}")
    print(f"[INFO] Shards       : {len(shards)}")
    print(f"[INFO] Mosaic output: {mosaic_out}")
    print(f"[INFO] Work dir     : {work_dir}")

    ref_profile, shard_infos = merged_profile_from_shards(shards)
    input_meta = {
        "tile": args.tile,
        "year": args.year,
        "shard_paths": [str(p) for p in shards],
        "crs": ref_profile["crs"].to_string() if ref_profile["crs"] else None,
        "width": ref_profile["width"],
        "height": ref_profile["height"],
        "count": ref_profile["count"],
        "dtype": ref_profile["dtype"],
        "transform": list(ref_profile["transform"]),
    }

    print("[STEP 1/3] Warp glacier mask to mosaic grid...")
    glacier_stats = warp_binary_to_mosaic(glacier_src, ref_profile, glacier_on_mosaic)
    print(f"           glacier pixels=1: {glacier_stats['pixels_1']:,} ({glacier_stats['fraction_1']:.4%})")

    print("[STEP 2/3] Warp water mask to mosaic grid...")
    water_stats = warp_binary_to_mosaic(water_src, ref_profile, water_on_mosaic)
    print(f"           water pixels=1  : {water_stats['pixels_1']:,} ({water_stats['fraction_1']:.4%})")

    print("[STEP 2/3] Build combined exclude mask...")
    exclude_stats = build_exclude_mask(glacier_on_mosaic, water_on_mosaic, exclude_mask, ref_profile)
    print(
        f"           exclude pixels=1: {exclude_stats['pixels_1']:,} "
        f"({exclude_stats['fraction_1']:.4%})"
    )

    print("[STEP 3/3] Apply mask and write merged mosaic...")
    output_stats = apply_mask_to_shards(shard_infos, exclude_mask, mosaic_out, ref_profile)
    print(
        f"           masked pixels   : {output_stats['masked_pixels']:,} "
        f"({output_stats['masked_fraction']:.4%})"
    )

    if not args.keep_intermediates:
        for path in (glacier_on_mosaic, water_on_mosaic, exclude_mask):
            path.unlink(missing_ok=True)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tile": args.tile,
        "year": args.year,
        "mosaic_input": input_meta,
        "mosaic_output": output_stats,
        "glacier_mask": glacier_stats,
        "water_mask": water_stats,
        "exclude_mask": exclude_stats,
        "notes": {
            "mask_rule": "(glacier == 1) OR (water == 1)",
            "output_nodata": OUTPUT_NODATA,
            "source_shards_unmodified": True,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
