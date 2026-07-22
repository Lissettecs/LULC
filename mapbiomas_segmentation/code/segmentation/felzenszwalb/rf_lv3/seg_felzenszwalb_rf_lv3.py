#!/usr/bin/env python3
"""
Felzenszwalb sobre bandas seleccionadas por RF (Level 3) leídas desde REPORT .md.

A diferencia de seg_felzenszwalb_rf_n (índices embebidos lv1/lv3 en rf_selected_bands.py),
este script parsea lv3_multitile.md y resuelve bandas por NOMBRE en el GeoTIFF 184B.

Salidas en seg_felzenszwalb_rf_lv3/ — no sobrescribe seg_felzenszwalb/ ni seg_felzenszwalb_rf_n/.

Uso:
  python seg_felzenszwalb_rf_lv3.py --dry-run
  python seg_felzenszwalb_rf_lv3.py --tile 18HYD --year 2010
  python seg_felzenszwalb_rf_lv3.py --resume
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from skimage.segmentation import felzenszwalb

_SCRIPT_DIR = Path(__file__).resolve().parent
_FELZ_DIR = _SCRIPT_DIR.parent / "seg_felzenszwalb"
_RF_N_DIR = _SCRIPT_DIR.parent / "seg_felzenszwalb_rf_n"
for _p in (_SCRIPT_DIR, _FELZ_DIR, _RF_N_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import seg_felzenszwalb_grid as base  # noqa: E402
from parse_lv3_report import (  # noqa: E402
    BandEntry,
    ReportParseError,
    bandas_para_tile,
    imprimir_bandas_tile,
    parse_lv3_report_md,
)
from rf_selected_bands import resolver_rgb_desde_descriptions  # noqa: E402

# ── FUENTE REPORT ──────────────────────────────────────────────────────────────
REPORT_MD = Path(
    "/home/lserey/repositorio/coverage_test/random_forest/REPORT/reports/lv3_multitile.md"
)

# ── ENTRADA STACK ──────────────────────────────────────────────────────────────
MOSAIC_184_DIR = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")

# ── PARÁMETROS FIJOS ───────────────────────────────────────────────────────────
DEFAULT_TILE = "18HYD"
DEFAULT_YEAR = 2010
SCALE_LIST = [200]
SIGMA_LIST = [0.1]
MIN_SIZE = 20
STANDARDIZE = True
REF_3BANDAS_NSEG = 16732

OUTPUT_DIR = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_lv3")
NODATA = base.NODATA
# ─────────────────────────────────────────────────────────────────────────────


def stack_path(tile: str, year: int, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    return MOSAIC_184_DIR / tile / f"TMP-CHILE-{tile}-{year}-SBAND-184B.tif"


def stem_salida(tile: str, year: int, scale: int, sigma: float) -> str:
    return f"seg_{tile}_{year}_lv3_rf_s{scale}_sig{sigma}"


def resolver_nombres_en_geotiff(
    descriptions: list[str],
    entradas_report: list[BandEntry],
) -> tuple[list[str], list[BandEntry], list[BandEntry]]:
    """Devuelve (nombres_usados, encontradas, faltantes). No sustituye faltantes."""
    mapa = {d: i for i, d in enumerate(descriptions) if d}
    encontradas: list[BandEntry] = []
    faltantes: list[BandEntry] = []
    for e in entradas_report:
        if e.name in mapa:
            encontradas.append(e)
        else:
            faltantes.append(e)
    nombres_usados = [e.name for e in encontradas]
    return nombres_usados, encontradas, faltantes


def leer_bandas(
    src: rasterio.io.DatasetReader,
    descriptions: list[str],
    nombres: list[str],
) -> np.ndarray:
    mapa = {d: i for i, d in enumerate(descriptions) if d}
    return np.stack(
        [src.read(mapa[n] + 1).astype(np.float32) for n in nombres],
        axis=-1,
    )


def imprimir_stats_bandas(
    datos: np.ndarray,
    validos: np.ndarray,
    nombres: list[str],
    titulo: str,
) -> None:
    print(f"\n=== {titulo} ===")
    print(f"{'Banda':<28}  {'Media':>10}  {'Std':>10}")
    print("-" * 54)
    for i, nombre in enumerate(nombres):
        vals = datos[..., i][validos]
        if vals.size:
            media, std = float(vals.mean()), float(vals.std())
        else:
            media, std = float("nan"), float("nan")
        print(f"{nombre:<28}  {media:10.4f}  {std:10.4f}")


def imprimir_resolucion_stack(
    descriptions: list[str],
    encontradas: list[BandEntry],
    faltantes: list[BandEntry],
) -> None:
    no_vacias = [d for d in descriptions if d]
    print(f"\n=== Resolución bandas REPORT → GeoTIFF ===")
    print(f"Descriptions no vacías: {len(no_vacias)} / {len(descriptions)}")
    if not no_vacias:
        print("[ERROR] El stack no trae nombres; definir mapa manual.")
        sys.exit(1)

    print(f"Encontradas en stack: {len(encontradas)}")
    for e in encontradas:
        print(f"  ✓ band_{e.index:>3}  {e.name}")
    if faltantes:
        print(f"Faltantes (se omiten, sin sustituto): {len(faltantes)}")
        for e in faltantes:
            print(f"  ✗ band_{e.index:>3}  {e.name}")


def comparar_referencias(tile: str, year: int, scale: int, sigma: float, n_segmentos: int) -> None:
    print("\n=== VERIFICACIÓN vs referencias ===")
    ratio = n_segmentos / REF_3BANDAS_NSEG
    print(f"Lv3 RF (este run)     : {n_segmentos:,} segmentos")
    print(f"3 bandas (referencia) : {REF_3BANDAS_NSEG:,}  →  ratio = {ratio:.2f}×")
    if ratio > 4.0:
        print(
            "[ADVERTENCIA] Ratio >4× vs 3 bandas: el stack Lv3 fragmenta de más para geometría."
        )

    ref_rf_n = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_n")
    patron = ref_rf_n / f"resumen_{tile}_{year}_lv3_rfn.csv"
    if not patron.is_file():
        patron = ref_rf_n / f"resumen_{tile}_{year}_lv1_rfn.csv"
    if patron.is_file():
        with patron.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if int(float(row["scale"])) == scale and abs(float(row["sigma"]) - sigma) < 1e-9:
                    n_prev = int(float(row["n_segmentos"]))
                    n_bands = row.get("n_bands", "?")
                    print(
                        f"RF_N previo ({patron.name}) : {n_prev:,} segmentos "
                        f"({n_bands} bandas índice)  →  ratio = {n_segmentos / n_prev:.2f}×"
                    )
                    break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Felzenszwalb Lv3: bandas desde REPORT .md + stack 184B por nombre.",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--report-md", type=Path, default=REPORT_MD)
    parser.add_argument("--stack-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Solo parsear REPORT e imprimir bandas")
    parser.add_argument("--list-tiles-report", action="store_true", help="Listar tiles en el REPORT")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tile = args.tile.upper()
    year = args.year
    report_path = args.report_md.resolve()
    output_dir = args.output_dir.resolve()

    try:
        por_tile = parse_lv3_report_md(report_path)
    except ReportParseError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if args.list_tiles_report:
        print(f"[INFO] Tiles en {report_path.name}:")
        for t in sorted(por_tile):
            print(f"  - {t}: {len(por_tile[t])} bandas")
        return 0

    try:
        entradas_report = bandas_para_tile(report_path, tile)
    except ReportParseError as exc:
        print(f"[ERROR] {exc}")
        return 1

    imprimir_bandas_tile(entradas_report, tile, report_path)

    if args.dry_run:
        print("\n[OK] --dry-run: parseo verificado. Sin segmentación.")
        return 0

    ruta_stack = stack_path(tile, year, args.stack_path)
    if not ruta_stack.is_file():
        print(f"[ERROR] STACK no encontrado: {ruta_stack}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[OK] Stack 184B: {ruta_stack}")
    print(f"[OK] Salida: {output_dir}")
    print(f"[OK] Parámetros: scale={SCALE_LIST}, σ={SIGMA_LIST}, min_size={MIN_SIZE}, z-score=ON")

    rutas_previstas: list[Path] = []
    for scale in SCALE_LIST:
        for sigma in SIGMA_LIST:
            stem = stem_salida(tile, year, scale, sigma)
            rutas_previstas.extend([output_dir / f"{stem}.tif", output_dir / f"{stem}.png"])
    ruta_csv = output_dir / f"resumen_{tile}_{year}_lv3_rf.csv"
    rutas_previstas.append(ruta_csv)

    if args.resume:
        print(f"[OK] --resume: {sum(1 for r in rutas_previstas if r.exists())} archivos ya existen")
    else:
        existentes = [r for r in rutas_previstas if r.exists()]
        if existentes:
            print("[ERROR] Archivos existentes (no se sobrescriben):")
            for r in existentes[:12]:
                print(f"  - {r}")
            if len(existentes) > 12:
                print(f"  … y {len(existentes) - 12} más")
            print("Usa --resume o elimina OUTPUT_DIR.")
            return 1

    with rasterio.open(ruta_stack) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [
                descriptions[i] if i < len(descriptions) else "" for i in range(src.count)
            ]

        nombres_usados, encontradas, faltantes = resolver_nombres_en_geotiff(
            descriptions, entradas_report
        )
        imprimir_resolucion_stack(descriptions, encontradas, faltantes)

        if not nombres_usados:
            print("[ERROR] Ninguna banda del REPORT está en el GeoTIFF.")
            return 1

        rgb_positions = resolver_rgb_desde_descriptions(descriptions)
        perfil = src.profile
        nodata_valor = base.resolver_nodata(src, NODATA)

        # Máscara ÚNICA sobre el stack completo de bandas del REPORT (encontradas).
        feat_stack = leer_bandas(src, descriptions, nombres_usados)
        validos = base.construir_mascara_nodata(feat_stack, nodata_valor)
        print(
            f"\n[OK] Máscara única (stack REPORT completo, {len(nombres_usados)} bandas): "
            f"{validos.sum():,} / {validos.size:,} píxeles válidos "
            f"({100 * validos.mean():.2f}%)"
        )

        rgb_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in rgb_positions],
            axis=-1,
        )
        rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos)

        img = base.rellenar_nodata_mediana(feat_stack, validos)
        imprimir_stats_bandas(img, validos, nombres_usados, "ANTES z-score (por banda)")

        if not STANDARDIZE:
            print("[ERROR] STANDARDIZE debe ser True")
            return 1
        img = base.estandarizar_zscore(img, validos)
        imprimir_stats_bandas(img, validos, nombres_usados, "DESPUÉS z-score (objetivo ~0 / ~1)")

        filas_resumen: list[dict] = []
        for scale in SCALE_LIST:
            for sigma in SIGMA_LIST:
                stem = stem_salida(tile, year, scale, sigma)
                ruta_tif = output_dir / f"{stem}.tif"
                ruta_png = output_dir / f"{stem}.png"

                if args.resume and ruta_tif.is_file() and ruta_png.is_file():
                    print(f"\n[resume] {ruta_tif.name}")
                    with rasterio.open(ruta_tif) as src_l:
                        labels = src_l.read(1).astype(np.int32)
                    stats = base.estadisticas_segmentos(labels, validos)
                else:
                    print(f"\n[Felzenszwalb Lv3 RF] scale={scale}, sigma={sigma}, min_size={MIN_SIZE}")
                    print(f"[INFO] img.shape={img.shape}  C={img.shape[-1]} bandas desde REPORT")

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
                        f"Felzenszwalb Lv3 RF — {tile} {year} — "
                        f"s={scale}, σ={sigma}, N={len(nombres_usados)}"
                    )
                    base.guardar_geotiff_labels(labels, perfil, ruta_tif)
                    base.guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
                    print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")

                print(
                    f"  → segmentos={stats['n_segmentos']:,}, "
                    f"tam_medio={stats['tam_medio_px']:.1f} px, "
                    f"tam_mediano={stats['tam_mediano_px']:.1f} px"
                )
                comparar_referencias(tile, year, scale, sigma, stats["n_segmentos"])

                filas_resumen.append(
                    {
                        "report_md": str(report_path),
                        "n_bands_report": len(entradas_report),
                        "n_bands_usadas": len(nombres_usados),
                        "n_bands_faltantes": len(faltantes),
                        "scale": scale,
                        "sigma": sigma,
                        "min_size": MIN_SIZE,
                        **stats,
                    }
                )

    columnas = [
        "report_md", "n_bands_report", "n_bands_usadas", "n_bands_faltantes",
        "scale", "sigma", "min_size",
        "n_segmentos", "tam_medio_px", "tam_mediano_px",
        "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    if not (args.resume and ruta_csv.is_file()):
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        print(f"\n[resume] CSV existente: {ruta_csv}")

    base.imprimir_tabla(filas_resumen)
    print(f"[OK] Salidas Lv3 RF en: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
