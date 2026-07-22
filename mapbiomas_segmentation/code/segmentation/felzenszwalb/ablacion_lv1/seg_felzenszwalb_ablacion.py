#!/usr/bin/env python3
"""
Ablación dirigida de features RF_N para Felzenszwalb (geometría).

FASE A: stack solo-medianas (base robusta).
FASE B: medianas + una feature "dura" a la vez (aislar fragmentación).

Salidas en seg_felzenszwalb_ablacion/ — no toca corridas previas.

Uso:
  python seg_felzenszwalb_ablacion.py
  python seg_felzenszwalb_ablacion.py --tile 18HYD --year 2010 --resume

FASE 2 — NO IMPLEMENTADO (ver final del archivo):
  - Si el ganador no supera 3 bandas por tam_mediano_px, segmentar con 3 bandas
    y reservar RF_N solo para clasificar.
"""

from __future__ import annotations

import argparse
import csv
import re
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

# ── FASE A: solo medianas ──────────────────────────────────────────────────────
FEATURES_MEDIANAS = [
    "blue_median",
    "green_median",
    "nir_median",
    "swir1_median",
    "swir2_median",
    "ndvi_median",
    "ndwi_median",
]

# ── FASE B: medianas + una feature dura ────────────────────────────────────────
FEATURES_DURAS = [
    "swir1_min",
    "ndwi_min",
    "gcvi_max",
    "ndvi_max",
    "savi_median_dry",
    "ndwi_median_wet",
    "cai_median_dry",
]

# ── PARÁMETROS FIJOS ───────────────────────────────────────────────────────────
SCALE = 200
SIGMA = 0.1
MIN_SIZE = 20
STANDARDIZE = True
REF_3BANDAS_NSEG = 16732

OUTPUT_DIR = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_ablacion")
DISPLAY_RGB_CANDIDATOS = [
    ("nir_median", "swir1_min", "green_median"),
    ("nir_median", "swir1_median", "green_median"),
    ("nir_median", "green_median", "blue_median"),
]

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


def nombres_stack_rfn(tile: str, descriptions: list[str], rf_level: int) -> set[str]:
    indices = indices_para_tile(tile, rf_level)
    nombres = nombres_para_indices(indices)
    mapa = {d for d in descriptions if d}
    return {n for n in nombres if n in mapa}


def resolver_medianas_presentes(stack: set[str]) -> tuple[list[str], list[str]]:
    encontradas = [n for n in FEATURES_MEDIANAS if n in stack]
    faltantes = [n for n in FEATURES_MEDIANAS if n not in stack]
    print(f"[OK] FASE A — medianas encontradas ({len(encontradas)}): {', '.join(encontradas) or '—'}")
    if faltantes:
        print(f"[INFO] FASE A — medianas faltantes (no se sustituyen): {', '.join(faltantes)}")
    if not encontradas:
        print("[ERROR] Ninguna FEATURES_MEDIANAS presente en el stack RF_N")
        sys.exit(1)
    return encontradas, faltantes


def resolver_rgb_nombres(stack: set[str]) -> list[str]:
    for trio in DISPLAY_RGB_CANDIDATOS:
        if all(n in stack for n in trio):
            return list(trio)
    fallback = [n for n in ("nir_median", "green_median", "swir1_min", "swir1_median") if n in stack]
    if len(fallback) >= 3:
        return fallback[:3]
    raise ValueError(f"No hay trio RGB en el stack. Disponibles: {sorted(stack)}")


def etiqueta_archivo(etiqueta: str) -> str:
    saneada = etiqueta.replace("+", "_mas_")
    saneada = re.sub(r"[^\w.\-]", "_", saneada)
    return saneada


def imprimir_stats_bandas(
    datos: np.ndarray,
    validos: np.ndarray,
    nombres: list[str],
    titulo: str,
) -> None:
    print(f"\n=== {titulo} — {', '.join(nombres)} ===")
    print(f"{'Banda':<22}  {'Media':>10}  {'Std':>10}")
    print("-" * 48)
    for i, nombre in enumerate(nombres):
        vals = datos[..., i][validos]
        media = float(vals.mean()) if vals.size else float("nan")
        std = float(vals.std()) if vals.size else float("nan")
        print(f"{nombre:<22}  {media:10.4f}  {std:10.4f}")


def leer_stack(
    src: rasterio.io.DatasetReader,
    descriptions: list[str],
    nombres: list[str],
) -> np.ndarray:
    posiciones = resolver_posiciones_geotiff(descriptions, nombres)
    return np.stack(
        [src.read(pos + 1).astype(np.float32) for pos in posiciones],
        axis=-1,
    )


def preparar_imagen_zscore(
    datos: np.ndarray,
    validos: np.ndarray,
    nombres: list[str],
    etiqueta: str,
    verbose_stats: bool = True,
) -> np.ndarray:
    img = base.rellenar_nodata_mediana(datos, validos)
    if verbose_stats:
        imprimir_stats_bandas(img, validos, nombres, f"ANTES z-score [{etiqueta}]")
    if not STANDARDIZE:
        print("[ERROR] STANDARDIZE debe ser True para ablación")
        sys.exit(1)
    img = base.estandarizar_zscore(img, validos)
    if verbose_stats:
        imprimir_stats_bandas(img, validos, nombres, f"DESPUÉS z-score [{etiqueta}]")
    return img


