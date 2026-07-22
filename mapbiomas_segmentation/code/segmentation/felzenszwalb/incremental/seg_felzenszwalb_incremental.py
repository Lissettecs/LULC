#!/usr/bin/env python3
"""
Prueba CONSTRUCTIVA de features para Felzenszwalb.

Parte de 3 bandas base (medianas del stack 184B) y agrega UN incremento a la vez,
midiendo si la granularidad se mantiene. Opuesto a la ablación: sumar desde lo que
funciona, no restar desde lo que fragmenta.

Salidas en seg_felzenszwalb_incremental/ — no sobrescribe corridas previas.

Uso:
  python seg_felzenszwalb_incremental.py --dry-run
  python seg_felzenszwalb_incremental.py --tile 18HYD --year 2010
  python seg_felzenszwalb_incremental.py --resume
  python seg_felzenszwalb_incremental.py --acumular

FASE 2 — NO IMPLEMENTADO (ver final del archivo):
  - Verificación sobre C2: para incrementos con ratio aceptable, comprobar si
    RECUPERA pares de clases que la base fusiona (agua/humedal con mndwi, nieve
    con ndsi, suelo/desierto con swir2).
  - Repetir el ganador en SLIC+hierarchical para A/B de segmentadores.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

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
from rf_selected_bands import resolver_posiciones_geotiff  # noqa: E402

# ── FUENTE STACK 184B ──────────────────────────────────────────────────────────
DEFAULT_TILE = "18HYD"
DEFAULT_YEAR = 2010
STACK_PATH = (
    "/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands"
    "/{tile}/TMP-CHILE-{tile}-{year}-SBAND-184B.tif"
)

# ── BANDAS BASE (medianas del stack 184) ───────────────────────────────────────
BANDAS_BASE = ["nir_median", "swir1_median", "red_median"]
RGB_DISPLAY = list(BANDAS_BASE)

# ── INCREMENTOS ────────────────────────────────────────────────────────────────
INCREMENTOS: list[dict[str, Any]] = [
    {"etiqueta": "base", "tipo": "nada"},
    {"etiqueta": "+swir2", "tipo": "banda", "banda": "swir2_median"},
    {
        "etiqueta": "+ndvi",
        "tipo": "indice",
        "formula": "ndvi",
        "bandas": ["nir_median", "red_median"],
    },
    {
        "etiqueta": "+mndwi",
        "tipo": "indice",
        "formula": "mndwi",
        "bandas": ["green_median", "swir1_median"],
    },
    {
        "etiqueta": "+ndsi",
        "tipo": "indice",
        "formula": "ndsi",
        "bandas": ["green_median", "swir1_median"],
    },
]

# ── PARÁMETROS FIJOS ─────────────────────────────────────────────────────────
SCALE = 200
SIGMA = 0.1
MIN_SIZE = 20
STANDARDIZE = True
REF_3BANDAS_NSEG = 16732
RATIO_VIABLE = 1.5
RATIO_FRAGMENTA = 2.0

OUTPUT_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_incremental"
)
NODATA = base.NODATA
# ─────────────────────────────────────────────────────────────────────────────


def stack_path_para(tile: str, year: int, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    return Path(STACK_PATH.format(tile=tile, year=year))


def etiqueta_archivo(etiqueta: str) -> str:
    if etiqueta.startswith("+"):
        etiqueta = "base" + etiqueta
    saneada = etiqueta.replace("+", "_mas_")
    return re.sub(r"[^\w.\-]", "_", saneada)


def calcular_indice(formula: str, bandas: list[str], cache: dict[str, np.ndarray]) -> np.ndarray:
    """Índice sobre reflectancia cruda (antes de z-score)."""
    if formula == "ndvi":
        nir, red = cache[bandas[0]], cache[bandas[1]]
        return (nir - red) / (nir + red + 1e-6)
    if formula in ("mndwi", "ndsi"):
        green, swir1 = cache[bandas[0]], cache[bandas[1]]
        return (green - swir1) / (green + swir1 + 1e-6)
    raise ValueError(f"Fórmula de índice desconocida: {formula}")


def bandas_para_mascara(incrementos_ok: list[dict[str, Any]]) -> list[str]:
    nombres: set[str] = set(BANDAS_BASE)
    for inc in incrementos_ok:
        if inc["tipo"] == "banda":
            nombres.add(inc["banda"])
        elif inc["tipo"] == "indice":
            nombres.update(inc["bandas"])
    orden = list(BANDAS_BASE)
    for inc in incrementos_ok:
        if inc["tipo"] == "banda" and inc["banda"] not in orden:
            orden.append(inc["banda"])
        elif inc["tipo"] == "indice":
            for b in inc["bandas"]:
                if b not in orden:
                    orden.append(b)
    return orden


def filtrar_incrementos(disponibles: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for inc in INCREMENTOS:
        if inc["tipo"] == "nada":
            out.append(inc)
            continue
        if inc["tipo"] == "banda":
            if inc["banda"] not in disponibles:
                print(
                    f"[INFO] Omitiendo '{inc['etiqueta']}': "
                    f"banda '{inc['banda']}' no está en el stack"
                )
                continue
            out.append(inc)
        elif inc["tipo"] == "indice":
            faltan = [b for b in inc["bandas"] if b not in disponibles]
            if faltan:
                print(
                    f"[INFO] Omitiendo '{inc['etiqueta']}': "
                    f"faltan {', '.join(faltan)} en el stack"
                )
                continue
            out.append(inc)
    return out


def listar_corridas(
    incrementos_ok: list[dict[str, Any]],
    acumular: bool,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Devuelve (etiqueta_corrida, pasos_incremento). pasos=[] solo para base."""
    if not acumular:
        corridas: list[tuple[str, list[dict[str, Any]]]] = []
        for inc in incrementos_ok:
            if inc["tipo"] == "nada":
                corridas.append(("base", []))
            else:
                corridas.append((inc["etiqueta"], [inc]))
        return corridas

    corridas = []
    acumulado: list[dict[str, Any]] = []
    for inc in incrementos_ok:
        if inc["tipo"] == "nada":
            corridas.append(("base", []))
            continue
        acumulado.append(inc)
        etiqueta = "base" + "".join(p["etiqueta"] for p in acumulado)
        corridas.append((etiqueta, list(acumulado)))
    return corridas


