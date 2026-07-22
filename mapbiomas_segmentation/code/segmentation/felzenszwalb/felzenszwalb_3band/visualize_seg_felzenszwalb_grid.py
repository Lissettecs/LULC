#!/usr/bin/env python3
"""
Visualizador de resultados de seg_felzenszwalb_grid.py.

Genera un dashboard HTML con capas apiladas:
  - Mosaico RGB (GeoTIFF fuente)
  - Segmentos coloreados (derivado del TIF de etiquetas)
  - Contornos (opcional)
  - Quick-look compuesto (opcional)

Cada capa se puede activar/desactivar en el explorador.

Uso:
  python visualize_seg_felzenszwalb_grid.py
  python visualize_seg_felzenszwalb_grid.py --output-dir /ruta/seg_Felzenszwalb
  python visualize_seg_felzenszwalb_grid.py --skip-capas   # solo HTML, capas ya exportadas

Abrir con servidor local (recomendado en cluster):
  cd OUTPUT_DIR && python3 -m http.server 8765
  → http://localhost:8765/viewer_felzenszwalb.html
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from html import escape
from pathlib import Path

from seg_felzenszwalb_grid import (
    MOSAIC_DIR as SEG_MOSAIC_DIR,
    OUTPUT_DIR as SEG_OUTPUT_DIR,
    localizar_mosaico_tile,
    nombre_mosaico,
)

DEFAULT_OUTPUT_DIR = str(SEG_OUTPUT_DIR)
DEFAULT_MOSAIC_DIR = str(SEG_MOSAIC_DIR)
CAPAS_SUBDIR = "capas"
RES_TIERS = [1024, 2048, 4096]

PNG_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)\.png$"
)
TIF_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)\.tif$"
)
PNG_RAG_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>rag(?:p\d+|[\d.]+))\.png$"
)
TIF_RAG_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>rag(?:p\d+|[\d.]+))\.tif$"
)
TIF_RAG_MIN_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>ragp\d+)_min(?P<min_px>\d+)\.tif$"
)
PNG_RAG_MIN_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>ragp\d+)_min(?P<min_px>\d+)\.png$"
)
TIF_HIER_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>hier_p\d+)\.tif$"
)
PNG_HIER_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>hier_p\d+)\.png$"
)
TIF_HIER_MIN_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>hier_p\d+)_min(?P<min_px>\d+)\.tif$"
)
PNG_HIER_MIN_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+(?:\.\d+)?)_sig(?P<sigma>\d+(?:\.\d+)?)_(?P<rag>hier_p\d+)_min(?P<min_px>\d+)\.png$"
)
CSV_PATTERN = re.compile(r"^resumen_(?P<tile>[^_]+)_(?P<year>\d+)\.csv$")


def ruta_publica(html_dir: Path, archivo: Path) -> str:
    """Ruta relativa desde html_dir hacia archivo (para src/href en HTML)."""
    return os.path.relpath(archivo.resolve(), html_dir.resolve()).replace("\\", "/")


def buscar_resumen(output_dir: Path) -> Path | None:
    candidatos = sorted(output_dir.glob("resumen_*.csv"))
    if not candidatos:
        return None
    if len(candidatos) > 1:
        print(f"[INFO] Varios CSV resumen; se usa: {candidatos[0].name}")
    return candidatos[0]


def cargar_resumen(ruta_csv: Path) -> tuple[list[dict], str, str]:
    filas: list[dict] = []
    tile = ""
    year = ""
    match = CSV_PATTERN.match(ruta_csv.name)
    if match:
        tile = match.group("tile")
        year = match.group("year")

    with ruta_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rag_p_raw = (row.get("rag_percentil") or "").strip()
            rag_percentil = int(float(rag_p_raw)) if rag_p_raw else None
            rag_abs_raw = (row.get("rag_thresh_abs") or row.get("rag_thresh") or "").strip()
            rag_thresh_abs = float(rag_abs_raw) if rag_abs_raw else None
            n_seg = row.get("n_regiones_fusionadas") or row["n_segmentos"]
            filas.append(
                {
                    "scale": int(float(row["scale"])),
                    "sigma": float(row["sigma"]),
                    "min_size": int(float(row["min_size"])),
                    "n_segmentos": int(float(n_seg)),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "rag_mode": (row.get("rag_mode") or "").strip(),
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


def clave_desde_params(scale: int, sigma: float, rag_suffix: str | None = None) -> str:
    base = f"s{scale}_sig{str(sigma).replace('.', '_')}"
    if rag_suffix:
        return f"{base}_{rag_suffix.replace('.', '_')}"
    return base


def fila_a_clave(fila: dict) -> str:
    percentil = fila.get("rag_percentil")
    rag_mode = (fila.get("rag_mode") or "").strip()
    if percentil not in (None, ""):
        if rag_mode == "hierarchical":
            rag_suffix = f"hier_p{int(percentil)}"
        else:
            rag_suffix = f"ragp{int(percentil)}"
    else:
        thr = fila.get("rag_thresh_abs") or fila.get("rag_thresh")
        rag_suffix = f"rag{float(thr):g}" if thr not in (None, "") else None
    min_px = fila.get("rag_min_size_px")
    if min_px not in (None, ""):
        rag_suffix = f"{rag_suffix}_min{int(min_px)}" if rag_suffix else f"min{int(min_px)}"
    return clave_desde_params(fila["scale"], fila["sigma"], rag_suffix)


def listar_tifs_segmentacion(
    output_dir: Path,
    incluir_rag: bool = False,
    rag_min_px: int | None = None,
    rag_hierarchical: bool = False,
    rag_hier_min_px: int | None = None,
) -> list[Path]:
    if rag_hier_min_px is not None:
        return sorted(
            p
            for p in output_dir.glob(f"seg_*_s*_sig*_hier_p*_min{rag_hier_min_px}.tif")
            if TIF_HIER_MIN_PATTERN.match(p.name)
        )
    if rag_hierarchical:
        return sorted(
            p for p in output_dir.glob("seg_*_s*_sig*_hier_p*.tif") if TIF_HIER_PATTERN.match(p.name)
        )
    if rag_min_px is not None:
        return sorted(
            p for p in output_dir.glob(f"seg_*_s*_sig*_ragp*_min{rag_min_px}.tif")
            if TIF_RAG_MIN_PATTERN.match(p.name)
        )
    tifs = sorted(p for p in output_dir.glob("seg_*_s*_sig*.tif") if TIF_PATTERN.match(p.name))
    if incluir_rag:
        tifs.extend(
            sorted(p for p in output_dir.glob("seg_*_s*_sig*.tif") if TIF_RAG_PATTERN.match(p.name))
        )
        tifs = sorted(set(tifs), key=lambda p: p.name)
    return tifs


def descubrir_mosaic_tiers(html_dir: Path, capas_dir: Path, tile: str, year: str) -> dict[str, str]:
    stem = f"mosaic_{tile}_{year}_rgb" if tile and year else "mosaic_rgb"
    tiers: dict[str, str] = {}
    for lado in RES_TIERS:
        ruta = capas_dir / f"{stem}_l{lado}.png"
        if ruta.exists():
            tiers[str(lado)] = ruta_publica(html_dir, ruta)
    if tiers:
        return tiers
    legacy = capas_dir / f"{stem}.png"
    if legacy.exists():
        tiers["1024"] = ruta_publica(html_dir, legacy)
    return tiers


def descubrir_tiers_capa(html_dir: Path, capas_dir: Path, stem: str, kind: str) -> dict[str, str]:
    """Rutas relativas por nivel de resolución (l1024, l2048, …)."""
    tiers: dict[str, str] = {}
    for lado in RES_TIERS:
        ruta = capas_dir / f"{stem}_{kind}_l{lado}.png"
        if ruta.exists():
            tiers[str(lado)] = ruta_publica(html_dir, ruta)
    if tiers:
        return tiers
    legacy = capas_dir / f"{stem}_{kind}.png"
    if legacy.exists():
        tiers["1024"] = ruta_publica(html_dir, legacy)
    return tiers


def _entrada_desde_tif(
    match: re.Match[str],
    ruta_tif: Path,
    html_dir: Path,
    capas_dir: Path,
    rag_suffix: str | None = None,
) -> dict:
    scale = int(float(match.group("scale")))
    sigma = float(match.group("sigma"))
    clave = clave_desde_params(scale, sigma, rag_suffix)
    base = ruta_tif.stem
    ruta_png = ruta_tif.with_suffix(".png")
    rag_percentil = None
    rag_thresh_abs = None
    rag_min_size_px = None
    if rag_suffix:
        suffix = rag_suffix
        if "_min" in suffix:
            base_part, min_part = suffix.rsplit("_min", 1)
            rag_min_size_px = int(min_part)
            suffix = base_part
        if suffix.startswith("hier_p"):
            rag_percentil = int(suffix.removeprefix("hier_p"))
        elif suffix.startswith("ragp"):
            rag_percentil = int(suffix.removeprefix("ragp"))
        elif suffix.startswith("rag"):
            rag_thresh_abs = float(suffix.removeprefix("rag"))
    return {
        "tile": match.group("tile"),
        "year": match.group("year"),
        "scale": scale,
        "sigma": sigma,
        "rag_percentil": rag_percentil,
        "rag_thresh_abs": rag_thresh_abs,
        "rag_thresh": rag_thresh_abs,
        "rag_min_size_px": rag_min_size_px,
        "clave": clave,
        "tif": ruta_publica(html_dir, ruta_tif),
        "png": ruta_publica(html_dir, ruta_png) if ruta_png.exists() else None,
        "overlay_tiers": descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
        "boundaries_tiers": descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
    }


def descubrir_combinaciones(
    output_dir: Path,
    html_dir: Path,
    incluir_rag: bool = False,
    rag_min_px: int | None = None,
    rag_hierarchical: bool = False,
    rag_hier_min_px: int | None = None,
) -> list[dict]:
    entradas: list[dict] = []
    capas_dir = output_dir / CAPAS_SUBDIR

    if rag_hier_min_px is not None:
        for ruta_tif in sorted(
            output_dir.glob(f"seg_*_s*_sig*_hier_p*_min{rag_hier_min_px}.tif")
        ):
            match = TIF_HIER_MIN_PATTERN.match(ruta_tif.name)
            if not match:
                continue
            rag_suffix = f"{match.group('rag')}_min{match.group('min_px')}"
            entradas.append(
                _entrada_desde_tif(
                    match,
                    ruta_tif,
                    html_dir,
                    capas_dir,
                    rag_suffix=rag_suffix,
                )
            )
        if entradas:
            return entradas
        for ruta_png in sorted(
            output_dir.glob(f"seg_*_s*_sig*_hier_p*_min{rag_hier_min_px}.png")
        ):
            match = PNG_HIER_MIN_PATTERN.match(ruta_png.name)
            if not match:
                continue
            scale = int(float(match.group("scale")))
            sigma = float(match.group("sigma"))
            rag_suffix = f"{match.group('rag')}_min{match.group('min_px')}"
            clave = clave_desde_params(scale, sigma, rag_suffix)
            entradas.append(
                {
                    "tile": match.group("tile"),
                    "year": match.group("year"),
                    "scale": scale,
                    "sigma": sigma,
                    "rag_percentil": int(match.group("rag").removeprefix("hier_p")),
                    "rag_thresh_abs": None,
                    "rag_thresh": None,
                    "rag_min_size_px": int(match.group("min_px")),
                    "rag_mode": "hierarchical",
                    "clave": clave,
                    "tif": ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                    "png": ruta_publica(html_dir, ruta_png),
                    "overlay_tiers": {},
                    "boundaries_tiers": {},
                }
            )
        return entradas

    if rag_hierarchical:
        for ruta_tif in sorted(output_dir.glob("seg_*_s*_sig*_hier_p*.tif")):
            match = TIF_HIER_PATTERN.match(ruta_tif.name)
            if not match:
                continue
            entradas.append(
                _entrada_desde_tif(
                    match,
                    ruta_tif,
                    html_dir,
                    capas_dir,
                    rag_suffix=match.group("rag"),
                )
            )
        if entradas:
            return entradas
        for ruta_png in sorted(output_dir.glob("seg_*_s*_sig*_hier_p*.png")):
            match = PNG_HIER_PATTERN.match(ruta_png.name)
            if not match:
                continue
            scale = int(float(match.group("scale")))
            sigma = float(match.group("sigma"))
            rag_suffix = match.group("rag")
            clave = clave_desde_params(scale, sigma, rag_suffix)
            entradas.append(
                {
                    "tile": match.group("tile"),
                    "year": match.group("year"),
                    "scale": scale,
                    "sigma": sigma,
                    "rag_percentil": int(rag_suffix.removeprefix("hier_p")),
                    "rag_thresh_abs": None,
                    "rag_thresh": None,
                    "rag_min_size_px": None,
                    "rag_mode": "hierarchical",
                    "clave": clave,
                    "tif": ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                    "png": ruta_publica(html_dir, ruta_png),
                    "overlay_tiers": {},
                    "boundaries_tiers": {},
                }
            )
        return entradas

    if rag_min_px is not None:
        for ruta_tif in sorted(output_dir.glob(f"seg_*_s*_sig*_ragp*_min{rag_min_px}.tif")):
            match = TIF_RAG_MIN_PATTERN.match(ruta_tif.name)
            if not match:
                continue
            rag_suffix = f"{match.group('rag')}_min{match.group('min_px')}"
            entradas.append(
                _entrada_desde_tif(
                    match,
                    ruta_tif,
                    html_dir,
                    capas_dir,
                    rag_suffix=rag_suffix,
                )
            )
        if entradas:
            return entradas
        for ruta_png in sorted(output_dir.glob(f"seg_*_s*_sig*_ragp*_min{rag_min_px}.png")):
            match = PNG_RAG_MIN_PATTERN.match(ruta_png.name)
            if not match:
                continue
            scale = int(float(match.group("scale")))
            sigma = float(match.group("sigma"))
            rag_suffix = f"{match.group('rag')}_min{match.group('min_px')}"
            clave = clave_desde_params(scale, sigma, rag_suffix)
            entradas.append(
                {
                    "tile": match.group("tile"),
                    "year": match.group("year"),
                    "scale": scale,
                    "sigma": sigma,
                    "rag_percentil": int(match.group("rag").removeprefix("ragp")),
                    "rag_thresh_abs": None,
                    "rag_thresh": None,
                    "rag_min_size_px": int(match.group("min_px")),
                    "clave": clave,
                    "tif": ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                    "png": ruta_publica(html_dir, ruta_png),
                    "overlay_tiers": {},
                    "boundaries_tiers": {},
                }
            )
        return entradas

    for ruta_tif in sorted(output_dir.glob("seg_*_s*_sig*.tif")):
        match = TIF_PATTERN.match(ruta_tif.name)
        if not match:
            continue
        entradas.append(_entrada_desde_tif(match, ruta_tif, html_dir, capas_dir))

    if incluir_rag:
        for ruta_tif in sorted(output_dir.glob("seg_*_s*_sig*.tif")):
            match = TIF_RAG_PATTERN.match(ruta_tif.name)
            if not match:
                continue
            entradas.append(
                _entrada_desde_tif(
                    match, ruta_tif, html_dir, capas_dir, rag_suffix=match.group("rag")
                )
            )

    if entradas:
        return entradas

    for ruta_png in sorted(output_dir.glob("seg_*_s*_sig*.png")):
        match = PNG_PATTERN.match(ruta_png.name)
        if match:
            scale = int(float(match.group("scale")))
            sigma = float(match.group("sigma"))
            clave = clave_desde_params(scale, sigma)
            entradas.append(
                {
                    "tile": match.group("tile"),
                    "year": match.group("year"),
                    "scale": scale,
                    "sigma": sigma,
                    "rag_thresh": None,
                    "clave": clave,
                    "tif": ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                    "png": ruta_publica(html_dir, ruta_png),
                    "overlay_tiers": {},
                    "boundaries_tiers": {},
                }
            )
            continue
        if incluir_rag:
            match_rag = PNG_RAG_PATTERN.match(ruta_png.name)
            if not match_rag:
                continue
            scale = int(float(match_rag.group("scale")))
            sigma = float(match_rag.group("sigma"))
            rag_suffix = match_rag.group("rag")
            clave = clave_desde_params(scale, sigma, rag_suffix)
            rag_percentil = None
            rag_thresh_abs = None
            if rag_suffix.startswith("ragp"):
                rag_percentil = int(rag_suffix.removeprefix("ragp"))
            elif rag_suffix.startswith("rag"):
                rag_thresh_abs = float(rag_suffix.removeprefix("rag"))
            entradas.append(
                {
                    "tile": match_rag.group("tile"),
                    "year": match_rag.group("year"),
                    "scale": scale,
                    "sigma": sigma,
                    "rag_percentil": rag_percentil,
                    "rag_thresh_abs": rag_thresh_abs,
                    "rag_thresh": rag_thresh_abs,
                    "clave": clave,
                    "tif": ruta_publica(html_dir, ruta_png.with_suffix(".tif")),
                    "png": ruta_publica(html_dir, ruta_png),
                    "overlay_tiers": {},
                    "boundaries_tiers": {},
                }
            )
    return entradas


def exportar_capas(
    output_dir: Path,
    mosaic_dir: Path,
    tile: str,
    year: str,
    incluir_rag: bool = False,
    rag_min_px: int | None = None,
    rag_hierarchical: bool = False,
    rag_hier_min_px: int | None = None,
) -> dict[str, str] | None:
    """Exporta PNG del mosaico y capas en varios niveles de resolución."""
    try:
        import numpy as np
        import rasterio
        from seg_felzenszwalb_grid import (
            DISPLAY_BANDS,
            NODATA,
            componer_rgb,
            construir_mascara_nodata,
            contornos_rgba_desde_labels,
            guardar_rgba_png,
            localizar_mosaico_tile,
            overlay_rgba_desde_labels,
            reducir_para_quicklook,
            resolver_nodata,
        )
        from PIL import Image
    except ImportError as exc:
        print(f"[ADVERTENCIA] No se exportan capas (faltan dependencias): {exc}")
        return None

    capas_dir = output_dir / CAPAS_SUBDIR
    capas_dir.mkdir(parents=True, exist_ok=True)

    ruta_mosaico = localizar_mosaico_tile(mosaic_dir, tile, int(year))
    mosaic_stem = f"mosaic_{tile}_{year}_rgb" if tile and year else "mosaic_rgb"
    mosaic_tiers: dict[str, str] = {}

    print(f"[INFO] Exportando capas ({', '.join(str(t) for t in RES_TIERS)} px) → {capas_dir}")

    with rasterio.open(ruta_mosaico) as src:
        n_bandas = src.count
        datos = np.stack([src.read(i + 1) for i in range(n_bandas)], axis=-1).astype(np.float32)
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(datos, nodata_valor)
        rgb = componer_rgb(datos, DISPLAY_BANDS, validos)
        rgb = np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0)

    labels_vacio = np.zeros(validos.shape, dtype=np.int32)
    for lado in RES_TIERS:
        rgb_q, _, _ = reducir_para_quicklook(rgb, labels_vacio, validos, lado)
        mosaic_uint8 = (np.clip(rgb_q, 0.0, 1.0) * 255).astype(np.uint8)
        fname = f"{mosaic_stem}_l{lado}.png"
        Image.fromarray(mosaic_uint8, mode="RGB").save(capas_dir / fname)
        mosaic_tiers[str(lado)] = f"{CAPAS_SUBDIR}/{fname}"
        print(f"  → {fname} ({rgb_q.shape[1]}×{rgb_q.shape[0]})")

    tifs = listar_tifs_segmentacion(
        output_dir,
        incluir_rag=incluir_rag,
        rag_min_px=rag_min_px,
        rag_hierarchical=rag_hierarchical,
        rag_hier_min_px=rag_hier_min_px,
    )
    for ruta_tif in tifs:
        with rasterio.open(ruta_tif) as seg:
            labels = seg.read(1).astype(np.int32)

        if labels.shape != validos.shape:
            print(f"[ERROR] Shape distinta: {ruta_tif.name} {labels.shape} vs mosaico {validos.shape}")
            sys.exit(1)

        base = ruta_tif.stem
        for lado in RES_TIERS:
            rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos, lado)
            overlay = overlay_rgba_desde_labels(labels_q, validos_q)
            bordes = contornos_rgba_desde_labels(
                labels_q, validos_q, labels_ref=labels, validos_ref=validos
            )
            ruta_overlay = capas_dir / f"{base}_overlay_l{lado}.png"
            ruta_bordes = capas_dir / f"{base}_boundaries_l{lado}.png"
            guardar_rgba_png(ruta_overlay, overlay)
            guardar_rgba_png(ruta_bordes, bordes)
        print(f"  → {base}_overlay/boundaries_l*.png")

    return mosaic_tiers


def fmt_num(val: float | int, decimales: int = 1) -> str:
    if isinstance(val, int):
        return f"{val:,}".replace(",", ".")
    return f"{val:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def construir_tabla_html(filas: list[dict]) -> str:
    columnas = [
        ("scale", "scale"),
        ("sigma", "σ"),
        ("min_size", "min_size"),
        ("n_segmentos", "n segmentos"),
        ("tam_medio_px", "tam. medio (px)"),
        ("tam_mediano_px", "tam. mediano (px)"),
        ("tam_min_px", "tam. min (px)"),
        ("tam_max_px", "tam. max (px)"),
        ("tam_medio_ha", "tam. medio (ha)"),
    ]
    thead = "".join(f"<th>{escape(titulo)}</th>" for _, titulo in columnas)
    cuerpo: list[str] = []
    for fila in filas:
        celdas: list[str] = []
        for clave, _ in columnas:
            valor = fila[clave]
            if clave in {"scale", "min_size", "n_segmentos", "tam_min_px", "tam_max_px"}:
                texto = fmt_num(int(valor), 0)
            elif clave == "sigma":
                texto = f"{valor:g}"
            else:
                texto = fmt_num(float(valor))
            celdas.append(f"<td>{texto}</td>")
        cuerpo.append(
            f'<tr data-key="{escape(fila_a_clave(fila))}" class="fila-resumen">'
            + "".join(celdas)
            + "</tr>"
        )
    return f"<table class='data resumen-table'><thead><tr>{thead}</tr></thead><tbody>{''.join(cuerpo)}</tbody></table>"


def construir_matriz_html(
    combinaciones: list[dict],
    scales: list[int],
    sigmas: list[float],
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
            clave = f"s{scale}_sig{str(sigma).replace('.', '_')}"
            thumb = thumb_por_clave.get(clave)
            if thumb:
                titulo = f"s={scale}, σ={sigma:g}"
                celdas.append(
                    f"<button type='button' class='matrix-cell' data-key='{escape(clave)}' "
                    f"title='{escape(titulo)}'>"
                    f"<img src='{escape(thumb)}' alt='{escape(titulo)}' loading='lazy'>"
                    f"<span>{escape(titulo)}</span></button>"
                )
            else:
                celdas.append("<div class='matrix-cell empty'>—</div>")

    encabezados = "".join(f"<div class='matrix-label col-label'>s={s}</div>" for s in scales)
    return (
        f"<div class='matrix-grid' style='--cols:{len(scales)}'>"
        f"<div></div>{encabezados}{''.join(celdas)}</div>"
    )


def panel_capas_html(panel_id: str, oculto: bool = False) -> str:
    cls = "panel hidden" if oculto else "panel"
    return f"""
      <div class="{cls}" id="panel-{panel_id}">
        <header id="title-{panel_id}">—</header>
        <div class="zoom-bar">
          <button type="button" class="zoom-btn" data-panel="{panel_id}" data-action="in" title="Acercar">+</button>
          <button type="button" class="zoom-btn" data-panel="{panel_id}" data-action="out" title="Alejar">−</button>
          <button type="button" class="zoom-btn" data-panel="{panel_id}" data-action="reset" title="Restablecer">100%</button>
          <span class="zoom-label" id="zoom-label-{panel_id}">100%</span>
          <span class="zoom-hint">Rueda = zoom · Arrastrar = mover · más detalle al acercar</span>
        </div>
        <div class="zoom-viewport" id="viewport-{panel_id}">
          <div class="zoom-stage" id="stage-{panel_id}">
            <div class="layer-stack" id="stack-{panel_id}">
              <img class="layer layer-mosaic" id="layer-mosaic-{panel_id}" alt="Mosaico" loading="lazy">
              <img class="layer layer-seg" id="layer-seg-{panel_id}" alt="Segmentos TIF" loading="lazy">
              <img class="layer layer-bnd" id="layer-bnd-{panel_id}" alt="Contornos" loading="lazy">
              <img class="layer layer-quicklook" id="layer-quicklook-{panel_id}" alt="Quick-look" loading="lazy">
            </div>
          </div>
        </div>
        <div class="layer-meta" id="meta-{panel_id}"></div>
        <div class="stats-inline" id="stats-{panel_id}"></div>
      </div>"""


def generar_html(
    output_dir: Path,
    html_dir: Path,
    filas: list[dict],
    combinaciones: list[dict],
    tile: str,
    year: str,
    mosaic_tiers: dict[str, str] | None,
) -> str:
    scales = sorted({f["scale"] for f in filas})
    sigmas = sorted({f["sigma"] for f in filas})
    capas_por_clave = {c["clave"]: c for c in combinaciones}

    stats = {
        "n_combinaciones": len(filas),
        "n_segmentos_min": min(f["n_segmentos"] for f in filas) if filas else 0,
        "n_segmentos_max": max(f["n_segmentos"] for f in filas) if filas else 0,
        "tam_medio_ha_min": min(f["tam_medio_ha"] for f in filas) if filas else 0.0,
        "tam_medio_ha_max": max(f["tam_medio_ha"] for f in filas) if filas else 0.0,
    }

    mosaic_tiers = mosaic_tiers or {}

    payload = {
        "filas": filas,
        "combinaciones": combinaciones,
        "capas_por_clave": capas_por_clave,
        "mosaic_tiers": mosaic_tiers,
        "res_tiers": RES_TIERS,
        "scales": scales,
        "sigmas": sigmas,
        "tile": tile,
        "year": year,
        "stats": stats,
    }

    tabla_html = construir_tabla_html(filas)
    matriz_html = construir_matriz_html(combinaciones, scales, sigmas)
    titulo = f"Felzenszwalb — {tile} {year}" if tile and year else "Felzenszwalb grid"
    tiene_capas = bool(mosaic_tiers) and any(c.get("overlay_tiers") for c in combinaciones)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{
  --bg: #f4f6f8; --text: #1f2933; --muted: #627d98; --line: #d9e2ec;
  --hero-a: #0f4c75; --hero-b: #1b6ca8; --card: #fff;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }}
.wrap {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
.hero {{ background: linear-gradient(135deg, var(--hero-a), var(--hero-b)); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px; }}
.hero h1 {{ margin: 0 0 8px; font-size: 1.8rem; }}
.hero p {{ margin: 0; opacity: 0.92; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.kpi {{ background: var(--card); border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.kpi .label {{ font-size: 0.85rem; color: #52606d; margin-bottom: 6px; }}
.kpi .value {{ font-size: 1.45rem; font-weight: 700; color: #102a43; }}
.section {{ background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.section h2 {{ margin: 0 0 16px; font-size: 1.15rem; color: #243b53; border-bottom: 2px solid var(--line); padding-bottom: 8px; }}
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
.panel header {{ background: #102a43; color: #fff; padding: 10px 14px; font-size: 0.92rem; }}
.zoom-bar {{
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #edf2f7; border-bottom: 1px solid var(--line); flex-wrap: wrap;
}}
.zoom-btn {{
  min-width: 34px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px;
  background: #fff; cursor: pointer; font-size: 1rem; line-height: 1.2;
}}
.zoom-label {{ font-size: 0.85rem; color: #334e68; min-width: 48px; font-weight: 600; }}
.zoom-hint {{ font-size: 0.78rem; color: #627d98; margin-left: auto; }}
.zoom-viewport {{
  position: relative; width: 100%; aspect-ratio: 1; overflow: hidden;
  background: #111; cursor: grab; touch-action: none;
}}
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
    <p>Calibración visual Felzenszwalb · <code>{escape(str(output_dir))}</code></p>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="label">Combinaciones</div><div class="value">{stats['n_combinaciones']}</div></div>
    <div class="kpi"><div class="label">Segmentos (min–max)</div><div class="value">{stats['n_segmentos_min']:,} – {stats['n_segmentos_max']:,}</div></div>
    <div class="kpi"><div class="label">Tam. medio (ha)</div><div class="value">{stats['tam_medio_ha_min']:.1f} – {stats['tam_medio_ha_max']:.1f}</div></div>
    <div class="kpi"><div class="label">Scale</div><div class="value">{', '.join(str(s) for s in scales)}</div></div>
    <div class="kpi"><div class="label">Sigma</div><div class="value">{', '.join(f'{s:g}' for s in sigmas)}</div></div>
  </div>

  <section class="section">
    <h2>Explorador de capas</h2>
    <p class="note">Activa capas, ajusta opacidad y usa zoom (rueda del mouse o botones +/−). Arrastra para desplazar cuando hay zoom.</p>
    <div class="layer-controls">
      <label class="row"><input type="checkbox" id="chk-mosaic" checked> Mosaico RGB</label>
      <label class="row"><input type="checkbox" id="chk-seg" checked> Segmentos (TIF)</label>
      <label class="row"><input type="checkbox" id="chk-bnd" checked> Contornos</label>
      <label class="row"><input type="checkbox" id="chk-quicklook"> Quick-look PNG</label>
      <label>Opacidad segmentos
        <input type="range" id="opacity-seg" min="0" max="100" value="62">
      </label>
    </div>
    <div class="controls">
      <label>A scale <select id="sel-scale-a"></select></label>
      <label>A sigma <select id="sel-sigma-a"></select></label>
      <label id="lbl-scale-b" class="hidden">B scale <select id="sel-scale-b"></select></label>
      <label id="lbl-sigma-b" class="hidden">B sigma <select id="sel-sigma-b"></select></label>
      <button type="button" id="btn-compare">Comparar</button>
    </div>
    <div class="viewer" id="viewer">
      {panel_capas_html("a")}
      {panel_capas_html("b", oculto=True)}
    </div>
  </section>

  <section class="section">
    <h2>Matriz scale × sigma</h2>
    {matriz_html}
  </section>

  <section class="section">
    <h2>Métricas del grid</h2>
    <div class="grid-2">
      <div id="chart-segmentos" class="chart"></div>
      <div id="chart-tamano" class="chart"></div>
    </div>
    <div id="chart-heatmap" class="chart" style="margin-top:16px; min-height:320px;"></div>
  </section>

  <section class="section">
    <h2>Tabla resumen</h2>
    {tabla_html}
  </section>
</div>

<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const TIENE_CAPAS = {json.dumps(tiene_capas)};
const RES_TIERS = DATA.res_tiers || [1024, 2048, 4096];
const PANEL = {{
  a: {{ clave: null, tier: RES_TIERS[0], userZoom: 1, panX: 0, panY: 0, fit: 1, imgW: 100, imgH: 100, loading: false }},
  b: {{ clave: null, tier: RES_TIERS[0], userZoom: 1, panX: 0, panY: 0, fit: 1, imgW: 100, imgH: 100, loading: false }},
}};
let SYNC_LOCK = false;

function isCompareMode() {{
  return document.getElementById('viewer').classList.contains('compare');
}}

function peerPanel(sufijo) {{
  return sufijo === 'a' ? 'b' : 'a';
}}

function getViewState(sufijo) {{
  const st = PANEL[sufijo];
  const center = getViewCenter(sufijo);
  return {{
    userZoom: st.userZoom,
    cx: center.cx,
    cy: center.cy,
    tier: st.tier,
  }};
}}

async function applyViewState(sufijo, view) {{
  const st = PANEL[sufijo];
  const needed = tierForZoom(view.userZoom);
  if (needed > st.tier && tierSrc(DATA.mosaic_tiers, needed) && !st.loading) {{
    await loadPanelTier(sufijo, needed, false);
  }}
  st.userZoom = view.userZoom;
  if (view.userZoom === 1) {{
    st.panX = 0;
    st.panY = 0;
  }} else {{
    setViewCenter(sufijo, view.cx, view.cy);
  }}
  aplicarZoomTransform(sufijo, true);
}}

function syncPeerView(source) {{
  if (SYNC_LOCK || !isCompareMode()) return;
  const peer = peerPanel(source);
  if (document.getElementById(`panel-${{peer}}`).classList.contains('hidden')) return;
  SYNC_LOCK = true;
  applyViewState(peer, getViewState(source)).finally(() => {{ SYNC_LOCK = false; }});
}}

function claveFila(fila) {{
  return `s${{fila.scale}}_sig${{String(fila.sigma).replace('.', '_')}}`;
}}

function capaPorClave(clave) {{
  return DATA.capas_por_clave[clave] || null;
}}

function filaPorClave(clave) {{
  return DATA.filas.find(f => claveFila(f) === clave);
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

function tierForZoom(userZoom) {{
  if (userZoom >= 3.5) return RES_TIERS[Math.min(2, RES_TIERS.length - 1)];
  if (userZoom >= 1.8) return RES_TIERS[Math.min(1, RES_TIERS.length - 1)];
  return RES_TIERS[0];
}}

function loadImageEl(el, src) {{
  return new Promise(resolve => {{
    if (!src) {{
      el.removeAttribute('src');
      el.style.display = 'none';
      resolve(null);
      return;
    }}
    if (el.getAttribute('src') === src && el.complete && el.naturalWidth) {{
      resolve(el);
      return;
    }}
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
  const capa = capaPorClave(st.clave);
  const mosaicSrc = tierSrc(DATA.mosaic_tiers, tier);
  const segSrc = capa ? tierSrc(capa.overlay_tiers, tier) : null;
  const bndSrc = capa ? tierSrc(capa.boundaries_tiers, tier) : null;
  const center = preserveView ? getViewCenter(sufijo) : null;

  st.loading = true;
  const mosaic = document.getElementById(`layer-mosaic-${{sufijo}}`);
  const seg = document.getElementById(`layer-seg-${{sufijo}}`);
  const bnd = document.getElementById(`layer-bnd-${{sufijo}}`);
  const ql = document.getElementById(`layer-quicklook-${{sufijo}}`);

  if (capa && capa.png) {{
    ql.src = capa.png;
    ql.style.display = 'block';
  }} else {{
    ql.removeAttribute('src');
    ql.style.display = 'none';
  }}

  const loadedMosaic = await loadImageEl(mosaic, mosaicSrc);
  await Promise.all([
    loadImageEl(seg, segSrc),
    loadImageEl(bnd, bndSrc),
  ]);

  const imgW = loadedMosaic ? loadedMosaic.naturalWidth : 100;
  const imgH = loadedMosaic ? loadedMosaic.naturalHeight : 100;
  const stage = document.getElementById(`stage-${{sufijo}}`);
  stage.style.width = `${{imgW}}px`;
  stage.style.height = `${{imgH}}px`;

  const vp = document.getElementById(`viewport-${{sufijo}}`);
  const rect = vp.getBoundingClientRect();
  st.fit = Math.min(rect.width / imgW, rect.height / imgH);
  st.imgW = imgW;
  st.imgH = imgH;
  st.tier = tier;
  st.loading = false;

  if (!preserveView) {{
    st.userZoom = 1;
    st.panX = 0;
    st.panY = 0;
  }} else if (center) {{
    setViewCenter(sufijo, center.cx, center.cy);
  }}
  aplicarZoomTransform(sufijo);
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
  if (needed > st.tier && tierSrc(DATA.mosaic_tiers, needed) && !st.loading) {{
    loadPanelTier(sufijo, needed, true);
    return;
  }}

  if (!noSync) syncPeerView(sufijo);
}}

function resetZoom(sufijo) {{
  const st = PANEL[sufijo];
  st.userZoom = 1;
  st.panX = 0;
  st.panY = 0;
  if (st.tier !== RES_TIERS[0]) {{
    loadPanelTier(sufijo, RES_TIERS[0], false);
  }} else {{
    aplicarZoomTransform(sufijo);
  }}
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
  if (st.userZoom === 1) {{
    st.panX = 0;
    st.panY = 0;
  }}
  aplicarZoomTransform(sufijo);
}}

function initZoom(sufijo) {{
  const viewport = document.getElementById(`viewport-${{sufijo}}`);
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let startPanX = 0;
  let startPanY = 0;

  viewport.addEventListener('wheel', (e) => {{
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    zoomFactor(sufijo, factor, e.clientX, e.clientY);
  }}, {{ passive: false }});

  viewport.addEventListener('mousedown', (e) => {{
    if (e.button !== 0) return;
    dragging = true;
    viewport.classList.add('dragging');
    startX = e.clientX;
    startY = e.clientY;
    startPanX = PANEL[sufijo].panX;
    startPanY = PANEL[sufijo].panY;
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
}}

async function mostrarPanel(sufijo, clave) {{
  const fila = filaPorClave(clave);
  const capa = capaPorClave(clave);

  document.getElementById(`title-${{sufijo}}`).textContent = fila
    ? `s=${{fila.scale}}, σ=${{fila.sigma}} · ${{fmtInt(fila.n_segmentos)}} segmentos`
    : 'Sin datos';

  if (capa) {{
    const tifLink = capa.tif ? `<a href="${{capa.tif}}" download>Descargar GeoTIFF</a>` : '';
    document.getElementById(`meta-${{sufijo}}`).innerHTML = tifLink
      ? `${{tifLink}} · resolución progresiva al acercar`
      : '';
  }} else {{
    document.getElementById(`meta-${{sufijo}}`).innerHTML = '';
  }}

  document.getElementById(`stats-${{sufijo}}`).innerHTML = statsHtml(fila);
  PANEL[sufijo].clave = clave;

  if (isCompareMode() && sufijo === 'b' && PANEL.a.clave) {{
    const view = getViewState('a');
    await loadPanelTier(sufijo, view.tier, false);
    await applyViewState(sufijo, view);
    return;
  }}

  await loadPanelTier(sufijo, RES_TIERS[0], false);
}}

function seleccion(clave) {{
  const fila = filaPorClave(clave);
  if (!fila) return;
  document.getElementById('sel-scale-a').value = String(fila.scale);
  document.getElementById('sel-sigma-a').value = String(fila.sigma);
  mostrarPanel('a', clave).then(() => {{
    if (isCompareMode()) syncPeerView('a');
  }});
  document.querySelectorAll('.matrix-cell[data-key]').forEach(el => {{
    el.classList.toggle('selected', el.dataset.key === clave);
  }});
  document.querySelectorAll('.fila-resumen').forEach(el => {{
    el.classList.toggle('selected', el.dataset.key === clave);
  }});
}}

function seleccionB() {{
  const scale = document.getElementById('sel-scale-b').value;
  const sigma = document.getElementById('sel-sigma-b').value;
  return mostrarPanel('b', `s${{scale}}_sig${{String(sigma).replace('.', '_')}}`);
}}

function toggleCompare() {{
  const btn = document.getElementById('btn-compare');
  const viewer = document.getElementById('viewer');
  const panelB = document.getElementById('panel-b');
  const show = !btn.classList.contains('active');
  btn.classList.toggle('active', show);
  btn.textContent = show ? 'Una vista' : 'Comparar';
  viewer.classList.toggle('compare', show);
  panelB.classList.toggle('hidden', !show);
  document.getElementById('lbl-scale-b').classList.toggle('hidden', !show);
  document.getElementById('lbl-sigma-b').classList.toggle('hidden', !show);
  if (show) {{
    seleccionB().then(() => syncPeerView('a'));
  }}
}}

function renderCharts() {{
  const tracesSeg = DATA.sigmas.map(sigma => ({{
    x: DATA.scales,
    y: DATA.scales.map(scale => {{
      const f = DATA.filas.find(r => r.scale === scale && r.sigma === sigma);
      return f ? f.n_segmentos : null;
    }}),
    mode: 'lines+markers', name: `σ=${{sigma}}`,
    hovertemplate: 'scale=%{{x}}<br>segmentos=%{{y:,}}<extra></extra>'
  }}));
  Plotly.newPlot('chart-segmentos', tracesSeg, {{
    title: 'Número de segmentos vs scale',
    xaxis: {{ title: 'scale', dtick: 1 }}, yaxis: {{ title: 'n segmentos' }},
    margin: {{ t: 50, l: 50, r: 20, b: 50 }}, legend: {{ orientation: 'h', y: -0.2 }}
  }}, {{ responsive: true }});

  const tracesTam = DATA.sigmas.map(sigma => ({{
    x: DATA.scales,
    y: DATA.scales.map(scale => {{
      const f = DATA.filas.find(r => r.scale === scale && r.sigma === sigma);
      return f ? f.tam_medio_ha : null;
    }}),
    mode: 'lines+markers', name: `σ=${{sigma}}`,
    hovertemplate: 'scale=%{{x}}<br>tam. medio=%{{y:.2f}} ha<extra></extra>'
  }}));
  Plotly.newPlot('chart-tamano', tracesTam, {{
    title: 'Tamaño medio de segmento vs scale',
    xaxis: {{ title: 'scale', dtick: 1 }}, yaxis: {{ title: 'tam. medio (ha)' }},
    margin: {{ t: 50, l: 50, r: 20, b: 50 }}, legend: {{ orientation: 'h', y: -0.2 }}
  }}, {{ responsive: true }});

  const z = DATA.sigmas.map(sigma => DATA.scales.map(scale => {{
    const f = DATA.filas.find(r => r.scale === scale && r.sigma === sigma);
    return f ? f.n_segmentos : null;
  }}));
  Plotly.newPlot('chart-heatmap', [{{
    z, x: DATA.scales.map(String), y: DATA.sigmas.map(s => `σ=${{s}}`),
    type: 'heatmap', colorscale: 'Blues',
    hovertemplate: 'scale=%{{x}}<br>%{{y}}<br>segmentos=%{{z:,}}<extra></extra>'
  }}], {{
    title: 'Mapa de calor: segmentos (scale × sigma)',
    margin: {{ t: 50, l: 70, r: 20, b: 50 }}
  }}, {{ responsive: true }});
}}

function init() {{
  llenarSelect('sel-scale-a', DATA.scales);
  llenarSelect('sel-scale-b', DATA.scales);
  llenarSelect('sel-sigma-a', DATA.sigmas, s => `σ=${{s}}`);
  llenarSelect('sel-sigma-b', DATA.sigmas, s => `σ=${{s}}`);

  ['chk-mosaic','chk-seg','chk-bnd','chk-quicklook','opacity-seg'].forEach(id => {{
    document.getElementById(id).addEventListener('input', () => {{
      aplicarVisibilidadCapas('a');
      if (!document.getElementById('panel-b').classList.contains('hidden')) {{
        aplicarVisibilidadCapas('b');
      }}
    }});
  }});

  const primera = DATA.filas[0];
  if (primera) {{
    document.getElementById('sel-scale-a').value = String(primera.scale);
    document.getElementById('sel-sigma-a').value = String(primera.sigma);
    document.getElementById('sel-scale-b').value = String(DATA.scales[Math.min(1, DATA.scales.length - 1)]);
    document.getElementById('sel-sigma-b').value = String(DATA.sigmas[0]);
    seleccion(claveFila(primera));
  }}

  ['sel-scale-a', 'sel-sigma-a'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => {{
      const scale = document.getElementById('sel-scale-a').value;
      const sigma = document.getElementById('sel-sigma-a').value;
      seleccion(`s${{scale}}_sig${{String(sigma).replace('.', '_')}}`);
    }});
  }});
  ['sel-scale-b', 'sel-sigma-b'].forEach(id => {{
    document.getElementById(id).addEventListener('change', seleccionB);
  }});
  document.getElementById('btn-compare').addEventListener('click', toggleCompare);
  document.querySelectorAll('.matrix-cell[data-key]').forEach(el => {{
    el.addEventListener('click', () => seleccion(el.dataset.key));
  }});
  document.querySelectorAll('.fila-resumen').forEach(el => {{
    el.addEventListener('click', () => seleccion(el.dataset.key));
  }});

  if (!TIENE_CAPAS) {{
    document.querySelector('.layer-controls').insertAdjacentHTML('beforeend',
      '<span style="color:#b45309;font-size:0.88rem">Capas no exportadas — ejecuta visualize_seg_felzenszwalb_grid.py sin --skip-capas</span>');
  }}

  initZoom('a');
  initZoom('b');
  renderCharts();
}}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera dashboard HTML de segmentación Felzenszwalb.")
    parser.add_argument("--output-dir", type=Path, default=Path(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--mosaic-dir", type=Path, default=Path(DEFAULT_MOSAIC_DIR))
    parser.add_argument("--html", type=Path, default=None)
    parser.add_argument(
        "--skip-capas",
        action="store_true",
        help="No regenerar PNG de mosaico/overlay (usar capas existentes en capas/)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if not output_dir.is_dir():
        print(f"[ERROR] OUTPUT_DIR no existe: {output_dir}")
        sys.exit(1)

    ruta_csv = buscar_resumen(output_dir)
    if ruta_csv is None:
        print(f"[ERROR] No se encontró resumen_*.csv en {output_dir}")
        sys.exit(1)

    filas, tile, year = cargar_resumen(ruta_csv)
    if not filas:
        print(f"[ERROR] CSV vacío: {ruta_csv}")
        sys.exit(1)

    html_path = (args.html or (output_dir / "viewer_felzenszwalb.html")).resolve()
    html_dir = html_path.parent

    mosaic_tiers: dict[str, str] = {}
    capas_dir = output_dir / CAPAS_SUBDIR
    if not args.skip_capas:
        rel_tiers = exportar_capas(output_dir, args.mosaic_dir, tile, year)
        if rel_tiers:
            mosaic_tiers = {
                k: ruta_publica(html_dir, output_dir / v) for k, v in rel_tiers.items()
            }
    else:
        mosaic_tiers = descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)
        if mosaic_tiers:
            print(f"[INFO] Mosaico multi-res: {', '.join(mosaic_tiers.keys())} px")

    combinaciones = descubrir_combinaciones(output_dir, html_dir)
    if not combinaciones:
        print(f"[ADVERTENCIA] No se encontraron TIF/PNG seg_* en {output_dir}")

    contenido = generar_html(output_dir, html_dir, filas, combinaciones, tile, year, mosaic_tiers)

    try:
        html_path.write_text(contenido, encoding="utf-8")
    except OSError as exc:
        fallback = Path(__file__).resolve().parent / "viewer_felzenszwalb.html"
        print(f"[ADVERTENCIA] No se pudo escribir en {html_path}: {exc}")
        print(f"[INFO] Guardando en: {fallback}")
        html_path = fallback
        html_dir = html_path.parent
        html_path.write_text(contenido, encoding="utf-8")

    print(f"[OK] Dashboard: {html_path}")
    print(f"[OK] Combinaciones: {len(combinaciones)} · Capas: {capas_dir if capas_dir.exists() else '—'}")
    print(f"[INFO] Servir: cd {output_dir} && python3 -m http.server 8765")
    print(f"[INFO] URL: http://localhost:8765/viewer_felzenszwalb.html")


if __name__ == "__main__":
    main()
