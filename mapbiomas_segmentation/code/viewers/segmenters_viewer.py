#!/usr/bin/env python3
"""
Unified Felzenszwalb + SLIC viewer (scale × sigma grid).

Based on visualize_seg_felzenszwalb_grid.py. Builds an HTML dashboard with layer explorer,
side-by-side segmenter comparison, and per-algorithm metrics.

Usage:
  cd labeling/image_segmentation
  python segmenters_viewer.py --skip-layers
  python segmenters_viewer.py --html /path/segmenters_viewer.html

Serve (from the data parent directory):
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765 --bind 0.0.0.0
  → http://localhost:8765/segmenters_viewer.html
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from html import escape
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_FELZ_DIR = _SCRIPT_DIR / "seg_felzenszwalb"
if str(_FELZ_DIR) not in sys.path:
    sys.path.insert(0, str(_FELZ_DIR))

from seg_felzenszwalb_grid import (  # noqa: E402
    MOSAIC_DIR,
    OUTPUT_DIR as FELZ_OUTPUT_DIR,
    _DATA_ROOT,
)
import visualize_seg_felzenszwalb_grid as viz  # noqa: E402

RES_TIERS = viz.RES_TIERS
CAPAS_SUBDIR = viz.CAPAS_SUBDIR

_RF_N_DIR = _SCRIPT_DIR / "seg_felzenszwalb_rf_n"
_RF_N_OUTPUT = Path("/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_n")
_MOSAIC_184_DIR = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")

RF_N_TIF_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_lv(?P<rf_level>\d+)_rfn_s(?P<scale>\d+)_sig(?P<sigma>\d+(?:\.\d+)?)\.tif$"
)
RF_N_CSV_PATTERN = re.compile(
    r"^resumen_(?P<tile>[^_]+)_(?P<year>\d+)_lv(?P<rf_level>\d+)_rfn\.csv$"
)

_SLIC_ROOT = _DATA_ROOT / "seg_slic"
_PIPELINE_A = _SLIC_ROOT / "pipeline_a"

SEGMENTADORES: dict[str, dict] = {
    "felzenszwalb": {
        "label": "Felzenszwalb",
        "output_dir": FELZ_OUTPUT_DIR,
        "color": "#1b6ca8",
    },
    "felzenszwalb_rf_n": {
        "label": "Felzenszwalb RF_N Lv3",
        "output_dir": _RF_N_OUTPUT,
        "color": "#7c3aed",
        "rf_n": True,
        "rf_level": 3,
        "mosaic_184_dir": _MOSAIC_184_DIR,
    },
    "slic": {
        "label": "SLIC",
        "output_dir": _PIPELINE_A,
        "color": "#059669",
        "incluir_rag": True,
    },
    "slic_min": {
        "label": "SLIC + min150",
        "output_dir": _PIPELINE_A / "size_filter",
        "color": "#065f46",
        "incluir_rag": True,
        "rag_min_px": 150,
    },
    "slic_hier": {
        "label": "SLIC + RAG hier",
        "output_dir": _PIPELINE_A / "rag_hierarchical",
        "color": "#047857",
        "incluir_rag": True,
        "rag_hierarchical": True,
        "rag_suffix": "hier_p",
    },
    "slic_pipeline_b": {
        "label": "Pipeline B",
        "output_dir": _DATA_ROOT / "seg_slic" / "pipeline_b",
        "color": "#0d9488",
        "incluir_rag": True,
        "pipeline_b": True,
        "rag_hierarchical": True,
        "rag_suffix": "hier_p",
        "rag_hier_min_px": 150,
    },
}

DEFAULT_HTML = _DATA_ROOT / "segmenters_viewer.html"


def buscar_resumen_rf_n(output_dir: Path, rf_level: int = 1) -> Path | None:
    candidatos = sorted(
        p for p in output_dir.glob(f"resumen_*_lv{rf_level}_rfn.csv") if "_idx" not in p.name
    )
    if candidatos:
        return candidatos[0]
    idx_files = sorted(output_dir.glob(f"resumen_*_lv{rf_level}_rfn_idx*.csv"))
    if idx_files:
        if len(idx_files) > 1:
            print(f"[INFO] Varios CSV RF_N parciales; se usa: {idx_files[0].name}")
        return idx_files[0]
    return None


def cargar_resumen_rf_n(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = RF_N_CSV_PATTERN.match(ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")
    elif m := re.match(r"^resumen_(?P<tile>[^_]+)_(?P<year>\d+)_lv\d+_rfn_idx\d+\.csv$", ruta_csv.name):
        tile = m.group("tile")
        year = m.group("year")

    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": int(float(row["min_size"])),
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "rf_level": int(float(row.get("rf_level", 1))),
                    "n_bands": int(float(row.get("n_bands", 0))),
                }
            )

    filas.sort(key=lambda r: (r["scale"], r["sigma"]))
    return filas, tile, year


def descubrir_combinaciones_rf_n(
    output_dir: Path,
    html_dir: Path,
    rf_level: int = 1,
) -> list[dict]:
    entradas: list[dict] = []
    capas_dir = output_dir / CAPAS_SUBDIR
    patron = f"seg_*_lv{rf_level}_rfn_s*_sig*.tif"
    for ruta_tif in sorted(output_dir.glob(patron)):
        match = RF_N_TIF_PATTERN.match(ruta_tif.name)
        if not match:
            continue
        scale = int(match.group("scale"))
        sigma = float(match.group("sigma"))
        clave = viz.clave_desde_params(scale, sigma)
        base = ruta_tif.stem
        ruta_png = ruta_tif.with_suffix(".png")
        entradas.append(
            {
                "tile": match.group("tile"),
                "year": match.group("year"),
                "scale": scale,
                "sigma": sigma,
                "clave": clave,
                "tif": viz.ruta_publica(html_dir, ruta_tif),
                "png": viz.ruta_publica(html_dir, ruta_png) if ruta_png.is_file() else "",
                "overlay_tiers": viz.descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
                "boundaries_tiers": viz.descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
            }
        )
    if entradas:
        return entradas

    for ruta_png in sorted(output_dir.glob(patron.replace(".tif", ".png"))):
        match = RF_N_TIF_PATTERN.match(ruta_png.with_suffix(".tif").name)
        if not match:
            continue
        scale = int(match.group("scale"))
        sigma = float(match.group("sigma"))
        clave = viz.clave_desde_params(scale, sigma)
        entradas.append(
            {
                "tile": match.group("tile"),
                "year": match.group("year"),
                "scale": scale,
                "sigma": sigma,
                "clave": clave,
                "tif": viz.ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                "png": viz.ruta_publica(html_dir, ruta_png),
                "overlay_tiers": {},
                "boundaries_tiers": {},
            }
        )
    return entradas


def exportar_capas_rf_n(
    output_dir: Path,
    mosaic_184_dir: Path,
    tile: str,
    year: str,
    rf_level: int = 1,
) -> dict[str, str] | None:
    """Exporta capas RGB desde mosaico 184B y overlays de segmentos RF_N."""
    try:
        import numpy as np
        import rasterio
        from seg_felzenszwalb_grid import (
            NODATA,
            componer_rgb,
            construir_mascara_nodata,
            contornos_rgba_desde_labels,
            guardar_rgba_png,
            overlay_rgba_desde_labels,
            reducir_para_quicklook,
            resolver_nodata,
        )
        from PIL import Image
    except ImportError as exc:
        print(f"[ADVERTENCIA] No se exportan capas RF_N (faltan dependencias): {exc}")
        return None

    if str(_RF_N_DIR) not in sys.path:
        sys.path.insert(0, str(_RF_N_DIR))
    from rf_selected_bands import resolver_rgb_desde_descriptions  # noqa: E402
    from seg_felzenszwalb_rf_n_grid import localizar_mosaico_184  # noqa: E402

    capas_dir = output_dir / CAPAS_SUBDIR
    capas_dir.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = localizar_mosaico_184(mosaic_184_dir, tile, int(year))
    mosaic_stem = f"mosaic_{tile}_{year}_rgb"
    mosaic_tiers: dict[str, str] = {}

    print(f"[INFO] Exportando capas RF_N ({', '.join(str(t) for t in RES_TIERS)} px) → {capas_dir}")

    with rasterio.open(ruta_mosaico) as src:
        descriptions = list(src.descriptions or [])
        if len(descriptions) != src.count:
            descriptions = [descriptions[i] if i < len(descriptions) else "" for i in range(src.count)]
        rgb_positions = resolver_rgb_desde_descriptions(descriptions)
        rgb_stack = np.stack(
            [src.read(pos + 1).astype(np.float32) for pos in rgb_positions],
            axis=-1,
        )
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(rgb_stack, nodata_valor)
        rgb = componer_rgb(rgb_stack, [0, 1, 2], validos)
        rgb = np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0)

    labels_vacio = np.zeros(validos.shape, dtype=np.int32)
    for lado in RES_TIERS:
        rgb_q, _, _ = reducir_para_quicklook(rgb, labels_vacio, validos, lado)
        mosaic_uint8 = (np.clip(rgb_q, 0.0, 1.0) * 255).astype(np.uint8)
        fname = f"{mosaic_stem}_l{lado}.png"
        Image.fromarray(mosaic_uint8, mode="RGB").save(capas_dir / fname)
        mosaic_tiers[str(lado)] = f"{CAPAS_SUBDIR}/{fname}"
        print(f"  → {fname} ({rgb_q.shape[1]}×{rgb_q.shape[0]})")

    patron = f"seg_*_lv{rf_level}_rfn_s*_sig*.tif"
    for ruta_tif in sorted(output_dir.glob(patron)):
        if not RF_N_TIF_PATTERN.match(ruta_tif.name):
            continue
        with rasterio.open(ruta_tif) as seg:
            labels = seg.read(1).astype(np.int32)
        if labels.shape != validos.shape:
            print(
                f"[ERROR] Shape distinta RF_N: {ruta_tif.name} {labels.shape} vs mosaico {validos.shape}"
            )
            sys.exit(1)
        base = ruta_tif.stem
        for lado in RES_TIERS:
            rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos, lado)
            overlay = overlay_rgba_desde_labels(labels_q, validos_q)
            bordes = contornos_rgba_desde_labels(
                labels_q, validos_q, labels_ref=labels, validos_ref=validos
            )
            guardar_rgba_png(capas_dir / f"{base}_overlay_l{lado}.png", overlay)
            guardar_rgba_png(capas_dir / f"{base}_boundaries_l{lado}.png", bordes)
        print(f"  → {base}_overlay/boundaries_l*.png")

    return mosaic_tiers


def stats_desde_filas(filas: list[dict]) -> dict:
    if not filas:
        return {
            "n_combinaciones": 0,
            "n_segmentos_min": 0,
            "n_segmentos_max": 0,
            "tam_medio_ha_min": 0.0,
            "tam_medio_ha_max": 0.0,
        }
    return {
        "n_combinaciones": len(filas),
        "n_segmentos_min": min(f["n_segmentos"] for f in filas),
        "n_segmentos_max": max(f["n_segmentos"] for f in filas),
        "tam_medio_ha_min": min(f["tam_medio_ha"] for f in filas),
        "tam_medio_ha_max": max(f["tam_medio_ha"] for f in filas),
    }


def filas_base(filas: list[dict]) -> list[dict]:
    return [f for f in filas if f.get("rag_percentil") in (None, "") and not f.get("rag_min_size_px")]


def buscar_resumen_pipeline_b(output_dir: Path) -> Path | None:
    candidatos = sorted(
        p for p in output_dir.glob("resumen_pipeline_b_*.csv") if "_idx" not in p.name
    )
    if not candidatos:
        return None
    if len(candidatos) > 1:
        print(f"[INFO] Varios CSV pipeline_b; se usa: {candidatos[0].name}")
    return candidatos[0]


def cargar_resumen_pipeline_b(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = re.match(r"^resumen_pipeline_b_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")

    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rag_p_raw = (row.get("rag_percentil") or "").strip()
            rag_percentil = int(float(rag_p_raw)) if rag_p_raw else None
            rag_abs_raw = (row.get("rag_thresh_abs") or "").strip()
            rag_thresh_abs = float(rag_abs_raw) if rag_abs_raw else None
            min_px = int(float(row.get("second_pass_min_px", 150)))
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": min_px,
                    "n_segmentos": int(float(row["n_regiones_final"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "rag_mode": "hierarchical",
                    "rag_thresh_mode": "percentile",
                    "rag_percentil": rag_percentil,
                    "rag_thresh_abs": rag_thresh_abs,
                    "rag_thresh": rag_thresh_abs,
                    "rag_min_size_px": min_px,
                    "n_regiones_post_rag": int(float(row.get("n_regiones_post_rag", 0))),
                    "n_regiones_final": int(float(row["n_regiones_final"])),
                }
            )

    filas.sort(
        key=lambda r: (
            r["scale"],
            r["sigma"],
            r["rag_percentil"] is not None,
            r["rag_percentil"] or 0,
        )
    )
    return filas, tile, year


def buscar_resumen_hier(output_dir: Path) -> Path | None:
    candidatos = sorted(
        p for p in output_dir.glob("resumen_hier_*.csv") if "_idx" not in p.name
    )
    if not candidatos:
        return None
    if len(candidatos) > 1:
        print(f"[INFO] Varios CSV hierarchical; se usa: {candidatos[0].name}")
    return candidatos[0]


def cargar_resumen_hier(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = re.match(r"^resumen_hier_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")

    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rag_p_raw = (row.get("rag_percentil") or "").strip()
            rag_percentil = int(float(rag_p_raw)) if rag_p_raw else None
            rag_abs_raw = (row.get("rag_thresh_abs") or "").strip()
            rag_thresh_abs = float(rag_abs_raw) if rag_abs_raw else None
            n_seg = row.get("n_regiones_fusionadas") or row["n_segmentos"]
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": 20,
                    "n_segmentos": int(float(n_seg)),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "rag_mode": (row.get("rag_mode") or "hierarchical").strip(),
                    "rag_thresh_mode": (row.get("rag_thresh_mode") or "").strip(),
                    "rag_percentil": rag_percentil,
                    "rag_thresh_abs": rag_thresh_abs,
                    "rag_thresh": rag_thresh_abs,
                }
            )

    filas.sort(
        key=lambda r: (
            r["scale"],
            r["sigma"],
            r["rag_percentil"] is not None,
            r["rag_percentil"] or 0,
        )
    )
    return filas, tile, year


def buscar_resumen_size_filter(output_dir: Path) -> Path | None:
    candidatos = sorted(
        p for p in output_dir.glob("resumen_size_filter_*.csv") if "_idx" not in p.name
    )
    if not candidatos:
        return None
    if len(candidatos) > 1:
        print(f"[INFO] Varios CSV size_filter; se usa: {candidatos[0].name}")
    return candidatos[0]


def cargar_resumen_size_filter(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = re.match(r"^resumen_size_filter_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$", ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")

    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rag_p_raw = (row.get("rag_percentil") or "").strip()
            rag_percentil = int(float(rag_p_raw)) if rag_p_raw else None
            min_px = int(float(row["rag_min_size_px"]))
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": min_px,
                    "n_segmentos": int(float(row["n_regiones_post_filtro"])),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "rag_mode": "",
                    "rag_thresh_mode": "",
                    "rag_percentil": rag_percentil,
                    "rag_thresh_abs": None,
                    "rag_thresh": None,
                    "rag_min_size_px": min_px,
                    "n_regiones_pre_filtro": int(float(row.get("n_regiones_pre_filtro", 0))),
                    "n_regiones_post_filtro": int(float(row["n_regiones_post_filtro"])),
                }
            )

    filas.sort(
        key=lambda r: (
            r["scale"],
            r["sigma"],
            r["rag_percentil"] is not None,
            r["rag_percentil"] or 0,
        )
    )
    return filas, tile, year


def rag_percentiles_desde_filas(filas: list[dict]) -> list[int]:
    return sorted({int(f["rag_percentil"]) for f in filas if f.get("rag_percentil") not in (None, "")})


def construir_tabla_html_seg(filas: list[dict], seg_id: str, incluir_rag: bool = False) -> str:
    columnas = [
        ("scale", "scale"),
        ("sigma", "σ"),
        ("min_size", "min_size"),
    ]
    if incluir_rag:
        columnas.append(("rag_percentil", "RAG p"))
        columnas.append(("rag_thresh_abs", "thr abs"))
    columnas.extend(
        [
            ("n_segmentos", "n segmentos"),
            ("tam_medio_px", "tam. medio (px)"),
            ("tam_mediano_px", "tam. mediano (px)"),
            ("tam_min_px", "tam. min (px)"),
            ("tam_max_px", "tam. max (px)"),
            ("tam_medio_ha", "tam. medio (ha)"),
        ]
    )
    thead = "".join(f"<th>{escape(titulo)}</th>" for _, titulo in columnas)
    cuerpo: list[str] = []
    for fila in filas:
        celdas: list[str] = []
        for clave, _ in columnas:
            valor = fila.get(clave, "")
            if clave == "rag_percentil":
                texto = "—" if valor in (None, "") else str(int(valor))
            elif clave == "rag_thresh_abs":
                texto = "—" if valor in (None, "") else f"{float(valor):.6f}"
            elif clave in {"scale", "min_size", "n_segmentos", "tam_min_px", "tam_max_px"}:
                texto = viz.fmt_num(int(valor), 0)
            elif clave == "sigma":
                texto = f"{valor:g}"
            else:
                texto = viz.fmt_num(float(valor))
            celdas.append(f"<td>{texto}</td>")
        clave = viz.fila_a_clave(fila)
        rag_attr = "" if fila.get("rag_percentil") in (None, "") else str(int(fila["rag_percentil"]))
        cuerpo.append(
            f'<tr data-key="{escape(clave)}" data-seg="{escape(seg_id)}" '
            f'data-rag="{escape(rag_attr)}" class="fila-resumen">'
            + "".join(celdas)
            + "</tr>"
        )
    return (
        f"<table class='data resumen-table' id='tabla-{escape(seg_id)}'>"
        f"<thead><tr>{thead}</tr></thead><tbody>{''.join(cuerpo)}</tbody></table>"
    )


def construir_matriz_html_seg(
    combinaciones: list[dict],
    scales: list[int],
    sigmas: list[float],
    seg_id: str,
    incluir_rag: bool = False,
) -> str:
    thumb_por_clave: dict[str, str | None] = {}
    for c in combinaciones:
        tiers = c.get("overlay_tiers") or {}
        thumb = tiers.get("1024") or next(iter(tiers.values()), None) or c.get("png")
        thumb_por_clave[c["clave"]] = thumb
    celdas: list[str] = []
    for sigma in sigmas:
        celdas.append(f"<div class='matrix-label row-label'>σ={sigma:g}</div>")
        for scale in scales:
            clave = viz.clave_desde_params(scale, sigma)
            thumb = thumb_por_clave.get(clave)
            if thumb or incluir_rag:
                titulo = f"s={scale}, σ={sigma:g}"
                img_src = escape(thumb) if thumb else ""
                img_tag = (
                    f"<img src='{img_src}' alt='{escape(titulo)}' loading='lazy'>"
                    if thumb
                    else "<div class='matrix-placeholder'>—</div>"
                )
                celdas.append(
                    f"<button type='button' class='matrix-cell' data-key='{escape(clave)}' "
                    f"data-scale='{scale}' data-sigma='{sigma:g}' "
                    f"data-seg='{escape(seg_id)}' title='{escape(titulo)}'>"
                    f"{img_tag}"
                    f"<span>{escape(titulo)}</span></button>"
                )
            else:
                celdas.append("<div class='matrix-cell empty'>—</div>")

    encabezados = "".join(f"<div class='matrix-label col-label'>s={s}</div>" for s in scales)
    return (
        f"<div class='matrix-grid' id='matriz-{escape(seg_id)}' style='--cols:{len(scales)}'>"
        f"<div></div>{encabezados}{''.join(celdas)}</div>"
    )


def cargar_segmentador(
    seg_id: str,
    config: dict,
    html_dir: Path,
    mosaic_dir: Path,
    skip_layers: bool,
    mosaic_tiers_ref: dict[str, str] | None,
) -> tuple[dict, dict[str, str] | None]:
    """Carga CSV, combinaciones y opcionalmente exporta capas para un segmentador."""
    output_dir = Path(config["output_dir"]).resolve()
    if not output_dir.is_dir():
        print(f"[ERROR] OUTPUT_DIR no existe ({seg_id}): {output_dir}")
        sys.exit(1)

    rag_min_px = config.get("rag_min_px")
    rag_hier_min_px = config.get("rag_hier_min_px")
    rag_hierarchical = config.get("rag_hierarchical", False)
    pipeline_b = config.get("pipeline_b", False)
    rf_n = config.get("rf_n", False)
    rf_level = int(config.get("rf_level", 1))

    if rf_n:
        ruta_csv = buscar_resumen_rf_n(output_dir, rf_level)
        if ruta_csv is None:
            print(f"[ERROR] No se encontró resumen RF_N en {output_dir} ({seg_id})")
            sys.exit(1)
        filas, tile, year = cargar_resumen_rf_n(ruta_csv)
    elif pipeline_b:
        ruta_csv = buscar_resumen_pipeline_b(output_dir)
        if ruta_csv is None:
            print(f"[ADVERTENCIA] Sin resumen_pipeline_b_*.csv en {output_dir} ({seg_id})")
            filas, tile, year = [], "", ""
        else:
            filas, tile, year = cargar_resumen_pipeline_b(ruta_csv)
    elif rag_hierarchical and rag_hier_min_px is None:
        ruta_csv = buscar_resumen_hier(output_dir)
        if ruta_csv is None:
            print(f"[ERROR] No se encontró resumen_hier_*.csv en {output_dir} ({seg_id})")
            sys.exit(1)
        filas, tile, year = cargar_resumen_hier(ruta_csv)
    elif rag_min_px is not None:
        ruta_csv = buscar_resumen_size_filter(output_dir)
        if ruta_csv is None:
            print(f"[ERROR] No se encontró resumen_size_filter_*.csv en {output_dir} ({seg_id})")
            sys.exit(1)
        filas, tile, year = cargar_resumen_size_filter(ruta_csv)
    else:
        ruta_csv = viz.buscar_resumen(output_dir)
        if ruta_csv is None:
            print(f"[ERROR] No se encontró resumen_*.csv en {output_dir} ({seg_id})")
            sys.exit(1)
        filas, tile, year = viz.cargar_resumen(ruta_csv)
    if not filas and not pipeline_b:
        print(f"[ERROR] CSV vacío ({seg_id}): {ruta_csv}")
        sys.exit(1)

    capas_dir = output_dir / CAPAS_SUBDIR
    mosaic_tiers: dict[str, str] = {}

    if not skip_layers:
        print(f"[INFO] Exportando capas {config['label']} → {capas_dir}")
        if rf_n:
            rel_tiers = exportar_capas_rf_n(
                output_dir,
                Path(config.get("mosaic_184_dir", _MOSAIC_184_DIR)),
                tile,
                year,
                rf_level=rf_level,
            )
        else:
            rel_tiers = viz.exportar_capas(
                output_dir,
                mosaic_dir,
                tile,
                year,
                incluir_rag=config.get("incluir_rag", False),
                rag_min_px=rag_min_px,
                rag_hierarchical=rag_hierarchical and rag_hier_min_px is None,
                rag_hier_min_px=rag_hier_min_px,
            )
        if rel_tiers:
            mosaic_tiers = {
                k: viz.ruta_publica(html_dir, output_dir / v) for k, v in rel_tiers.items()
            }
    else:
        if mosaic_tiers_ref:
            mosaic_tiers = dict(mosaic_tiers_ref)
        else:
            mosaic_tiers = viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)
        if mosaic_tiers:
            print(f"[INFO] Mosaico multi-res ({seg_id}): {', '.join(mosaic_tiers.keys())} px")

    incluir_rag = config.get("incluir_rag", False)
    if rf_n:
        combinaciones = descubrir_combinaciones_rf_n(output_dir, html_dir, rf_level=rf_level)
    else:
        combinaciones = viz.descubrir_combinaciones(
            output_dir,
            html_dir,
            incluir_rag=incluir_rag,
            rag_min_px=rag_min_px,
            rag_hierarchical=rag_hierarchical and rag_hier_min_px is None,
            rag_hier_min_px=rag_hier_min_px,
        )
    if not combinaciones:
        print(f"[ADVERTENCIA] Sin TIF/PNG seg_* en {output_dir} ({seg_id})")

    capas_por_clave = {c["clave"]: c for c in combinaciones}
    if (rag_min_px is not None or rag_hier_min_px is not None or pipeline_b) and len(
        filas
    ) < len(combinaciones):
        origen = "pipeline_b" if pipeline_b else ("hierarchical" if rag_hier_min_px else "size_filter")
        print(
            f"[ADVERTENCIA] CSV {origen} ({len(filas)} filas) < TIF ({len(combinaciones)}); "
            "se complementan filas desde archivos"
        )
        filas_por_clave = {viz.fila_a_clave(f): f for f in filas}
        for c in combinaciones:
            if c["clave"] in filas_por_clave:
                continue
            filas.append(
                {
                    "scale": c["scale"],
                    "sigma": c["sigma"],
                    "min_size": rag_hier_min_px or rag_min_px or 150,
                    "n_segmentos": 0,
                    "tam_medio_px": 0.0,
                    "tam_mediano_px": 0.0,
                    "tam_min_px": 0,
                    "tam_max_px": 0,
                    "tam_medio_ha": 0.0,
                    "rag_mode": c.get("rag_mode", "hierarchical" if rag_hierarchical else ""),
                    "rag_thresh_mode": "",
                    "rag_percentil": c.get("rag_percentil"),
                    "rag_thresh_abs": None,
                    "rag_thresh": None,
                    "rag_min_size_px": c.get("rag_min_size_px")
                    or (rag_hier_min_px if rag_hier_min_px else rag_min_px),
                }
            )
        filas.sort(
            key=lambda r: (
                r["scale"],
                r["sigma"],
                r["rag_percentil"] is not None,
                r["rag_percentil"] or 0,
            )
        )

    if not tile and combinaciones:
        tile = str(combinaciones[0].get("tile", ""))
        year = str(combinaciones[0].get("year", ""))

    rag_percentiles = rag_percentiles_desde_filas(filas) if incluir_rag else []
    datos = {
        "label": config["label"],
        "color": config["color"],
        "output_dir": str(output_dir),
        "filas": filas,
        "combinaciones": combinaciones,
        "capas_por_clave": capas_por_clave,
        "stats": stats_desde_filas(
            filas
            if rag_hierarchical or pipeline_b or not incluir_rag
            else filas_base(filas)
        ),
        "incluir_rag": incluir_rag,
        "rag_percentiles": rag_percentiles,
        "rag_min_px": rag_min_px,
        "rag_hierarchical": rag_hierarchical,
        "rag_hier_min_px": rag_hier_min_px,
        "rag_suffix": config.get("rag_suffix"),
        "pipeline_b": pipeline_b,
        "tile": tile,
        "year": year,
        "mosaic_tiers": mosaic_tiers,
    }
    return datos, mosaic_tiers or None


def generar_html(
    html_dir: Path,
    segmentadores: dict[str, dict],
    mosaic_tiers: dict[str, str],
    tile: str,
    year: str,
) -> str:
    seg_ids = list(segmentadores.keys())
    todas_filas = [f for d in segmentadores.values() for f in d["filas"]]
    scales = sorted({f["scale"] for f in todas_filas})
    sigmas = sorted({f["sigma"] for f in todas_filas})

    payload_segmentadores = {
        seg_id: {
            "label": d["label"],
            "color": d["color"],
            "output_dir": d["output_dir"],
            "filas": d["filas"],
            "capas_por_clave": d["capas_por_clave"],
            "stats": d["stats"],
            "incluir_rag": d.get("incluir_rag", False),
            "rag_percentiles": d.get("rag_percentiles", []),
            "rag_min_px": d.get("rag_min_px"),
            "rag_hierarchical": d.get("rag_hierarchical", False),
            "rag_suffix": d.get("rag_suffix"),
            "rag_hier_min_px": d.get("rag_hier_min_px"),
            "pipeline_b": d.get("pipeline_b", False),
            "mosaic_tiers": d.get("mosaic_tiers", {}),
        }
        for seg_id, d in segmentadores.items()
    }

    payload = {
        "segmenters": payload_segmentadores,
        "seg_ids": seg_ids,
        "mosaic_tiers": mosaic_tiers,
        "res_tiers": RES_TIERS,
        "scales": scales,
        "sigmas": sigmas,
        "scales_by_seg": {
            seg_id: sorted({f["scale"] for f in d["filas"]}) for seg_id, d in segmentadores.items()
        },
        "sigmas_by_seg": {
            seg_id: sorted({f["sigma"] for f in d["filas"]}) for seg_id, d in segmentadores.items()
        },
        "tile": tile,
        "year": year,
    }

    tiene_capas = bool(mosaic_tiers) and any(
        c.get("overlay_tiers") for d in segmentadores.values() for c in d["combinaciones"]
    )

    titulo = f"Segmenters — {tile} {year}" if tile and year else "Segmenters grid"
    kpis_html = ""
    for seg_id in seg_ids:
        st = segmentadores[seg_id]["stats"]
        lbl = segmentadores[seg_id]["label"]
        kpis_html += f"""
    <div class="kpi kpi-seg" style="border-left:4px solid {segmentadores[seg_id]['color']}">
      <div class="label">{escape(lbl)} · combinations</div>
      <div class="value">{st['n_combinaciones']}</div>
    </div>
    <div class="kpi kpi-seg" style="border-left:4px solid {segmentadores[seg_id]['color']}">
      <div class="label">{escape(lbl)} · segments (min–max)</div>
      <div class="value">{st['n_segmentos_min']:,} – {st['n_segmentos_max']:,}</div>
    </div>"""

    rag_opts = '<option value="">SLIC (superpíxeles)</option>'
    rag_pcts: set[int] = set()
    for sid in ("slic", "slic_min", "slic_hier", "slic_pipeline_b"):
        for p in segmentadores.get(sid, {}).get("rag_percentiles", []):
            rag_pcts.add(int(p))
    for p in sorted(rag_pcts):
        rag_opts += f'<option value="{p}">RAG p{p}</option>'

    heatmaps_html = "".join(
        f'<div id="chart-heatmap-{escape(seg_id)}" class="chart" style="min-height:320px;"></div>'
        for seg_id in seg_ids
    )

    matrices_html = ""
    tablas_html = ""
    for seg_id in seg_ids:
        d = segmentadores[seg_id]
        incluir_rag = d.get("incluir_rag", False)
        matrices_html += f"""
    <div class="seg-block">
      <h3 style="color:{d['color']}">{escape(d['label'])}</h3>
      {construir_matriz_html_seg(d["combinaciones"], scales, sigmas, seg_id, incluir_rag=incluir_rag)}
    </div>"""
        tablas_html += f"""
    <div class="seg-block">
      <h3 style="color:{d['color']}">{escape(d['label'])}</h3>
      {construir_tabla_html_seg(d["filas"], seg_id, incluir_rag=incluir_rag)}
    </div>"""

    opts_seg = "".join(
        f'<option value="{escape(sid)}">{escape(segmentadores[sid]["label"])}</option>'
        for sid in seg_ids
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{
  --bg: #f4f6f8; --text: #1f2933; --muted: #627d98; --line: #d9e2ec;
  --hero-a: #0f4c75; --hero-b: #3282b8; --card: #fff;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }}
.wrap {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
.hero {{ background: linear-gradient(135deg, var(--hero-a), #1b6ca8 50%, #059669); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px; }}
.hero h1 {{ margin: 0 0 8px; font-size: 1.8rem; }}
.hero p {{ margin: 0; opacity: 0.92; font-size: 0.95rem; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.kpi {{ background: var(--card); border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.kpi .label {{ font-size: 0.85rem; color: #52606d; margin-bottom: 6px; }}
.kpi .value {{ font-size: 1.25rem; font-weight: 700; color: #102a43; }}
.section {{ background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.section h2 {{ margin: 0 0 16px; font-size: 1.15rem; color: #243b53; border-bottom: 2px solid var(--line); padding-bottom: 8px; }}
.seg-block {{ margin-bottom: 24px; }}
.seg-block h3 {{ margin: 0 0 12px; font-size: 1rem; }}
.note {{ color: var(--muted); font-size: 0.92rem; margin: 0 0 14px; }}
.grid-2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; }}
.chart {{ min-height: 360px; }}
.controls, .layer-controls {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 16px; }}
.controls label, .layer-controls label {{ display: flex; flex-direction: column; gap: 6px; font-size: 0.88rem; color: #486581; }}
.layer-controls label.row {{ flex-direction: row; align-items: center; gap: 8px; padding: 8px 12px; background: #f0f4f8; border-radius: 8px; border: 1px solid var(--line); }}
.controls select {{ min-width: 120px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; font-size: 0.95rem; }}
.controls button {{ padding: 9px 14px; border: 1px solid var(--line); border-radius: 8px; background: #eef4fa; cursor: pointer; font-size: 0.92rem; }}
.controls button.active {{ background: #1b6ca8; color: #fff; border-color: #1b6ca8; }}
.viewer {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
.viewer.compare {{ grid-template-columns: 1fr 1fr; }}
.panel {{ border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: #0b0b0b; }}
.panel header {{ color: #fff; padding: 10px 14px; font-size: 0.92rem; background: #102a43; }}
.panel header.seg-felzenszwalb {{ background: #1b6ca8; }}
.panel header.seg-felzenszwalb_rf_n {{ background: #7c3aed; }}
.panel header.seg-slic {{ background: #059669; }}
.panel header.seg-slic_hier {{ background: #047857; }}
.panel header.seg-slic_min {{ background: #065f46; }}
.panel header.seg-slic_pipeline_b {{ background: #0d9488; }}
.zoom-bar {{ display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #edf2f7; border-bottom: 1px solid var(--line); flex-wrap: wrap; }}
.zoom-btn {{ min-width: 34px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: #fff; cursor: pointer; font-size: 1rem; line-height: 1.2; }}
.zoom-label {{ font-size: 0.85rem; color: #334e68; min-width: 48px; font-weight: 600; }}
.zoom-hint {{ font-size: 0.78rem; color: #627d98; margin-left: auto; }}
.zoom-viewport {{ position: relative; width: 100%; aspect-ratio: 1; overflow: hidden; background: #111; cursor: grab; touch-action: none; }}
.zoom-viewport.dragging {{ cursor: grabbing; }}
.zoom-stage {{ transform-origin: 0 0; will-change: transform; position: relative; }}
.layer-stack {{ position: relative; width: 100%; height: 100%; background: #111; }}
.layer-stack .layer {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; image-rendering: auto; }}
.layer-stack .layer.hidden-layer {{ visibility: hidden; opacity: 0; }}
.layer-meta {{ padding: 8px 14px; background: #f7fafc; font-size: 0.82rem; color: #486581; border-top: 1px solid var(--line); }}
.layer-meta a {{ color: #1b6ca8; }}
.stats-inline {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; padding: 12px; background: #fff; }}
.stat-chip {{ background: #f0f4f8; border-radius: 8px; padding: 10px 12px; }}
.stat-chip .k {{ font-size: 0.78rem; color: #627d98; }}
.stat-chip .v {{ font-size: 1rem; font-weight: 600; color: #102a43; }}
table.data {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
table.data th, table.data td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: right; }}
table.data thead th {{ background: #e6f0f8; color: #102a43; }}
table.data tbody tr {{ cursor: pointer; }}
table.data tbody tr:hover {{ background: #f8fbff; }}
table.data tbody tr.selected {{ background: #dbeafe; }}
.matrix-grid {{ display: grid; grid-template-columns: 72px repeat(var(--cols), minmax(120px, 1fr)); gap: 10px; }}
.matrix-label {{ display: flex; align-items: center; justify-content: center; font-size: 0.85rem; color: #486581; font-weight: 600; }}
.matrix-cell {{ border: 2px solid transparent; border-radius: 10px; padding: 0; background: #fff; cursor: pointer; overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.08); }}
.matrix-cell img {{ width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }}
.matrix-placeholder {{ width: 100%; aspect-ratio: 1; display: flex; align-items: center; justify-content: center; background: #edf2f7; color: #9fb3c8; }}
.matrix-cell span {{ display: block; padding: 6px 8px; font-size: 0.78rem; text-align: center; color: #334e68; background: #f7fafc; }}
.matrix-cell.selected {{ border-color: #1b6ca8; }}
.matrix-cell.empty {{ display: flex; align-items: center; justify-content: center; color: #9fb3c8; background: #f0f4f8; min-height: 120px; }}
.hidden {{ display: none !important; }}
@media (max-width: 900px) {{ .viewer.compare {{ grid-template-columns: 1fr; }} .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>{escape(titulo)}</h1>
    <p>Felzenszwalb vs Felzenszwalb RF_N vs SLIC vs Pipeline B · tile {escape(tile)} {escape(year)}</p>
  </header>

  <div class="kpis">{kpis_html}
    <div class="kpi"><div class="label">Scale</div><div class="value">{', '.join(str(s) for s in scales)}</div></div>
    <div class="kpi"><div class="label">Sigma</div><div class="value">{', '.join(f'{s:g}' for s in sigmas)}</div></div>
  </div>

  <section class="section">
    <h2>Layer explorer</h2>
    <p class="note">Compare segmenters with the same scale/σ parameters. Synchronized zoom in compare mode.</p>
    <div class="layer-controls">
      <label class="row"><input type="checkbox" id="chk-mosaic" checked> RGB mosaic</label>
      <label class="row"><input type="checkbox" id="chk-seg" checked> Segments (TIF)</label>
      <label class="row"><input type="checkbox" id="chk-bnd" checked> Boundaries</label>
      <label class="row"><input type="checkbox" id="chk-quicklook"> Quick-look PNG</label>
      <label>Segment opacity
        <input type="range" id="opacity-seg" min="0" max="100" value="62">
      </label>
    </div>
    <div class="controls">
      <label>A segmenter <select id="sel-seg-a">{opts_seg}</select></label>
      <label>A scale <select id="sel-scale-a"></select></label>
      <label>A sigma <select id="sel-sigma-a"></select></label>
      <label id="lbl-rag-a" class="hidden">A · SLIC RAG view <select id="sel-rag-a">{rag_opts}</select></label>
      <label id="lbl-seg-b" class="hidden">B segmenter <select id="sel-seg-b">{opts_seg}</select></label>
      <label id="lbl-scale-b" class="hidden">B scale <select id="sel-scale-b"></select></label>
      <label id="lbl-sigma-b" class="hidden">B sigma <select id="sel-sigma-b"></select></label>
      <label id="lbl-rag-b" class="hidden">B · SLIC RAG view <select id="sel-rag-b">{rag_opts}</select></label>
      <button type="button" id="btn-compare">Compare segmenters</button>
    </div>
    <div class="viewer" id="viewer">
      {viz.panel_capas_html("a")}
      {viz.panel_capas_html("b", oculto=True)}
    </div>
  </section>

  <section class="section">
    <h2>Scale × sigma matrix</h2>
    <div class="grid-2">{matrices_html}</div>
  </section>

  <section class="section">
    <h2>Comparative metrics</h2>
    <div class="grid-2">
      <div id="chart-segmentos" class="chart"></div>
      <div id="chart-tamano" class="chart"></div>
    </div>
    <div class="grid-2" style="margin-top:16px">
      {heatmaps_html}
    </div>
  </section>

  <section class="section">
    <h2>Summary table</h2>
    {tablas_html}
  </section>
</div>

<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const TIENE_CAPAS = {json.dumps(tiene_capas)};
const RES_TIERS = DATA.res_tiers || [1024, 2048, 4096];
const PANEL = {{
  a: {{ clave: null, segId: DATA.seg_ids[0], tier: RES_TIERS[0], userZoom: 1, panX: 0, panY: 0, fit: 1, imgW: 100, imgH: 100, loading: false, contentKey: '' }},
  b: {{ clave: null, segId: DATA.seg_ids[Math.min(1, DATA.seg_ids.length - 1)], tier: RES_TIERS[0], userZoom: 1, panX: 0, panY: 0, fit: 1, imgW: 100, imgH: 100, loading: false, contentKey: '' }},
}};
let SYNC_LOCK = false;

function segData(segId) {{ return DATA.segmenters[segId]; }}
function segActivo(sufijo) {{ return document.getElementById(`sel-seg-${{sufijo}}`).value; }}

function isCompareMode() {{
  return document.getElementById('viewer').classList.contains('compare');
}}

function peerPanel(sufijo) {{ return sufijo === 'a' ? 'b' : 'a'; }}

function getViewState(sufijo) {{
  const st = PANEL[sufijo];
  const center = getViewCenter(sufijo);
  return {{ userZoom: st.userZoom, cx: center.cx, cy: center.cy, tier: st.tier }};
}}

async function applyViewState(sufijo, view) {{
  const st = PANEL[sufijo];
  recalcFit(sufijo);
  const needed = tierForZoom(view.userZoom);
  if (needed > st.tier && tierSrc(mosaicTiersFor(st.segId), needed) && !st.loading) {{
    await loadPanelTier(sufijo, needed, true);
  }}
  st.userZoom = view.userZoom;
  if (view.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
  else {{ setViewCenter(sufijo, view.cx, view.cy); }}
  aplicarZoomTransform(sufijo, true);
}}

function recalcFit(sufijo) {{
  const st = PANEL[sufijo];
  const vp = document.getElementById(`viewport-${{sufijo}}`);
  if (!vp || st.imgW <= 0 || st.imgH <= 0) return false;
  const rect = vp.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  st.fit = Math.min(rect.width / st.imgW, rect.height / st.imgH);
  return true;
}}

function syncPeerView(source) {{
  if (SYNC_LOCK || !isCompareMode()) return;
  const peer = peerPanel(source);
  if (document.getElementById(`panel-${{peer}}`).classList.contains('hidden')) return;
  SYNC_LOCK = true;
  applyViewState(peer, getViewState(source)).finally(() => {{ SYNC_LOCK = false; }});
}}

function ragSuffixFromFila(fila, segId) {{
  const p = fila.rag_percentil;
  if (p == null || p === '') return '';
  if (fila.rag_mode === 'hierarchical' || (segData(segId) && segData(segId).rag_suffix === 'hier_p')) {{
    return `_hier_p${{p}}`;
  }}
  return `_ragp${{p}}`;
}}

function claveFila(fila, segId) {{
  let base = `s${{fila.scale}}_sig${{String(fila.sigma).replace('.', '_')}}`;
  const sid = segId || '';
  if (fila.rag_percentil != null && fila.rag_percentil !== '') {{
    base += ragSuffixFromFila(fila, sid);
  }} else if (fila.rag_thresh_abs != null && fila.rag_thresh_abs !== '') {{
    base += `_rag${{String(parseFloat(fila.rag_thresh_abs)).replace('.', '_')}}`;
  }} else if (fila.rag_thresh != null && fila.rag_thresh !== '') {{
    base += `_rag${{String(parseFloat(fila.rag_thresh)).replace('.', '_')}}`;
  }}
  if (fila.rag_min_size_px != null && fila.rag_min_size_px !== '') {{
    base += `_min${{fila.rag_min_size_px}}`;
  }}
  return base;
}}

function segUsaRagSelector(segId) {{
  return segId === 'slic' || segId === 'slic_min' || segId === 'slic_hier' || segId === 'slic_pipeline_b';
}}

function getSlicRagMode(sufijo) {{
  const el = document.getElementById(`sel-rag-${{sufijo}}`);
  if (!el) return '';
  const lbl = document.getElementById(`lbl-rag-${{sufijo}}`);
  if (lbl && lbl.classList.contains('hidden')) return '';
  return el.value;
}}

function filaMatchesRag(fila, ragMode) {{
  const p = fila.rag_percentil;
  if (!ragMode) return p == null || p === '';
  return String(p) === ragMode || parseInt(p, 10) === parseInt(ragMode, 10);
}}

function ragPercentilesSeg(segId) {{
  const d = segData(segId);
  if (!d || !d.rag_percentiles) return [];
  return d.rag_percentiles.map(p => String(p));
}}

function actualizarRagSelect(sufijo, segId) {{
  if (!segUsaRagSelector(segId)) return;
  const el = document.getElementById(`sel-rag-${{sufijo}}`);
  const pcts = ragPercentilesSeg(segId);
  let html = '';
  if (segId === 'slic') {{
    html += '<option value="">SLIC (superpíxeles)</option>';
  }}
  pcts.forEach(p => {{ html += `<option value="${{p}}">RAG p${{p}}</option>`; }});
  const prev = el.value;
  el.innerHTML = html;
  if (segId === 'slic' && (prev === '' || pcts.includes(prev))) {{
    el.value = prev;
  }} else if (pcts.includes(prev)) {{
    el.value = prev;
  }} else if (pcts.length) {{
    el.value = pcts[0];
  }} else {{
    el.value = '';
  }}
}}

function ragModeEfectivo(segId, sufijo) {{
  let ragMode = getSlicRagMode(sufijo || 'a');
  const pcts = ragPercentilesSeg(segId);
  if (segId === 'slic_min' || segId === 'slic_hier' || segId === 'slic_pipeline_b') {{
    if (!ragMode && pcts.length) ragMode = pcts[0];
    else if (ragMode && pcts.length && !pcts.includes(String(ragMode))) ragMode = pcts[0];
  }}
  return ragMode;
}}

function asegurarRagSelect(sufijo, segId) {{
  if (!segUsaRagSelector(segId)) return;
  actualizarRagSelect(sufijo, segId);
}}

function filasParaSeg(segId, sufijo) {{
  const d = segData(segId);
  if (!d) return [];
  if (!d.incluir_rag) return d.filas;
  if (segId === 'slic') {{
    return d.filas.filter(f => filaMatchesRag(f, getSlicRagMode(sufijo || 'a')));
  }}
  return d.filas.filter(f => filaMatchesRag(f, ragModeEfectivo(segId, sufijo)));
}}

function construirClaveIdeal(segId, scale, sigma, sufijo) {{
  const ragMode = ragModeEfectivo(segId, sufijo);
  let clave = `s${{scale}}_sig${{String(sigma).replace('.', '_')}}`;
  if (segUsaRagSelector(segId) && ragMode) {{
    if (segData(segId).rag_suffix === 'hier_p') {{
      clave += `_hier_p${{ragMode}}`;
      if (segData(segId).rag_hier_min_px) clave += `_min${{segData(segId).rag_hier_min_px}}`;
    }} else clave += `_ragp${{ragMode}}`;
  }}
  if (segId === 'slic_min') {{
    const minPx = (segData(segId) && segData(segId).rag_min_px) || 150;
    clave += `_min${{minPx}}`;
  }}
  return clave;
}}

function claveBaseFila(fila) {{
  return `s${{fila.scale}}_sig${{String(fila.sigma).replace('.', '_')}}`;
}}

function resolverClavePanel(segId, scale, sigma, sufijo) {{
  const claveIdeal = segUsaRagSelector(segId)
    ? construirClaveIdeal(segId, scale, sigma, sufijo)
    : `s${{scale}}_sig${{String(sigma).replace('.', '_')}}`;
  if (capaPorClave(claveIdeal, segId)) return claveIdeal;

  const candidatas = segUsaRagSelector(segId)
    ? filasParaSeg(segId, sufijo)
    : (segData(segId) ? segData(segId).filas : []);
  const numScale = Number(scale);
  const numSigma = Number(sigma);
  let fila = candidatas.find(
    f => f.scale === numScale && Math.abs(f.sigma - numSigma) < 1e-9
  );
  if (!fila) fila = candidatas.find(f => Math.abs(f.sigma - numSigma) < 1e-9);
  if (!fila) fila = candidatas[0];
  if (fila) {{
    const clave = segUsaRagSelector(segId) ? claveFila(fila, segId) : claveBaseFila(fila);
    if (capaPorClave(clave, segId)) return clave;
  }}
  return claveIdeal;
}}

function filasVisibles(segId, sufijo) {{
  return filasParaSeg(segId, sufijo);
}}

function claveDesdeParams(segId, scale, sigma, sufijo) {{
  return resolverClavePanel(segId, scale, sigma, sufijo);
}}

function filaDesdeCapa(clave, segId) {{
  const capa = capaPorClave(clave, segId);
  if (!capa) return null;
  const d = segData(segId);
  const fila = d.filas.find(f => claveFila(f, segId) === clave);
  if (fila) return fila;
  return {{
    scale: capa.scale,
    sigma: capa.sigma,
    rag_percentil: capa.rag_percentil,
    rag_min_size_px: capa.rag_min_size_px || (d.rag_min_px || null),
    n_segmentos: 0,
  }};
}}

function updateSlicRagVisibility() {{
  const segA = segActivo('a');
  const segB = segActivo('b');
  const showA = segUsaRagSelector(segA);
  const showB = isCompareMode() && segUsaRagSelector(segB);
  document.getElementById('lbl-rag-a').classList.toggle('hidden', !showA);
  document.getElementById('lbl-rag-b').classList.toggle('hidden', !showB);
  if (showA) actualizarRagSelect('a', segA);
  if (showB) actualizarRagSelect('b', segB);
}}

function capaPorClave(clave, segId) {{
  const d = segData(segId);
  return d && d.capas_por_clave ? d.capas_por_clave[clave] || null : null;
}}

function filaPorClave(clave, segId) {{
  const d = segData(segId);
  if (!d) return null;
  return d.filas.find(f => claveFila(f, segId) === clave) || filaDesdeCapa(clave, segId);
}}

function refreshSlicTable() {{
  const ragMode = getSlicRagMode('a');
  ['slic', 'slic_min', 'slic_hier', 'slic_pipeline_b'].forEach(segId => {{
    document.querySelectorAll(`#tabla-${{segId}} .fila-resumen`).forEach(row => {{
      const rowRag = row.dataset.rag || '';
      const show = (segId === 'slic_min' || segId === 'slic_hier' || segId === 'slic_pipeline_b')
        ? (ragMode ? rowRag === ragMode : false)
        : (!ragMode ? rowRag === '' : rowRag === ragMode);
      row.classList.toggle('hidden', !show);
    }});
  }});
}}

function refreshSlicMatrix() {{
  ['slic', 'slic_min', 'slic_hier', 'slic_pipeline_b'].forEach(segId => {{
    const d = segData(segId);
    if (!d) return;
    const ragMode = getSlicRagMode('a');
    const matrizId = `matriz-${{segId}}`;
    document.querySelectorAll(`#${{matrizId}} button.matrix-cell[data-scale]`).forEach(btn => {{
      const scale = Number(btn.dataset.scale);
      const sigma = Number(btn.dataset.sigma);
      const clave = claveDesdeParams(segId, scale, sigma, 'a');
      const capa = capaPorClave(clave, segId);
      const tiers = capa ? (capa.overlay_tiers || {{}}) : {{}};
      const thumb = tiers['1024'] || (capa && capa.png) || null;
      btn.dataset.key = clave;
      const ragLabel = ragMode
        ? (d.rag_suffix === 'hier_p' ? ` · RAG hier p${{ragMode}}` : ` · RAG p${{ragMode}}`)
        : '';
      const minLabel = (segId === 'slic_min' || segId === 'slic_pipeline_b')
        ? ` · min${{segData(segId).rag_min_px || segData(segId).rag_hier_min_px || 150}}`
        : '';
      btn.title = `s=${{scale}}, σ=${{sigma}}${{ragLabel}}${{minLabel}}`;
      let img = btn.querySelector('img');
      if (thumb) {{
        if (!img) {{
          const placeholder = btn.querySelector('.matrix-placeholder');
          if (placeholder) placeholder.remove();
          img = document.createElement('img');
          img.loading = 'lazy';
          btn.insertBefore(img, btn.querySelector('span'));
        }}
        img.src = thumb;
        img.alt = btn.title;
      }} else if (img) {{
        img.remove();
        if (!btn.querySelector('.matrix-placeholder')) {{
          const ph = document.createElement('div');
          ph.className = 'matrix-placeholder';
          ph.textContent = '—';
          btn.insertBefore(ph, btn.querySelector('span'));
        }}
      }}
    }});
  }});
}}

function onSlicRagChange(sufijo) {{
  if (sufijo === 'a') {{
    refreshSlicTable();
    refreshSlicMatrix();
    renderCharts();
  }}
  const scale = document.getElementById('sel-scale-a').value;
  const sigma = document.getElementById('sel-sigma-a').value;
  if (sufijo === 'a' && segUsaRagSelector(segActivo('a'))) {{
    seleccion(claveDesdeParams(segActivo('a'), scale, sigma, 'a'), segActivo('a'));
  }}
  if (sufijo === 'b' && isCompareMode() && segUsaRagSelector(segActivo('b'))) {{
    seleccionB();
  }}
}}

function fmtInt(n) {{ return new Intl.NumberFormat('es-CL').format(n); }}
function fmtFloat(n, d=1) {{
  return new Intl.NumberFormat('es-CL', {{ minimumFractionDigits: d, maximumFractionDigits: d }}).format(n);
}}

function llenarSelect(id, valores, formato=(v)=>v) {{
  document.getElementById(id).innerHTML = valores.map(v => `<option value="${{v}}">${{formato(v)}}</option>`).join('');
}}

function statsHtml(fila) {{
  if (!fila) return '';
  return [
    ['Segmentos', fmtInt(fila.n_segmentos)],
    ['Tam. medio', `${{fmtFloat(fila.tam_medio_px)}} px`],
    ['Tam. mediano', `${{fmtFloat(fila.tam_mediano_px)}} px`],
    ['Tam. medio', `${{fmtFloat(fila.tam_medio_ha, 2)}} ha`],
    ['Tam. min–max', `${{fmtInt(fila.tam_min_px)}} – ${{fmtInt(fila.tam_max_px)}} px`],
  ].map(([k,v]) => `<div class="stat-chip"><div class="k">${{k}}</div><div class="v">${{v}}</div></div>`).join('');
}}

function aplicarVisibilidadCapas(sufijo) {{
  const showMosaic = document.getElementById('chk-mosaic').checked;
  const showSeg = document.getElementById('chk-seg').checked;
  const showBnd = document.getElementById('chk-bnd').checked;
  const showQl = document.getElementById('chk-quicklook').checked;
  const opacitySeg = document.getElementById('opacity-seg').value / 100;
  const mosaic = document.getElementById(`layer-mosaic-${{sufijo}}`);
  const seg = document.getElementById(`layer-seg-${{sufijo}}`);
  const bnd = document.getElementById(`layer-bnd-${{sufijo}}`);
  const ql = document.getElementById(`layer-quicklook-${{sufijo}}`);
  [mosaic, seg, bnd, ql].forEach(el => el.classList.toggle('hidden-layer', false));
  mosaic.classList.toggle('hidden-layer', !showMosaic || !mosaic.getAttribute('src'));
  seg.classList.toggle('hidden-layer', !showSeg || !seg.getAttribute('src'));
  bnd.classList.toggle('hidden-layer', !showBnd || !bnd.getAttribute('src'));
  ql.classList.toggle('hidden-layer', !showQl || !ql.getAttribute('src'));
  seg.style.opacity = showSeg ? opacitySeg : 0;
  bnd.style.opacity = showBnd ? 1 : 0;
  ql.style.opacity = showQl ? 1 : 0;
}}

function tierSrc(tiers, tier) {{
  if (!tiers) return null;
  const key = String(tier);
  return tiers[key] || tiers[String(RES_TIERS[0])] || Object.values(tiers)[0] || null;
}}

function mosaicTiersFor(segId) {{
  const seg = DATA.segmenters && DATA.segmenters[segId];
  if (seg && seg.mosaic_tiers && Object.keys(seg.mosaic_tiers).length) return seg.mosaic_tiers;
  return DATA.mosaic_tiers || {{}};
}}

function tierForZoom(userZoom) {{
  if (userZoom >= 3.5) return RES_TIERS[Math.min(2, RES_TIERS.length - 1)];
  if (userZoom >= 1.8) return RES_TIERS[Math.min(1, RES_TIERS.length - 1)];
  return RES_TIERS[0];
}}

function loadImageEl(el, src) {{
  return new Promise(resolve => {{
    if (!src) {{ el.removeAttribute('src'); el.style.display = 'none'; resolve(null); return; }}
    if (el.getAttribute('src') === src && el.complete && el.naturalWidth) {{ resolve(el); return; }}
    el.onload = () => resolve(el);
    el.onerror = () => resolve(null);
    el.style.display = 'block';
    el.src = src;
  }});
}}

function getViewCenter(sufijo) {{
  const st = PANEL[sufijo];
  const vp = document.getElementById(`viewport-${{sufijo}}`).getBoundingClientRect();
  const total = st.userZoom * st.fit;
  if (total <= 0) return {{ cx: 0.5, cy: 0.5 }};
  return {{
    cx: (vp.width / 2 - st.panX) / (st.imgW * total),
    cy: (vp.height / 2 - st.panY) / (st.imgH * total),
  }};
}}

function setViewCenter(sufijo, cx, cy) {{
  const st = PANEL[sufijo];
  const vp = document.getElementById(`viewport-${{sufijo}}`).getBoundingClientRect();
  const total = st.userZoom * st.fit;
  st.panX = vp.width / 2 - cx * st.imgW * total;
  st.panY = vp.height / 2 - cy * st.imgH * total;
}}

async function loadPanelTier(sufijo, tier, preserveView) {{
  const st = PANEL[sufijo];
  if (st.loading) return;
  const segId = st.segId;
  const capa = capaPorClave(st.clave, segId);
  const contentKey = `${{segId}}:${{st.clave}}`;
  const mosaicSrc = tierSrc(mosaicTiersFor(segId), tier);
  const segSrc = capa ? tierSrc(capa.overlay_tiers, tier) : null;
  const bndSrc = capa ? tierSrc(capa.boundaries_tiers, tier) : null;
  const center = preserveView ? getViewCenter(sufijo) : null;
  st.loading = true;
  const mosaic = document.getElementById(`layer-mosaic-${{sufijo}}`);
  const seg = document.getElementById(`layer-seg-${{sufijo}}`);
  const bnd = document.getElementById(`layer-bnd-${{sufijo}}`);
  const ql = document.getElementById(`layer-quicklook-${{sufijo}}`);
  if (st.contentKey !== contentKey) {{
    seg.removeAttribute('src');
    bnd.removeAttribute('src');
    ql.removeAttribute('src');
    st.contentKey = contentKey;
  }}
  if (capa && capa.png) {{ ql.src = capa.png; ql.style.display = 'block'; }}
  else {{ ql.removeAttribute('src'); ql.style.display = 'none'; }}
  const loadedMosaic = await loadImageEl(mosaic, mosaicSrc);
  await Promise.all([loadImageEl(seg, segSrc), loadImageEl(bnd, bndSrc)]);
  const imgW = loadedMosaic ? loadedMosaic.naturalWidth : 100;
  const imgH = loadedMosaic ? loadedMosaic.naturalHeight : 100;
  const stage = document.getElementById(`stage-${{sufijo}}`);
  stage.style.width = `${{imgW}}px`;
  stage.style.height = `${{imgH}}px`;
  st.imgW = imgW;
  st.imgH = imgH;
  st.tier = tier;
  st.loading = false;
  if (!recalcFit(sufijo)) {{
    await new Promise(r => requestAnimationFrame(r));
    recalcFit(sufijo);
  }}
  if (!preserveView) {{ st.userZoom = 1; st.panX = 0; st.panY = 0; }}
  else if (center) {{ setViewCenter(sufijo, center.cx, center.cy); }}
  aplicarZoomTransform(sufijo, true);
  aplicarVisibilidadCapas(sufijo);
  return true;
}}

function aplicarZoomTransform(sufijo, noSync = false) {{
  const st = PANEL[sufijo];
  const stage = document.getElementById(`stage-${{sufijo}}`);
  const total = st.userZoom * st.fit;
  stage.style.transform = `translate(${{st.panX}}px, ${{st.panY}}px) scale(${{total}})`;
  document.getElementById(`zoom-label-${{sufijo}}`).textContent =
    `${{Math.round(st.userZoom * 100)}}% · ${{st.tier}}px`;
  const needed = tierForZoom(st.userZoom);
  if (needed > st.tier && tierSrc(mosaicTiersFor(st.segId), needed) && !st.loading) {{
    loadPanelTier(sufijo, needed, true);
    return;
  }}
  if (!noSync) syncPeerView(sufijo);
}}

function resetZoom(sufijo) {{
  const st = PANEL[sufijo];
  st.userZoom = 1; st.panX = 0; st.panY = 0;
  if (st.tier !== RES_TIERS[0]) loadPanelTier(sufijo, RES_TIERS[0], false);
  else aplicarZoomTransform(sufijo);
}}

function zoomFactor(sufijo, factor, cx, cy) {{
  const st = PANEL[sufijo];
  const viewport = document.getElementById(`viewport-${{sufijo}}`);
  const rect = viewport.getBoundingClientRect();
  const mx = cx !== undefined ? cx - rect.left : rect.width / 2;
  const my = cy !== undefined ? cy - rect.top : rect.height / 2;
  const totalOld = st.userZoom * st.fit;
  st.userZoom = Math.min(24, Math.max(1, st.userZoom * factor));
  const totalNew = st.userZoom * st.fit;
  st.panX = mx - (mx - st.panX) * (totalNew / totalOld);
  st.panY = my - (my - st.panY) * (totalNew / totalOld);
  if (st.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
  aplicarZoomTransform(sufijo);
}}

function initZoom(sufijo) {{
  const viewport = document.getElementById(`viewport-${{sufijo}}`);
  let dragging = false, startX = 0, startY = 0, startPanX = 0, startPanY = 0;
  viewport.addEventListener('wheel', (e) => {{
    e.preventDefault();
    zoomFactor(sufijo, e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
  }}, {{ passive: false }});
  viewport.addEventListener('mousedown', (e) => {{
    if (e.button !== 0) return;
    dragging = true;
    viewport.classList.add('dragging');
    startX = e.clientX; startY = e.clientY;
    startPanX = PANEL[sufijo].panX; startPanY = PANEL[sufijo].panY;
    e.preventDefault();
  }});
  window.addEventListener('mousemove', (e) => {{
    if (!dragging) return;
    PANEL[sufijo].panX = startPanX + (e.clientX - startX);
    PANEL[sufijo].panY = startPanY + (e.clientY - startY);
    aplicarZoomTransform(sufijo);
  }});
  window.addEventListener('mouseup', () => {{
    if (!dragging) return;
    dragging = false;
    viewport.classList.remove('dragging');
  }});
  document.querySelectorAll(`.zoom-btn[data-panel="${{sufijo}}"]`).forEach(btn => {{
    btn.addEventListener('click', () => {{
      const action = btn.dataset.action;
      if (action === 'reset') resetZoom(sufijo);
      else if (action === 'in') zoomFactor(sufijo, 1.25);
      else if (action === 'out') zoomFactor(sufijo, 1 / 1.25);
    }});
  }});
  if (typeof ResizeObserver !== 'undefined') {{
    new ResizeObserver(() => {{
      if (recalcFit(sufijo)) aplicarZoomTransform(sufijo, true);
    }}).observe(viewport);
  }}
}}

function updatePanelHeader(sufijo, segId, fila) {{
  const hdr = document.getElementById(`title-${{sufijo}}`);
  hdr.className = '';
  hdr.classList.add(`seg-${{segId}}`);
  const lbl = segData(segId).label;
  const ragTxt = (fila && fila.rag_percentil != null && fila.rag_percentil !== '')
    ? (fila.rag_mode === 'hierarchical' || segData(segId).rag_suffix === 'hier_p'
        ? ` · RAG hier p=${{fila.rag_percentil}}`
        : ` · RAG p=${{fila.rag_percentil}}`)
    : '';
  const minTxt = (fila && fila.rag_min_size_px)
    ? ` · min=${{fila.rag_min_size_px}}px` : '';
  const capa = fila ? capaPorClave(PANEL[sufijo].clave, segId) : null;
  if (!fila && !capa) {{
    hdr.textContent = `${{lbl}} · sin datos`;
    return;
  }}
  const escala = fila ? fila.scale : (capa ? capa.scale : '?');
  const sig = fila ? fila.sigma : (capa ? capa.sigma : '?');
  const nSeg = fila && fila.n_segmentos ? fmtInt(fila.n_segmentos) + ' seg.' : 'capas OK';
  hdr.textContent = `${{lbl}} · s=${{escala}}, σ=${{sig}}${{ragTxt}}${{minTxt}} · ${{nSeg}}`;
}}

async function mostrarPanel(sufijo, clave) {{
  const segId = segActivo(sufijo);
  PANEL[sufijo].segId = segId;
  PANEL[sufijo].clave = clave;
  const fila = filaPorClave(clave, segId);
  const capa = capaPorClave(clave, segId);
  updatePanelHeader(sufijo, segId, fila);
  if (capa) {{
    const tifLink = capa.tif ? `<a href="${{capa.tif}}" download>Descargar GeoTIFF</a>` : '';
    document.getElementById(`meta-${{sufijo}}`).innerHTML = tifLink
      ? `${{tifLink}} · resolución progresiva al acercar` : '';
  }} else document.getElementById(`meta-${{sufijo}}`).innerHTML = '';
  document.getElementById(`stats-${{sufijo}}`).innerHTML = statsHtml(fila);
  await loadPanelTier(sufijo, RES_TIERS[0], false);
  if (isCompareMode() && sufijo === 'b') {{
    await applyViewState(sufijo, getViewState('a'));
  }}
}}

function marcarSeleccion(clave, segId) {{
  document.querySelectorAll('.matrix-cell[data-key]').forEach(el => {{
    el.classList.toggle('selected', el.dataset.key === clave && el.dataset.seg === segId);
  }});
  document.querySelectorAll('.fila-resumen').forEach(el => {{
    el.classList.toggle('selected', el.dataset.key === clave && el.dataset.seg === segId);
  }});
}}

function scalesParaSeg(segId) {{
  return (DATA.scales_by_seg && DATA.scales_by_seg[segId]) || DATA.scales;
}}

function sigmasParaSeg(segId) {{
  return (DATA.sigmas_by_seg && DATA.sigmas_by_seg[segId]) || DATA.sigmas;
}}

function actualizarSelectsB() {{
  const segId = segActivo('b');
  const scales = scalesParaSeg(segId);
  const sigmas = sigmasParaSeg(segId);
  const prevScale = document.getElementById('sel-scale-b').value;
  const prevSigma = document.getElementById('sel-sigma-b').value;
  llenarSelect('sel-scale-b', scales);
  llenarSelect('sel-sigma-b', sigmas, s => `σ=${{s}}`);
  if (scales.map(String).includes(prevScale)) {{
    document.getElementById('sel-scale-b').value = prevScale;
  }} else if (scales.length) {{
    document.getElementById('sel-scale-b').value = String(scales[0]);
  }}
  if (sigmas.map(String).includes(prevSigma)) {{
    document.getElementById('sel-sigma-b').value = prevSigma;
  }} else if (sigmas.length) {{
    document.getElementById('sel-sigma-b').value = String(sigmas[0]);
  }}
}}

function seleccionDesdeCelda(clave, segId) {{
  if (isCompareMode() && segId !== segActivo('a')) {{
    document.getElementById('sel-seg-b').value = segId;
    actualizarSelectsB();
    updateSlicRagVisibility();
    const fila = filaPorClave(clave, segId);
    if (fila) {{
      document.getElementById('sel-scale-b').value = String(fila.scale);
      document.getElementById('sel-sigma-b').value = String(fila.sigma);
    }}
    seleccionB().then(() => syncPeerView('a'));
    marcarSeleccion(clave, segId);
    return;
  }}
  seleccion(clave, segId);
}}

function seleccion(clave, segIdOverride) {{
  const segId = segIdOverride || segActivo('a');
  document.getElementById('sel-seg-a').value = segId;
  const fila = filaPorClave(clave, segId);
  if (!fila) return;
  document.getElementById('sel-scale-a').value = String(fila.scale);
  document.getElementById('sel-sigma-a').value = String(fila.sigma);
  mostrarPanel('a', clave).then(() => {{
    if (isCompareMode()) syncPeerView('a');
  }});
  marcarSeleccion(clave, segId);
}}

function seleccionB() {{
  const segId = segActivo('b');
  PANEL.b.segId = segId;
  asegurarRagSelect('b', segId);
  const scale = document.getElementById('sel-scale-b').value;
  const sigma = document.getElementById('sel-sigma-b').value;
  const clave = resolverClavePanel(segId, scale, sigma, 'b');
  return mostrarPanel('b', clave);
}}

function toggleCompare() {{
  const btn = document.getElementById('btn-compare');
  const viewer = document.getElementById('viewer');
  const panelB = document.getElementById('panel-b');
  const show = !btn.classList.contains('active');
  btn.classList.toggle('active', show);
  btn.textContent = show ? 'Single view' : 'Compare segmenters';
  viewer.classList.toggle('compare', show);
  panelB.classList.toggle('hidden', !show);
  document.getElementById('lbl-seg-b').classList.toggle('hidden', !show);
  document.getElementById('lbl-scale-b').classList.toggle('hidden', !show);
  document.getElementById('lbl-sigma-b').classList.toggle('hidden', !show);
  updateSlicRagVisibility();
  if (show) {{
    if (document.getElementById('sel-seg-b').value === document.getElementById('sel-seg-a').value) {{
      const alt = DATA.seg_ids.find(s => s !== document.getElementById('sel-seg-a').value);
      if (alt) document.getElementById('sel-seg-b').value = alt;
    }}
    actualizarSelectsB();
    asegurarRagSelect('b', segActivo('b'));
    seleccionB().then(() => {{
      requestAnimationFrame(() => {{
        recalcFit('a');
        recalcFit('b');
        syncPeerView('a');
      }});
    }});
  }}
}}

function renderCharts() {{
  const tracesSeg = [];
  const tracesTam = [];
  DATA.seg_ids.forEach(segId => {{
    const d = segData(segId);
    const filas = d.incluir_rag ? filasVisibles(segId, 'a') : d.filas;
    DATA.sigmas.forEach(sigma => {{
      tracesSeg.push({{
        x: DATA.scales,
        y: DATA.scales.map(scale => {{
          const f = filas.find(r => r.scale === scale && r.sigma === sigma);
          return f ? f.n_segmentos : null;
        }}),
        mode: 'lines+markers',
        name: `${{d.label}} σ=${{sigma}}`,
        line: {{ color: d.color }},
        legendgroup: segId,
        hovertemplate: `${{d.label}}<br>scale=%{{x}}<br>segmentos=%{{y:,}}<extra></extra>`
      }});
      tracesTam.push({{
        x: DATA.scales,
        y: DATA.scales.map(scale => {{
          const f = filas.find(r => r.scale === scale && r.sigma === sigma);
          return f ? f.tam_medio_ha : null;
        }}),
        mode: 'lines+markers',
        name: `${{d.label}} σ=${{sigma}}`,
        line: {{ color: d.color, dash: sigma === DATA.sigmas[0] ? 'solid' : 'dot' }},
        legendgroup: segId,
        hovertemplate: `${{d.label}}<br>scale=%{{x}}<br>tam. medio=%{{y:.2f}} ha<extra></extra>`
      }});
    }});
  }});
  Plotly.newPlot('chart-segmentos', tracesSeg, {{
    title: 'Number of segments vs scale',
    xaxis: {{ title: 'scale', dtick: 1 }}, yaxis: {{ title: 'n segmentos' }},
    margin: {{ t: 50, l: 50, r: 20, b: 50 }}, legend: {{ orientation: 'h', y: -0.25 }}
  }}, {{ responsive: true }});
  Plotly.newPlot('chart-tamano', tracesTam, {{
    title: 'Mean segment size vs scale',
    xaxis: {{ title: 'scale', dtick: 1 }}, yaxis: {{ title: 'tam. medio (ha)' }},
    margin: {{ t: 50, l: 50, r: 20, b: 50 }}, legend: {{ orientation: 'h', y: -0.25 }}
  }}, {{ responsive: true }});

  DATA.seg_ids.forEach(segId => {{
    const d = segData(segId);
    const filas = d.incluir_rag ? filasVisibles(segId, 'a') : d.filas;
    const z = DATA.sigmas.map(sigma => DATA.scales.map(scale => {{
      const f = filas.find(r => r.scale === scale && r.sigma === sigma);
      return f ? f.n_segmentos : null;
    }}));
    Plotly.newPlot(`chart-heatmap-${{segId}}`, [{{
      z, x: DATA.scales.map(String), y: DATA.sigmas.map(s => `σ=${{s}}`),
      type: 'heatmap', colorscale: segId === 'felzenszwalb' ? 'Blues' : 'Greens',
      hovertemplate: 'scale=%{{x}}<br>%{{y}}<br>segmentos=%{{z:,}}<extra></extra>'
    }}], {{
      title: `${{d.label}}: segment heatmap`,
      margin: {{ t: 50, l: 70, r: 20, b: 50 }}
    }}, {{ responsive: true }});
  }});
}}

function init() {{
  llenarSelect('sel-scale-a', DATA.scales);
  llenarSelect('sel-sigma-a', DATA.sigmas, s => `σ=${{s}}`);

  document.getElementById('sel-seg-a').value = DATA.seg_ids[0];
  document.getElementById('sel-seg-b').value = DATA.seg_ids[Math.min(1, DATA.seg_ids.length - 1)];

  ['chk-mosaic','chk-seg','chk-bnd','chk-quicklook','opacity-seg'].forEach(id => {{
    document.getElementById(id).addEventListener('input', () => {{
      aplicarVisibilidadCapas('a');
      if (!document.getElementById('panel-b').classList.contains('hidden')) aplicarVisibilidadCapas('b');
    }});
  }});

  const primera = segData(DATA.seg_ids[0]).filas[0];
  if (primera) {{
    document.getElementById('sel-scale-a').value = String(primera.scale);
    document.getElementById('sel-sigma-a').value = String(primera.sigma);
    seleccion(claveFila(primera, DATA.seg_ids[0]), DATA.seg_ids[0]);
  }}

  document.getElementById('sel-seg-a').addEventListener('change', () => {{
    updateSlicRagVisibility();
    const segId = segActivo('a');
    const scale = document.getElementById('sel-scale-a').value;
    const sigma = document.getElementById('sel-sigma-a').value;
    const clave = resolverClavePanel(segId, scale, sigma, 'a');
    seleccion(clave, segId);
  }});
  ['sel-scale-a', 'sel-sigma-a'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => {{
      const scale = document.getElementById('sel-scale-a').value;
      const sigma = document.getElementById('sel-sigma-a').value;
      const segId = segActivo('a');
      const clave = resolverClavePanel(segId, scale, sigma, 'a');
      seleccion(clave, segId);
    }});
  }});
  document.getElementById('sel-rag-a').addEventListener('change', () => onSlicRagChange('a'));
  document.getElementById('sel-rag-b').addEventListener('change', () => onSlicRagChange('b'));
  document.getElementById('sel-seg-b').addEventListener('change', () => {{
    updateSlicRagVisibility();
    actualizarSelectsB();
    seleccionB();
  }});
  ['sel-scale-b', 'sel-sigma-b'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => {{
      if (!isCompareMode()) return;
      seleccionB().then(() => syncPeerView('a'));
    }});
  }});
  document.getElementById('btn-compare').addEventListener('click', toggleCompare);
  document.querySelectorAll('.matrix-cell[data-key]').forEach(el => {{
    el.addEventListener('click', () => seleccionDesdeCelda(el.dataset.key, el.dataset.seg));
  }});
  document.querySelectorAll('.fila-resumen').forEach(el => {{
    el.addEventListener('click', () => seleccionDesdeCelda(el.dataset.key, el.dataset.seg));
  }});

  if (!TIENE_CAPAS) {{
    document.querySelector('.layer-controls').insertAdjacentHTML('beforeend',
      '<span style="color:#b45309;font-size:0.88rem">Layers not exported — run segmenters_viewer.py without --skip-layers</span>');
  }}

  initZoom('a');
  initZoom('b');
  updateSlicRagVisibility();
  refreshSlicTable();
  refreshSlicMatrix();
  renderCharts();
}}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dashboard HTML unificado Felzenszwalb + SLIC."
    )
    parser.add_argument(
        "--mosaic-dir",
        type=Path,
        default=Path(MOSAIC_DIR),
        help="Directorio de mosaicos nir/swir1/red",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=DEFAULT_HTML,
        help="Ruta del HTML de salida (por defecto en image_segmentation/)",
    )
    parser.add_argument(
        "--skip-layers",
        action="store_true",
        help="Do not regenerate mosaic/overlay PNG layers (use existing capas/)",
    )
    parser.add_argument(
        "--only-segmenter",
        choices=tuple(SEGMENTADORES.keys()),
        default=None,
        help="Exportar capas solo de un segmentador (los demás usan capas existentes)",
    )
    parser.add_argument(
        "--segmenters",
        default=None,
        help="Lista separada por comas de segmentadores a incluir (default: todos)",
    )
    args = parser.parse_args()

    html_path = args.html.resolve()
    html_dir = html_path.parent
    html_dir.mkdir(parents=True, exist_ok=True)

    segmentadores: dict[str, dict] = {}
    mosaic_tiers: dict[str, str] = {}
    tile = ""
    year = ""

    seg_ids = (
        [s.strip() for s in args.segmenters.split(",") if s.strip()]
        if args.segmenters
        else list(SEGMENTADORES.keys())
    )
    for seg_id in seg_ids:
        if seg_id not in SEGMENTADORES:
            print(f"[ERROR] Segmentador desconocido: {seg_id}")
            sys.exit(1)
        config = SEGMENTADORES[seg_id]
        skip_layers_seg = args.skip_layers or (
            args.only_segmenter is not None and seg_id != args.only_segmenter
        )
        datos, tiers = cargar_segmentador(
            seg_id,
            config,
            html_dir,
            args.mosaic_dir,
            skip_layers_seg,
            mosaic_tiers if mosaic_tiers else None,
        )
        segmentadores[seg_id] = datos
        if tiers and not mosaic_tiers:
            mosaic_tiers = tiers
        if not tile:
            tile = datos["tile"]
            year = datos["year"]

    if tile and year:
        for seg_id, datos in segmentadores.items():
            if datos["tile"] != tile or datos["year"] != year:
                print(
                    f"[ADVERTENCIA] Tile/año distinto en {seg_id}: "
                    f"{datos['tile']}/{datos['year']} vs {tile}/{year}"
                )

    if not mosaic_tiers:
        for seg_id, config in SEGMENTADORES.items():
            capas_dir = Path(config["output_dir"]) / CAPAS_SUBDIR
            mosaic_tiers = viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)
            if mosaic_tiers:
                break

    contenido = generar_html(html_dir, segmentadores, mosaic_tiers, tile, year)

    try:
        html_path.write_text(contenido, encoding="utf-8")
    except OSError as exc:
        fallback = _SCRIPT_DIR / "segmenters_viewer.html"
        print(f"[ADVERTENCIA] No se pudo escribir en {html_path}: {exc}")
        print(f"[INFO] Guardando en: {fallback}")
        html_path = fallback
        html_path.write_text(contenido, encoding="utf-8")

    print(f"[OK] Dashboard: {html_path}")
    for seg_id, datos in segmentadores.items():
        n = len(datos["combinaciones"])
        print(f"[OK] {datos['label']}: {n} combinaciones · {datos['output_dir']}")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765 --bind 0.0.0.0")
    print(f"[INFO] URL: http://localhost:8765/{html_path.name}")


if __name__ == "__main__":
    main()