def leer_bandas_cache(
    src: rasterio.io.DatasetReader,
    descriptions: list[str],
    cache: dict[str, np.ndarray],
    nombres: list[str],
) -> None:
    faltantes = [n for n in nombres if n not in cache]
    if not faltantes:
        return
    posiciones = resolver_posiciones_geotiff(descriptions, faltantes)
    for nombre, pos in zip(faltantes, posiciones):
        cache[nombre] = src.read(pos + 1).astype(np.float32)


def armar_stack_corrida(
    cache: dict[str, np.ndarray],
    pasos: list[dict[str, Any]],
) -> tuple[np.ndarray, list[str]]:
    nombres = list(BANDAS_BASE)
    canales = [cache[n] for n in BANDAS_BASE]
    for paso in pasos:
        if paso["tipo"] == "banda":
            nombres.append(paso["banda"])
            canales.append(cache[paso["banda"]])
        elif paso["tipo"] == "indice":
            nombres.append(paso["formula"])
            canales.append(calcular_indice(paso["formula"], paso["bandas"], cache))
    return np.stack(canales, axis=-1), nombres


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


def preparar_imagen_zscore(
    datos: np.ndarray,
    validos: np.ndarray,
    nombres: list[str],
    etiqueta: str,
    verbose_stats: bool,
) -> np.ndarray:
    img = base.rellenar_nodata_mediana(datos, validos)
    if verbose_stats:
        imprimir_stats_bandas(img, validos, nombres, f"ANTES z-score [{etiqueta}]")
    if not STANDARDIZE:
        print("[ERROR] STANDARDIZE debe ser True")
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
    ruta_tif = output_dir / f"seg_inc_{tile}_{year}_{slug}.tif"
    ruta_png = output_dir / f"seg_inc_{tile}_{year}_{slug}.png"

    if resume and ruta_tif.is_file() and ruta_png.is_file():
        print(f"\n[resume] {etiqueta} → {ruta_tif.name}")
        with rasterio.open(ruta_tif) as src_l:
            labels = src_l.read(1).astype(np.int32)
        stats = base.estadisticas_segmentos(labels, validos)
        return _fila_corrida(etiqueta, nombres, stats)

    print(f"\n=== Corrida: {etiqueta} ({len(nombres)} bandas) ===")
    print(f"[INFO] Canales: {', '.join(nombres)}")
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

    titulo = f"Incremental {etiqueta} — {tile} {year} — s={SCALE}, σ={SIGMA}"
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


