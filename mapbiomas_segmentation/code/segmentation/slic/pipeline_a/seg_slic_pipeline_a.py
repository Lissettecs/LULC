#!/usr/bin/env python3
"""
Pipeline A (legado) — SLIC descompuesto en 3 etapas separadas.

Etapa 1 (default): SLIC + RAG threshold (cut_threshold + percentiles p10/p20/p30)
  → salida en pipeline_a/ (raíz)

Etapa 2 (--solo-rag-hierarchical): RAG hierarchical (p10/p20)
  → salida en pipeline_a/rag_hierarchical/
  Con --solo-rag-hierarchical se reutiliza SLIC existente si está en pipeline_a/.

Etapa 3 (--solo-size-filter): absorber_pequenos(min=150) sobre RAG threshold
  → salida en pipeline_a/size_filter/

Uso:
  python seg_slic_pipeline_a.py --tile 18HYD
  python seg_slic_pipeline_a.py --solo-rag-hierarchical --combo-index 0
  python seg_slic_pipeline_a.py --solo-size-filter --combo-index 0 --resume
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

# ── PARÁMETROS PIPELINE A ─────────────────────────────────────────────────────
DEFAULT_TILE = base.DEFAULT_TILE
DEFAULT_YEAR = base.DEFAULT_YEAR
MOSAIC_DIR = base.MOSAIC_DIR
OUTPUT_DIR = Path(
    "/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a"
)
OUTPUT_DIR_HIER = OUTPUT_DIR / "rag_hierarchical"
OUTPUT_DIR_SIZE = OUTPUT_DIR / "size_filter"

# Etapa 1 — mismo grid que Felzenszwalb
SCALE_LIST = list(base.SCALE_LIST)
SIGMA_LIST = list(base.SIGMA_LIST)
RAG_PERCENTILES = [10, 20, 30]
RAG_MODE_ETAPA1 = "threshold"
RAG_THRESH_MODE = "percentile"

# Etapa 2 — subgrid hierarchical
SCALE_LIST_HIER = [100, 150]
SIGMA_LIST_HIER = [0.1]
RAG_PERCENTILES_HIER = [10, 20]
RAG_MODE_HIER = "hierarchical"

# Etapa 3 — filtro tamaño sobre RAG threshold
RAG_MIN_SIZE_PX = 150

NODATA = None
DISPLAY_BANDS = [0, 1, 2]
PIXEL_HA = 0.09
# ─────────────────────────────────────────────────────────────────────────────


def n_combinaciones_etapa1() -> int:
    return len(SCALE_LIST) * len(SIGMA_LIST) * (1 + len(RAG_PERCENTILES))


def n_combinaciones_hier() -> int:
    return len(SCALE_LIST_HIER) * len(SIGMA_LIST_HIER) * len(RAG_PERCENTILES_HIER)


def n_combinaciones_size_filter() -> int:
    return len(SCALE_LIST) * len(SIGMA_LIST) * len(RAG_PERCENTILES)


def ruta_slic_base(output_dir: Path, tile: str, year: int, scale: int, sigma: float) -> Path:
    stem = common.stem_combo(tile, year, scale, sigma)
    return output_dir / f"{stem}.tif"


def ruta_rag_threshold(
    output_dir: Path, tile: str, year: int, scale: int, sigma: float, percentil: int
) -> Path:
    stem = common.stem_combo(tile, year, scale, sigma)
    return output_dir / f"{stem}_{common.sufijo_ragp(percentil)}.tif"


def ruta_hier(
    output_dir: Path, tile: str, year: int, scale: int, sigma: float, percentil: int
) -> Path:
    stem = common.stem_combo(tile, year, scale, sigma)
    return output_dir / f"{stem}_{common.sufijo_hier(percentil)}.tif"


def ruta_size_filter(
    output_dir: Path, tile: str, year: int, scale: int, sigma: float, percentil: int
) -> Path:
    stem = common.stem_combo(tile, year, scale, sigma)
    return output_dir / f"{stem}_{common.sufijo_ragp(percentil)}_min{RAG_MIN_SIZE_PX}.tif"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline A: SLIC + RAG threshold / hierarchical / size filter.",
    )
    parser.add_argument("--tile", default=DEFAULT_TILE)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--mosaic-dir", type=Path, default=MOSAIC_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--list-tiles", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--scale", type=int, default=None)
    parser.add_argument("--sigma", type=float, default=None)
    parser.add_argument("--rag-percentil", type=int, default=None)
    parser.add_argument("--combo-index", type=int, default=None)
    parser.add_argument(
        "--solo-rag-hierarchical",
        action="store_true",
        help="Etapa 2: RAG hierarchical → rag_hierarchical/ (reutiliza SLIC si existe)",
    )
    parser.add_argument(
        "--solo-size-filter",
        action="store_true",
        help="Etapa 3: absorber_pequenos sobre RAG threshold → size_filter/",
    )
    return parser.parse_args()


def _validar_tile(mosaic_dir: Path, tile: str, year: int) -> None:
    if not mosaic_dir.is_dir():
        print(f"[ERROR] MOSAIC_DIR no existe: {mosaic_dir}")
        sys.exit(1)
    tiles = base.listar_tiles(mosaic_dir, year)
    if tile not in tiles:
        print(f"[ERROR] Tile '{tile}' no encontrado en {mosaic_dir}")
        if tiles:
            print(f"[INFO] Tiles disponibles: {', '.join(tiles)}")
        sys.exit(1)


def _cargar_mosaico(ruta_mosaico: Path) -> tuple:
    with rasterio.open(ruta_mosaico) as src:
        perfil = src.profile
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(
            np.float32
        )
        nodata_valor = base.resolver_nodata(src, NODATA)
        validos = base.construir_mascara_nodata(datos, nodata_valor)
        base.diagnosticar_mosaico(src, datos, validos, nodata_valor)
        feats = common.construir_features(datos, validos)
        rgb_base = base.componer_rgb(datos, DISPLAY_BANDS, validos)
        n_validos = int(validos.sum())
    return perfil, datos, validos, feats, rgb_base, n_validos


def _guardar_combo(
    labels: np.ndarray,
    perfil: dict,
    rgb_base: np.ndarray,
    validos: np.ndarray,
    ruta_tif: Path,
    titulo: str,
) -> None:
    ruta_png = ruta_tif.with_suffix(".png")
    base.guardar_geotiff_labels(labels, perfil, ruta_tif)
    base.guardar_quicklook(rgb_base, labels, validos, ruta_png, titulo)
    print(f"  → guardado: {ruta_tif.name}, {ruta_png.name}")


def _obtener_o_calcular_slic(
    feats: np.ndarray,
    validos: np.ndarray,
    scale: int,
    sigma: float,
    n_validos: int,
    slic_dir: Path,
    tile: str,
    year: int,
    perfil: dict,
    rgb_base: np.ndarray,
    resume: bool,
    solo_reutilizar: bool,
) -> np.ndarray:
    ruta_slic = ruta_slic_base(slic_dir, tile, year, scale, sigma)
    ruta_png = ruta_slic.with_suffix(".png")

    if resume and ruta_slic.is_file() and ruta_png.is_file():
        with rasterio.open(ruta_slic) as src_s:
            sp = src_s.read(1).astype(np.int32)
        print(f"  → [resume] SLIC desde {ruta_slic.name}")
        return sp

    if solo_reutilizar:
        if not ruta_slic.is_file():
            print(f"  → [ERROR] Falta SLIC para reutilizar: {ruta_slic}")
            sys.exit(1)
        with rasterio.open(ruta_slic) as src_s:
            sp = src_s.read(1).astype(np.int32)
        print(f"  → SLIC cargado: {ruta_slic.name}")
        return sp

    n_seg = common.n_segments_desde_scale(n_validos, scale)
    t0 = time.perf_counter()
    sp = common.ejecutar_slic(feats, validos, n_seg, sigma)
    print(f"  → SLIC calculado en {time.perf_counter() - t0:.1f}s (n_seg={n_seg:,})")
    stats = base.estadisticas_segmentos(sp, validos)
    print(
        f"  → SLIC: regiones={stats['n_segmentos']:,}, "
        f"tam_medio_px={stats['tam_medio_px']:.1f}"
    )
    titulo = f"Pipeline A — {tile} {year} — s={scale}, σ={sigma} (SLIC)"
    _guardar_combo(sp, perfil, rgb_base, validos, ruta_slic, titulo)
    return sp


def ejecutar_etapa1(
    args: argparse.Namespace,
    tile: str,
    year: int,
    mosaic_dir: Path,
    output_dir: Path,
) -> None:
    scales = [args.scale] if args.scale is not None else SCALE_LIST
    sigmas = [args.sigma] if args.sigma is not None else SIGMA_LIST
    pcts = (
        [args.rag_percentil]
        if args.rag_percentil is not None
        else [int(p) for p in RAG_PERCENTILES]
    )

    ruta_mosaico = base.localizar_mosaico_tile(mosaic_dir, tile, year)
    print(f"[OK] Pipeline A etapa 1 · tile={tile} · año={year}")
    print(f"[OK] Mosaico: {ruta_mosaico}")
    print(f"[OK] Salida: {output_dir}")
    print(f"[OK] Grid: scales={scales}, sigmas={sigmas}, RAG p={pcts}")

    output_dir.mkdir(parents=True, exist_ok=True)

    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            stem = common.stem_combo(tile, year, scale, sigma)
            rutas_previstas.extend(
                [
                    output_dir / f"{stem}.tif",
                    output_dir / f"{stem}.png",
                ]
            )
            for pct in pcts:
                suf = common.sufijo_ragp(int(pct))
                rutas_previstas.extend(
                    [
                        output_dir / f"{stem}_{suf}.tif",
                        output_dir / f"{stem}_{suf}.png",
                    ]
                )
    rutas_previstas.append(output_dir / f"resumen_{tile}_{year}.csv")

    if args.resume:
        print(f"[OK] --resume: omitir {sum(1 for r in rutas_previstas if r.exists())} existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    perfil, _, validos, feats, rgb_base, n_validos = _cargar_mosaico(ruta_mosaico)
    filas: list[dict] = []
    total_rag = len(scales) * len(sigmas) * len(pcts)
    paso_rag = 0

    print(f"\n=== PIPELINE A etapa 1 ({len(scales)*len(sigmas)} SLIC + {total_rag} RAG) ===")

    for scale in scales:
        for sigma in sigmas:
            print(f"\n--- scale={scale}, σ={sigma} ---", flush=True)
            ruta_slic = ruta_slic_base(output_dir, tile, year, scale, sigma)
            ruta_png = ruta_slic.with_suffix(".png")

            if args.resume and ruta_slic.is_file() and ruta_png.is_file():
                with rasterio.open(ruta_slic) as src_s:
                    sp = src_s.read(1).astype(np.int32)
                print(f"  → [resume] SLIC desde {ruta_slic.name}")
            else:
                n_seg = common.n_segments_desde_scale(n_validos, scale)
                t0 = time.perf_counter()
                sp = common.ejecutar_slic(feats, validos, n_seg, sigma)
                print(f"  → SLIC en {time.perf_counter() - t0:.1f}s (n_seg={n_seg:,})")
                stats_slic = base.estadisticas_segmentos(sp, validos)
                titulo = f"Pipeline A — {tile} {year} — s={scale}, σ={sigma} (SLIC)"
                _guardar_combo(sp, perfil, rgb_base, validos, ruta_slic, titulo)
                filas.append(
                    {
                        "scale": scale,
                        "sigma": sigma,
                        "min_size": scale,
                        "n_segments_objetivo": n_seg,
                        "compactness": common.COMPACTNESS,
                        "rag_mode": "",
                        "rag_thresh_mode": "",
                        "rag_percentil": "",
                        "rag_thresh_abs": "",
                        "rag_use_indices": common.RAG_USE_INDICES,
                        "n_regiones_fusionadas": "",
                        "n_segmentos": stats_slic["n_segmentos"],
                        "tam_medio_px": stats_slic["tam_medio_px"],
                        "tam_mediano_px": stats_slic["tam_mediano_px"],
                        "tam_min_px": stats_slic["tam_min_px"],
                        "tam_max_px": stats_slic["tam_max_px"],
                        "tam_medio_ha": stats_slic["tam_medio_ha"],
                    }
                )

            g_base = rag_mean_color(common._feats_para_rag(feats, validos), sp)
            pesos = common.pesos_aristas_rag(g_base)
            common.imprimir_distribucion_pesos(pesos, scale, sigma)
            del g_base

            if pesos.size == 0:
                print("  → [ADVERTENCIA] RAG sin aristas; se omiten percentiles")
                del sp
                gc.collect()
                continue

            for pct in pcts:
                paso_rag += 1
                pct = int(pct)
                thr_abs = common.umbral_rag_desde_pesos(pesos, pct)
                r_rag = ruta_rag_threshold(output_dir, tile, year, scale, sigma, pct)
                r_png = r_rag.with_suffix(".png")
                print(f"\n  [{paso_rag}/{total_rag}] ragp{pct}, thr={thr_abs:.6f}")

                if args.resume and r_rag.is_file() and r_png.is_file():
                    with rasterio.open(r_rag) as src_r:
                        merged = src_r.read(1).astype(np.int32)
                    print(f"  → [resume] RAG desde {r_rag.name}")
                else:
                    merged = common.fusionar_threshold_rag(sp, feats, thr_abs, validos)
                    stats_rag = base.estadisticas_segmentos(merged, validos)
                    common.verificar_stats_rag(stats_rag)
                    titulo = (
                        f"Pipeline A — {tile} {year} — s={scale}, σ={sigma}, "
                        f"ragp{pct} (threshold)"
                    )
                    _guardar_combo(merged, perfil, rgb_base, validos, r_rag, titulo)
                    filas.append(
                        {
                            "scale": scale,
                            "sigma": sigma,
                            "min_size": scale,
                            "n_segments_objetivo": common.n_segments_desde_scale(
                                n_validos, scale
                            ),
                            "compactness": common.COMPACTNESS,
                            "rag_mode": RAG_MODE_ETAPA1,
                            "rag_thresh_mode": RAG_THRESH_MODE,
                            "rag_percentil": pct,
                            "rag_thresh_abs": thr_abs,
                            "rag_use_indices": common.RAG_USE_INDICES,
                            "n_regiones_fusionadas": stats_rag["n_segmentos"],
                            "n_segmentos": stats_rag["n_segmentos"],
                            "tam_medio_px": stats_rag["tam_medio_px"],
                            "tam_mediano_px": stats_rag["tam_mediano_px"],
                            "tam_min_px": stats_rag["tam_min_px"],
                            "tam_max_px": stats_rag["tam_max_px"],
                            "tam_medio_ha": stats_rag["tam_medio_ha"],
                        }
                    )
                    del merged
                    gc.collect()

            del sp
            gc.collect()

    columnas = [
        "scale", "sigma", "min_size", "n_segments_objetivo", "compactness",
        "rag_mode", "rag_thresh_mode", "rag_percentil", "rag_thresh_abs",
        "rag_use_indices", "n_regiones_fusionadas", "n_segmentos",
        "tam_medio_px", "tam_mediano_px", "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    ruta_csv = output_dir / f"resumen_{tile}_{year}.csv"
    filas_csv = _fusionar_filas_csv(ruta_csv, filas) if args.rag_percentil is not None else filas
    with ruta_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas_csv)
    print(f"\n[OK] CSV: {ruta_csv}")
    print(f"[OK] Salidas etapa 1 en: {output_dir}")


def _fusionar_filas_csv(
    ruta_csv: Path, nuevas: list[dict]
) -> list[dict]:
    """Al recalcular un subconjunto (p. ej. solo ragp10), conserva filas previas."""
    if not ruta_csv.is_file() or not nuevas:
        return nuevas
    with ruta_csv.open(newline="", encoding="utf-8") as f:
        previas = list(csv.DictReader(f))
    claves_nuevas = {
        (str(r.get("scale")), str(r.get("sigma")), str(r.get("rag_percentil")))
        for r in nuevas
    }
    conservadas = [
        r
        for r in previas
        if (str(r.get("scale")), str(r.get("sigma")), str(r.get("rag_percentil")))
        not in claves_nuevas
    ]
    return conservadas + nuevas


def ejecutar_etapa2_hierarchical(
    args: argparse.Namespace,
    tile: str,
    year: int,
    mosaic_dir: Path,
    slic_dir: Path,
    output_dir: Path,
) -> None:
    try:
        scales, sigmas, pcts = common.resolver_grid_filtros(
            SCALE_LIST_HIER,
            SIGMA_LIST_HIER,
            RAG_PERCENTILES_HIER,
            args.scale,
            args.sigma,
            args.rag_percentil,
            args.combo_index,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    ruta_mosaico = base.localizar_mosaico_tile(mosaic_dir, tile, year)
    print(f"[OK] Pipeline A etapa 2 (RAG hierarchical) · tile={tile} · año={year}")
    print(f"[OK] SLIC entrada: {slic_dir}")
    print(f"[OK] Salida: {output_dir}")
    print(f"[OK] Grid: scales={scales}, sigmas={sigmas}, RAG p={pcts}")

    output_dir.mkdir(parents=True, exist_ok=True)
    solo_reutilizar = True

    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            for pct in pcts:
                r = ruta_hier(output_dir, tile, year, scale, sigma, int(pct))
                rutas_previstas.extend([r, r.with_suffix(".png")])
    if args.combo_index is None:
        rutas_previstas.append(output_dir / f"resumen_hier_{tile}_{year}.csv")

    if args.resume:
        print(f"[OK] --resume: omitir {sum(1 for r in rutas_previstas if r.exists())} existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    perfil, _, validos, feats, rgb_base, n_validos = _cargar_mosaico(ruta_mosaico)
    filas: list[dict] = []
    total = len(scales) * len(sigmas) * len(pcts)
    paso = 0

    print(f"\n=== PIPELINE A etapa 2 ({total} combinaciones) ===")

    for scale in scales:
        for sigma in sigmas:
            sp = _obtener_o_calcular_slic(
                feats,
                validos,
                scale,
                sigma,
                n_validos,
                slic_dir,
                tile,
                year,
                perfil,
                rgb_base,
                args.resume,
                solo_reutilizar,
            )

            g_base = rag_mean_color(common._feats_para_rag(feats, validos), sp)
            pesos = common.pesos_aristas_rag(g_base)
            common.imprimir_distribucion_pesos(pesos, scale, sigma)
            del g_base

            if pesos.size == 0:
                print("  → [ADVERTENCIA] RAG sin aristas")
                del sp
                gc.collect()
                continue

            for pct in pcts:
                paso += 1
                pct = int(pct)
                thr_abs = common.umbral_rag_desde_pesos(pesos, pct)
                r_hier = ruta_hier(output_dir, tile, year, scale, sigma, pct)
                r_png = r_hier.with_suffix(".png")
                print(f"\n[{paso}/{total}] s={scale}, σ={sigma}, p={pct}, thr={thr_abs:.6f}")

                if args.resume and r_hier.is_file() and r_png.is_file():
                    with rasterio.open(r_hier) as src_h:
                        merged = src_h.read(1).astype(np.int32)
                    print(f"  → [resume] hier desde {r_hier.name}")
                else:
                    merged = common.fusionar_hierarchical_rag(sp, feats, thr_abs, validos)
                    stats = base.estadisticas_segmentos(merged, validos)
                    common.verificar_stats_rag(stats)
                    titulo = (
                        f"Pipeline A — {tile} {year} — s={scale}, σ={sigma}, "
                        f"hier_p{pct}"
                    )
                    _guardar_combo(merged, perfil, rgb_base, validos, r_hier, titulo)
                    filas.append(
                        {
                            "scale": scale,
                            "sigma": sigma,
                            "rag_mode": RAG_MODE_HIER,
                            "rag_thresh_mode": RAG_THRESH_MODE,
                            "rag_percentil": pct,
                            "rag_thresh_abs": thr_abs,
                            "n_regiones_fusionadas": stats["n_segmentos"],
                            "n_segmentos": stats["n_segmentos"],
                            "tam_medio_px": stats["tam_medio_px"],
                            "tam_mediano_px": stats["tam_mediano_px"],
                            "tam_min_px": stats["tam_min_px"],
                            "tam_max_px": stats["tam_max_px"],
                            "tam_medio_ha": stats["tam_medio_ha"],
                        }
                    )
                    del merged
                    gc.collect()

            del sp
            gc.collect()

    columnas = [
        "scale", "sigma", "rag_mode", "rag_thresh_mode", "rag_percentil",
        "rag_thresh_abs", "n_regiones_fusionadas", "n_segmentos",
        "tam_medio_px", "tam_mediano_px", "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    ruta_csv = output_dir / f"resumen_hier_{tile}_{year}.csv"
    if args.combo_index is None:
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        fila_path = output_dir / f"resumen_hier_{tile}_{year}_idx{args.combo_index}.csv"
        with fila_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] CSV parcial: {fila_path}")

    print(f"[OK] Salidas etapa 2 en: {output_dir}")


def ejecutar_etapa3_size_filter(
    args: argparse.Namespace,
    tile: str,
    year: int,
    mosaic_dir: Path,
    rag_dir: Path,
    output_dir: Path,
) -> None:
    try:
        scales, sigmas, pcts = common.resolver_grid_filtros(
            SCALE_LIST,
            SIGMA_LIST,
            RAG_PERCENTILES,
            args.scale,
            args.sigma,
            args.rag_percentil,
            args.combo_index,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    ruta_mosaico = base.localizar_mosaico_tile(mosaic_dir, tile, year)
    print(f"[OK] Pipeline A etapa 3 (size filter) · tile={tile} · año={year}")
    print(f"[OK] Entrada RAG threshold: {rag_dir}")
    print(f"[OK] Salida: {output_dir}")
    print(f"[OK] Grid: {scales} × {sigmas} × p={pcts}, min_px={RAG_MIN_SIZE_PX}")

    output_dir.mkdir(parents=True, exist_ok=True)

    rutas_previstas: list[Path] = []
    for scale in scales:
        for sigma in sigmas:
            for pct in pcts:
                r = ruta_size_filter(output_dir, tile, year, scale, sigma, int(pct))
                rutas_previstas.extend([r, r.with_suffix(".png")])
    if args.combo_index is None:
        rutas_previstas.append(output_dir / f"resumen_size_filter_{tile}_{year}.csv")

    if args.resume:
        print(f"[OK] --resume: omitir {sum(1 for r in rutas_previstas if r.exists())} existentes")
    else:
        base.verificar_sobrescritura(rutas_previstas)

    perfil, _, validos, feats, rgb_base, _ = _cargar_mosaico(ruta_mosaico)
    filas: list[dict] = []
    total = len(scales) * len(sigmas) * len(pcts)
    paso = 0

    print(f"\n=== PIPELINE A etapa 3 ({total} combinaciones) ===")

    for scale in scales:
        for sigma in sigmas:
            for pct in pcts:
                paso += 1
                pct = int(pct)
                r_rag = ruta_rag_threshold(rag_dir, tile, year, scale, sigma, pct)
                r_out = ruta_size_filter(output_dir, tile, year, scale, sigma, pct)
                r_png = r_out.with_suffix(".png")
                print(f"\n[{paso}/{total}] s={scale}, σ={sigma}, ragp{pct}")

                if not r_rag.is_file():
                    print(f"  → [ERROR] Falta entrada: {r_rag.name}")
                    sys.exit(1)

                if args.resume and r_out.is_file() and r_png.is_file():
                    with rasterio.open(r_rag) as src_r:
                        merged = src_r.read(1).astype(np.int32)
                    with rasterio.open(r_out) as src_o:
                        final = src_o.read(1).astype(np.int32)
                    stats_pre = base.estadisticas_segmentos(merged, validos)
                    stats_post = base.estadisticas_segmentos(final, validos)
                    print(f"  → [resume] desde {r_out.name}")
                else:
                    with rasterio.open(r_rag) as src_r:
                        merged = src_r.read(1).astype(np.int32)
                    stats_pre = base.estadisticas_segmentos(merged, validos)
                    print(
                        f"  → pre-filtro: n_regiones={stats_pre['n_segmentos']:,}, "
                        f"tam_medio_px={stats_pre['tam_medio_px']:.1f}"
                    )
                    print(f"  → absorber_pequenos (min={RAG_MIN_SIZE_PX}px) ...")
                    final, n_irres = common.absorber_pequenos(
                        merged, feats, validos, RAG_MIN_SIZE_PX
                    )
                    stats_post = base.estadisticas_segmentos(final, validos)
                    print(
                        f"  → post-filtro: n_regiones "
                        f"{stats_pre['n_segmentos']:,} → {stats_post['n_segmentos']:,}"
                    )
                    common.verificar_stats_final(stats_post, RAG_MIN_SIZE_PX, n_irres)
                    titulo = (
                        f"Pipeline A — {tile} {year} — s={scale}, σ={sigma}, "
                        f"ragp{pct}, min={RAG_MIN_SIZE_PX}px"
                    )
                    _guardar_combo(final, perfil, rgb_base, validos, r_out, titulo)
                    del final
                    gc.collect()

                filas.append(
                    {
                        "scale": scale,
                        "sigma": sigma,
                        "rag_percentil": pct,
                        "rag_min_size_px": RAG_MIN_SIZE_PX,
                        "n_regiones_pre_filtro": stats_pre["n_segmentos"],
                        "n_regiones_post_filtro": stats_post["n_segmentos"],
                        "tam_medio_px": stats_post["tam_medio_px"],
                        "tam_mediano_px": stats_post["tam_mediano_px"],
                        "tam_min_px": stats_post["tam_min_px"],
                        "tam_max_px": stats_post["tam_max_px"],
                        "tam_medio_ha": stats_post["tam_medio_ha"],
                    }
                )
                del merged
                gc.collect()

    columnas = [
        "scale", "sigma", "rag_percentil", "rag_min_size_px",
        "n_regiones_pre_filtro", "n_regiones_post_filtro",
        "tam_medio_px", "tam_mediano_px", "tam_min_px", "tam_max_px", "tam_medio_ha",
    ]
    ruta_csv = output_dir / f"resumen_size_filter_{tile}_{year}.csv"
    if args.combo_index is None:
        with ruta_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] CSV: {ruta_csv}")
    else:
        fila_path = (
            output_dir / f"resumen_size_filter_{tile}_{year}_idx{args.combo_index}.csv"
        )
        with fila_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] CSV parcial: {fila_path}")

    print(f"[OK] Salidas etapa 3 en: {output_dir}")


def main() -> None:
    args = parse_args()
    mosaic_dir = args.mosaic_dir.resolve()
    output_dir = args.output_dir.resolve()
    tile = args.tile.upper()
    year = args.year

    if args.list_tiles:
        tiles = base.listar_tiles(mosaic_dir, year)
        if not tiles:
            print(f"[INFO] No hay tiles en {mosaic_dir}")
        else:
            print(f"[INFO] Tiles en {mosaic_dir}:")
            for nombre in tiles:
                print(f"  - {nombre}  →  {base.nombre_mosaico(nombre, year)}")
        return

    _validar_tile(mosaic_dir, tile, year)

    if common.RAG_USE_INDICES:
        print("[ERROR] RAG_USE_INDICES=True no implementado.")
        sys.exit(1)

    if args.solo_size_filter:
        ejecutar_etapa3_size_filter(
            args, tile, year, mosaic_dir, output_dir, OUTPUT_DIR_SIZE.resolve()
        )
    elif args.solo_rag_hierarchical:
        ejecutar_etapa2_hierarchical(
            args,
            tile,
            year,
            mosaic_dir,
            output_dir,
            OUTPUT_DIR_HIER.resolve(),
        )
    else:
        ejecutar_etapa1(args, tile, year, mosaic_dir, output_dir)


if __name__ == "__main__":
    main()
