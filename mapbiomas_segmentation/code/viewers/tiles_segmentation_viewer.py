#!/usr/bin/env python3
"""
Visualizador multi-tile de segmentación (Felzenszwalb + SLIC).

Muestra los 6 tiles MGRS en una vista comparativa con explorador de capas
(mosaico, overlay, contornos) y zoom/pan por tile.

Uso:
  cd coverage_test/labeling/image_segmentation
  python tiles_segmentation_viewer.py
  python tiles_segmentation_viewer.py --skip-layers
  python tiles_segmentation_viewer.py --segmenters felzenszwalb,slic --skip-layers

Servir:
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765 --bind 0.0.0.0
  → http://localhost:8765/tiles_segmentation_viewer.html
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
    estadisticas_segmentos,
    localizar_mosaico_tile,
)
import visualize_seg_felzenszwalb_grid as viz  # noqa: E402

TILES = ("18HYD", "18FXH", "18GXP", "19HCD", "19JCJ", "19KDU")
DEFAULT_YEAR = 2010
DEFAULT_HTML = _DATA_ROOT / "tiles_segmentation_viewer.html"
CAPAS_SUBDIR = viz.CAPAS_SUBDIR
RES_TIERS = viz.RES_TIERS
TIF_PATTERN = viz.TIF_PATTERN

SEGMENTADORES: dict[str, dict] = {
    "felzenszwalb": {
        "label": "Felzenszwalb",
        "color": "#1b6ca8",
        "output_dir": FELZ_OUTPUT_DIR,
        "incluir_rag": False,
    },
    "slic": {
        "label": "SLIC",
        "color": "#059669",
        "output_dir": _DATA_ROOT / "seg_slic" / "pipeline_a",
        "incluir_rag": True,
    },
}


def ruta_publica(html_dir: Path, archivo: Path) -> str:
    import os

    return os.path.relpath(archivo.resolve(), html_dir.resolve()).replace("\\", "/")


def cargar_resumen_tile(output_dir: Path, tile: str, year: int) -> list[dict]:
    ruta = output_dir / f"resumen_{tile}_{year}.csv"
    if not ruta.is_file():
        return []
    filas, _, _ = viz.cargar_resumen(ruta)
    return filas


def stats_desde_tif(ruta_tif: Path, mosaic_dir: Path, tile: str, year: int) -> dict:
    import numpy as np
    import rasterio
    from seg_felzenszwalb_grid import NODATA, construir_mascara_nodata, resolver_nodata

    match = TIF_PATTERN.match(ruta_tif.name)
    if not match:
        return {}

    ruta_mosaico = localizar_mosaico_tile(mosaic_dir, tile, year)
    with rasterio.open(ruta_mosaico) as mos:
        nodata_valor = resolver_nodata(mos, NODATA)
        datos = np.stack([mos.read(i + 1) for i in range(mos.count)], axis=-1).astype(np.float32)
        validos = construir_mascara_nodata(datos, nodata_valor)

    with rasterio.open(ruta_tif) as seg:
        labels = seg.read(1).astype(np.int32)

    stats = estadisticas_segmentos(labels, validos)
    return {
        "scale": int(float(match.group("scale"))),
        "sigma": float(match.group("sigma")),
        "min_size": 20,
        **stats,
    }


def descubrir_combinaciones_tile(
    output_dir: Path,
    html_dir: Path,
    tile: str,
    year: int,
    mosaic_dir: Path,
    incluir_rag: bool = False,
    compute_stats: bool = True,
) -> tuple[list[dict], list[dict]]:
    filas_csv = cargar_resumen_tile(output_dir, tile, year)
    csv_por_clave = {viz.fila_a_clave(f): f for f in filas_csv}

    todas = viz.descubrir_combinaciones(output_dir, html_dir, incluir_rag=incluir_rag)
    combinaciones: list[dict] = []
    for entrada in todas:
        if entrada.get("tile") != tile or str(entrada.get("year")) != str(year):
            continue
        clave = entrada["clave"]
        fila = csv_por_clave.get(clave)
        if fila is None and compute_stats and not entrada.get("rag_percentil"):
            ruta_tif = (html_dir / entrada["tif"]).resolve()
            if not ruta_tif.is_file():
                ruta_tif = output_dir / Path(entrada["tif"]).name
            if ruta_tif.is_file() and TIF_PATTERN.match(ruta_tif.name):
                fila = stats_desde_tif(ruta_tif, mosaic_dir, tile, year)
        if fila is None:
            fila = {
                "scale": entrada["scale"],
                "sigma": entrada["sigma"],
                "min_size": 20,
                "rag_percentil": entrada.get("rag_percentil"),
            }

        combinaciones.append(
            {
                "clave": clave,
                "scale": entrada["scale"],
                "sigma": entrada["sigma"],
                "rag_percentil": entrada.get("rag_percentil"),
                "fila": fila,
                "tif": entrada["tif"],
                "png": entrada.get("png") or "",
                "overlay_tiers": entrada.get("overlay_tiers") or {},
                "boundaries_tiers": entrada.get("boundaries_tiers") or {},
            }
        )

    combinaciones.sort(
        key=lambda c: (
            c["scale"],
            c["sigma"],
            c.get("rag_percentil") is not None,
            c.get("rag_percentil") or 0,
        )
    )
    return combinaciones, filas_csv


TIF_RAG_S50_PATTERN = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s50_sig0\.1_ragp(?P<pct>\d+)\.tif$"
)


def filtrar_tifs_export(
    tifs_tile: list[Path], tile: str, year: int, modo: str
) -> list[Path]:
    """modo: full (18HYD grid+RAG), s50_rag (s50 σ0.1 base+RAG), base (sin RAG)."""
    if modo == "full":
        return tifs_tile
    pref = f"seg_{tile}_{year}_s50_sig0.1"
    if modo == "s50_rag":
        return sorted(
            p
            for p in tifs_tile
            if p.name == f"{pref}.tif" or p.name.startswith(f"{pref}_ragp")
        )
    return [p for p in tifs_tile if TIF_PATTERN.match(p.name)]


def exportar_capas_tile(
    output_dir: Path,
    mosaic_dir: Path,
    tile: str,
    year: int,
    incluir_rag: bool = False,
    export_modo: str = "base",
    force: bool = False,
) -> dict[str, str] | None:
    capas_dir = output_dir / CAPAS_SUBDIR
    mosaic_stem = f"mosaic_{tile}_{year}_rgb"
    mosaic_ok = all((capas_dir / f"{mosaic_stem}_l{t}.png").is_file() for t in RES_TIERS)

    all_tifs = viz.listar_tifs_segmentacion(output_dir, incluir_rag=incluir_rag)
    tifs_tile = filtrar_tifs_export(
        sorted(p for p in all_tifs if p.name.startswith(f"seg_{tile}_{year}_")),
        tile,
        year,
        export_modo,
    )
    overlays_ok = True
    for ruta_tif in tifs_tile:
        base = ruta_tif.stem
        if not all((capas_dir / f"{base}_overlay_l{t}.png").is_file() for t in RES_TIERS):
            overlays_ok = False
            break

    if mosaic_ok and overlays_ok and not force:
        return viz.descubrir_mosaic_tiers(_DATA_ROOT, capas_dir, tile, str(year))

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
            overlay_rgba_desde_labels,
            reducir_para_quicklook,
            resolver_nodata,
        )
        from PIL import Image
    except ImportError as exc:
        print(f"[ADVERTENCIA] No se exportan capas para {tile} (faltan dependencias): {exc}")
        return None

    capas_dir.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = localizar_mosaico_tile(mosaic_dir, tile, year)
    mosaic_tiers: dict[str, str] = {}

    print(f"[INFO] Exportando capas {tile} {year} → {capas_dir}")

    with rasterio.open(ruta_mosaico) as src:
        datos = np.stack([src.read(i + 1) for i in range(src.count)], axis=-1).astype(np.float32)
        nodata_valor = resolver_nodata(src, NODATA)
        validos = construir_mascara_nodata(datos, nodata_valor)
        rgb = componer_rgb(datos, DISPLAY_BANDS, validos)
        rgb = np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0)

    labels_vacio = np.zeros(validos.shape, dtype=np.int32)
    if not mosaic_ok or force:
        for lado in RES_TIERS:
            rgb_q, _, _ = reducir_para_quicklook(rgb, labels_vacio, validos, lado)
            fname = f"{mosaic_stem}_l{lado}.png"
            Image.fromarray((np.clip(rgb_q, 0, 1) * 255).astype(np.uint8), mode="RGB").save(
                capas_dir / fname
            )
            mosaic_tiers[str(lado)] = f"{CAPAS_SUBDIR}/{fname}"
            print(f"  → {fname}")

    for ruta_tif in tifs_tile:
        base = ruta_tif.stem
        if not force and all((capas_dir / f"{base}_overlay_l{t}.png").is_file() for t in RES_TIERS):
            continue
        with rasterio.open(ruta_tif) as seg:
            labels = seg.read(1).astype(np.int32)
        if labels.shape != validos.shape:
            print(f"[ERROR] Shape distinta {ruta_tif.name}: {labels.shape} vs {validos.shape}")
            continue
        for lado in RES_TIERS:
            rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos, lado)
            guardar_rgba_png(capas_dir / f"{base}_overlay_l{lado}.png", overlay_rgba_desde_labels(labels_q, validos_q))
            guardar_rgba_png(
                capas_dir / f"{base}_boundaries_l{lado}.png",
                contornos_rgba_desde_labels(labels_q, validos_q, labels_ref=labels, validos_ref=validos),
            )
        print(f"  → {base}_overlay/boundaries_l*.png")

    if not mosaic_tiers:
        mosaic_tiers = {
            str(t): f"{CAPAS_SUBDIR}/{mosaic_stem}_l{t}.png" for t in RES_TIERS
        }
    return mosaic_tiers


def elegir_default(combinaciones: list[dict], prefer_base: bool = False) -> str | None:
    if not combinaciones:
        return None
    for pref_scale, pref_sigma in ((50, 0.1), (100, 0.1), (50, 0.5)):
        for c in combinaciones:
            if c["scale"] != pref_scale or c["sigma"] != pref_sigma:
                continue
            if prefer_base and c.get("rag_percentil") not in (None, ""):
                continue
            return c["clave"]
    for c in combinaciones:
        if not prefer_base or c.get("rag_percentil") in (None, ""):
            return c["clave"]
    return combinaciones[0]["clave"]


def mosaic_fallback_felzenszwalb(html_dir: Path, tile: str, year: int) -> dict[str, str]:
    capas_dir = Path(FELZ_OUTPUT_DIR) / CAPAS_SUBDIR
    return viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, str(year))


def construir_datos_segmentador(
    seg_id: str,
    config: dict,
    mosaic_dir: Path,
    html_dir: Path,
    tiles: tuple[str, ...],
    year: int,
    skip_layers: bool,
    mosaic_fallback: dict[str, dict[str, str]] | None = None,
) -> dict:
    output_dir = Path(config["output_dir"])
    incluir_rag = config.get("incluir_rag", False)
    tiles_data: dict = {}

    for tile in tiles:
        if not skip_layers:
            export_modo = "full" if (incluir_rag and tile == "18HYD") else (
                "s50_rag" if incluir_rag else "base"
            )
            exportar_capas_tile(
                output_dir,
                mosaic_dir,
                tile,
                year,
                incluir_rag=incluir_rag,
                export_modo=export_modo,
            )

        combinaciones, filas_csv = descubrir_combinaciones_tile(
            output_dir,
            html_dir,
            tile,
            year,
            mosaic_dir,
            incluir_rag=incluir_rag,
            compute_stats=not skip_layers,
        )
        capas_dir = output_dir / CAPAS_SUBDIR
        mosaic_tiers_rel = viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, str(year))
        if not mosaic_tiers_rel:
            if mosaic_fallback and tile in mosaic_fallback:
                mosaic_tiers_rel = mosaic_fallback[tile]
            elif seg_id == "slic":
                mosaic_tiers_rel = mosaic_fallback_felzenszwalb(html_dir, tile, year)

        # Re-leer tiers de overlay/boundaries por si se exportaron después
        for combo in combinaciones:
            base = Path(combo["tif"]).name.replace(".tif", "")
            combo["overlay_tiers"] = viz.descubrir_tiers_capa(
                html_dir, capas_dir, base, "overlay"
            ) or combo.get("overlay_tiers") or {}
            combo["boundaries_tiers"] = viz.descubrir_tiers_capa(
                html_dir, capas_dir, base, "boundaries"
            ) or combo.get("boundaries_tiers") or {}
        default_clave = elegir_default(combinaciones, prefer_base=incluir_rag)

        thumb = ""
        if default_clave:
            combo = next(c for c in combinaciones if c["clave"] == default_clave)
            tiers = combo.get("overlay_tiers") or {}
            thumb = tiers.get("1024") or combo.get("png") or ""

        mosaic_thumb = mosaic_tiers_rel.get("1024", "")

        n_seg = [
            c["fila"]["n_segmentos"]
            for c in combinaciones
            if c.get("fila") and "n_segmentos" in c["fila"]
        ]
        rag_pcts = sorted(
            {
                int(c["rag_percentil"])
                for c in combinaciones
                if c.get("rag_percentil") not in (None, "")
            }
        )
        tiles_data[tile] = {
            "tile": tile,
            "year": year,
            "n_combinaciones": len(combinaciones),
            "n_segmentos_min": min(n_seg) if n_seg else 0,
            "n_segmentos_max": max(n_seg) if n_seg else 0,
            "default_clave": default_clave,
            "mosaic_tiers": mosaic_tiers_rel,
            "mosaic_thumb": mosaic_thumb,
            "thumb_overlay": thumb,
            "combinaciones": combinaciones,
            "filas": filas_csv,
            "rag_percentiles": rag_pcts,
            "tiene_datos": bool(combinaciones),
        }

    return {
        "id": seg_id,
        "label": config["label"],
        "color": config["color"],
        "incluir_rag": incluir_rag,
        "tiles": tiles_data,
    }


def construir_datos(
    mosaic_dir: Path,
    html_dir: Path,
    tiles: tuple[str, ...],
    year: int,
    skip_layers: bool,
    segmenter_ids: tuple[str, ...],
) -> dict:
    segmenters: dict = {}
    felz_mosaics: dict[str, dict[str, str]] = {}
    if "felzenszwalb" in segmenter_ids:
        felz = construir_datos_segmentador(
            "felzenszwalb",
            SEGMENTADORES["felzenszwalb"],
            mosaic_dir,
            html_dir,
            tiles,
            year,
            skip_layers,
        )
        segmenters["felzenszwalb"] = felz
        felz_mosaics = {t: d["mosaic_tiers"] for t, d in felz["tiles"].items() if d["mosaic_tiers"]}

    for seg_id in segmenter_ids:
        if seg_id == "felzenszwalb":
            continue
        if seg_id not in SEGMENTADORES:
            print(f"[ERROR] Segmentador desconocido: {seg_id}")
            sys.exit(1)
        segmenters[seg_id] = construir_datos_segmentador(
            seg_id,
            SEGMENTADORES[seg_id],
            mosaic_dir,
            html_dir,
            tiles,
            year,
            skip_layers,
            mosaic_fallback=felz_mosaics,
        )
    return {"year": year, "segmenters": segmenters}


def construir_datos_tiles(
    output_dir: Path,
    mosaic_dir: Path,
    html_dir: Path,
    tiles: tuple[str, ...],
    year: int,
    skip_layers: bool,
) -> dict:
    """Compat: solo Felzenszwalb."""
    return construir_datos(mosaic_dir, html_dir, tiles, year, skip_layers, ("felzenszwalb",))


def generar_html(datos: dict) -> str:
    payload = json.dumps(datos, ensure_ascii=False)
    year = datos["year"]
    seg_labels = " · ".join(s["label"] for s in datos["segmenters"].values())

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Segmentación multi-tile — {year}</title>
<style>
:root {{
  --bg: #f0f4f8; --text: #102a43; --muted: #627d98; --line: #d9e2ec;
  --hero-a: #0f4c75; --hero-b: #1b6ca8; --card: #fff;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); }}
.wrap {{ max-width: 1480px; margin: 0 auto; padding: 24px; }}
.hero {{
  background: linear-gradient(135deg, var(--hero-a), var(--hero-b) 45%, #059669);
  color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;
}}
.hero h1 {{ margin: 0 0 8px; font-size: 1.75rem; }}
.hero p {{ margin: 0; opacity: 0.92; font-size: 0.95rem; }}
.section {{
  background: var(--card); border-radius: 12px; padding: 20px;
  margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}}
.section h2 {{
  margin: 0 0 16px; font-size: 1.12rem; color: #243b53;
  border-bottom: 2px solid var(--line); padding-bottom: 8px;
}}
.tiles-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;
}}
.tile-card {{
  border: 2px solid var(--line); border-radius: 10px; overflow: hidden;
  cursor: pointer; background: #fff; transition: border-color .15s, box-shadow .15s;
}}
.tile-card:hover {{ border-color: #94a3b8; box-shadow: 0 4px 12px rgba(0,0,0,.1); }}
.tile-card.active {{ border-color: var(--hero-b); box-shadow: 0 0 0 3px rgba(27,108,168,.25); }}
.tile-card.no-data {{ opacity: 0.55; cursor: not-allowed; }}
.tile-preview {{ position: relative; aspect-ratio: 1; background: #111; }}
.tile-preview img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
.tile-preview .mosaic {{ z-index: 1; }}
.tile-preview .overlay {{ z-index: 2; opacity: 0.55; }}
.tile-info {{ padding: 10px 12px; }}
.tile-info .name {{ font-weight: 700; font-size: 1rem; }}
.tile-info .meta {{ font-size: 0.82rem; color: var(--muted); margin-top: 4px; }}
.controls {{
  display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 16px;
}}
.controls label {{
  display: flex; flex-direction: column; gap: 6px;
  font-size: 0.88rem; color: #486581;
}}
.controls label.row {{
  flex-direction: row; align-items: center; gap: 8px;
  padding: 8px 12px; background: #f0f4f8; border-radius: 8px; border: 1px solid var(--line);
}}
.controls select, .controls input[type=range] {{ font-size: 0.95rem; }}
.controls select {{ min-width: 120px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; }}
.zoom-bar {{
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #edf2f7; border-bottom: 1px solid var(--line); flex-wrap: wrap;
}}
.zoom-btn {{
  min-width: 34px; padding: 4px 10px; border: 1px solid var(--line);
  border-radius: 6px; background: #fff; cursor: pointer;
}}
.zoom-label {{ font-size: 0.85rem; color: #334e68; min-width: 120px; font-weight: 600; }}
.zoom-hint {{ font-size: 0.78rem; color: #627d98; margin-left: auto; }}
.zoom-viewport {{
  position: relative; width: 100%; aspect-ratio: 1; overflow: hidden;
  background: #111; cursor: grab; touch-action: none;
}}
.zoom-viewport.dragging {{ cursor: grabbing; }}
.zoom-stage {{ transform-origin: 0 0; will-change: transform; position: relative; }}
.layer-stack {{ position: relative; width: 100%; height: 100%; }}
.layer-stack .layer {{
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: fill; image-rendering: auto;
}}
.layer-stack .layer.hidden-layer {{ visibility: hidden; opacity: 0; }}
.stats-inline {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px; padding: 12px; background: #fff;
}}
.stat-chip {{ background: #f0f4f8; border-radius: 8px; padding: 10px 12px; }}
.stat-chip .k {{ font-size: 0.78rem; color: #627d98; }}
.stat-chip .v {{ font-size: 1rem; font-weight: 600; color: #102a43; }}
.layer-meta {{ padding: 8px 14px; background: #f7fafc; font-size: 0.82rem; color: #486581; border-top: 1px solid var(--line); }}
.layer-meta a {{ color: #1b6ca8; }}
.badge {{
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 0.75rem; font-weight: 600;
}}
.badge.ok {{ background: #d1fae5; color: #065f46; }}
.badge.pending {{ background: #fef3c7; color: #92400e; }}
.hidden {{ display: none !important; }}
@media (max-width: 768px) {{ .tiles-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Segmentación multi-tile — 6 tiles MGRS</h1>
    <p>{seg_labels} · año {year} · comparación visual por tile</p>
  </header>

  <section class="section">
    <h2>Vista general — <span id="overview-seg-label">—</span></h2>
    <p style="color:var(--muted);font-size:0.92rem;margin:0 0 14px">
      Selecciona segmentador abajo. SLIC incluye variantes RAG (p10/p20/p30) en s50 σ=0.1 para todos los tiles.
    </p>
    <div class="controls" style="margin-bottom:14px">
      <label>Segmentador
        <select id="sel-segmenter"></select>
      </label>
    </div>
    <div class="tiles-grid" id="tiles-grid"></div>
  </section>

  <section class="section" id="detail-section">
    <h2>Explorador — <span id="detail-tile-name">—</span></h2>
    <div class="controls">
      <label>Segmentador
        <select id="sel-segmenter-detail"></select>
      </label>
      <label>Tile
        <select id="sel-tile"></select>
      </label>
      <label>Scale
        <select id="sel-scale"></select>
      </label>
      <label>Sigma
        <select id="sel-sigma"></select>
      </label>
      <label id="lbl-rag" class="hidden">RAG
        <select id="sel-rag"></select>
      </label>
      <label class="row"><input type="checkbox" id="chk-mosaic" checked> Mosaico RGB</label>
      <label class="row"><input type="checkbox" id="chk-seg" checked> Overlay segmentos</label>
      <label class="row"><input type="checkbox" id="chk-bnd"> Contornos</label>
      <label>Opacidad overlay
        <input type="range" id="opacity-seg" min="0" max="100" value="55">
      </label>
    </div>
    <div class="panel" style="border:1px solid var(--line);border-radius:10px;overflow:hidden">
      <div class="zoom-bar">
        <button class="zoom-btn" data-action="out">−</button>
        <span class="zoom-label" id="zoom-label">100%</span>
        <button class="zoom-btn" data-action="in">+</button>
        <button class="zoom-btn" data-action="reset">Reset</button>
        <span class="zoom-hint">Rueda = zoom · arrastrar = pan</span>
      </div>
      <div class="zoom-viewport" id="viewport">
        <div class="zoom-stage" id="stage">
          <div class="layer-stack" id="layer-stack">
            <img class="layer" id="layer-mosaic" alt="mosaic">
            <img class="layer" id="layer-seg" alt="segments">
            <img class="layer hidden-layer" id="layer-bnd" alt="boundaries">
          </div>
        </div>
      </div>
      <div class="stats-inline" id="stats-panel"></div>
      <div class="layer-meta" id="layer-meta"></div>
    </div>
  </section>
</div>

<script>
const DATA = {payload};
const RES_TIERS = [1024, 2048, 4096];
let currentSeg = Object.keys(DATA.segmenters)[0];
const VIEW = {{
  fit: 1, userZoom: 1, panX: 0, panY: 0, clave: null, tile: null,
  imgW: 1024, imgH: 1024, tier: 1024, loading: false, contentKey: '',
}};

function fmtInt(n) {{ return n == null ? '—' : Number(n).toLocaleString('es-CL'); }}
function fmtFloat(n, d=2) {{ return n == null ? '—' : Number(n).toFixed(d); }}

function segData(segId) {{ return DATA.segmenters[segId || currentSeg]; }}
function tileData(tile) {{
  const s = segData();
  return s && s.tiles ? s.tiles[tile] : null;
}}
function combo(tile, clave) {{
  const t = tileData(tile);
  return t ? t.combinaciones.find(c => c.clave === clave) : null;
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
    if (!src) {{ el.removeAttribute('src'); resolve(null); return; }}
    if (el.getAttribute('src') === src && el.complete && el.naturalWidth) {{ resolve(el); return; }}
    el.onload = () => resolve(el);
    el.onerror = () => resolve(null);
    el.src = src;
  }});
}}

function recalcFit() {{
  const vp = document.getElementById('viewport');
  if (!vp || VIEW.imgW <= 0 || VIEW.imgH <= 0) return false;
  const rect = vp.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  VIEW.fit = Math.min(rect.width / VIEW.imgW, rect.height / VIEW.imgH);
  return true;
}}

function getViewCenter() {{
  const vp = document.getElementById('viewport').getBoundingClientRect();
  const total = VIEW.userZoom * VIEW.fit;
  if (total <= 0) return {{ cx: 0.5, cy: 0.5 }};
  return {{
    cx: (vp.width / 2 - VIEW.panX) / (VIEW.imgW * total),
    cy: (vp.height / 2 - VIEW.panY) / (VIEW.imgH * total),
  }};
}}

function setViewCenter(cx, cy) {{
  const vp = document.getElementById('viewport').getBoundingClientRect();
  const total = VIEW.userZoom * VIEW.fit;
  VIEW.panX = vp.width / 2 - cx * VIEW.imgW * total;
  VIEW.panY = vp.height / 2 - cy * VIEW.imgH * total;
}}

function fillSelect(id, values, fmt=v => v) {{
  const sel = document.getElementById(id);
  sel.innerHTML = values.map(v => `<option value="${{v}}">${{fmt(v)}}</option>`).join('');
}}

function syncSegmenterSelects() {{
  ['sel-segmenter', 'sel-segmenter-detail'].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.value = currentSeg;
  }});
  const s = segData();
  document.getElementById('overview-seg-label').textContent = s ? s.label : '—';
}}

function renderOverview() {{
  const grid = document.getElementById('tiles-grid');
  grid.innerHTML = '';
  const s = segData();
  if (!s) return;
  Object.keys(s.tiles).forEach(tileId => {{
    const t = s.tiles[tileId];
    const card = document.createElement('div');
    card.className = 'tile-card' + (t.tiene_datos ? '' : ' no-data');
    card.dataset.tile = tileId;
    const badge = t.tiene_datos
      ? `<span class="badge ok">${{t.n_combinaciones}} combo${{t.n_combinaciones !== 1 ? 's' : ''}}</span>`
      : '<span class="badge pending">sin datos</span>';
    const mosaic = t.mosaic_thumb ? `<img class="mosaic" src="${{t.mosaic_thumb}}" alt="mosaic" loading="lazy">` : '';
    const overlay = t.thumb_overlay ? `<img class="overlay" src="${{t.thumb_overlay}}" alt="seg" loading="lazy">` : '';
    const segRange = t.n_segmentos_min && t.n_segmentos_max
      ? `${{fmtInt(t.n_segmentos_min)}} – ${{fmtInt(t.n_segmentos_max)}} seg`
      : '—';
    card.innerHTML = `
      <div class="tile-preview">${{mosaic}}${{overlay}}</div>
      <div class="tile-info">
        <div class="name">${{tileId}} ${{badge}}</div>
        <div class="meta">${{segRange}}</div>
      </div>`;
    if (t.tiene_datos) {{
      card.addEventListener('click', () => selectTile(tileId, null, true));
    }}
    grid.appendChild(card);
  }});
}}

function updateTileCardActive(tile) {{
  document.querySelectorAll('.tile-card').forEach(el => {{
    el.classList.toggle('active', el.dataset.tile === tile);
  }});
}}

function combosForScaleSigma(tile, scale, sigma) {{
  const t = tileData(tile);
  if (!t) return [];
  return t.combinaciones.filter(c => String(c.scale) === String(scale) && String(c.sigma) === String(sigma));
}}

function updateRagSelect(tile, scale, sigma) {{
  const lbl = document.getElementById('lbl-rag');
  const sel = document.getElementById('sel-rag');
  const s = segData();
  if (!s || !s.incluir_rag) {{
    lbl.classList.add('hidden');
    sel.innerHTML = '';
    return;
  }}
  const combos = combosForScaleSigma(tile, scale, sigma);
  const hasBase = combos.some(c => c.rag_percentil == null || c.rag_percentil === '');
  const pcts = [...new Set(combos.map(c => c.rag_percentil).filter(p => p != null && p !== ''))].sort((a,b) => a-b);
  if (!hasBase && !pcts.length) {{
    lbl.classList.add('hidden');
    sel.innerHTML = '';
    return;
  }}
  lbl.classList.remove('hidden');
  let html = '';
  if (hasBase) html += '<option value="">SLIC (superpíxeles)</option>';
  pcts.forEach(p => {{ html += `<option value="${{p}}">RAG p${{p}}</option>`; }});
  const prev = sel.value;
  sel.innerHTML = html;
  if (hasBase && (prev === '' || !pcts.includes(Number(prev)))) sel.value = '';
  else if (pcts.includes(Number(prev))) sel.value = prev;
  else if (pcts.length) sel.value = String(pcts[0]);
  else sel.value = '';
}}

function construirClave(scale, sigma, ragMode) {{
  let clave = `s${{scale}}_sig${{String(sigma).replace('.', '_')}}`;
  if (ragMode) clave += `_ragp${{ragMode}}`;
  return clave;
}}

function resolverClave(tile, scale, sigma, ragMode) {{
  const ideal = construirClave(scale, sigma, ragMode);
  const combos = combosForScaleSigma(tile, scale, sigma);
  if (combos.find(c => c.clave === ideal)) return ideal;
  const match = combos.find(c => String(c.rag_percentil || '') === String(ragMode || ''));
  return match ? match.clave : (combos[0] ? combos[0].clave : ideal);
}}

function selectSegmenter(segId, keepTile) {{
  if (!DATA.segmenters[segId]) return;
  currentSeg = segId;
  syncSegmenterSelects();
  renderOverview();
  const tiles = Object.keys(segData().tiles).filter(t => tileData(t).tiene_datos);
  fillSelect('sel-tile', tiles);
  const tile = keepTile && VIEW.tile && tileData(VIEW.tile) ? VIEW.tile : tiles[0];
  if (tile) selectTile(tile, null, false);
}}

function selectTile(tile, clave, scroll) {{
  const t = tileData(tile);
  if (!t || !t.tiene_datos) return;
  VIEW.tile = tile;
  document.getElementById('detail-tile-name').textContent = `${{tile}} · ${{segData().label}}`;
  document.getElementById('sel-tile').value = tile;
  updateTileCardActive(tile);

  const scales = [...new Set(t.combinaciones.map(c => c.scale))].sort((a,b) => a-b);
  const sigmas = [...new Set(t.combinaciones.map(c => c.sigma))].sort((a,b) => a-b);
  fillSelect('sel-scale', scales);
  fillSelect('sel-sigma', sigmas, s => `σ=${{s}}`);

  const useClave = clave || t.default_clave;
  let c = combo(tile, useClave);
  if (!c && t.combinaciones.length) {{
    c = t.combinaciones[0];
  }}
  if (c) {{
    document.getElementById('sel-scale').value = String(c.scale);
    document.getElementById('sel-sigma').value = String(c.sigma);
    updateRagSelect(tile, c.scale, c.sigma);
    if (c.rag_percentil != null && c.rag_percentil !== '') {{
      document.getElementById('sel-rag').value = String(c.rag_percentil);
    }} else {{
      document.getElementById('sel-rag').value = '';
    }}
    showCombo(tile, c.clave);
  }} else {{
    document.getElementById('stats-panel').innerHTML = statsHtml(null);
    document.getElementById('layer-meta').innerHTML = 'Sin combinaciones disponibles';
  }}
  if (scroll) {{
    document.getElementById('detail-section').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }}
}}

function currentClave() {{
  const scale = document.getElementById('sel-scale').value;
  const sigma = document.getElementById('sel-sigma').value;
  const rag = document.getElementById('sel-rag').value;
  return resolverClave(VIEW.tile, scale, sigma, rag);
}}

function statsHtml(fila) {{
  if (!fila) return '<div class="stat-chip"><div class="k">Estadísticas</div><div class="v">N/D</div></div>';
  const chips = [
    ['Segmentos', fmtInt(fila.n_segmentos)],
    ['Tam. medio', fila.tam_medio_ha != null ? `${{fmtFloat(fila.tam_medio_ha)}} ha` : '—'],
    ['Tam. mediano', fila.tam_mediano_px != null ? `${{fmtFloat(fila.tam_mediano_px, 0)}} px` : '—'],
    ['Tam. min–max', fila.tam_min_px != null ? `${{fmtInt(fila.tam_min_px)}} – ${{fmtInt(fila.tam_max_px)}} px` : '—'],
    ['Scale', fila.scale],
    ['Sigma', fila.sigma],
  ];
  if (fila.rag_percentil != null && fila.rag_percentil !== '') {{
    chips.push(['RAG', `p${{fila.rag_percentil}}`]);
  }}
  return chips.map(([k,v]) => `<div class="stat-chip"><div class="k">${{k}}</div><div class="v">${{v}}</div></div>`).join('');
}}

function applyVisibility() {{
  const showMosaic = document.getElementById('chk-mosaic').checked;
  const showSeg = document.getElementById('chk-seg').checked;
  const showBnd = document.getElementById('chk-bnd').checked;
  const opacity = document.getElementById('opacity-seg').value / 100;
  const mosaic = document.getElementById('layer-mosaic');
  const seg = document.getElementById('layer-seg');
  const bnd = document.getElementById('layer-bnd');
  mosaic.classList.toggle('hidden-layer', !showMosaic || !mosaic.getAttribute('src'));
  seg.classList.toggle('hidden-layer', !showSeg || !seg.getAttribute('src'));
  bnd.classList.toggle('hidden-layer', !showBnd || !bnd.getAttribute('src'));
  seg.style.opacity = showSeg ? opacity : 0;
  if (showBnd && !bnd.getAttribute('src') && VIEW.tile && VIEW.clave) {{
    loadPanelTier(VIEW.tier, true);
  }}
}}

async function loadPanelTier(tier, preserveView) {{
  if (VIEW.loading) return;
  const t = tileData(VIEW.tile);
  const c = combo(VIEW.tile, VIEW.clave);
  if (!t || !c) return;

  const contentKey = `${{currentSeg}}:${{VIEW.tile}}:${{VIEW.clave}}`;
  const mosaicSrc = tierSrc(t.mosaic_tiers, tier);
  const segSrc = tierSrc(c.overlay_tiers, tier) || c.png || null;
  const showBnd = document.getElementById('chk-bnd').checked;
  const bndSrc = showBnd ? tierSrc(c.boundaries_tiers, tier) : null;
  const center = preserveView ? getViewCenter() : null;

  VIEW.loading = true;
  const mosaic = document.getElementById('layer-mosaic');
  const seg = document.getElementById('layer-seg');
  const bnd = document.getElementById('layer-bnd');

  if (VIEW.contentKey !== contentKey) {{
    seg.removeAttribute('src');
    bnd.removeAttribute('src');
    VIEW.contentKey = contentKey;
  }}

  const loadedMosaic = await loadImageEl(mosaic, mosaicSrc);
  const loadedSeg = await loadImageEl(seg, segSrc);
  if (showBnd) await loadImageEl(bnd, bndSrc);
  else bnd.removeAttribute('src');

  const ref = loadedMosaic || loadedSeg;
  VIEW.imgW = ref ? ref.naturalWidth : 1024;
  VIEW.imgH = ref ? ref.naturalHeight : 1024;
  const stage = document.getElementById('stage');
  stage.style.width = `${{VIEW.imgW}}px`;
  stage.style.height = `${{VIEW.imgH}}px`;
  VIEW.tier = tier;
  VIEW.loading = false;

  if (!recalcFit()) {{
    await new Promise(r => requestAnimationFrame(r));
    recalcFit();
  }}
  if (!preserveView) {{ VIEW.userZoom = 1; VIEW.panX = 0; VIEW.panY = 0; }}
  else if (center) setViewCenter(center.cx, center.cy);
  applyTransform(true);
  applyVisibility();
}}

function applyTransform(noReload) {{
  const stage = document.getElementById('stage');
  const total = VIEW.userZoom * VIEW.fit;
  stage.style.transform = `translate(${{VIEW.panX}}px, ${{VIEW.panY}}px) scale(${{total}})`;
  document.getElementById('zoom-label').textContent =
    `${{Math.round(VIEW.userZoom * 100)}}% · ${{VIEW.tier}}px`;

  if (noReload || VIEW.loading) return;
  const needed = tierForZoom(VIEW.userZoom);
  const t = tileData(VIEW.tile);
  if (needed > VIEW.tier && t && tierSrc(t.mosaic_tiers, needed)) {{
    loadPanelTier(needed, true);
  }}
}}

function zoomFactor(factor, cx, cy) {{
  const viewport = document.getElementById('viewport');
  const rect = viewport.getBoundingClientRect();
  const mx = cx !== undefined ? cx - rect.left : rect.width / 2;
  const my = cy !== undefined ? cy - rect.top : rect.height / 2;
  const totalOld = VIEW.userZoom * VIEW.fit;
  VIEW.userZoom = Math.min(24, Math.max(1, VIEW.userZoom * factor));
  const totalNew = VIEW.userZoom * VIEW.fit;
  VIEW.panX = mx - (mx - VIEW.panX) * (totalNew / totalOld);
  VIEW.panY = my - (my - VIEW.panY) * (totalNew / totalOld);
  if (VIEW.userZoom === 1) {{ VIEW.panX = 0; VIEW.panY = 0; }}
  applyTransform();
}}

function resetZoom() {{
  VIEW.userZoom = 1;
  VIEW.panX = 0;
  VIEW.panY = 0;
  if (VIEW.tier !== RES_TIERS[0]) loadPanelTier(RES_TIERS[0], false);
  else applyTransform(true);
}}

function showCombo(tile, clave) {{
  VIEW.clave = clave;
  const c = combo(tile, clave);
  document.getElementById('stats-panel').innerHTML = statsHtml(c ? c.fila : null);
  const tif = c && c.tif ? `<a href="${{c.tif}}" download>Descargar GeoTIFF</a>` : '';
  document.getElementById('layer-meta').innerHTML = tif
    ? `${{tif}} · resolución progresiva al acercar`
    : 'Sin GeoTIFF disponible';
  loadPanelTier(RES_TIERS[0], false);
}}

function onScaleSigmaChange() {{
  const scale = document.getElementById('sel-scale').value;
  const sigma = document.getElementById('sel-sigma').value;
  if (!scale || !sigma) return;
  updateRagSelect(VIEW.tile, scale, sigma);
  const clave = currentClave();
  if (combo(VIEW.tile, clave)) showCombo(VIEW.tile, clave);
  else showCombo(VIEW.tile, resolverClave(VIEW.tile, scale, sigma, document.getElementById('sel-rag').value));
}}

function init() {{
  const segIds = Object.keys(DATA.segmenters);
  const segOpts = segIds.map(id => {{
    const s = DATA.segmenters[id];
    return `<option value="${{id}}">${{s.label}}</option>`;
  }}).join('');
  document.getElementById('sel-segmenter').innerHTML = segOpts;
  document.getElementById('sel-segmenter-detail').innerHTML = segOpts;

  selectSegmenter(currentSeg, false);

  document.getElementById('sel-segmenter').addEventListener('change', e => selectSegmenter(e.target.value, true));
  document.getElementById('sel-segmenter-detail').addEventListener('change', e => selectSegmenter(e.target.value, true));
  document.getElementById('sel-tile').addEventListener('change', e => selectTile(e.target.value, null, true));
  document.getElementById('sel-scale').addEventListener('change', onScaleSigmaChange);
  document.getElementById('sel-sigma').addEventListener('change', onScaleSigmaChange);
  document.getElementById('sel-rag').addEventListener('change', () => showCombo(VIEW.tile, currentClave()));
  ['chk-mosaic','chk-seg','chk-bnd','opacity-seg'].forEach(id => {{
    document.getElementById(id).addEventListener('input', applyVisibility);
  }});

  const viewport = document.getElementById('viewport');
  let dragging = false, sx = 0, sy = 0, spx = 0, spy = 0;
  viewport.addEventListener('wheel', e => {{
    e.preventDefault();
    zoomFactor(e.deltaY < 0 ? 1.15 : 1/1.15, e.clientX, e.clientY);
  }}, {{ passive: false }});
  viewport.addEventListener('mousedown', e => {{
    if (e.button !== 0) return;
    dragging = true; viewport.classList.add('dragging');
    sx = e.clientX; sy = e.clientY; spx = VIEW.panX; spy = VIEW.panY;
  }});
  window.addEventListener('mousemove', e => {{
    if (!dragging) return;
    VIEW.panX = spx + (e.clientX - sx);
    VIEW.panY = spy + (e.clientY - sy);
    applyTransform(true);
  }});
  window.addEventListener('mouseup', () => {{ dragging = false; viewport.classList.remove('dragging'); }});
  document.querySelectorAll('.zoom-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const a = btn.dataset.action;
      if (a === 'reset') resetZoom();
      else if (a === 'in') zoomFactor(1.25);
      else if (a === 'out') zoomFactor(1/1.25);
    }});
  }});
  applyVisibility();
}}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualizador multi-tile de segmentación.")
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--mosaic-dir", type=Path, default=Path(MOSAIC_DIR))
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--tiles", default=",".join(TILES), help="Tiles separados por coma")
    parser.add_argument(
        "--segmenters",
        default="felzenszwalb,slic",
        help="Segmentadores a incluir (felzenszwalb,slic)",
    )
    parser.add_argument("--skip-layers", action="store_true", help="No regenerar PNG en capas/")
    args = parser.parse_args()

    tiles = tuple(t.strip() for t in args.tiles.split(",") if t.strip())
    segmenter_ids = tuple(s.strip() for s in args.segmenters.split(",") if s.strip())
    html_path = args.html.resolve()
    html_dir = html_path.parent
    html_dir.mkdir(parents=True, exist_ok=True)

    datos = construir_datos(
        args.mosaic_dir,
        html_dir,
        tiles,
        args.year,
        args.skip_layers,
        segmenter_ids,
    )

    html_path.write_text(generar_html(datos), encoding="utf-8")
    print(f"[OK] Dashboard: {html_path}")
    for seg_id in segmenter_ids:
        seg = datos["segmenters"][seg_id]
        n_tiles = sum(1 for t in seg["tiles"].values() if t["tiene_datos"])
        print(f"  · {seg['label']}: {n_tiles} tiles con datos")
        for tile in tiles:
            t = seg["tiles"][tile]
            if t["tiene_datos"]:
                print(f"      {tile}: {t['n_combinaciones']} combos")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765 --bind 0.0.0.0")
    print(f"[INFO] URL: http://localhost:8765/{html_path.name}")


if __name__ == "__main__":
    main()
