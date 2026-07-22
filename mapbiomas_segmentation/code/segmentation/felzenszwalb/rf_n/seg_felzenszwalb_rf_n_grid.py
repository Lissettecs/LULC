#!/usr/bin/env python3
"""
Pipeline Felzenszwalb RF_N — segmentación con bandas seleccionadas por Random Forest.

Independiente de seg_felzenszwalb/seg_felzenszwalb_grid.py (mosaico 3 bandas nir/swir1/red).

Entrada: mosaico 184 bandas + selección per-tile del REPORT RF
  (importance_gated_clusters, Level 1 o Level 3).

Salida: seg_felzenszwalb_rf_n/ (no toca seg_felzenszwalb/).

Uso:
  python seg_felzenszwalb_rf_n_grid.py --tile 18HYD --year 2010
  python seg_felzenszwalb_rf_n_grid.py --rf-level 3 --combo-index 0 --resume
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from skimage.segmentation import felzenszwalb

_FELZ_DIR = Path(__file__).resolve().parent.parent / "seg_felzenszwalb"
if str(_FELZ_DIR) not in sys.path:
    sys.path.insert(0, str(_FELZ_DIR))

import seg_felzenszwalb_grid as base  # noqa: E402

from rf_selected_bands import (  # noqa: E402
    cargar_indices_desde_json,
    indices_para_tile,
    nombres_para_indices,
    resolver_posiciones_geotiff,
    resolver_rgb_desde_descriptions,
)

# ── PARÁMETROS PIPELINE RF_N ───────────────────────────────────────────────────
DEFAULT_TILE = base.DEFAULT_TILE
DEFAULT_YEAR = base.DEFAULT_YEAR
MOSAIC_184_DIR = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")
OUTPUT_DIR = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_n")

SCALE_LIST = list(base.SCALE_LIST)
SIGMA_LIST = list(base.SIGMA_LIST)
MIN_SIZE = base.MIN_SIZE
NODATA = base.NODATA
# ─────────────────────────────────────────────────────────────────────────────


def nombre_mosaico_184(tile: str, year: int) -> str:
    return f"TMP-CHILE-{tile}-{year}-SBAND-184B.tif"


def localizar_mosaico_184(mosaic_dir: Path, tile: str, year: int) -> Path:
    ruta = mosaic_dir / tile / nombre_mosaico_184(tile, year)
    if ruta.is_file():
        return ruta
    print(f"[ERROR] No se encontró '{ruta.name}' en {mosaic_dir / tile}")
    sys.exit(1)


def stem_salida(tile: str, year: int, scale: int, sigma: float, rf_level: int) -> str:
    return f"seg_{tile}_{year}_lv{rf_level}_rfn_s{scale}_sig{sigma}"


def resolver_grid_combos(combo_index: int | None) -> tuple[list[int], list[float]]:
    combos = [(scale, sigma) for scale in SCALE_LIST for sigma in SIGMA_LIST]
    if combo_index is None:
        return SCALE_LIST, SIGMA_LIST
    if combo_index < 0 or combo_index >= len(combos):
        raise ValueError(f"--combo-index fuera de rango: {combo_index} (0..{len(combos) - 1})")
    scale, sigma = combos[combo_index]
    return [scale], [sigma]


def diagnosticar_features_rf_n(
    src: rasterio.io.DatasetReader,
    datos: np.ndarray,
    validos: np.ndarray,
    nodata_valor: float | None,
    nombres: list[str],
) -> None:
    """Diagnóstico sobre el subconjunto de bandas RF (no las 184 del GeoTIFF)."""
    n_bandas = datos.shape[-1]
    h, w = datos.shape[:2]

    print("\n=== DIAGNÓSTICO BANDAS SELECCIONADAS (RF_N) ===")
    print(f"Archivo      : {src.name}")
    print(f"Bandas origen: {src.count} (usando {n_bandas} seleccionadas RF)")
    print(f"Dtype        : {src.dtypes[0]}")
    print(f"CRS          : {src.crs}")
    print(f"Transform    : {src.transform}")
    print(f"Shape (H,W)  : ({h}, {w})")
    print(f"NoData config: parámetro={NODATA!r}, metadata={src.nodata!r}, efectivo={nodata_valor!r}")
    if nodata_valor is None:
        print("Regla nodata : 0 en TODAS las bandas simultáneamente")
    print(f"Píxeles válidos: {validos.sum():,} / {validos.size:,} ({100 * validos.mean():.2f}%)")

    print("\nEstadísticas por banda (solo píxeles válidos):")
    print(f"{'Banda':>5}  {'Nombre':<28}  {'Min':>10}  {'Max':>10}  {'Media':>10}  {'%NoData':>8}")
    print("-" * 80)
    pct_nodata = 100.0 * (~validos).mean()
    for i in range(n_bandas):
        banda = datos[..., i]
        if np.any(validos):
            vals = banda[validos]
            vmin, vmax, vmean = float(vals.min()), float(vals.max()), float(vals.mean())
        else:
            vmin = vmax = vmean = float("nan")
        print(f"{i + 1:>5}  {nombres[i]:<28}  {vmin:10.3f}  {vmax:10.3f}  {vmean:10.3f}  {pct_nodata:7.2f}")


def listar_tiles_184(mosaic_dir: Path, year: int) -> list[str]:
    if not mosaic_dir.is_dir():
        return []
    tiles: list[str] = []
    for sub in sorted(mosaic_dir.iterdir()):
        if sub.is_dir() and (sub / nombre_mosaico_184(sub.name, year)).is_file():
            tiles.append(sub.name)
    return tiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Felzenszwalb RF_N: grid scale×sigma sobre bandas seleccionadas RF.",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--mosaic-184-dir", type=Path, default=MOSAIC_184_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--rf-level", type=int, choices=(1, 3), default=1)
    parser.add_argument("--selected-bands-json", type=Path, default=None)
    parser.add_argument("--list-tiles", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--combo-index",
        type=int,
        default=None,
        help=f"Índice 0..{len(SCALE_LIST) * len(SIGMA_LIST) - 1} para SLURM --array",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mosaic_dir = args.mosaic_184_dir.resolve()
    output_dir = args.output_dir.resolve()
    tile = args.tile.upper()
    year = args.year
    rf_level = args.rf_level

    if args.list_tiles:
        tiles = listar_tiles_184(mosaic_dir, year)
        if not tiles:
            print(f"[INFO] No hay tiles 184B en {mosaic_dir}")
        else:
            print(f"[INFO] Tiles 184B en {mosaic_dir}:")
            for nombre in tiles:
                print(f"  - {nombre}")
        return

    if not mosaic_dir.is_dir():
        print(f"[ERROR] MOSAIC_184_DIR no existe: {mosaic_dir}")
        sys.exit(1)

    tiles_disponibles = listar_tiles_184(mosaic_dir, year)
    if tile not in tiles_disponibles:
        print(f"[ERROR] Tile '{tile}' no encontrado en {mosaic_dir}")
        if tiles_disponibles:
            print(f"[INFO] Tiles disponibles: {', '.join(tiles_disponibles)}")
        sys.exit(1)

    ruta_mosaico = localizar_mosaico_184(mosaic_dir, tile, year)
    print(f"[OK] Pipeline Felzenszwalb RF_N · tile={tile} · año={year} · level={rf_level}")
    print(f"[OK] Mosaico 184B: {ruta_mosaico}")
    print(f"[OK] Salida: {output_dir}")

    if args.selected_bands_json:
        selected_indices = cargar_indices_desde_json(args.selected_bands_json.resolve())
        print(f"[OK] Bandas desde JSON ({len(selected_indices)}): {args.selected_bands_json}")
    else:
        selected_indices = indices_para_tile(tile, rf_level)
        print(f"[OK] Bandas REPORT lv{rf_level}: {len(selected_indices)} índices catálogo RF")

    selected_names = nombres_para_indices(selected_indices)
    print(f"[OK] Ej.: {', '.join(selected_names[:6])} …")

    try:
        scales, sigmas = resolver_grid_combos(args.combo_index)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    sufijo_csv = f"lv{rf_level}_rfn"
    ruta_csv = output_dir / f"resumen_{tile}_{year}_{sufijo_csv}.csv"
    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            stem = stem_salida(tile, year, scale, sigma, rf_level)
            rutas_previstas.extend([output_dir / f"{stem}.tif", output_dir / f"{stem}.png"])
    if args.combo_index is None:
        rutas_previstas.append(ruta_csv)

    if args.resume:
        print(f"[OK] --resume: omitir {sum(1 for r in rutas_previstas if r.exists())} existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    with rasterio.open(ruta_mosaico) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [descriptions[i] if i < len(descriptions) else "" for i in range(src.count)]

        feat_positions = resolver_posiciones_geotiff(descriptions, selected_names)
        rgb_positions = resolver_rgb_desde_descriptions(descriptions)
        print(f"[OK] GeoTIFF: {len(feat_positions)} features, RGB pos={rgb_positions}")

        perfil = src.profile
        nodata_valor = base.resolver_nodata(src, NODATA)

        feat_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in feat_positions],
            axis=-1,
        )
        rgb_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in rgb_positions],
            axis=-1,
        )

        validos = base.construir_mascara_nodata(feat_stack, nodata_valor)
        diagnosticar_features_rf_n(src, feat_stack, validos, nodata_valor, selected_names)

        img = base.rellenar_nodata_mediana(feat_stack, validos)
        print("\n[INFO] z-score por banda seleccionada (mosaico 184B heterogéneo).")
        img = base.estandarizar_zscore(img, validos)

        rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos)
        filas_resumen: list[dict] = []
        total = len(scales) * len(sigmas)
        paso = 0
        print(f"\n=== FELZENSZWALB RF_N ({total} combinaciones) ===")

        for scale in scales:
            for sigma in sigmas:
                paso += 1
                stem = stem_salida(tile, year, scale, sigma, rf_level)
                ruta_tif = output_dir / f"{stem}.tif"
                ruta_png = output_dir / f"{stem}.png"
                print(f"\n[{paso}/{total}] scale={scale}, sigma={sigma}, min_size={MIN_SIZE} ...")

                if args.resume and ruta_tif.is_file() and ruta_png.is_file():
                    print(f"  → [resume] {ruta_tif.name}")
                    with rasterio.open(ruta_tif) as src_l:
                        labels = src_l.read(1).astype(np.int32)
                    stats = base.estadisticas_segmentos(labels, validos)
                else:
                    labels = felzenszwalb(
                        img,
                        scale=scale,
                        sigma=sigma,
                        min_size=MIN_SIZE,
                        channel_axis=-1,
                    )
                    labels = labels.astype(np.int32)
                    labels[~validos] = 0
                    stats = base.estadisticas_segmentos(labels, validos)
                    titulo = (
                        f"Felzenszwalb RF_N lv{rf_level} — {tile} {year} — "
                        f"s={scale}, σ={sigma}, N={len(selected_indices)}"
                    )
                    base.guardar_geotiff_labels(labels, perfil, ruta_tif)
                    base.guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
                    print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")

                print(
                    f"  → segmentos={stats['n_segmentos']:,}, "
                    f"tam_medio={stats['tam_medio_px']:.1f} px"
                )
                filas_resumen.append(
                    {
                        "rf_level": rf_level,
                        "n_bands": len(selected_indices),
                        "scale": scale,
                        "sigma": sigma,
                        "min_size": MIN_SIZE,
                        **stats,
                    }
                )

    columnas = [
        "rf_level", "n_bands", "scale", "sigma", "min_size",
        "n_segmentos", "tam_medio_px", "tam_mediano_px",
        "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    if args.combo_index is None:
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        parcial = output_dir / f"resumen_{tile}_{year}_{sufijo_csv}_idx{args.combo_index}.csv"
        with parcial.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV parcial: {parcial}")

    base.imprimir_tabla(filas_resumen)
    print(f"[OK] Salidas RF_N en: {output_dir}")


if __name__ == "__main__":
    main()
