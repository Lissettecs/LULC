#!/usr/bin/env python3
"""
Pipeline B — SLIC → RAG hierarchical → filtro de tamaño selectivo.

Ruta B unificada sobre mosaico multibanda (nir, swir1, red, 0–1).
Tres etapas por combinación (scale × sigma × percentil RAG):
  1. SLIC con mask=validos
  2. Fusión espectral jerárquica (merge_hierarchical + media-color)
  3. Absorción selectiva de regiones < SECOND_PASS_MIN_PX

Pipeline A (legado descompuesto): ver legacy_pipeline_a/README.md y seg_slic/README.md.
Salidas A en pipeline_a/, pipeline_a/rag_hierarchical/, pipeline_a/size_filter/.

Uso:
  python seg_slic_pipeline_b.py --tile 18HYD
  python seg_slic_grid.py --tile 18HYD --year 2010 --resume
  python seg_slic_grid.py --combo-index 0   # SLURM array
  python seg_slic_grid.py --from-rag-dir .../rag_hierarchical --resume

Dependencias:
  rasterio, numpy, scikit-image (slic, rag_mean_color, merge_hierarchical,
  relabel_sequential), matplotlib (vía base.guardar_quicklook)

FASE 2 — NO implementado (alcance futuro):
  - Etapa 3 después de atribuir C2 y congelar tier protegido (11,61,67,23,34,24,33).
  - Bug tam_min_px < piso SLIC: rastrear slivers de relabel en borde nodata.
  - Ablación RAG_USE_INDICES=True (NDVI+NDMI).
  - A/B contra Felzenszwalb al mismo scale/sigma, comparando por tam_mediano_px.
  - Ronda 2: barrer COMPACTNESS [5, 10, 20].
"""

from __future__ import annotations

import argparse
import csv
import gc
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from skimage.graph import rag_mean_color

_SEG_SLIC_DIR = Path(__file__).resolve().parent.parent
_FELZ_DIR = _SEG_SLIC_DIR.parent / "seg_felzenszwalb"
if str(_FELZ_DIR) not in sys.path:
    sys.path.insert(0, str(_FELZ_DIR))
if str(_SEG_SLIC_DIR) not in sys.path:
    sys.path.insert(0, str(_SEG_SLIC_DIR))

import seg_felzenszwalb_grid as base  # noqa: E402
import common  # noqa: E402

# ── BLOQUE DE PARÁMETROS (Ruta B) ─────────────────────────────────────────────
DEFAULT_TILE = base.DEFAULT_TILE
DEFAULT_YEAR = base.DEFAULT_YEAR
MOSAIC_DIR = base.MOSAIC_DIR
OUTPUT_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_b"
)
RAG_HIER_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/rag_hierarchical"
)

# Etapa 1 — SLIC (scale = px objetivo por superpíxel)
SCALE_LIST = [100, 150]
SIGMA_LIST = [0.1]

# Etapa 2 — RAG hierarchical
RAG_PERCENTILES = [10, 20]

# Etapa 3 — filtro de tamaño selectivo (0 = desactivar)
SECOND_PASS_MIN_PX = 150

STANDARDIZE = False
NORMALIZE_01 = False
NODATA = None
DISPLAY_BANDS = [0, 1, 2]
PIXEL_HA = 0.09
# ─────────────────────────────────────────────────────────────────────────────


def n_combinaciones_grid() -> int:
    return len(SCALE_LIST) * len(SIGMA_LIST) * len(RAG_PERCENTILES)


def combo_desde_indice(idx: int) -> tuple[int, float, int]:
    return common.combo_desde_indice(SCALE_LIST, SIGMA_LIST, RAG_PERCENTILES, idx)


def resolver_grid_filtros(
    scale: int | None,
    sigma: float | None,
    rag_percentil: int | None,
    combo_index: int | None,
) -> tuple[list[int], list[float], list[int]]:
    return common.resolver_grid_filtros(
        SCALE_LIST,
        SIGMA_LIST,
        RAG_PERCENTILES,
        scale,
        sigma,
        rag_percentil,
        combo_index,
    )


