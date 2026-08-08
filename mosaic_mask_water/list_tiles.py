#!/usr/bin/env python3
"""List CIM tiles available under mosaic_184bands/<year>/."""

from __future__ import annotations

import argparse
from pathlib import Path

from mask_mosaic_cim_tile import list_tiles


def parse_args() -> argparse.Namespace:
    base = Path("/home/lserey/mapbiomas_land")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2015)
    parser.add_argument(
        "--mosaic-root",
        type=Path,
        default=base / "mosaic_184bands",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tiles = list_tiles(args.mosaic_root, args.year)
    for tile in tiles:
        print(tile)
    print(f"# total: {len(tiles)}", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
