#!/usr/bin/env python3
"""
Visualizador de etiquetado C2 (varios τ) + fusión adyacente.

Uso:
  python labeling_tau95_viewer.py
  python labeling_tau95_viewer.py --skip-layers

Servir:
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765 --bind 0.0.0.0
  → http://localhost:8765/labeling_tau95_viewer.html
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html import escape
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
_LABEL_PKG = _DATA_ROOT / "segmentation_labels"
_FELZ_DIR = _SCRIPT_DIR / "seg_felzenszwalb"

for p in (_SCRIPT_DIR, _FELZ_DIR, _SCRIPT_DIR / "segmentation_labels", _LABEL_PKG.parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from col2_palette import CLASES_VALIDAS, COL2_NAMES, COL2_RGB, build_lut  # noqa: E402
from seg_felzenszwalb_grid import (  # noqa: E402
    DISPLAY_BANDS,
    MOSAIC_DIR,
    NODATA,
    componer_rgb,
    construir_mascara_nodata,
    contornos_rgba_desde_labels,
    guardar_rgba_png,
    localizar_mosaico_tile,
    reducir_para_quicklook,
    resolver_nodata,
)
from segmentation_labels import config as cfg  # noqa: E402
from segmentation_labels.assign import assign_labels  # noqa: E402
from segmentation_labels.io_rasters import load_raster_pair  # noqa: E402
from segmentation_labels.stats import compute_segment_stats  # noqa: E402

DEFAULT_HTML = _DATA_ROOT / "labeling_tau95_viewer.html"
CAPAS_SUBDIR = "capas/viewer"
RES_TIERS = [1024, 2048, 4096]

TAU_LEVELS = [
    {"id": "95", "tau": 0.95, "dir_name": "labeling_tau95", "label": "95%"},
    {"id": "90", "tau": 0.90, "dir_name": "labeling_tau090", "label": "90%"},
    {"id": "85", "tau": 0.85, "dir_name": "labeling_tau085", "label": "85%"},
    {"id": "80", "tau": 0.80, "dir_name": "labeling_tau080", "label": "80%"},
]

RUN_LABELS = {
    "felzenszwalb_s50_sig01": "Felzenszwalb s50 σ0.1",
    "slic_s50_sig01_ragp10": "SLIC s50 σ0.1 RAG p10",
}


def ruta_publica(html_dir: Path, archivo: Path) -> str:
    return os.path.relpath(archivo.resolve(), html_dir.resolve()).replace("\\", "/")


def render_label_rgba(labels: np.ndarray, validos: np.ndarray, *, alpha_ok: float = 0.78) -> np.ndarray:
    palette, _ = build_lut(255)
    h, w = labels.shape
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for cls_id, color in enumerate(palette):
        if cls_id == 0:
            continue
        mask = labels == cls_id
        if mask.any():
            rgb[mask] = color
    alpha = np.where((labels > 0) & validos, alpha_ok, 0.0).astype(np.float32)
    return np.dstack([rgb, alpha])


def write_assigned_raster(segments: np.ndarray, segment_ids: np.ndarray, label_final: np.ndarray) -> np.ndarray:
    max_id = int(segment_ids.max())
    lut = np.full(max_id + 1, 0, dtype=np.uint8)
    for seg_id, label in zip(segment_ids, label_final):
        lut[int(seg_id)] = np.uint8(label)
    out = np.zeros(segments.shape, dtype=np.uint8)
    fg = segments != cfg.BACKGROUND_SEGMENT_ID
    out[fg] = lut[segments[fg].astype(np.int64)]
    return out


def export_label_tiers(
    capas_dir: Path,
    html_dir: Path,
    stem: str,
    labels_u8: np.ndarray,
    validos: np.ndarray,
    *,
    force: bool = False,
    alpha_ok: float = 0.78,
) -> dict[str, str]:
    tiers: dict[str, str] = {}
    capas_dir.mkdir(parents=True, exist_ok=True)
    dummy = np.zeros((*labels_u8.shape, 3), dtype=np.float32)
    for lado in RES_TIERS:
        fname = f"{stem}_l{lado}.png"
        out_path = capas_dir / fname
        tiers[str(lado)] = ruta_publica(html_dir, out_path)
        if out_path.is_file() and not force:
            continue
        _, labels_q, validos_q = reducir_para_quicklook(
            dummy, labels_u8.astype(np.int32), validos, lado
        )
        guardar_rgba_png(out_path, render_label_rgba(labels_q.astype(np.uint8), validos_q, alpha_ok=alpha_ok))
        print(f"    → {fname}")
    return tiers


def export_boundary_tiers(
    capas_dir: Path,
    html_dir: Path,
    stem: str,
    segments: np.ndarray,
    validos: np.ndarray,
    *,
    force: bool = False,
) -> dict[str, str]:
    tiers: dict[str, str] = {}
    capas_dir.mkdir(parents=True, exist_ok=True)
    dummy = np.zeros((*segments.shape, 3), dtype=np.float32)
    for lado in RES_TIERS:
        fname = f"{stem}_l{lado}.png"
        out_path = capas_dir / fname
        tiers[str(lado)] = ruta_publica(html_dir, out_path)
        if out_path.is_file() and not force:
            continue
        _, labels_q, validos_q = reducir_para_quicklook(
            dummy, segments.astype(np.int32), validos, lado
        )
        guardar_rgba_png(out_path, contornos_rgba_desde_labels(labels_q, validos_q))
        print(f"    → {fname}")
    return tiers


def export_run_capas(run_dir: Path, html_dir: Path, *, force: bool = False) -> dict:
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    capas_dir = run_dir / CAPAS_SUBDIR
    capas_dir.mkdir(parents=True, exist_ok=True)

    seg_path = Path(summary["segments_raster"])
    c2_path = Path(summary["c2_raster"])
    merged_path = run_dir / "C2_labels_merged.tif"

    tile_m = re.search(r"seg_([^_]+)_", seg_path.name)
    year_m = re.search(r"_(\d{4})_", seg_path.name)
    tile = tile_m.group(1) if tile_m else "?"
    year = int(year_m.group(1)) if year_m else 2010

    print(f"  Export capas {run_dir.name} ({tile} {year})")

    import rasterio

    pair = load_raster_pair(seg_path, c2_path, subset=False, subset_window=None)
    stats = compute_segment_stats(
        pair.segments, pair.c2, cfg.C2_NODATA, background_id=cfg.BACKGROUND_SEGMENT_ID
    )
    assignment = assign_labels(
        stats,
        tau_purity=summary.get("tau_purity", 0.95),
        kappa_coverage=summary.get("kappa_coverage", cfg.KAPPA_COVERAGE),
        n_min_pixels=summary.get("n_min_pixels", cfg.N_MIN_PIXELS),
        label_mixed=cfg.LABEL_MIXED,
        label_nodata=cfg.LABEL_NODATA,
    )
    assigned_u8 = write_assigned_raster(pair.segments, stats.segment_ids, assignment.label_final)
    validos = pair.segments != cfg.BACKGROUND_SEGMENT_ID

    ruta_mosaico = localizar_mosaico_tile(MOSAIC_DIR, tile, year)
    with rasterio.open(ruta_mosaico) as src:
        datos = np.stack([src.read(i + 1) for i in range(src.count)], axis=-1).astype(np.float32)
        nodata_valor = resolver_nodata(src, NODATA)
        validos_m = construir_mascara_nodata(datos, nodata_valor)
        rgb = componer_rgb(datos, DISPLAY_BANDS, validos_m)

    mosaic_stem = f"mosaic_{tile}_{year}_rgb"
    mosaic_tiers: dict[str, str] = {}
    for lado in RES_TIERS:
        fname = f"{mosaic_stem}_l{lado}.png"
        out_path = capas_dir / fname
        rel = ruta_publica(html_dir, out_path)
        mosaic_tiers[str(lado)] = rel
        if out_path.is_file() and not force:
            continue
        rgb_q, _, _ = reducir_para_quicklook(rgb, pair.segments, validos_m, lado)
        from PIL import Image

        Image.fromarray((np.clip(rgb_q, 0, 1) * 255).astype(np.uint8), mode="RGB").save(out_path)
        print(f"    → {fname}")

    c2_u8 = np.clip(pair.c2, 0, 255).astype(np.uint8)
    lc_tiers = export_label_tiers(
        capas_dir, html_dir, f"lc_{tile}_{year}", c2_u8, c2_u8 != 0, force=force, alpha_ok=0.72
    )
    assigned_tiers = export_label_tiers(
        capas_dir, html_dir, "assigned", assigned_u8, validos, force=force, alpha_ok=0.78
    )

    merged_tiers: dict[str, str] = {}
    if merged_path.is_file():
        with rasterio.open(merged_path) as src:
            merged = src.read(1).astype(np.uint8)
        merged_tiers = export_label_tiers(
            capas_dir, html_dir, "merged", merged, validos & (merged > 0), force=force, alpha_ok=0.82
        )

    bnd_tiers = export_boundary_tiers(
        capas_dir, html_dir, "boundaries", pair.segments, validos, force=force
    )

    classes_used = sorted(
        int(c)
        for c in np.unique(assigned_u8)
        if int(c) not in (0, cfg.LABEL_MIXED, cfg.LABEL_NODATA)
    )
    if merged_path.is_file():
        with rasterio.open(merged_path) as src:
            merged = src.read(1)
        classes_used = sorted(set(classes_used) | {int(c) for c in np.unique(merged) if int(c) > 0})

    return {
        "id": run_dir.name,
        "label": RUN_LABELS.get(run_dir.name, run_dir.name),
        "tile": tile,
        "year": year,
        "summary": summary,
        "mosaic_tiers": mosaic_tiers,
        "lc_tiers": lc_tiers,
        "assigned_tiers": assigned_tiers,
        "merged_tiers": merged_tiers,
        "boundaries_tiers": bnd_tiers,
        "classes_used": classes_used,
    }


def discover_runs(label_root: Path) -> list[Path]:
    runs: list[Path] = []
    for tile_dir in sorted(label_root.glob("tile_*")):
        if not tile_dir.is_dir():
            continue
        for run_dir in sorted(tile_dir.iterdir()):
            if (run_dir / "summary.json").is_file():
                runs.append(run_dir)
    return runs


def build_legend(classes: list[int]) -> list[dict]:
    items = []
    for cls_id in classes:
        if cls_id in (cfg.LABEL_MIXED, cfg.LABEL_NODATA):
            continue
        r, g, b = COL2_RGB.get(cls_id, (200, 200, 200))
        items.append(
            {
                "id": cls_id,
                "name": COL2_NAMES.get(cls_id, f"Clase {cls_id}"),
                "color": f"rgb({r},{g},{b})",
            }
        )
    for sentinel, name in ((cfg.LABEL_MIXED, "Mixto (< τ)"), (cfg.LABEL_NODATA, "Sin datos")):
        r, g, b = COL2_RGB.get(sentinel, (160, 160, 160))
        items.append({"id": sentinel, "name": name, "color": f"rgb({r},{g},{b})", "sentinel": True})
    return items


def load_run_entry(run_dir: Path, html_dir: Path, *, skip_layers: bool, force: bool) -> dict:
    if not skip_layers:
        return export_run_capas(run_dir, html_dir, force=force)

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    capas_dir = run_dir / CAPAS_SUBDIR
    seg_path = Path(summary["segments_raster"])
    tile_m = re.search(r"seg_([^_]+)_", seg_path.name)
    year_m = re.search(r"_(\d{4})_", seg_path.name)
    tile = tile_m.group(1) if tile_m else "?"
    year = int(year_m.group(1)) if year_m else 2010

    def tiers(stem: str) -> dict[str, str]:
        return {
            str(t): ruta_publica(html_dir, capas_dir / f"{stem}_l{t}.png")
            for t in RES_TIERS
            if (capas_dir / f"{stem}_l{t}.png").is_file()
        }

    return {
        "id": run_dir.name,
        "label": RUN_LABELS.get(run_dir.name, run_dir.name),
        "tile": tile,
        "year": year,
        "summary": summary,
        "mosaic_tiers": tiers(f"mosaic_{tile}_{year}_rgb"),
        "lc_tiers": tiers(f"lc_{tile}_{year}"),
        "assigned_tiers": tiers("assigned"),
        "merged_tiers": tiers("merged"),
        "boundaries_tiers": tiers("boundaries"),
        "classes_used": [],
    }


def build_data(html_dir: Path, *, skip_layers: bool, force: bool) -> dict:
    tiles: dict[str, dict] = {}
    tau_levels: list[dict] = []

    for tau_cfg in TAU_LEVELS:
        label_root = _DATA_ROOT / tau_cfg["dir_name"]
        if not label_root.is_dir():
            continue
        runs = discover_runs(label_root)
        if not runs:
            continue
        tau_levels.append(
            {"id": tau_cfg["id"], "label": tau_cfg["label"], "tau": tau_cfg["tau"]}
        )
        for run_dir in runs:
            run = load_run_entry(run_dir, html_dir, skip_layers=skip_layers, force=force)
            tile = run["tile"]
            tiles.setdefault(tile, {"tile": tile, "year": run["year"], "taus": {}})
            block = tiles[tile]["taus"].setdefault(
                tau_cfg["id"],
                {"tau": tau_cfg["tau"], "label": tau_cfg["label"], "runs": []},
            )
            block["runs"].append(run)

    used_classes = {
        c
        for t in tiles.values()
        for block in t["taus"].values()
        for r in block["runs"]
        for c in r.get("classes_used", [])
    }
    legend = build_legend(sorted(set(CLASES_VALIDAS) | used_classes))

    return {
        "tau_levels": tau_levels,
        "tiles": tiles,
        "legend": legend,
    }


def render_html(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etiquetado C2 — visualizador</title>
<style>
:root {{
  --bg: #f8fafc; --panel: #ffffff; --text: #1e293b; --muted: #64748b;
  --accent: #2563eb; --border: #e2e8f0; --viewport-bg: #e5e7eb;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); }}
header {{ padding: 16px 20px; border-bottom: 1px solid var(--border); background: var(--panel); }}
header h1 {{ margin: 0 0 6px; font-size: 1.25rem; }}
header p {{ margin: 0; color: var(--muted); font-size: 0.9rem; }}
.layout {{ display: grid; grid-template-columns: 1fr 280px; gap: 0; min-height: calc(100vh - 80px); }}
main {{ padding: 16px; background: var(--bg); }}
aside {{ border-left: 1px solid var(--border); padding: 16px; background: var(--panel); overflow-y: auto; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; align-items: flex-end; position: relative; z-index: 10; }}
.controls label {{ font-size: 0.85rem; color: var(--muted); display: flex; flex-direction: column; gap: 4px; }}
.controls select, .controls button {{
  padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: #fff; color: var(--text); font-size: 0.9rem; cursor: pointer;
  min-width: 180px;
}}
.controls button {{ min-width: auto; background: var(--panel); }}
.controls select:focus, .controls button:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
.layer-toggles {{
  display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; font-size: 0.88rem;
  position: relative; z-index: 10; background: var(--panel); padding: 10px 12px;
  border-radius: 8px; border: 1px solid var(--border);
}}
.viewport-wrap {{
  background: var(--viewport-bg); border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border); height: min(72vh, 820px); position: relative;
}}
#viewport {{ width: 100%; height: 100%; overflow: hidden; cursor: grab; position: relative; }}
#viewport.dragging {{ cursor: grabbing; }}
#stage {{ position: absolute; top: 0; left: 0; transform-origin: 0 0; }}
#stage img {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: block; }}
.hidden-layer {{ opacity: 0 !important; pointer-events: none; }}
#zoom-label {{
  position: absolute; bottom: 8px; left: 8px; background: rgba(255,255,255,0.92);
  color: var(--text); border: 1px solid var(--border);
  padding: 4px 8px; border-radius: 4px; font-size: 0.78rem;
}}
.stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }}
.stat {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; }}
.stat .k {{ font-size: 0.72rem; color: var(--muted); }}
.stat .v {{ font-size: 1rem; font-weight: 600; }}
.legend h3 {{ margin: 0 0 10px; font-size: 0.95rem; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 0.8rem; }}
.swatch {{ width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; border: 1px solid rgba(0,0,0,0.12); }}
</style>
</head>
<body>
<header>
  <h1>Etiquetado Col2 · fusión adyacente</h1>
  <p id="hdr-sub">Voto mayoritario MapBiomas Collection 2; solo segmentos con pureza ≥ τ; luego se fusionan parches contiguos iguales.</p>
</header>
<div class="layout">
<main>
  <div class="controls">
    <label>Tile <select id="sel-tile"></select></label>
    <label>Pureza τ <select id="sel-tau"></select></label>
    <label>Segmentador <select id="sel-run"></select></label>
    <button type="button" id="btn-reset">Reset zoom</button>
  </div>
  <div class="layer-toggles">
    <label><input type="checkbox" id="chk-mosaic" checked> Mosaico</label>
    <label><input type="checkbox" id="chk-lc"> Col2 referencia</label>
    <label><input type="checkbox" id="chk-assigned"> Etiquetas (pre-merge)</label>
    <label><input type="checkbox" id="chk-merged" checked> Etiquetas fusionadas</label>
    <label><input type="checkbox" id="chk-bnd"> Contornos segmento</label>
    <label>Opacidad <input type="range" id="opacity" min="20" max="100" value="75"></label>
  </div>
  <div class="viewport-wrap">
    <div id="viewport">
      <div id="stage">
        <img id="layer-mosaic" alt="mosaic">
        <img id="layer-lc" alt="lc">
        <img id="layer-assigned" alt="assigned">
        <img id="layer-merged" alt="merged">
        <img id="layer-bnd" alt="bnd">
      </div>
      <div id="zoom-label">100%</div>
    </div>
  </div>
</main>
<aside>
  <div class="stats" id="stats"></div>
  <div class="legend">
    <h3>Leyenda Col2</h3>
    <div id="legend-items"></div>
  </div>
</aside>
</div>
<script>
const DATA = {data_json};
const RES_TIERS = [1024, 2048, 4096];
const VIEW = {{ tile: null, tauId: null, runId: null, tier: 1024, userZoom: 1, fit: 1, panX: 0, panY: 0, imgW: 1024, imgH: 1024, loading: false }};

function tileIds() {{ return Object.keys(DATA.tiles); }}
function tileData(id) {{ return DATA.tiles[id]; }}
function currentTauBlock() {{
  const t = tileData(VIEW.tile);
  if (!t) return null;
  return t.taus[VIEW.tauId] || Object.values(t.taus)[0];
}}
function currentRun() {{
  const block = currentTauBlock();
  if (!block) return null;
  return block.runs.find(r => r.id === VIEW.runId) || block.runs[0];
}}
function tierSrc(tiers, tier) {{ return tiers && tiers[String(tier)] ? tiers[String(tier)] : null; }}

function fillSelect(id, values, fmt=v=>v) {{
  document.getElementById(id).innerHTML = values.map(v => `<option value="${{v}}">${{fmt(v)}}</option>`).join('');
}}

function renderLegend() {{
  document.getElementById('legend-items').innerHTML = DATA.legend.map(it =>
    `<div class="legend-item"><span class="swatch" style="background:${{it.color}}"></span><span>${{it.id}} · ${{it.name}}</span></div>`
  ).join('');
}}

function renderStats(run) {{
  const s = run.summary;
  const tauPct = Math.round((s.tau_purity ?? 0.95) * 100);
  const chips = [
    ['τ pureza', tauPct + '%'],
    ['Segmentos', s.n_segments_total?.toLocaleString() || '—'],
    [`Ok (≥${{tauPct}}%)`, s.ok?.toLocaleString()],
    ['Mixed', s.mixed?.toLocaleString()],
    ['Regiones merge', s.n_merged_regions?.toLocaleString()],
    ['Reducción', s.reduction_pct != null ? s.reduction_pct + '%' : '—'],
  ];
  document.getElementById('stats').innerHTML = chips.map(([k,v]) =>
    `<div class="stat"><div class="k">${{k}}</div><div class="v">${{v ?? '—'}}</div></div>`
  ).join('');
}}

function updateHeader() {{
  const block = currentTauBlock();
  if (!block) return;
  const pct = Math.round(block.tau * 100);
  document.getElementById('hdr-sub').textContent =
    `Voto mayoritario MapBiomas Collection 2; solo segmentos con ≥${{pct}}% de una clase; luego se fusionan parches contiguos iguales.`;
}}

function applyVisibility() {{
  const op = document.getElementById('opacity').value / 100;
  [['chk-mosaic','layer-mosaic',1],['chk-lc','layer-lc',op],['chk-assigned','layer-assigned',op],
   ['chk-merged','layer-merged',op],['chk-bnd','layer-bnd',1]].forEach(([cid, lid, baseOp]) => {{
    const el = document.getElementById(lid);
    const on = document.getElementById(cid).checked && el.getAttribute('src');
    el.classList.toggle('hidden-layer', !on);
    el.style.opacity = on ? baseOp : 0;
  }});
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

async function loadTier(tier, preserve) {{
  const run = currentRun();
  if (!run || VIEW.loading) return;
  VIEW.loading = true;
  const mosaic = document.getElementById('layer-mosaic');
  const lc = document.getElementById('layer-lc');
  const assigned = document.getElementById('layer-assigned');
  const merged = document.getElementById('layer-merged');
  const bnd = document.getElementById('layer-bnd');
  const ref = await loadImageEl(mosaic, tierSrc(run.mosaic_tiers, tier))
    || await loadImageEl(merged, tierSrc(run.merged_tiers, tier));
  await loadImageEl(lc, tierSrc(run.lc_tiers, tier));
  await loadImageEl(assigned, tierSrc(run.assigned_tiers, tier));
  await loadImageEl(merged, tierSrc(run.merged_tiers, tier));
  await loadImageEl(bnd, tierSrc(run.boundaries_tiers, tier));
  if (ref) {{ VIEW.imgW = ref.naturalWidth; VIEW.imgH = ref.naturalHeight; }}
  const stage = document.getElementById('stage');
  stage.style.width = VIEW.imgW + 'px';
  stage.style.height = VIEW.imgH + 'px';
  VIEW.tier = tier;
  VIEW.loading = false;
  recalcFit();
  if (!preserve) {{ VIEW.userZoom = 1; VIEW.panX = 0; VIEW.panY = 0; }}
  applyTransform(true);
  applyVisibility();
}}

function recalcFit() {{
  const vp = document.getElementById('viewport').getBoundingClientRect();
  if (VIEW.imgW <= 0 || vp.width <= 0) return false;
  VIEW.fit = Math.min(vp.width / VIEW.imgW, vp.height / VIEW.imgH);
  return true;
}}

function applyTransform(noReload) {{
  const total = VIEW.userZoom * VIEW.fit;
  document.getElementById('stage').style.transform =
    `translate(${{VIEW.panX}}px, ${{VIEW.panY}}px) scale(${{total}})`;
  document.getElementById('zoom-label').textContent = Math.round(VIEW.userZoom * 100) + '% · ' + VIEW.tier + 'px';
  if (noReload || VIEW.loading) return;
  const run = currentRun();
  const needed = RES_TIERS.find(t => t > VIEW.tier && tierSrc(run?.mosaic_tiers, t)) || VIEW.tier;
  if (needed > VIEW.tier) loadTier(needed, true);
}}

function selectTile(tileId) {{
  VIEW.tile = tileId;
  const t = tileData(tileId);
  if (!t) return;
  const tauIds = Object.keys(t.taus);
  if (!tauIds.length) return;
  fillSelect('sel-tau', tauIds, id => `${{t.taus[id].label}} (≥${{Math.round(t.taus[id].tau * 100)}}%)`);
  selectTau(tileId, tauIds[0]);
}}

function selectTau(tileId, tauId) {{
  VIEW.tile = tileId;
  VIEW.tauId = tauId;
  const t = tileData(tileId);
  const block = t?.taus[tauId];
  if (!block || !block.runs.length) return;
  const tileSel = document.getElementById('sel-tile');
  const tauSel = document.getElementById('sel-tau');
  if (tileSel.value !== tileId) tileSel.value = tileId;
  if (tauSel.value !== tauId) tauSel.value = tauId;
  fillSelect('sel-run', block.runs.map(r => r.id), id => block.runs.find(r => r.id === id).label);
  selectRun(tileId, tauId, block.runs[0].id);
}}

function selectRun(tileId, tauId, runId) {{
  VIEW.tile = tileId;
  VIEW.tauId = tauId;
  VIEW.runId = runId;
  const runSel = document.getElementById('sel-run');
  if (runSel.value !== runId) runSel.value = runId;
  const run = currentRun();
  if (!run) return;
  updateHeader();
  renderStats(run);
  loadTier(RES_TIERS[0], false);
}}

function init() {{
  renderLegend();
  const tiles = tileIds();
  if (!tiles.length) {{
    document.body.innerHTML = '<p style="padding:24px">Sin datos de etiquetado.</p>';
    return;
  }}
  fillSelect('sel-tile', tiles, id => `${{id}} (${{tileData(id).year}})`);
  selectTile(tiles[0]);
  document.getElementById('sel-tile').addEventListener('change', e => selectTile(e.target.value));
  document.getElementById('sel-tau').addEventListener('change', e => selectTau(VIEW.tile, e.target.value));
  document.getElementById('sel-run').addEventListener('change', e => selectRun(VIEW.tile, VIEW.tauId, e.target.value));
  ['chk-mosaic','chk-lc','chk-assigned','chk-merged','chk-bnd','opacity'].forEach(id =>
    document.getElementById(id).addEventListener('input', applyVisibility));
  document.getElementById('btn-reset').addEventListener('click', () => {{
    VIEW.userZoom = 1; VIEW.panX = 0; VIEW.panY = 0; loadTier(RES_TIERS[0], false);
  }});
  const vp = document.getElementById('viewport');
  let drag = false, sx, sy, spx, spy;
  vp.addEventListener('wheel', e => {{
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.12 : 1/1.12;
    const rect = vp.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const old = VIEW.userZoom * VIEW.fit;
    VIEW.userZoom = Math.min(20, Math.max(1, VIEW.userZoom * f));
    const nw = VIEW.userZoom * VIEW.fit;
    VIEW.panX = mx - (mx - VIEW.panX) * (nw / old);
    VIEW.panY = my - (my - VIEW.panY) * (nw / old);
    applyTransform();
  }}, {{passive: false}});
  vp.addEventListener('mousedown', e => {{
    if (e.button !== 0) return;
    drag = true; vp.classList.add('dragging');
    sx = e.clientX; sy = e.clientY; spx = VIEW.panX; spy = VIEW.panY;
  }});
  window.addEventListener('mousemove', e => {{
    if (!drag) return;
    VIEW.panX = spx + (e.clientX - sx);
    VIEW.panY = spy + (e.clientY - sy);
    applyTransform(true);
  }});
  window.addEventListener('mouseup', () => {{ drag = false; vp.classList.remove('dragging'); }});
}}
init();
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualizador etiquetado C2 (varios τ).")
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--skip-layers", action="store_true")
    parser.add_argument("--force-layers", action="store_true")
    args = parser.parse_args()

    html_path = args.html.expanduser().resolve()
    html_dir = html_path.parent
    print(f"[INFO] Tau levels: {[t['dir_name'] for t in TAU_LEVELS]}")
    data = build_data(html_dir, skip_layers=args.skip_layers, force=args.force_layers)
    html_path.write_text(render_html(data), encoding="utf-8")
    n_runs = sum(len(block["runs"]) for t in data["tiles"].values() for block in t["taus"].values())
    print(f"[OK] Dashboard: {html_path} ({n_runs} runs, {len(data['tiles'])} tiles)")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765 --bind 0.0.0.0")
    print(f"[INFO] URL: http://localhost:8765/{html_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
