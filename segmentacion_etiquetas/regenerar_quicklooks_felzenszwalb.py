#!/usr/bin/env python3
"""
Regenera PNG de quick-look a partir de GeoTIFF de etiquetas ya exportados.

Útil cuando cambia la lógica de guardar_quicklook() pero no hace falta
re-ejecutar Felzenszwalb.

Uso:
  python regenerar_quicklooks_felzenszwalb.py
  python regenerar_quicklooks_felzenszwalb.py --output-dir /ruta/seg_Felzenszwalb
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import rasterio

from seg_felzenszwalb_grid import (
    DISPLAY_BANDS,
    MOSAIC_DIR,
    NODATA,
    OUTPUT_DIR,
    componer_rgb,
    construir_mascara_nodata,
    guardar_quicklook,
    localizar_mosaico_tile,
    resolver_nodata,
)

TIF_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)\.tif$"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenera PNG quick-look desde TIF de etiquetas.")
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT_DIR))
    parser.add_argument("--mosaic-dir", type=Path, default=Path(MOSAIC_DIR))
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if not output_dir.is_dir():
        print(f"[ERROR] OUTPUT_DIR no existe: {output_dir}")
        sys.exit(1)

    tifs = sorted(p for p in output_dir.glob("seg_*_s*_sig*.tif") if TIF_PATTERN.match(p.name))
    if not tifs:
        print(f"[ERROR] No hay TIF seg_*_s*_sig*.tif en {output_dir}")
        sys.exit(1)

    primer_match = TIF_PATTERN.match(tifs[0].name)
    assert primer_match is not None
    tile_ref = primer_match.group("tile")
    year_ref = int(primer_match.group("year"))
    ruta_mosaico = localizar_mosaico_tile(args.mosaic_dir, tile_ref, year_ref)
    print(f"[OK] Mosaico: {ruta_mosaico}")
    print(f"[OK] Regenerando {len(tifs)} PNG en {output_dir}")

    with rasterio.open(ruta_mosaico) as src:
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(np.float32)
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(datos, nodata_valor)
        rgb_base = componer_rgb(datos, DISPLAY_BANDS, validos)

        for ruta_tif in tifs:
            match = TIF_PATTERN.match(ruta_tif.name)
            assert match is not None
            scale = match.group("scale")
            sigma = match.group("sigma")
            tile = match.group("tile")
            year = match.group("year")

            with rasterio.open(ruta_tif) as seg:
                labels = seg.read(1).astype(np.int32)

            if labels.shape != validos.shape:
                print(f"[ERROR] Shape distinta en {ruta_tif.name}: {labels.shape} vs {validos.shape}")
                sys.exit(1)

            ruta_png = ruta_tif.with_suffix(".png")
            titulo = f"Felzenszwalb — {tile} {year} — s={scale}, σ={sigma}"
            guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
            print(f"  → {ruta_png.name}")

    print("[OK] PNG regenerados.")


if __name__ == "__main__":
    main()