def segmentar(
    img: np.ndarray,
    validos: np.ndarray,
    perfil: dict,
    rgb_base: np.ndarray,
    output_dir: Path,
    tile: str,
    year: int,
    etiqueta: str,
    nombres: list[str],
    resume: bool,
) -> dict:
    slug = etiqueta_archivo(etiqueta)
    ruta_tif = output_dir / f"seg_abl_{tile}_{year}_{slug}.tif"
    ruta_png = output_dir / f"seg_abl_{tile}_{year}_{slug}.png"

    if resume and ruta_tif.is_file() and ruta_png.is_file():
        print(f"\n[resume] {etiqueta} → {ruta_tif.name}")
        with rasterio.open(ruta_tif) as src_l:
            labels = src_l.read(1).astype(np.int32)
        stats = base.estadisticas_segmentos(labels, validos)
        return _fila_corrida(etiqueta, nombres, stats)

    print(f"\n=== Corrida: {etiqueta} ({len(nombres)} bandas) ===")
    print(f"[INFO] img.shape={img.shape}  channel_axis=-1")
    print(f"[INFO] Felzenszwalb scale={SCALE}, sigma={SIGMA}, min_size={MIN_SIZE}")

    labels = felzenszwalb(
        img,
        scale=SCALE,
        sigma=SIGMA,
        min_size=MIN_SIZE,
        channel_axis=-1,
    )
    labels = labels.astype(np.int32)
    labels[~validos] = 0
    stats = base.estadisticas_segmentos(labels, validos)

    titulo = f"Ablación {etiqueta} — {tile} {year} — s={SCALE}, σ={SIGMA}"
    base.guardar_geotiff_labels(labels, perfil, ruta_tif)
    base.guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
    print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")
    print(
        f"  → segmentos={stats['n_segmentos']:,}, "
        f"tam_mediano={stats['tam_mediano_px']:.1f} px"
    )
    return _fila_corrida(etiqueta, nombres, stats)


def _fila_corrida(etiqueta: str, nombres: list[str], stats: dict) -> dict:
    return {
        "corrida": etiqueta,
        "n_bandas": len(nombres),
        "n_segmentos": stats["n_segmentos"],
        "tam_medio_px": stats["tam_medio_px"],
        "tam_mediano_px": stats["tam_mediano_px"],
        "tam_min_px": stats["tam_min_px"],
        "tam_max_px": stats["tam_max_px"],
        "tam_medio_ha": stats["tam_medio_ha"],
    }


def enriquecer_tabla(filas: list[dict], n_seg_medianas: int | None) -> list[dict]:
    salida: list[dict] = []
    for fila in filas:
        n_seg = fila["n_segmentos"]
        ratio = n_seg / REF_3BANDAS_NSEG
        delta = n_seg - n_seg_medianas if n_seg_medianas is not None else ""
        if fila["corrida"] == "medianas":
            delta = 0
        salida.append(
            {
                **fila,
                "ratio_vs_3bandas": round(ratio, 3),
                "delta_vs_medianas": delta if delta != "" else 0,
            }
        )
    salida.sort(key=lambda r: r["n_segmentos"])
    return salida


def imprimir_tabla_comparativa(filas: list[dict]) -> None:
    print("\n=== TABLA COMPARATIVA (ordenada por n_segmentos) ===")
    cols = [
        ("corrida", "corrida"),
        ("n_bandas", "n_bandas"),
        ("n_segmentos", "n_segmentos"),
        ("ratio_vs_3bandas", "ratio_3b"),
        ("delta_vs_medianas", "Δ medianas"),
        ("tam_mediano_px", "tam_mediano"),
    ]
    header = "  ".join(f"{t:>14}" for _, t in cols)
    print(header)
    print("-" * len(header))
    for fila in filas:
        vals = []
        for clave, _ in cols:
            v = fila[clave]
            if clave == "n_segmentos":
                vals.append(f"{int(v):>14,}")
            elif clave in {"ratio_vs_3bandas", "tam_mediano_px"}:
                vals.append(f"{float(v):>14.2f}")
            elif clave == "delta_vs_medianas":
                vals.append(f"{int(v):>14,}")
            else:
                vals.append(f"{str(v):>14}")
        print("  ".join(vals))


