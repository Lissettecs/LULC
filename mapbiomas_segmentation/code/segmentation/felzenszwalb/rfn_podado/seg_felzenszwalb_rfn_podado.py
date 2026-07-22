#!/usr/bin/env python3
"""
Felzenszwalb sobre stack RF_N PODADO y estandarizado (geometría, no clasificación).

Compara si un subconjunto espectral (~8–12 bandas) segmenta mejor que las 39 bandas
crudas o las 3 bandas nir/swir1/red, al MISMO scale/sigma.

Salidas en seg_felzenszwalb_rfn/ — no toca seg_felzenszwalb/ ni seg_felzenszwalb_rf_n/.

Uso:
  python seg_felzenszwalb_rfn_podado.py
  python seg_felzenszwalb_rfn_podado.py --tile 18HYD --year 2010 --resume

FASE 2 — NO IMPLEMENTADO (ver comentarios al final del archivo):
  - Ablación por feature/categoría
  - Comparar tam_mediano_px vs 3 bandas y SLIC+RAG hierarchical
  - Decisión: si geometría no mejora, reservar RF_N solo para clasificar
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
for _p in (_FELZ_DIR, _RF_N_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import seg_felzenszwalb_grid as base  # noqa: E402
from rf_selected_bands import (  # noqa: E402
    indices_para_tile,
    nombres_para_indices,
    resolver_posiciones_geotiff,
)

# ── ENTRADA ────────────────────────────────────────────────────────────────────
DEFAULT_TILE = "18HYD"
DEFAULT_YEAR = 2010
STACK_RFN_PATH = Path(
    "/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands"
    f"/{DEFAULT_TILE}/TMP-CHILE-{DEFAULT_TILE}-{DEFAULT_YEAR}-SBAND-184B.tif"
)

# ── SELECCIÓN DE FEATURES (podado) ─────────────────────────────────────────────
EXCLUIR_PATRONES = ["elevation", "slope", "cloud", "texture", "stdDev"]

FEATURES_SEG = [
    "blue_max",
    "green_median",
    "nir_median",
    "swir1_min",
    "swir2_median_dry",
    "ndvi_max",
    "ndwi_median_wet",
    "ndsi",
    "gcvi_max",
    "savi_median_dry",
]

# ── PARÁMETROS ─────────────────────────────────────────────────────────────────
SCALE_LIST = [200]
SIGMA_LIST = [0.1]
MIN_SIZE = 20
STANDARDIZE = True

OUTPUT_DIR = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rfn")
DISPLAY_BANDS_NOMBRES = ["nir_median", "swir1_min", "green_median"]

REF_3BANDAS_CSV = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb")
REF_RFN39_CSV = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_n")
NODATA = base.NODATA
RF_LEVEL = 1
# ─────────────────────────────────────────────────────────────────────────────


def stack_path_para(tile: str, year: int, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    return Path(
        f"/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands"
        f"/{tile}/TMP-CHILE-{tile}-{year}-SBAND-184B.tif"
    )


def nombre_excluido(nombre: str, patrones: list[str]) -> bool:
    nl = nombre.lower()
    return any(p.lower() in nl for p in patrones)


def nombres_stack_rfn(tile: str, descriptions: list[str], rf_level: int) -> list[str]:
    """39 nombres RF_N del tile que existen en el GeoTIFF."""
    indices = indices_para_tile(tile, rf_level)
    nombres = nombres_para_indices(indices)
    mapa = {d: i for i, d in enumerate(descriptions) if d}
    presentes = [n for n in nombres if n in mapa]
    if len(presentes) != len(nombres):
        faltan = [n for n in nombres if n not in mapa]
        print(f"[ADVERTENCIA] Bandas RF_N no en GeoTIFF: {', '.join(faltan)}")
    return presentes


def construir_features_finales(
    stack_nombres: set[str],
    features_pedidas: list[str],
    excluir_patrones: list[str],
) -> list[str]:
    faltantes = [f for f in features_pedidas if f not in stack_nombres]
    if faltantes:
        print("[ERROR] FEATURES_SEG no encontradas en el stack RF_N:")
        for f in faltantes:
            print(f"  - {f}")
        print(f"[INFO] Disponibles en stack ({len(stack_nombres)}):")
        for n in sorted(stack_nombres):
            print(f"  · {n}")
        sys.exit(1)

    finales: list[str] = []
    for nombre in features_pedidas:
        if nombre_excluido(nombre, excluir_patrones):
            print(f"[ADVERTENCIA] Omitiendo '{nombre}' (patrón excluido)")
            continue
        finales.append(nombre)

    if not finales:
        print("[ERROR] Lista final de features vacía tras aplicar EXCLUIR_PATRONES")
        sys.exit(1)
    return finales


def imprimir_stats_bandas(
    datos: np.ndarray,
    validos: np.ndarray,
    nombres: list[str],
    titulo: str,
) -> None:
    print(f"\n=== {titulo} ===")
    print(f"{'Banda':<22}  {'Media':>10}  {'Std':>10}")
    print("-" * 48)
    for i, nombre in enumerate(nombres):
        vals = datos[..., i][validos]
        if vals.size:
            media, std = float(vals.mean()), float(vals.std())
        else:
            media, std = float("nan"), float("nan")
        print(f"{nombre:<22}  {media:10.4f}  {std:10.4f}")


def stem_salida(tile: str, year: int, scale: int, sigma: float) -> str:
    return f"seg_rfn_{tile}_{year}_s{scale}_sig{sigma}"


def cargar_ref_n_segmentos(
    ref_dir: Path,
    patron_csv: str,
    scale: int,
    sigma: float,
) -> int | None:
    candidatos = sorted(ref_dir.glob(patron_csv))
    if not candidatos:
        return None
    with candidatos[0].open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(float(row["scale"])) == scale and abs(float(row["sigma"]) - sigma) < 1e-9:
                return int(float(row["n_segmentos"]))
    return None


def comparar_con_referencias(
    tile: str,
    year: int,
    scale: int,
    sigma: float,
    n_segmentos: int,
) -> None:
    print("\n=== VERIFICACIÓN vs CORRIDAS DE REFERENCIA ===")
    n_3b = cargar_ref_n_segmentos(ref_dir=REF_3BANDAS_CSV, patron_csv=f"resumen_{tile}_{year}.csv", scale=scale, sigma=sigma)
    n_39 = cargar_ref_n_segmentos(
        ref_dir=REF_RFN39_CSV,
        patron_csv=f"resumen_{tile}_{year}_lv{RF_LEVEL}_rfn.csv",
        scale=scale,
        sigma=sigma,
    )

    print(f"Podado RF_N (este run) : {n_segmentos:,} segmentos  (scale={scale}, σ={sigma})")
    if n_3b is not None:
        ratio = n_segmentos / n_3b
        print(f"3 bandas (seg_felzenszwalb) : {n_3b:,}  →  ratio podado/3b = {ratio:.2f}×")
        if ratio > 4.0:
            print(
                "[ADVERTENCIA] Ratio >4× respecto a 3 bandas: el stack podado aún fragmenta de más.\n"
                "  → Revisar qué feature lo causa (ablación por categoría, FASE 2)."
            )
    else:
        print("[INFO] Sin referencia 3 bandas en CSV para este scale/σ")

    if n_39 is not None:
        ratio39 = n_segmentos / n_39
        print(f"39 bandas RF_N (crudo)      : {n_39:,}  →  ratio podado/39b = {ratio39:.2f}×")
    else:
        print("[INFO] Sin referencia 39 bandas RF_N en CSV para este scale/σ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Felzenszwalb RF_N podado: stack estandarizado para geometría.",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--stack-rfn-path", type=Path, default=None, help="GeoTIFF 184B (39 bandas RF_N)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--rf-level", type=int, default=RF_LEVEL, choices=(1, 3))
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tile = args.tile.upper()
    year = args.year
    output_dir = args.output_dir.resolve()
    ruta_stack = stack_path_para(tile, year, args.stack_rfn_path)

    if not ruta_stack.is_file():
        print(f"[ERROR] STACK_RFN_PATH no existe: {ruta_stack}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Stack RF_N: {ruta_stack}")
    print(f"[OK] Salida: {output_dir}")

    rutas_previstas: list[Path] = []
    for scale in SCALE_LIST:
        for sigma in SIGMA_LIST:
            stem = stem_salida(tile, year, scale, sigma)
            rutas_previstas.extend([output_dir / f"{stem}.tif", output_dir / f"{stem}.png"])
    ruta_csv = output_dir / f"resumen_rfn_{tile}_{year}.csv"
    rutas_previstas.append(ruta_csv)

    if args.resume:
        n_exist = sum(1 for r in rutas_previstas if r.exists())
        print(f"[OK] --resume: {n_exist} archivos previstos ya existen")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    with rasterio.open(ruta_stack) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [descriptions[i] if i < len(descriptions) else "" for i in range(src.count)]

        stack_rfn = set(nombres_stack_rfn(tile, descriptions, args.rf_level))
        features_finales = construir_features_finales(stack_rfn, FEATURES_SEG, EXCLUIR_PATRONES)
        print(f"[OK] Segmentando con {len(features_finales)} bandas: {', '.join(features_finales)}")

        feat_positions = resolver_posiciones_geotiff(descriptions, features_finales)
        display_positions = resolver_posiciones_geotiff(descriptions, DISPLAY_BANDS_NOMBRES)

        perfil = src.profile
        nodata_valor = base.resolver_nodata(src, NODATA)

        feat_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in feat_positions],
            axis=-1,
        )
        rgb_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in display_positions],
            axis=-1,
        )

        validos = base.construir_mascara_nodata(feat_stack, nodata_valor)
        print(f"[OK] Shape feat_stack: {feat_stack.shape}  (H, W, C={feat_stack.shape[-1]})")
        print(f"[OK] Píxeles válidos: {validos.sum():,} / {validos.size:,}")

        img = base.rellenar_nodata_mediana(feat_stack, validos)
        imprimir_stats_bandas(img, validos, features_finales, "ANTES z-score")

        if STANDARDIZE:
            img = base.estandarizar_zscore(img, validos)
            imprimir_stats_bandas(img, validos, features_finales, "DESPUÉS z-score (objetivo ~0 / ~1)")
        else:
            print("[ADVERTENCIA] STANDARDIZE=False: distancias dominadas por escalas heterogéneas")

        rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos)
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
                    print(f"\n[Felzenszwalb] scale={scale}, sigma={sigma}, min_size={MIN_SIZE}")
                    print(f"[INFO] img.shape={img.shape}  channel_axis=-1  (C={img.shape[-1]} bandas podadas)")

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
                        f"RFN podado — {tile} {year} — s={scale}, σ={sigma}, "
                        f"N={len(features_finales)} bandas"
                    )
                    base.guardar_geotiff_labels(labels, perfil, ruta_tif)
                    base.guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
                    print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")

                print(
                    f"  → segmentos={stats['n_segmentos']:,}, "
                    f"tam_medio={stats['tam_medio_px']:.1f} px, "
                    f"tam_mediano={stats['tam_mediano_px']:.1f} px"
                )
                comparar_con_referencias(tile, year, scale, sigma, stats["n_segmentos"])

                filas_resumen.append(
                    {
                        "scale": scale,
                        "sigma": sigma,
                        "min_size": MIN_SIZE,
                        "n_bandas_usadas": len(features_finales),
                        **stats,
                    }
                )

    columnas = [
        "scale", "sigma", "min_size", "n_bandas_usadas",
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
    print(f"[OK] Salidas en: {output_dir}")


# ── FASE 2 — NO IMPLEMENTAR ───────────────────────────────────────────────────
# - Ablación: correr quitando una feature/categoría a la vez para aislar fragmentación.
# - Comparar tam_mediano_px contra 3 bandas y contra SLIC+RAG hierarchical.
# - Si la geometría no mejora sobre 3 bandas, descartar RF_N para segmentar y
#   reservar el feature space rico solo para clasificar.


if __name__ == "__main__":
    main()
