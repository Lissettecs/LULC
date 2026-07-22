#!/usr/bin/env python3
"""Consolida CSV parciales de etapa 3 Pipeline A."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/size_filter"
)


def consolidar(output_dir: Path, tile: str, year: int) -> Path:
    patron = f"resumen_size_filter_{tile}_{year}_idx*.csv"
    idx_files = sorted(output_dir.glob(patron))
    if not idx_files:
        print(f"[ERROR] No hay archivos {patron} en {output_dir}")
        sys.exit(1)

    filas: list[dict] = []
    for ruta in idx_files:
        with ruta.open(newline="", encoding="utf-8") as f:
            filas.extend(list(csv.DictReader(f)))

    if not filas:
        print("[ERROR] CSV parciales vacíos")
        sys.exit(1)

    salida = output_dir / f"resumen_size_filter_{tile}_{year}.csv"
    with salida.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=filas[0].keys())
        writer.writeheader()
        writer.writerows(filas)

    print(f"[OK] {salida} ({len(filas)} filas desde {len(idx_files)} parciales)")
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolida resumen_size_filter_*_idx*.csv"
    )
    parser.add_argument("--tile", default="18HYD")
    parser.add_argument("--year", type=int, default=2010)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    consolidar(args.output_dir.resolve(), args.tile.upper(), args.year)


if __name__ == "__main__":
    main()