def imprimir_guia_lectura(filas: list[dict], n_seg_medianas: int) -> None:
    ratio_med = n_seg_medianas / REF_3BANDAS_NSEG
    print("\n=== GUÍA DE LECTURA ===")
    print(f"Referencia 3 bandas: {REF_3BANDAS_NSEG:,} segmentos (scale={SCALE}, σ={SIGMA})")
    print(f"FASE A 'medianas': {n_seg_medianas:,} segmentos (ratio {ratio_med:.2f}×)")

    if ratio_med <= 2.0:
        print(
            "→ 'medianas' ~ referencia 3 bandas (ratio 1–2×): los extremos eran el ruido;\n"
            "  el stack robusto de segmentación son medianas."
        )
    elif ratio_med > 4.0:
        print(
            "→ 'medianas' YA fragmenta mucho (ratio >4×): el problema no son solo los extremos;\n"
            "  re-evaluar si alguna banda RF mejora las 3 bandas para geometría."
        )
    else:
        print(
            "→ 'medianas' en rango intermedio (2–4×): revisar features duras en FASE B."
        )

    duras = [f for f in filas if f["corrida"].startswith("medianas+")]
    if duras:
        peor = max(duras, key=lambda r: r["delta_vs_medianas"])
        print(
            f"→ Feature dura con mayor Δ vs medianas: '{peor['corrida']}' "
            f"(+{peor['delta_vs_medianas']:,} segmentos, ratio 3b={peor['ratio_vs_3bandas']:.2f}×)"
        )


def listar_corridas(
    medianas: list[str],
    stack: set[str],
) -> list[tuple[str, list[str]]]:
    corridas: list[tuple[str, list[str]]] = [("medianas", list(medianas))]
    for dura in FEATURES_DURAS:
        if dura not in stack:
            print(f"[INFO] FASE B — omitiendo '{dura}' (no está en el stack RF_N)")
            continue
        etiqueta = f"medianas+{dura}"
        corridas.append((etiqueta, list(medianas) + [dura]))
    return corridas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ablación dirigida RF_N → Felzenszwalb.")
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--stack-rfn-path", type=Path, default=None)
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
    print(f"[OK] Parámetros fijos: scale={SCALE}, σ={SIGMA}, min_size={MIN_SIZE}, z-score=ON")

    with rasterio.open(ruta_stack) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [descriptions[i] if i < len(descriptions) else "" for i in range(src.count)]

        stack = nombres_stack_rfn(tile, descriptions, args.rf_level)
        medianas, _ = resolver_medianas_presentes(stack)
        rgb_nombres = resolver_rgb_nombres(stack)
        print(f"[OK] RGB quicklook: {', '.join(rgb_nombres)}")

        corridas = listar_corridas(medianas, stack)
        rutas_previstas = [
            output_dir / f"seg_abl_{tile}_{year}_{etiqueta_archivo(et)}.tif"
            for et, _ in corridas
        ] + [output_dir / f"resumen_ablacion_{tile}_{year}.csv"]

        if args.resume:
            print(f"[OK] --resume: {sum(1 for r in rutas_previstas if r.exists())} archivos ya existen")
        else:
            existentes = [r for r in rutas_previstas if r.exists()]
            if existentes:
                print("[ERROR] Archivos existentes (no se sobrescriben):")
                for r in existentes[:10]:
                    print(f"  - {r}")
                if len(existentes) > 10:
                    print(f"  … y {len(existentes) - 10} más")
                print("Usa --resume o elimina OUTPUT_DIR.")
                sys.exit(1)

        perfil = src.profile
        nodata_valor = base.resolver_nodata(src, NODATA)
        rgb_stack = leer_stack(src, descriptions, rgb_nombres)

        filas_raw: list[dict] = []
        validos_global: np.ndarray | None = None
        rgb_base: np.ndarray | None = None

        for etiqueta, nombres in corridas:
            feat_stack = leer_stack(src, descriptions, nombres)
            validos = base.construir_mascara_nodata(feat_stack, nodata_valor)
            if validos_global is None:
                validos_global = validos
                rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos)
            img = preparar_imagen_zscore(
                feat_stack,
                validos,
                nombres,
                etiqueta,
                verbose_stats=(etiqueta == "medianas"),
            )
            fila = segmentar(
                img,
                validos,
                perfil,
                rgb_base,
                output_dir,
                tile,
                year,
                etiqueta,
                nombres,
                resume=args.resume,
            )
            filas_raw.append(fila)

    n_seg_medianas = next(
        (f["n_segmentos"] for f in filas_raw if f["corrida"] == "medianas"),
        None,
    )
    filas = enriquecer_tabla(filas_raw, n_seg_medianas)
    imprimir_tabla_comparativa(filas)
    if n_seg_medianas is not None:
        imprimir_guia_lectura(filas, n_seg_medianas)

    ruta_csv = output_dir / f"resumen_ablacion_{tile}_{year}.csv"
    columnas = [
        "corrida", "n_bandas", "n_segmentos", "ratio_vs_3bandas", "delta_vs_medianas",
        "tam_medio_px", "tam_mediano_px", "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    if not (args.resume and ruta_csv.is_file()):
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        print(f"\n[resume] CSV existente: {ruta_csv}")

    print(f"[OK] Salidas en: {output_dir}")


# ── FASE 2 — NO IMPLEMENTAR ───────────────────────────────────────────────────
# Si el ganador (medianas o medianas+X) no supera las 3 bandas por tam_mediano_px,
# decisión estratégica: segmentar con 3 bandas, reservar RF_N solo para clasificar.


if __name__ == "__main__":
    main()
