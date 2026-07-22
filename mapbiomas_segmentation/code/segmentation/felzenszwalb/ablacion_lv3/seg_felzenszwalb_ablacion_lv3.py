#!/usr/bin/env python3
"""
Ablación dirigida Lv3: poda + features duras sobre las 34 bandas del REPORT.

FASE A: solo medianas puras (base robusta).
FASE B: medianas + una feature dura a la vez (aislar fragmentación).

Salidas en seg_felzenszwalb_ablacion_lv3/ — no toca corridas previas.

Uso:
  python seg_felzenszwalb_ablacion_lv3.py --dry-run
  python seg_felzenszwalb_ablacion_lv3.py --tile 18HYD --year 2010
  python seg_felzenszwalb_ablacion_lv3.py --resume

FASE 2 — NO IMPLEMENTADO (ver final del archivo):
  Si ni medianas ni medianas+X acercan el ratio a 1–2×, segmentar con 3 bandas
  y reservar RF (lv1/lv3) solo para clasificar.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from skimage.segmentation import felzenszwalb

_SCRIPT_DIR = Path(__file__).resolve().parent
_RF_LV3_DIR = _SCRIPT_DIR.parent / "seg_felzenszwalb_rf_lv3"
_FELZ_DIR = _SCRIPT_DIR.parent / "seg_felzenszwalb"
_RF_N_DIR = _SCRIPT_DIR.parent / "seg_felzenszwalb_rf_n"
for _p in (_SCRIPT_DIR, _RF_LV3_DIR, _FELZ_DIR, _RF_N_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import seg_felzenszwalb_grid as base  # noqa: E402
from parse_lv3_report import (  # noqa: E402
    BandEntry,
    ReportParseError,
    bandas_para_tile,
)
from rf_selected_bands import resolver_posiciones_geotiff  # noqa: E402

# ── FUENTE ─────────────────────────────────────────────────────────────────────
REPORT_MD = Path(
    "/home/lserey/repositorio/coverage_test/random_forest/REPORT/reports/lv3_multitile.md"
)
MOSAIC_184_DIR = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")

# ── CLASIFICACIÓN DE BANDAS ────────────────────────────────────────────────────
EXCLUIR_PATRONES = ("elevation", "slope", "cloud")
MEDIANA_EXCLUYE = ("_dry", "_wet", "_texture", "_stddev")
DURA_PATRONES = ("_min", "_max", "_dry", "_wet", "_stddev", "_texture", "_amp")

# ── PARÁMETROS FIJOS ───────────────────────────────────────────────────────────
DEFAULT_TILE = "18HYD"
DEFAULT_YEAR = 2010
SCALE = 200
SIGMA = 0.1
MIN_SIZE = 20
STANDARDIZE = True
REF_3BANDAS_NSEG = 16732
REF_LV3_COMPLETO_NSEG = 168723

OUTPUT_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_ablacion_lv3"
)
DISPLAY_RGB_PREFERIDO = ("nir_median", "swir1_median", "green_median")
DISPLAY_RGB_FALLBACK = ("nir_median", "swir1_median", "blue_median")

NODATA = base.NODATA
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ClasificacionBandas:
    medianas: list[str]
    duras: list[str]
    excluidas: list[str]
    sin_clasificar: list[str]
    faltantes_stack: list[str]

    @property
    def union(self) -> list[str]:
        return list(self.medianas) + list(self.duras)


def stack_path(tile: str, year: int, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    return MOSAIC_184_DIR / tile / f"TMP-CHILE-{tile}-{year}-SBAND-184B.tif"


def es_excluida(nombre: str) -> bool:
    nl = nombre.lower()
    return any(p in nl for p in EXCLUIR_PATRONES)


def es_mediana_pura(nombre: str) -> bool:
    nl = nombre.lower()
    return "_median" in nl and not any(x in nl for x in MEDIANA_EXCLUYE)


def es_dura(nombre: str) -> bool:
    nl = nombre.lower()
    return any(p in nl for p in DURA_PATRONES)


def clasificar_universo_lv3(nombres_lv3: list[str]) -> ClasificacionBandas:
    excluidas: list[str] = []
    medianas: list[str] = []
    duras: list[str] = []
    sin_clasificar: list[str] = []

    for nombre in nombres_lv3:
        if es_excluida(nombre):
            excluidas.append(nombre)
        elif es_mediana_pura(nombre):
            medianas.append(nombre)
        elif es_dura(nombre):
            duras.append(nombre)
        else:
            sin_clasificar.append(nombre)

    return ClasificacionBandas(
        medianas=medianas,
        duras=duras,
        excluidas=excluidas,
        sin_clasificar=sin_clasificar,
        faltantes_stack=[],
    )


def imprimir_clasificacion(clf: ClasificacionBandas, n_total: int) -> None:
    print("\n=== Clasificación del universo Lv3 ===")
    print(f"Total REPORT: {n_total}")
    print(f"  MEDIANAS puras : {len(clf.medianas)}")
    for n in clf.medianas:
        print(f"    · {n}")
    print(f"  DURAS          : {len(clf.duras)}")
    for n in clf.duras:
        print(f"    · {n}")
    print(f"  EXCLUIDAS      : {len(clf.excluidas)}  (elevation/slope/cloud — estáticas/calidad)")
    for n in clf.excluidas:
        print(f"    · {n}")
    print(f"  Sin clasificar : {len(clf.sin_clasificar)}  (revisión manual)")
    for n in clf.sin_clasificar:
        print(f"    · {n}")
    suma = len(clf.medianas) + len(clf.duras) + len(clf.excluidas) + len(clf.sin_clasificar)
    print(f"\nSuma categorías: {suma} (esperado {n_total})")
    print(f"Unión segmentación (MEDIANAS ∪ DURAS): {len(clf.union)} bandas")


def filtrar_presentes_en_stack(
    clf: ClasificacionBandas,
    descriptions: list[str],
) -> ClasificacionBandas:
    mapa = {d for d in descriptions if d}
    faltantes = [n for n in clf.union if n not in mapa]
    if faltantes:
        print(f"\n[ADVERTENCIA] Bandas del REPORT no en GeoTIFF ({len(faltantes)}):")
        for n in faltantes:
            print(f"  ✗ {n}")

    medianas = [n for n in clf.medianas if n in mapa]
    duras = [n for n in clf.duras if n in mapa]
    return ClasificacionBandas(
        medianas=medianas,
        duras=duras,
        excluidas=clf.excluidas,
        sin_clasificar=clf.sin_clasificar,
        faltantes_stack=faltantes,
    )


def etiqueta_archivo(etiqueta: str) -> str:
    saneada = etiqueta.replace("+", "_mas_")
    return re.sub(r"[^\w.\-]", "_", saneada)


def resolver_rgb_nombres(descriptions: list[str]) -> list[str]:
    mapa = {d for d in descriptions if d}
    for trio in (DISPLAY_RGB_PREFERIDO, DISPLAY_RGB_FALLBACK):
        if all(n in mapa for n in trio):
            return list(trio)
    raise ValueError(
        f"No hay trio RGB en el stack. Probado: {DISPLAY_RGB_PREFERIDO}, {DISPLAY_RGB_FALLBACK}"
    )


def leer_stack_por_nombres(
    src: rasterio.io.DatasetReader,
    descriptions: list[str],
    nombres: list[str],
) -> np.ndarray:
    posiciones = resolver_posiciones_geotiff(descriptions, nombres)
    return np.stack(
        [src.read(pos + 1).astype(np.float32) for pos in posiciones],
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
        media = float(vals.mean()) if vals.size else float("nan")
        std = float(vals.std()) if vals.size else float("nan")
        print(f"{nombre:<28}  {media:10.4f}  {std:10.4f}")


def preparar_substack_zscore(
    union_filled: np.ndarray,
    union_nombres: list[str],
    nombres_corrida: list[str],
    validos: np.ndarray,
    etiqueta: str,
    *,
    verbose: bool,
) -> np.ndarray:
    indices = [union_nombres.index(n) for n in nombres_corrida]
    sub = union_filled[..., indices]
    if verbose:
        imprimir_stats_bandas(sub, validos, nombres_corrida, f"ANTES z-score [{etiqueta}]")
    if not STANDARDIZE:
        print("[ERROR] STANDARDIZE debe ser True")
        sys.exit(1)
    sub = base.estandarizar_zscore(sub, validos)
    if verbose:
        imprimir_stats_bandas(sub, validos, nombres_corrida, f"DESPUÉS z-score [{etiqueta}]")
    return sub


def segmentar_corrida(
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
    ruta_tif = output_dir / f"seg_abl_lv3_{tile}_{year}_{slug}.tif"
    ruta_png = output_dir / f"seg_abl_lv3_{tile}_{year}_{slug}.png"

    if resume and ruta_tif.is_file() and ruta_png.is_file():
        print(f"\n[resume] {etiqueta} → {ruta_tif.name}")
        with rasterio.open(ruta_tif) as src_l:
            labels = src_l.read(1).astype(np.int32)
        stats = base.estadisticas_segmentos(labels, validos)
        return _fila_corrida(etiqueta, nombres, stats)

    print(f"\n=== Corrida: {etiqueta} ({len(nombres)} bandas) ===")
    print(f"[INFO] img.shape={img.shape}  Felzenszwalb s={SCALE}, σ={SIGMA}, min={MIN_SIZE}")

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

    titulo = f"Ablación Lv3 {etiqueta} — {tile} {year} — s={SCALE}, σ={SIGMA}"
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
        ratio_3b = n_seg / REF_3BANDAS_NSEG
        ratio_lv3 = n_seg / REF_LV3_COMPLETO_NSEG
        delta = n_seg - n_seg_medianas if n_seg_medianas is not None else ""
        if fila["corrida"] == "medianas":
            delta = 0
        salida.append(
            {
                **fila,
                "ratio_vs_3bandas": round(ratio_3b, 3),
                "ratio_vs_lv3_completo": round(ratio_lv3, 3),
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
        ("ratio_vs_lv3_completo", "ratio_lv3"),
        ("delta_vs_medianas", "Δ medianas"),
        ("tam_mediano_px", "tam_mediano"),
    ]
    print("  ".join(f"{titulo:>14}" for _, titulo in cols))
    print("-" * 110)
    for fila in filas:
        vals = []
        for clave, _ in cols:
            v = fila[clave]
            if clave == "n_segmentos":
                vals.append(f"{int(v):>14,}")
            elif clave == "delta_vs_medianas":
                vals.append(f"{int(v):>14,}")
            elif clave in {"ratio_vs_3bandas", "ratio_vs_lv3_completo", "tam_mediano_px"}:
                vals.append(f"{float(v):>14.3f}")
            else:
                vals.append(f"{str(v):>14}")
        print("  ".join(vals))


def imprimir_guia_lectura(filas: list[dict], n_seg_medianas: int) -> None:
    ratio_med = n_seg_medianas / REF_3BANDAS_NSEG
    ratio_lv3 = n_seg_medianas / REF_LV3_COMPLETO_NSEG
    print("\n=== GUÍA DE LECTURA ===")
    print(f"Referencia 3 bandas      : {REF_3BANDAS_NSEG:,} segmentos")
    print(f"Referencia Lv3 completo  : {REF_LV3_COMPLETO_NSEG:,} segmentos")
    print(f"FASE A 'medianas'        : {n_seg_medianas:,} (ratio 3b={ratio_med:.2f}×, lv3={ratio_lv3:.2f}×)")

    if ratio_med <= 2.0:
        print(
            "→ 'medianas' ~ referencia 3 bandas (ratio ≤2×): los extremos eran el ruido;\n"
            "  el stack robusto de segmentación son medianas puras."
        )
    elif ratio_med > 4.0:
        print(
            "→ 'medianas' YA fragmenta mucho (ratio >4×): el problema no son solo los extremos;\n"
            "  ninguna banda RF Lv3 parece mejorar la geometría vs 3 bandas."
        )
    else:
        print("→ 'medianas' en rango intermedio (2–4×): revisar culpables en FASE B.")

    duras = [f for f in filas if f["corrida"].startswith("medianas+")]
    if duras:
        peor = max(duras, key=lambda r: r["delta_vs_medianas"])
        print(
            f"→ Feature dura con mayor Δ vs medianas: '{peor['corrida']}' "
            f"(+{peor['delta_vs_medianas']:,} seg, ratio 3b={peor['ratio_vs_3bandas']:.2f}×)"
        )


def listar_corridas(medianas: list[str], duras: list[str]) -> list[tuple[str, list[str]]]:
    corridas: list[tuple[str, list[str]]] = [("medianas", list(medianas))]
    for dura in duras:
        corridas.append((f"medianas+{dura}", list(medianas) + [dura]))
    return corridas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ablación Lv3: medianas puras + features duras (poda REPORT).",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--report-md", type=Path, default=REPORT_MD)
    parser.add_argument("--stack-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tile = args.tile.upper()
    year = args.year
    report_path = args.report_md.resolve()
    output_dir = args.output_dir.resolve()

    try:
        entradas = bandas_para_tile(report_path, tile)
    except ReportParseError as exc:
        print(f"[ERROR] {exc}")
        return 1

    nombres_lv3 = [e.name for e in entradas]
    clf = clasificar_universo_lv3(nombres_lv3)
    imprimir_clasificacion(clf, len(nombres_lv3))

    if len(clf.medianas) < 3:
        print(f"\n[ERROR] MEDIANAS puras < 3 ({len(clf.medianas)}). Abortar.")
        return 1

    if args.dry_run:
        print("\n[OK] --dry-run: clasificación verificada. Sin segmentación.")
        return 0

    ruta_stack = stack_path(tile, year, args.stack_path)
    if not ruta_stack.is_file():
        print(f"[ERROR] STACK no encontrado: {ruta_stack}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[OK] Stack: {ruta_stack}")
    print(f"[OK] Salida: {output_dir}")

    with rasterio.open(ruta_stack) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [
                descriptions[i] if i < len(descriptions) else "" for i in range(src.count)
            ]

        no_vacias = [d for d in descriptions if d]
        print(f"[OK] GeoTIFF: {len(no_vacias)} descriptions no vacías / {src.count} bandas")
        if not no_vacias:
            print("[ERROR] El stack no trae nombres; definir mapa manual.")
            return 1

        clf = filtrar_presentes_en_stack(clf, descriptions)
        if len(clf.medianas) < 3:
            print(f"[ERROR] MEDIANAS presentes en stack < 3 ({len(clf.medianas)})")
            return 1

        union_nombres = clf.union
        if not union_nombres:
            print("[ERROR] Unión MEDIANAS ∪ DURAS vacía tras filtrar stack.")
            return 1

        corridas = listar_corridas(clf.medianas, clf.duras)
        rutas_previstas = [
            output_dir / f"seg_abl_lv3_{tile}_{year}_{etiqueta_archivo(et)}.tif"
            for et, _ in corridas
        ] + [output_dir / f"resumen_ablacion_lv3_{tile}_{year}.csv"]

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

        perfil = src.profile
        nodata_valor = base.resolver_nodata(src, NODATA)

        # Máscara ÚNICA sobre la unión MEDIANAS ∪ DURAS (mismo dominio en todas las corridas).
        union_stack = leer_stack_por_nombres(src, descriptions, union_nombres)
        validos_global = base.construir_mascara_nodata(union_stack, nodata_valor)
        print(
            f"\n[OK] Máscara única (unión {len(union_nombres)} bandas): "
            f"{validos_global.sum():,} / {validos_global.size:,} píxeles válidos "
            f"({100 * validos_global.mean():.2f}%)"
        )

        union_filled = base.rellenar_nodata_mediana(union_stack, validos_global)

        rgb_nombres = resolver_rgb_nombres(descriptions)
        print(f"[OK] RGB quicklook fijo: {', '.join(rgb_nombres)}")
        rgb_stack = leer_stack_por_nombres(src, descriptions, rgb_nombres)
        rgb_base = base.componer_rgb(rgb_stack, [0, 1, 2], validos_global)

        filas_raw: list[dict] = []
        for etiqueta, nombres_corrida in corridas:
            verbose = etiqueta == "medianas"
            img = preparar_substack_zscore(
                union_filled,
                union_nombres,
                nombres_corrida,
                validos_global,
                etiqueta,
                verbose=verbose,
            )
            fila = segmentar_corrida(
                img,
                validos_global,
                perfil,
                rgb_base,
                output_dir,
                tile,
                year,
                etiqueta,
                nombres_corrida,
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

    ruta_csv = output_dir / f"resumen_ablacion_lv3_{tile}_{year}.csv"
    columnas = [
        "corrida", "n_bandas", "n_segmentos", "ratio_vs_3bandas", "ratio_vs_lv3_completo",
        "delta_vs_medianas", "tam_medio_px", "tam_mediano_px", "tam_min_px", "tam_max_px",
        "tam_medio_ha",
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
    return 0


# ── FASE 2 — NO IMPLEMENTAR ───────────────────────────────────────────────────
# Si ni medianas ni medianas+X acercan ratio 3b a 1–2×, segmentar con 3 bandas
# y reservar feature space RF (lv1/lv3) solo para clasificar.


if __name__ == "__main__":
    raise SystemExit(main())