def ruta_rag_hier_entrada(
    rag_dir: Path,
    tile: str,
    year: int,
    scale: int,
    sigma: float,
    percentil: int,
) -> Path:
    stem = common.stem_combo(tile, year, scale, sigma)
    return rag_dir / f"{stem}_{common.sufijo_hier(percentil)}.tif"


def cargar_thr_abs_hier(rag_dir: Path, tile: str, year: int) -> dict[tuple[int, float, int], float]:
    """Lee umbrales RAG desde resumen_hier_{tile}_{year}.csv si existe."""
    ruta_csv = rag_dir / f"resumen_hier_{tile}_{year}.csv"
    umbrales: dict[tuple[int, float, int], float] = {}
    if not ruta_csv.is_file():
        return umbrales
    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scale = int(float(row["scale"]))
            sigma = float(row["sigma"])
            pct = int(float(row["rag_percentil"]))
            thr = row.get("rag_thresh_abs", "").strip()
            if thr:
                umbrales[(scale, sigma, pct)] = float(thr)
    return umbrales


def rutas_salida_combo(
    output_dir: Path,
    tile: str,
    year: int,
    scale: int,
    sigma: float,
    percentil: int,
) -> tuple[Path, Path, Path | None, Path | None]:
    stem = common.stem_combo(tile, year, scale, sigma)
    hier = f"{stem}_{common.sufijo_hier(percentil)}"
    ruta_hier_tif = output_dir / f"{hier}.tif"
    ruta_hier_png = output_dir / f"{hier}.png"
    if SECOND_PASS_MIN_PX > 0:
        final = f"{hier}_min{SECOND_PASS_MIN_PX}"
        return (
            ruta_hier_tif,
            ruta_hier_png,
            output_dir / f"{final}.tif",
            output_dir / f"{final}.png",
        )
    return ruta_hier_tif, ruta_hier_png, None, None


def fila_resumen_pipeline_b(
    scale: int,
    sigma: float,
    percentil: int,
    thr_abs: float,
    n_post_rag: int,
    n_final: int,
    stats_final: dict,
) -> dict:
    return {
        "scale": scale,
        "sigma": sigma,
        "rag_percentil": percentil,
        "rag_thresh_abs": thr_abs,
        "second_pass_min_px": SECOND_PASS_MIN_PX,
        "n_regiones_post_rag": n_post_rag,
        "n_regiones_final": n_final,
        "tam_medio_px": stats_final["tam_medio_px"],
        "tam_mediano_px": stats_final["tam_mediano_px"],
        "tam_min_px": stats_final["tam_min_px"],
        "tam_max_px": stats_final["tam_max_px"],
        "tam_medio_ha": stats_final["tam_medio_ha"],
    }