def enriquecer_filas(filas: list[dict], n_seg_base: int | None) -> list[dict]:
    salida: list[dict] = []
    for fila in filas:
        n_seg = fila["n_segmentos"]
        ratio_3b = n_seg / REF_3BANDAS_NSEG
        ratio_base = n_seg / n_seg_base if n_seg_base else 1.0
        salida.append(
            {
                **fila,
                "ratio_vs_base": round(ratio_base, 3),
                "ratio_vs_3bandas": round(ratio_3b, 3),
            }
        )
    return salida


def imprimir_tabla(filas: list[dict]) -> None:
    print("\n=== TABLA INCREMENTAL (orden de INCREMENTOS) ===")
    cols = [
        ("corrida", "corrida"),
        ("n_bandas", "n_bandas"),
        ("n_segmentos", "n_segmentos"),
        ("ratio_vs_base", "ratio_base"),
        ("ratio_vs_3bandas", "ratio_3b"),
        ("tam_mediano_px", "tam_mediano"),
        ("tam_medio_ha", "tam_medio_ha"),
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
            elif clave in {"ratio_vs_base", "ratio_vs_3bandas", "tam_mediano_px", "tam_medio_ha"}:
                vals.append(f"{float(v):>14.2f}")
            else:
                vals.append(f"{str(v):>14}")
        print("  ".join(vals))


def imprimir_guia_lectura(filas: list[dict], n_seg_base: int) -> None:
    print("\n=== GUÍA DE LECTURA ===")
    print(f"Referencia 3 bandas: {REF_3BANDAS_NSEG:,} segmentos (scale={SCALE}, σ={SIGMA})")
    print(f"Base (esta corrida): {n_seg_base:,} segmentos")
    print(
        f"Criterio: ratio_vs_base ≤ {RATIO_VIABLE}× → incremento NO fragmenta de más (viable);\n"
        f"          ratio_vs_base > {RATIO_FRAGMENTA}× → fragmenta (descartar salvo mejora de clase, FASE 2)."
    )
    for fila in filas:
        if fila["corrida"] == "base":
            continue
        r = fila["ratio_vs_base"]
        if r <= RATIO_VIABLE:
            veredicto = "VIABLE — no fragmenta de más"
        elif r > RATIO_FRAGMENTA:
            veredicto = "FRAGMENTA — descartar salvo justificación C2 (FASE 2)"
        else:
            veredicto = "INTERMEDIO — revisar visualmente y C2"
        print(
            f"  {fila['corrida']:<22}  ratio_base={r:.2f}×  "
            f"ratio_3b={fila['ratio_vs_3bandas']:.2f}×  → {veredicto}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba constructiva de features para Felzenszwalb (base + incrementos).",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--stack-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--acumular",
        action="store_true",
        help="Modo acumulativo: base, base+swir2, base+swir2+ndvi, …",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tile = args.tile.upper()
    year = args.year
    output_dir = args.output_dir.resolve()
    ruta_stack = stack_path_para(tile, year, args.stack_path)

    if not ruta_stack.is_file():
        print(f"[ERROR] STACK_PATH no existe: {ruta_stack}")
        sys.exit(1)

    print(f"[OK] Stack 184B: {ruta_stack}")
    print(f"[OK] Salida: {output_dir}")
    print(
        f"[OK] Parámetros: scale={SCALE}, σ={SIGMA}, min_size={MIN_SIZE}, "
        f"z-score=ON, acumular={'SÍ' if args.acumular else 'NO'}"
    )

    with rasterio.open(ruta_stack) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [
                descriptions[i] if i < len(descriptions) else "" for i in range(src.count)
            ]

        disponibles = {d for d in descriptions if d}
        print(f"[OK] GeoTIFF: {len(disponibles)} descriptions / {src.count} bandas")

        faltan_base = [b for b in BANDAS_BASE if b not in disponibles]
        if faltan_base:
            print(f"[ERROR] BANDAS_BASE faltantes en el stack: {', '.join(faltan_base)}")
            sys.exit(1)
        print(f"[OK] BANDAS_BASE resueltas: {', '.join(BANDAS_BASE)}")

        incrementos_ok = filtrar_incrementos(disponibles)
        corridas = listar_corridas(incrementos_ok, args.acumular)
        nombres_mascara = bandas_para_mascara(incrementos_ok)

        print(f"\n=== Plan de corridas ({len(corridas)}) ===")
        for etiqueta, pasos in corridas:
            extra = []
            for p in pasos:
                if p["tipo"] == "banda":
                    extra.append(p["banda"])
                elif p["tipo"] == "indice":
                    extra.append(p["formula"])
            n_can = len(BANDAS_BASE) + len(extra)
            print(f"  · {etiqueta}: {n_can} canales ({', '.join(BANDAS_BASE + extra)})")

        rutas_previstas = [
            output_dir / f"seg_inc_{tile}_{year}_{etiqueta_archivo(et)}.tif"
            for et, _ in corridas
        ] + [output_dir / f"resumen_incremental_{tile}_{year}.csv"]

        if args.dry_run:
            print("\n[OK] --dry-run: sin segmentación.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)

        if args.resume:
            n_exist = sum(1 for r in rutas_previstas if r.exists())
            print(f"[OK] --resume: {n_exist} archivos ya existen")
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
        cache: dict[str, np.ndarray] = {}

        leer_bandas_cache(src, descriptions, cache, nombres_mascara)
        mask_stack = np.stack([cache[n] for n in nombres_mascara], axis=-1)
        validos_global = base.construir_mascara_nodata(mask_stack, nodata_valor)
        print(
            f"[OK] Máscara única sobre {len(nombres_mascara)} bandas: "
            f"{validos_global.sum():,} px válidos"
        )

        leer_bandas_cache(src, descriptions, cache, RGB_DISPLAY)
        rgb_stack = np.stack([cache[n] for n in RGB_DISPLAY], axis=-1)
        rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos_global)
        print(f"[OK] RGB quicklook fijo: {', '.join(RGB_DISPLAY)}")

        filas_raw: list[dict] = []
        for i, (etiqueta, pasos) in enumerate(corridas):
            feat_stack, nombres = armar_stack_corrida(cache, pasos)
            img = preparar_imagen_zscore(
                feat_stack,
                validos_global,
                nombres,
                etiqueta,
                verbose_stats=(i == 0),
            )
            fila = segmentar(
                img,
                validos_global,
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

    n_seg_base = next(
        (f["n_segmentos"] for f in filas_raw if f["corrida"] == "base"),
        filas_raw[0]["n_segmentos"] if filas_raw else None,
    )
    filas = enriquecer_filas(filas_raw, n_seg_base)
    imprimir_tabla(filas)
    if n_seg_base is not None:
        imprimir_guia_lectura(filas, n_seg_base)

    ruta_csv = output_dir / f"resumen_incremental_{tile}_{year}.csv"
    columnas = [
        "corrida",
        "n_bandas",
        "n_segmentos",
        "ratio_vs_base",
        "ratio_vs_3bandas",
        "tam_mediano_px",
        "tam_medio_ha",
        "tam_medio_px",
        "tam_min_px",
        "tam_max_px",
    ]
    with ruta_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)
    print(f"\n[OK] CSV: {ruta_csv}")


if __name__ == "__main__":
    main()