def imprimir_tabla_pipeline_b(filas: list[dict]) -> None:
    if not filas:
        return
    columnas = [
        "scale",
        "sigma",
        "rag_percentil",
        "n_regiones_final",
        "tam_mediano_px",
        "tam_min_px",
        "tam_max_px",
        "tam_medio_ha",
    ]
    print("\n=== TABLA PIPELINE B ===")
    print("  ".join(f"{c:>14}" for c in columnas))
    print("-" * (15 * len(columnas)))
    for fila in filas:
        print(
            "  ".join(
                f"{fila[c]:>14.4f}" if isinstance(fila[c], float) else f"{fila[c]:>14}"
                for c in columnas
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline B: SLIC → RAG hierarchical → filtro tamaño selectivo.",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE, help=f"Tile MGRS (default: {DEFAULT_TILE})")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help=f"Año (default: {DEFAULT_YEAR})")
    parser.add_argument(
        "--mosaic-dir",
        type=Path,
        default=MOSAIC_DIR,
        help="Directorio con mosaicos {tile}_{year}_nir_swir1_red_0-1.tif",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directorio de salida pipeline B (TIF, PNG, CSV)",
    )
    parser.add_argument(
        "--list-tiles",
        action="store_true",
        help="Lista tiles disponibles en --mosaic-dir y termina",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Omite TIF/PNG ya existentes (útil si el job se interrumpió)",
    )
    parser.add_argument("--scale", type=int, default=None, help="Limitar a un scale del grid")
    parser.add_argument("--sigma", type=float, default=None, help="Limitar a un sigma del grid")
    parser.add_argument(
        "--rag-percentil",
        type=int,
        default=None,
        help="Limitar a un percentil RAG (p. ej. 10)",
    )
    parser.add_argument(
        "--combo-index",
        type=int,
        default=None,
        help=f"Índice 0..{n_combinaciones_grid() - 1} para SLURM --array",
    )
    parser.add_argument(
        "--from-rag-dir",
        type=Path,
        default=None,
        help=(
            "Solo etapa 3: lee post-RAG hier_p* desde este directorio "
            f"(p. ej. {RAG_HIER_DIR}) y escribe salidas finales en --output-dir"
        ),
    )
    return parser.parse_args()


def ejecutar_desde_rag_dir(
    args: argparse.Namespace,
    mosaic_dir: Path,
    output_dir: Path,
    rag_dir: Path,
    tile: str,
    year: int,
    scales: list[int],
    sigmas: list[float],
    pcts: list[int],
) -> None:
    """Etapa 3 únicamente: common.absorber_pequenos sobre TIFs post-RAG ya calculados."""
    if not rag_dir.is_dir():
        print(f"[ERROR] --from-rag-dir no existe: {rag_dir}")
        sys.exit(1)

    mosaic_file = base.nombre_mosaico(tile, year)
    ruta_mosaico = base.localizar_mosaico_tile(mosaic_dir, tile, year)
    umbrales = cargar_thr_abs_hier(rag_dir, tile, year)

    print(f"[OK] Modo --from-rag-dir · tile={tile} · año={year} · mosaico={mosaic_file}")
    print(f"[OK] Entrada post-RAG: {rag_dir}")
    print(f"[OK] Salida pipeline B: {output_dir}")
    print(
        f"[OK] Grid: scales={scales}, sigmas={sigmas}, RAG p={pcts}, "
        f"second_pass_min_px={SECOND_PASS_MIN_PX}"
    )
    if umbrales:
        print(f"[OK] Umbrales RAG desde resumen_hier ({len(umbrales)} combos)")
    else:
        print("[ADVERTENCIA] Sin resumen_hier_*.csv; rag_thresh_abs quedará vacío en CSV")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[ERROR] Sin permiso para crear OUTPUT_DIR: {output_dir}")
        sys.exit(1)

    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            for pct in pcts:
                _, _, r_fin_tif, r_fin_png = rutas_salida_combo(
                    output_dir, tile, year, scale, sigma, int(pct)
                )
                if r_fin_tif and r_fin_png:
                    rutas_previstas.extend([r_fin_tif, r_fin_png])
    if args.combo_index is None:
        rutas_previstas.append(output_dir / f"resumen_pipeline_b_{tile}_{year}.csv")

    if args.resume:
        existentes = [r for r in rutas_previstas if r.exists()]
        if existentes:
            print(f"[OK] --resume: se omitirán {len(existentes)} salidas ya existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    filas_resumen: list[dict] = []
    total = len(scales) * len(sigmas) * len(pcts)
    paso = 0

    with rasterio.open(ruta_mosaico) as src:
        perfil = src.profile
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(np.float32)
        nodata_valor = base.resolver_nodata(src, NODATA)
        validos = base.construir_mascara_nodata(datos, nodata_valor)

        base.diagnosticar_mosaico(src, datos, validos, nodata_valor)

        feats = common.construir_features(datos, validos)
        rgb_base = base.componer_rgb(datos, DISPLAY_BANDS, validos)

        print(f"\n[VERIFICACIÓN] feats.shape = {feats.shape}  (H, W, C={n_bandas})")
        print(f"[OK] Etapa 3: common.absorber_pequenos min_px={SECOND_PASS_MIN_PX}")
        print(f"\n=== PIPELINE B desde RAG ({total} combinaciones) ===")

        for scale in scales:
            for sigma in sigmas:
                for pct in pcts:
                    paso += 1
                    pct = int(pct)
                    r_rag_tif = ruta_rag_hier_entrada(rag_dir, tile, year, scale, sigma, pct)
                    _, _, r_fin_tif, r_fin_png = rutas_salida_combo(
                        output_dir, tile, year, scale, sigma, pct
                    )
                    thr_abs = umbrales.get((scale, sigma, pct), float("nan"))
                    thr_txt = f"{thr_abs:.6f}" if not np.isnan(thr_abs) else "—"
                    print(
                        f"\n[{paso}/{total}] s={scale}, σ={sigma}, p={pct}, thr={thr_txt}",
                        flush=True,
                    )

                    if not r_rag_tif.is_file():
                        print(f"  → [ERROR] Falta entrada: {r_rag_tif.name}")
                        sys.exit(1)

                    if (
                        args.resume
                        and r_fin_tif
                        and r_fin_png
                        and r_fin_tif.is_file()
                        and r_fin_png.is_file()
                    ):
                        with rasterio.open(r_fin_tif) as src_f:
                            final = src_f.read(1).astype(np.int32)
                        with rasterio.open(r_rag_tif) as src_h:
                            merged = src_h.read(1).astype(np.int32)
                        stats_rag = base.estadisticas_segmentos(merged, validos)
                        stats_final = base.estadisticas_segmentos(final, validos)
                        print(f"  → [resume] final desde {r_fin_tif.name}")
                    else:
                        with rasterio.open(r_rag_tif) as src_h:
                            merged = src_h.read(1).astype(np.int32)
                        stats_rag = base.estadisticas_segmentos(merged, validos)
                        print(
                            f"  → post-RAG: {r_rag_tif.name} · "
                            f"n_regiones={stats_rag['n_segmentos']:,}, "
                            f"tam_medio_px={stats_rag['tam_medio_px']:.1f}"
                        )

                        if SECOND_PASS_MIN_PX <= 0:
                            print("[ERROR] SECOND_PASS_MIN_PX=0 no tiene sentido con --from-rag-dir")
                            sys.exit(1)

                        print(
                            f"  → Etapa 3 common.absorber_pequenos (min={SECOND_PASS_MIN_PX}px) ..."
                        )
                        final, n_irres = common.absorber_pequenos(
                            merged, feats, validos, SECOND_PASS_MIN_PX
                        )
                        stats_final = base.estadisticas_segmentos(final, validos)
                        print(
                            f"  → Etapa 3: n_regiones "
                            f"{stats_rag['n_segmentos']:,} → "
                            f"{stats_final['n_segmentos']:,}, "
                            f"tam_medio_px={stats_final['tam_medio_px']:.1f}"
                        )
                        common.verificar_stats_final(stats_final, SECOND_PASS_MIN_PX, n_irres)
                        titulo_final = (
                            f"Pipeline B — {tile} {year} — s={scale}, σ={sigma}, "
                            f"p={pct}, min={SECOND_PASS_MIN_PX}px"
                        )
                        base.guardar_geotiff_labels(final, perfil, r_fin_tif)
                        base.guardar_quicklook(
                            rgb_base, final, validos, r_fin_png, titulo_final
                        )
                        print(f"  → guardado: {r_fin_tif.name}, {r_fin_png.name}")
                        del final

                    filas_resumen.append(
                        fila_resumen_pipeline_b(
                            scale,
                            sigma,
                            pct,
                            thr_abs if not np.isnan(thr_abs) else 0.0,
                            stats_rag["n_segmentos"],
                            stats_final["n_segmentos"],
                            stats_final,
                        )
                    )
                    del merged
                    gc.collect()

    columnas = [
        "scale",
        "sigma",
        "rag_percentil",
        "rag_thresh_abs",
        "second_pass_min_px",
        "n_regiones_post_rag",
        "n_regiones_final",
        "tam_medio_px",
        "tam_mediano_px",
        "tam_min_px",
        "tam_max_px",
        "tam_medio_ha",
    ]
    ruta_csv = output_dir / f"resumen_pipeline_b_{tile}_{year}.csv"
    if args.combo_index is None:
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        fila_path = output_dir / f"resumen_pipeline_b_{tile}_{year}_idx{args.combo_index}.csv"
        with fila_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV parcial: {fila_path}")

    imprimir_tabla_pipeline_b(filas_resumen)
    print(f"[OK] Salidas pipeline B en: {output_dir}")


def main() -> None:
    args = parse_args()
    mosaic_dir = args.mosaic_dir.resolve()
    output_dir = args.output_dir.resolve()
    tile = args.tile.upper()
    year = args.year

    if args.list_tiles:
        tiles = base.listar_tiles(mosaic_dir, year)
        if not tiles:
            print(f"[INFO] No hay tiles con GeoTIFF en {mosaic_dir}")
        else:
            print(f"[INFO] Tiles en {mosaic_dir}:")
            for nombre in tiles:
                print(f"  - {nombre}  →  {base.nombre_mosaico(nombre, year)}")
        return

    if not mosaic_dir.is_dir():
        print(f"[ERROR] MOSAIC_DIR no existe: {mosaic_dir}")
        sys.exit(1)

    tiles_disponibles = base.listar_tiles(mosaic_dir, year)
    if tile not in tiles_disponibles:
        print(f"[ERROR] Tile '{tile}' no encontrado en {mosaic_dir}")
        if tiles_disponibles:
            print(f"[INFO] Tiles disponibles: {', '.join(tiles_disponibles)}")
        sys.exit(1)

    if common.RAG_USE_INDICES:
        print("[ERROR] RAG_USE_INDICES=True no implementado (ablación futura).")
        sys.exit(1)

    try:
        scales, sigmas, pcts = resolver_grid_filtros(
            args.scale, args.sigma, args.rag_percentil, args.combo_index
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if args.from_rag_dir is not None:
        ejecutar_desde_rag_dir(
            args,
            mosaic_dir,
            output_dir,
            args.from_rag_dir.resolve(),
            tile,
            year,
            scales,
            sigmas,
            pcts,
        )
        return

    mosaic_file = base.nombre_mosaico(tile, year)
    ruta_mosaico = base.localizar_mosaico_tile(mosaic_dir, tile, year)
    print(f"[OK] Pipeline B · tile={tile} · año={year} · mosaico={mosaic_file}")
    print(f"[OK] Mosaico: {ruta_mosaico}")
    print(f"[OK] Salida: {output_dir}")
    print(
        f"[OK] Grid: scales={scales}, sigmas={sigmas}, RAG p={pcts}, "
        f"second_pass_min_px={SECOND_PASS_MIN_PX}"
    )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"[ERROR] Sin permiso para crear OUTPUT_DIR: {output_dir}")
        sys.exit(1)

    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            for pct in pcts:
                r_hier_tif, r_hier_png, r_fin_tif, r_fin_png = rutas_salida_combo(
                    output_dir, tile, year, scale, sigma, int(pct)
                )
                rutas_previstas.extend([r_hier_tif, r_hier_png])
                if r_fin_tif and r_fin_png:
                    rutas_previstas.extend([r_fin_tif, r_fin_png])
    rutas_previstas.append(output_dir / f"resumen_pipeline_b_{tile}_{year}.csv")

    if args.resume:
        existentes = [r for r in rutas_previstas if r.exists()]
        if existentes:
            print(f"[OK] --resume: se omitirán {len(existentes)} salidas ya existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    filas_resumen: list[dict] = []
    total = len(scales) * len(sigmas) * len(pcts)
    paso = 0

    with rasterio.open(ruta_mosaico) as src:
        perfil = src.profile
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(np.float32)
        nodata_valor = base.resolver_nodata(src, NODATA)
        validos = base.construir_mascara_nodata(datos, nodata_valor)

        base.diagnosticar_mosaico(src, datos, validos, nodata_valor)

        feats = common.construir_features(datos, validos)
        rgb_base = base.componer_rgb(datos, DISPLAY_BANDS, validos)
        n_validos = int(validos.sum())

        print(f"\n[VERIFICACIÓN] feats.shape = {feats.shape}  (H, W, C={n_bandas})")
        print(f"[OK] SLIC: n_segments = validos//scale, compactness={common.COMPACTNESS}")
        print(f"[OK] RAG: hierarchical, percentiles={RAG_PERCENTILES}, bandas=3 (nir,swir1,red)")
        if SECOND_PASS_MIN_PX > 0:
            print(f"[OK] Etapa 3: common.absorber_pequenos min_px={SECOND_PASS_MIN_PX}")

        print(f"\n=== PIPELINE B ({total} combinaciones) ===")

        for scale in scales:
            for sigma in sigmas:
                n_seg = common.n_segments_desde_scale(n_validos, scale)
                print(
                    f"\n--- scale={scale}, σ={sigma}, n_segments={n_seg:,} ---",
                    flush=True,
                )

                t_slic = time.perf_counter()
                sp = common.ejecutar_slic(feats, validos, n_seg, sigma)
                print(f"  → SLIC calculado en {time.perf_counter() - t_slic:.1f}s", flush=True)
                stats_slic = base.estadisticas_segmentos(sp, validos)
                print(
                    f"  → Etapa 1 SLIC: regiones={stats_slic['n_segmentos']:,}, "
                    f"tam_medio_px={stats_slic['tam_medio_px']:.1f}"
                )

                g_base = rag_mean_color(feats, sp)
                pesos = common.pesos_aristas_rag(g_base)
                common.imprimir_distribucion_pesos(pesos, scale, sigma)
                del g_base
                gc.collect()

                if pesos.size == 0:
                    print("  → [ADVERTENCIA] RAG sin aristas; se omiten percentiles")
                    del sp
                    continue

                for pct in pcts:
                    paso += 1
                    pct = int(pct)
                    thr_abs = common.umbral_rag_desde_pesos(pesos, pct)
                    r_hier_tif, r_hier_png, r_fin_tif, r_fin_png = rutas_salida_combo(
                        output_dir, tile, year, scale, sigma, pct
                    )
                    log_combo = f"s={scale}, σ={sigma}, p={pct}, thr={thr_abs:.6f}"
                    print(f"\n[{paso}/{total}] {log_combo}")

                    necesita_hier = not (
                        args.resume
                        and r_hier_tif.is_file()
                        and r_hier_png.is_file()
                    )
                    necesita_final = SECOND_PASS_MIN_PX > 0 and r_fin_tif and r_fin_png and not (
                        args.resume and r_fin_tif.is_file() and r_fin_png.is_file()
                    )

                    if not necesita_hier and not necesita_final:
                        with rasterio.open(
                            r_fin_tif if r_fin_tif and r_fin_tif.is_file() else r_hier_tif
                        ) as src_out:
                            final = src_out.read(1).astype(np.int32)
                        with rasterio.open(r_hier_tif) as src_h:
                            merged = src_h.read(1).astype(np.int32)
                        stats_rag = base.estadisticas_segmentos(merged, validos)
                        stats_final = base.estadisticas_segmentos(final, validos)
                        print(f"  → [resume] combo completo")
                    else:
                        if necesita_hier:
                            merged = common.fusionar_hierarchical_rag(sp, feats, thr_abs, validos)
                            stats_rag = base.estadisticas_segmentos(merged, validos)
                            print(
                                f"  → Etapa 2 RAG: n_regiones={stats_rag['n_segmentos']:,}, "
                                f"tam_medio_px={stats_rag['tam_medio_px']:.1f}"
                            )
                            common.verificar_stats_rag(stats_rag)
                            titulo_hier = (
                                f"Pipeline B — {tile} {year} — s={scale}, σ={sigma}, "
                                f"p={pct} (post-RAG)"
                            )
                            base.guardar_geotiff_labels(merged, perfil, r_hier_tif)
                            base.guardar_quicklook(
                                rgb_base, merged, validos, r_hier_png, titulo_hier
                            )
                            print(f"  → guardado: {r_hier_tif.name}, {r_hier_png.name}")
                        else:
                            with rasterio.open(r_hier_tif) as src_h:
                                merged = src_h.read(1).astype(np.int32)
                            stats_rag = base.estadisticas_segmentos(merged, validos)
                            print(f"  → [resume] post-RAG desde {r_hier_tif.name}")

                        if SECOND_PASS_MIN_PX > 0:
                            if necesita_final:
                                print(
                                    f"  → Etapa 3 common.absorber_pequenos (min={SECOND_PASS_MIN_PX}px) ..."
                                )
                                final, n_irres = common.absorber_pequenos(
                                    merged, feats, validos, SECOND_PASS_MIN_PX
                                )
                                stats_final = base.estadisticas_segmentos(final, validos)
                                print(
                                    f"  → Etapa 3: n_regiones "
                                    f"{stats_rag['n_segmentos']:,} → "
                                    f"{stats_final['n_segmentos']:,}, "
                                    f"tam_medio_px={stats_final['tam_medio_px']:.1f}"
                                )
                                common.verificar_stats_final(
                                    stats_final, SECOND_PASS_MIN_PX, n_irres
                                )
                                titulo_final = (
                                    f"Pipeline B — {tile} {year} — s={scale}, σ={sigma}, "
                                    f"p={pct}, min={SECOND_PASS_MIN_PX}px"
                                )
                                base.guardar_geotiff_labels(final, perfil, r_fin_tif)
                                base.guardar_quicklook(
                                    rgb_base, final, validos, r_fin_png, titulo_final
                                )
                                print(f"  → guardado: {r_fin_tif.name}, {r_fin_png.name}")
                                del final
                            else:
                                with rasterio.open(r_fin_tif) as src_f:
                                    final = src_f.read(1).astype(np.int32)
                                stats_final = base.estadisticas_segmentos(final, validos)
                                print(f"  → [resume] final desde {r_fin_tif.name}")
                        else:
                            final = merged
                            stats_final = stats_rag
                            n_irres = 0

                        del merged
                        gc.collect()

                    filas_resumen.append(
                        fila_resumen_pipeline_b(
                            scale,
                            sigma,
                            pct,
                            thr_abs,
                            stats_rag["n_segmentos"],
                            stats_final["n_segmentos"],
                            stats_final,
                        )
                    )

                del sp
                gc.collect()

    columnas = [
        "scale",
        "sigma",
        "rag_percentil",
        "rag_thresh_abs",
        "second_pass_min_px",
        "n_regiones_post_rag",
        "n_regiones_final",
        "tam_medio_px",
        "tam_mediano_px",
        "tam_min_px",
        "tam_max_px",
        "tam_medio_ha",
    ]
    ruta_csv = output_dir / f"resumen_pipeline_b_{tile}_{year}.csv"
    if args.combo_index is None:
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        fila_path = output_dir / f"resumen_pipeline_b_{tile}_{year}_idx{args.combo_index}.csv"
        with fila_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas_resumen)
        print(f"\n[OK] CSV parcial: {fila_path}")

    imprimir_tabla_pipeline_b(filas_resumen)
    print(f"[OK] Salidas pipeline B en: {output_dir}")


if __name__ == "__main__":
    main()
