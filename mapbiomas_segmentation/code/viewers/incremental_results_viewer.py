#!/usr/bin/env python3
"""
Visualizador de seg_felzenszwalb_incremental (prueba constructiva base + incrementos).

Uso:
  cd labeling/image_segmentation
  python incremental_results_viewer.py
  python incremental_results_viewer.py --skip-layers

Servir:
  cd /home/lserey/mapbiomas_land/test/image_segmentation
  python3 -m http.server 8765
  → http://localhost:8765/incremental_results_viewer.html
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
_RF_N_DIR = _SCRIPT_DIR / "seg_felzenszwalb_rf_n"
for _p in (_SCRIPT_DIR, _FELZ_DIR, _RF_N_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import segmenters_viewer as sv  # noqa: E402
from seg_felzenszwalb_rf_n_grid import localizar_mosaico_184  # noqa: E402

_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
_INC_DIR = _DATA_ROOT / "seg_felzenszwalb_incremental"
_MOSAIC_184 = Path("/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands")
_DEFAULT_HTML = _DATA_ROOT / "incremental_results_viewer.html"

CAPAS = sv.CAPAS_SUBDIR
RES_TIERS = sv.RES_TIERS
REF_3B = 16732
RATIO_VIABLE = 1.5
RATIO_FRAGMENTA = 2.0
SCALE = 200
SIGMA = 0.1


def slug_archivo(corrida: str) -> list[str]:
    """Candidatos de slug en disco (nuevo y legacy)."""
    if corrida == "base":
        return ["base"]
    if corrida.startswith("+"):
        nuevo = "base" + corrida.replace("+", "_mas_")
        legacy = corrida.replace("+", "_mas_")
        return [nuevo, legacy]
    saneada = corrida.replace("+", "_mas_")
    return [saneada]


def resolver_tif(output_dir: Path, tile: str, year: str, corrida: str) -> Path | None:
    for slug in slug_archivo(corrida):
        ruta = output_dir / f"seg_inc_{tile}_{year}_{slug}.tif"
        if ruta.is_file():
            return ruta
    return None


def cargar_resumen(output_dir: Path, tile: str, year: str) -> list[dict]:
    ruta = output_dir / f"resumen_incremental_{tile}_{year}.csv"
    if not ruta.is_file():
        return []
    filas: list[dict] = []
    with ruta.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            filas.append(
                {
                    "clave": row["corrida"],
                    "corrida": row["corrida"],
                    "n_bandas": int(float(row["n_bandas"])),
                    "n_segmentos": int(float(row["n_segmentos"])),
                    "ratio_vs_base": float(row["ratio_vs_base"]),
                    "ratio_vs_3bandas": float(row["ratio_vs_3bandas"]),
                    "tam_mediano_px": float(row["tam_mediano_px"]),
                    "tam_medio_ha": float(row["tam_medio_ha"]),
                    "tam_medio_px": float(row["tam_medio_px"]),
                    "tam_min_px": int(float(row["tam_min_px"])),
                    "tam_max_px": int(float(row["tam_max_px"])),
                }
            )
    return filas


def descubrir_capas(
    output_dir: Path,
    html_dir: Path,
    tile: str,
    year: str,
    filas: list[dict],
) -> dict[str, dict]:
    capas_dir = output_dir / CAPAS
    out: dict[str, dict] = {}
    for fila in filas:
        corrida = fila["corrida"]
        ruta_tif = resolver_tif(output_dir, tile, year, corrida)
        if not ruta_tif:
            print(f"[ADVERTENCIA] Sin TIF para corrida '{corrida}'")
            continue
        base = ruta_tif.stem
        ruta_png = ruta_tif.with_suffix(".png")
        out[corrida] = {
            "clave": corrida,
            "tile": tile,
            "year": year,
            "tif": sv.viz.ruta_publica(html_dir, ruta_tif),
            "png": sv.viz.ruta_publica(html_dir, ruta_png) if ruta_png.is_file() else "",
            "overlay_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "overlay"),
            "boundaries_tiers": sv.viz.descubrir_tiers_capa(html_dir, capas_dir, base, "boundaries"),
        }
    return out


def exportar_capas(
    output_dir: Path,
    mosaic_184_dir: Path,
    tile: str,
    year: str,
) -> dict[str, str] | None:
    try:
        import numpy as np
        import rasterio
        from rf_selected_bands import resolver_rgb_desde_descriptions
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
        print(f"[ADVERTENCIA] Sin export capas: {exc}")
        return None

    capas_dir = output_dir / CAPAS
    capas_dir.mkdir(parents=True, exist_ok=True)
    ruta_mosaico = localizar_mosaico_184(mosaic_184_dir, tile, int(year))
    mosaic_stem = f"mosaic_{tile}_{year}_rgb"
    mosaic_tiers: dict[str, str] = {}

    print(f"[INFO] Capas → {capas_dir}")

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
        fname = f"{mosaic_stem}_l{lado}.png"
        Image.fromarray((np.clip(rgb_q, 0, 1) * 255).astype(np.uint8), mode="RGB").save(capas_dir / fname)
        mosaic_tiers[str(lado)] = f"{CAPAS}/{fname}"

    for ruta_tif in sorted(output_dir.glob("seg_inc_*.tif")):
        with rasterio.open(ruta_tif) as seg:
            labels = seg.read(1).astype(np.int32)
        if labels.shape != validos.shape:
            print(f"[ERROR] Shape distinta: {ruta_tif.name}")
            sys.exit(1)
        base = ruta_tif.stem
        for lado in RES_TIERS:
            rgb_q, labels_q, validos_q = reducir_para_quicklook(rgb, labels, validos, lado)
            guardar_rgba_png(
                capas_dir / f"{base}_overlay_l{lado}.png",
                overlay_rgba_desde_labels(labels_q, validos_q),
            )
            guardar_rgba_png(
                capas_dir / f"{base}_boundaries_l{lado}.png",
                contornos_rgba_desde_labels(labels_q, validos_q, labels_ref=labels, validos_ref=validos),
            )
        print(f"  → {base}_overlay/boundaries_l*.png")

    return mosaic_tiers


def cargar_landcover_tiers(html_dir: Path, label_root: Path, tile: str, lc_year: int) -> dict[str, str]:
    lc_json = label_root / "landcover_tiers.json"
    if lc_json.is_file():
        payload = json.loads(lc_json.read_text(encoding="utf-8"))
        return {k: sv.viz.ruta_publica(html_dir, label_root / v) for k, v in payload.get("tiers", {}).items()}
    capas = label_root / CAPAS
    tiers = {}
    for lado in RES_TIERS:
        fname = f"{tile}_classification_{lc_year}_lc_l{lado}.png"
        if (capas / fname).is_file():
            tiers[str(lado)] = sv.viz.ruta_publica(html_dir, capas / fname)
    return tiers


def veredicto(ratio_base: float) -> str:
    if ratio_base <= RATIO_VIABLE:
        return "viable"
    if ratio_base > RATIO_FRAGMENTA:
        return "fragmenta"
    return "intermedio"


def generar_html(
    tile: str,
    year: str,
    lc_year: int,
    filas: list[dict],
    capas_por_clave: dict[str, dict],
    mosaic_tiers: dict[str, str],
    landcover_tiers: dict[str, str],
) -> str:
    n_base = next((f["n_segmentos"] for f in filas if f["corrida"] == "base"), 0)
    incrementos = [f for f in filas if f["corrida"] != "base"]
    mejor = min(incrementos, key=lambda r: r["ratio_vs_base"]) if incrementos else None
    peor = max(incrementos, key=lambda r: r["ratio_vs_base"]) if incrementos else None

    payload = {
        "tile": tile,
        "year": year,
        "lc_year": lc_year,
        "ref_3b": REF_3B,
        "ratio_viable": RATIO_VIABLE,
        "ratio_fragmenta": RATIO_FRAGMENTA,
        "mosaic_tiers": mosaic_tiers,
        "landcover_tiers": landcover_tiers,
        "res_tiers": RES_TIERS,
        "filas": filas,
        "capas_por_clave": capas_por_clave,
    }

    opts_inc = "".join(
        f"<option value='{escape(f['corrida'])}'>"
        f"{escape(f['corrida'])} ({f['n_segmentos']:,} seg · ratio_base {f['ratio_vs_base']:.2f}×)"
        f"</option>"
        for f in incrementos
    )
    mejor_ratio = f"{mejor['ratio_vs_base']:.2f}×" if mejor else "—"
    peor_txt = (
        f"{peor['corrida'].replace('+', '')} ({peor['ratio_vs_base']:.2f}×)"
        if peor
        else "—"
    )

    tabla_rows = ""
    first_inc = incrementos[0]["corrida"] if incrementos else ""
    for f in filas:
        v = veredicto(f["ratio_vs_base"]) if f["corrida"] != "base" else "referencia"
        cls = "selected" if f["corrida"] in ("base", first_inc) else ""
        tabla_rows += (
            f"<tr data-key='{escape(f['corrida'])}' class='fila-corrida {cls}'>"
            f"<td>{escape(f['corrida'])}</td>"
            f"<td>{f['n_bandas']}</td>"
            f"<td>{f['n_segmentos']:,}</td>"
            f"<td>{f['ratio_vs_base']:.3f}</td>"
            f"<td>{f['ratio_vs_3bandas']:.2f}</td>"
            f"<td>{f['tam_mediano_px']:.0f}</td>"
            f"<td class='veredicto {v}'>{v}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Incremental Felzenszwalb — {escape(tile)} {year}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --bg:#f4f6f8; --card:#fff; --line:#d9e2ec; --text:#1f2933; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ max-width:1440px; margin:0 auto; padding:24px; }}
.hero {{ background:linear-gradient(135deg,#065f46,#059669 45%,#0d9488); color:#fff; padding:28px 32px; border-radius:12px; margin-bottom:20px; }}
.hero h1 {{ margin:0 0 8px; font-size:1.7rem; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:20px; }}
.kpi {{ background:var(--card); border-radius:10px; padding:14px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.kpi .label {{ font-size:.82rem; color:#627d98; }}
.kpi .value {{ font-size:1.15rem; font-weight:700; }}
.section {{ background:var(--card); border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.section h2 {{ margin:0 0 14px; font-size:1.1rem; border-bottom:2px solid var(--line); padding-bottom:8px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:14px; }}
.controls label {{ display:flex; flex-direction:column; gap:4px; font-size:.88rem; color:#486581; }}
.controls select {{ min-width:220px; padding:8px; border:1px solid var(--line); border-radius:8px; }}
.viewer {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}
.panel {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#0b0b0b; }}
.panel header {{ color:#fff; padding:10px 14px; font-size:.9rem; }}
.panel-lc header {{ background:#6b4c9a; }}
.panel-a header {{ background:#059669; }}
.panel-b header {{ background:#0d9488; }}
.zoom-bar {{ display:flex; gap:8px; padding:8px 12px; background:#edf2f7; align-items:center; flex-wrap:wrap; }}
.zoom-btn {{ padding:4px 10px; border:1px solid var(--line); border-radius:6px; background:#fff; cursor:pointer; }}
.zoom-viewport {{ position:relative; width:100%; aspect-ratio:1; overflow:hidden; background:#111; cursor:grab; }}
.zoom-viewport:active {{ cursor:grabbing; }}
.zoom-stage {{ transform-origin:0 0; position:relative; }}
.layer-stack {{ position:relative; width:100%; height:100%; }}
.layer-stack img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:fill; }}
.hidden-layer {{ visibility:hidden; opacity:0; }}
.hidden {{ display:none !important; }}
.stats-inline {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(100px,1fr)); gap:6px; padding:10px; background:#fff; }}
.stat-chip {{ background:#f0f4f8; border-radius:8px; padding:8px; }}
.stat-chip .k {{ font-size:.75rem; color:#627d98; }}
.stat-chip .v {{ font-weight:600; font-size:.9rem; }}
table.data {{ width:100%; border-collapse:collapse; font-size:.88rem; }}
table.data th, table.data td {{ border:1px solid var(--line); padding:7px 9px; text-align:right; }}
table.data thead th {{ background:#d1fae5; }}
table.data tbody tr {{ cursor:pointer; }}
table.data tbody tr:hover {{ background:#ecfdf5; }}
table.data tbody tr.selected {{ background:#a7f3d0; }}
.veredicto.viable {{ color:#059669; font-weight:600; }}
.veredicto.fragmenta {{ color:#dc2626; font-weight:600; }}
.veredicto.intermedio {{ color:#d97706; }}
.chart {{ min-height:380px; }}
@media(max-width:1100px) {{ .viewer {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>Incremental Felzenszwalb — {escape(tile)} {year}</h1>
    <p>Base: nir_median + swir1_median + red_median · s={SCALE}, σ={SIGMA} · Col2 {lc_year}</p>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="label">Base (3 medianas)</div><div class="value">{n_base:,} seg</div></div>
    <div class="kpi"><div class="label">Ref. 3 bandas mosaico</div><div class="value">{REF_3B:,}</div></div>
    <div class="kpi"><div class="label">Ratio base / 3b</div><div class="value">{n_base/REF_3B:.1f}×</div></div>
    <div class="kpi"><div class="label">Mejor incremento</div><div class="value">{mejor['corrida'] if mejor else '—'}</div></div>
    <div class="kpi"><div class="label">Menor ratio_base</div><div class="value">{mejor_ratio}</div></div>
    <div class="kpi"><div class="label">Mayor ratio_base</div><div class="value">{peor_txt}</div></div>
  </div>

  <section class="section">
    <h2>Explorador — base vs incremento</h2>
    <div class="controls">
      <label><input type="checkbox" id="chk-mosaic" checked> Mosaico RGB</label>
      <label><input type="checkbox" id="chk-seg" checked> Segmentos</label>
      <label><input type="checkbox" id="chk-bnd" checked> Contornos</label>
      <label>Opacidad <input type="range" id="opacity-seg" min="0" max="100" value="55"></label>
      <label>Incremento <select id="sel-inc">{opts_inc}</select></label>
      <button type="button" id="btn-compare" class="active">Vista simple</button>
    </div>
    <div class="viewer" id="viewer">
      {panel_html("lc", f"Landcover Col2 {lc_year}", "panel-lc", landcover=True)}
      {panel_html("a", "Base (3 medianas)", "panel-a")}
      {panel_html("b", "Incremento", "panel-b")}
    </div>
  </section>

  <section class="section">
    <h2>Ratio vs base por incremento</h2>
    <div id="chart-ratio" class="chart"></div>
  </section>

  <section class="section">
    <h2>Tabla incremental (orden de corridas)</h2>
    <table class="data" id="tabla">
      <thead><tr>
        <th>corrida</th><th>n_bandas</th><th>n_segmentos</th>
        <th>ratio_base</th><th>ratio_3b</th><th>tam_mediano</th><th>veredicto</th>
      </tr></thead>
      <tbody>{tabla_rows}</tbody>
    </table>
  </section>
</div>

<script>
const DATA = {json.dumps(payload, ensure_ascii=False)};
const RES_TIERS = DATA.res_tiers;
const PANEL = {{
  lc: {{ clave:null, tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
  a:  {{ clave:'base', tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
  b:  {{ clave: DATA.filas.find(f=>f.corrida!=='base')?.corrida, tier:RES_TIERS[0], userZoom:1, panX:0, panY:0, fit:1, imgW:100, imgH:100, loading:false }},
}};
let SYNC_LOCK = false;

function capa(clave) {{ return DATA.capas_por_clave[clave] || null; }}
function tierSrc(tiers, tier) {{
  if (!tiers) return null;
  return tiers[String(tier)] || tiers[String(RES_TIERS[0])] || Object.values(tiers)[0];
}}
function fila(clave) {{ return DATA.filas.find(f => f.corrida===clave); }}

function tierForZoom(userZoom) {{
  if (userZoom >= 3.5) return RES_TIERS[Math.min(2, RES_TIERS.length - 1)];
  if (userZoom >= 1.8) return RES_TIERS[Math.min(1, RES_TIERS.length - 1)];
  return RES_TIERS[0];
}}
function recalcFit(suf) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf);
  if (!vp || st.imgW <= 0 || st.imgH <= 0) return false;
  const r = vp.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return false;
  st.fit = Math.min(r.width / st.imgW, r.height / st.imgH);
  return st.fit > 0;
}}
function aplicarZoom(suf, noSync) {{
  const st = PANEL[suf];
  const stage = document.getElementById('stage-'+suf);
  if (!stage) return;
  recalcFit(suf);
  const total = st.userZoom * st.fit;
  if (total <= 0) return;
  stage.style.transform = `translate(${{st.panX}}px,${{st.panY}}px) scale(${{total}})`;
  const lbl = document.getElementById('zoom-label-'+suf);
  if (lbl) lbl.textContent = Math.round(st.userZoom * 100) + '% · ' + st.tier + 'px';
  if (!noSync) syncPeers(suf);
}}
function getCenter(suf) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf).getBoundingClientRect();
  const total = st.userZoom * st.fit;
  if (total <= 0 || st.imgW <= 0 || st.imgH <= 0) return {{ cx: 0.5, cy: 0.5 }};
  return {{
    cx: (vp.width / 2 - st.panX) / (st.imgW * total),
    cy: (vp.height / 2 - st.panY) / (st.imgH * total),
  }};
}}
function setCenter(suf, cx, cy) {{
  const st = PANEL[suf];
  const vp = document.getElementById('viewport-'+suf).getBoundingClientRect();
  const total = st.userZoom * st.fit;
  if (total <= 0) return;
  st.panX = vp.width / 2 - cx * st.imgW * total;
  st.panY = vp.height / 2 - cy * st.imgH * total;
}}
function getViewState(suf) {{
  const c = getCenter(suf);
  return {{ userZoom: PANEL[suf].userZoom, cx: c.cx, cy: c.cy, tier: PANEL[suf].tier }};
}}
async function syncPeers(src) {{
  if (SYNC_LOCK) return;
  SYNC_LOCK = true;
  const v = getViewState(src);
  const peers = ['lc', 'a', 'b'].filter(s => {{
    if (s === src) return false;
    if (s === 'b' && document.getElementById('panel-b').classList.contains('hidden')) return false;
    return true;
  }});
  try {{
    await Promise.all(peers.map(s => applyView(s, v)));
  }} finally {{
    SYNC_LOCK = false;
  }}
}}
async function loadImg(el, src) {{
  return new Promise(res => {{
    if (!src) {{ el.removeAttribute('src'); res(null); return; }}
    if (el.getAttribute('src') === src && el.complete && el.naturalWidth) {{ res(el); return; }}
    el.onload = () => res(el);
    el.onerror = () => res(null);
    el.src = src;
  }});
}}
async function applyView(suf, v) {{
  const st = PANEL[suf];
  const needed = Math.max(v.tier, tierForZoom(v.userZoom));
  if (needed > st.tier && !st.loading) await loadPanel(suf, needed, true);
  st.userZoom = v.userZoom;
  recalcFit(suf);
  if (v.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
  else setCenter(suf, v.cx, v.cy);
  aplicarZoom(suf, true);
}}
async function loadPanel(suf, tier, preserve) {{
  const st = PANEL[suf];
  if (st.loading) return;
  const center = preserve ? getCenter(suf) : null;
  st.loading = true;
  let mosaicSrc = null, segSrc = null, bndSrc = null, lcSrc = null;
  if (suf === 'lc') {{
    lcSrc = tierSrc(DATA.landcover_tiers, tier);
  }} else {{
    const c = capa(st.clave);
    mosaicSrc = tierSrc(DATA.mosaic_tiers, tier);
    segSrc = c ? tierSrc(c.overlay_tiers, tier) : null;
    bndSrc = c ? tierSrc(c.boundaries_tiers, tier) : null;
  }}
  let ref = null;
  if (suf === 'lc') {{
    const lc = document.getElementById('layer-landcover-lc');
    ref = await loadImg(lc, lcSrc);
  }} else {{
    const mosaic = document.getElementById('layer-mosaic-'+suf);
    const seg = document.getElementById('layer-seg-'+suf);
    const bnd = document.getElementById('layer-bnd-'+suf);
    ref = await loadImg(mosaic, mosaicSrc);
    await Promise.all([loadImg(seg, segSrc), loadImg(bnd, bndSrc)]);
    if (!ref || !ref.naturalWidth) ref = seg;
  }}
  if (ref && ref.naturalWidth) {{
    st.imgW = ref.naturalWidth;
    st.imgH = ref.naturalHeight;
    const stage = document.getElementById('stage-'+suf);
    if (stage) {{
      stage.style.width = st.imgW + 'px';
      stage.style.height = st.imgH + 'px';
    }}
  }}
  st.tier = tier;
  st.loading = false;
  if (!recalcFit(suf)) {{
    await new Promise(r => requestAnimationFrame(r));
    recalcFit(suf);
  }}
  if (!preserve) {{ st.userZoom = 1; st.panX = 0; st.panY = 0; }}
  else if (center) setCenter(suf, center.cx, center.cy);
  aplicarZoom(suf, true);
  visCapas(suf);
  updateHeader(suf);
}}
function visCapas(suf) {{
  if (suf === 'lc') {{
    const lc = document.getElementById('layer-landcover-lc');
    if (lc) lc.classList.toggle('hidden-layer', !lc.getAttribute('src'));
    return;
  }}
  const showM = document.getElementById('chk-mosaic').checked;
  const showS = document.getElementById('chk-seg').checked;
  const showB = document.getElementById('chk-bnd').checked;
  const op = document.getElementById('opacity-seg').value / 100;
  ['mosaic', 'seg', 'bnd'].forEach(l => {{
    const el = document.getElementById('layer-' + l + '-' + suf);
    if (!el) return;
    const show = l === 'mosaic' ? showM : l === 'seg' ? showS : showB;
    el.classList.toggle('hidden-layer', !show || !el.getAttribute('src'));
  }});
  const segEl = document.getElementById('layer-seg-' + suf);
  if (segEl) segEl.style.opacity = showS ? op : 0;
}}
function updateHeader(suf) {{
  const hdr = document.getElementById('title-'+suf);
  if (suf==='lc') {{ hdr.textContent = 'Landcover Col2 '+DATA.lc_year; return; }}
  const f = fila(PANEL[suf].clave);
  if (!f) return;
  hdr.textContent = f.corrida + ' · ' + f.n_segmentos.toLocaleString('es-CL') + ' seg';
  document.getElementById('stats-'+suf).innerHTML = [
    ['Bandas', f.n_bandas], ['Ratio base', f.ratio_vs_base.toFixed(3)+'×'],
    ['Ratio 3b', f.ratio_vs_3bandas.toFixed(2)+'×'], ['Tam. mediano', f.tam_mediano_px+' px'],
  ].map(([k,v]) => `<div class="stat-chip"><div class="k">${{k}}</div><div class="v">${{v}}</div></div>`).join('');
}}
function initZoom(suf) {{
  const vp = document.getElementById('viewport-'+suf);
  if (!vp) return;
  let drag = false, sx = 0, sy = 0, px = 0, py = 0;
  vp.addEventListener('wheel', async e => {{
    e.preventDefault();
    const st = PANEL[suf];
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const newZoom = Math.min(24, Math.max(1, st.userZoom * f));
    const needed = tierForZoom(newZoom);
    if (needed > st.tier && !st.loading) await loadPanel(suf, needed, true);
    const r = vp.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const t0 = st.userZoom * st.fit;
    const t1 = newZoom * st.fit;
    if (t0 > 0) {{
      st.panX = mx - (mx - st.panX) * (t1 / t0);
      st.panY = my - (my - st.panY) * (t1 / t0);
    }}
    st.userZoom = newZoom;
    if (st.userZoom === 1) {{ st.panX = 0; st.panY = 0; }}
    aplicarZoom(suf);
  }}, {{ passive: false }});
  vp.addEventListener('mousedown', e => {{
    if (e.button !== 0) return;
    drag = true;
    sx = e.clientX;
    sy = e.clientY;
    px = PANEL[suf].panX;
    py = PANEL[suf].panY;
    e.preventDefault();
  }});
  vp.addEventListener('mousemove', e => {{
    if (!drag) return;
    PANEL[suf].panX = px + e.clientX - sx;
    PANEL[suf].panY = py + e.clientY - sy;
    aplicarZoom(suf);
  }});
  vp.addEventListener('mouseup', () => {{ drag = false; }});
  vp.addEventListener('mouseleave', () => {{ drag = false; }});
  document.querySelectorAll('.zoom-btn[data-panel="' + suf + '"]').forEach(btn => {{
    btn.onclick = async () => {{
      const st = PANEL[suf];
      if (btn.dataset.action === 'reset') {{
        st.userZoom = 1;
        st.panX = 0;
        st.panY = 0;
      }} else if (btn.dataset.action === 'in') {{
        st.userZoom = Math.min(24, st.userZoom * 1.25);
      }} else {{
        st.userZoom = Math.max(1, st.userZoom / 1.25);
      }}
      const needed = tierForZoom(st.userZoom);
      if (needed > st.tier && !st.loading) await loadPanel(suf, needed, true);
      aplicarZoom(suf);
    }};
  }});
}}
function seleccion(clave, panel) {{
  document.querySelectorAll('.fila-corrida').forEach(r => {{
    r.classList.toggle('selected', r.dataset.key===clave);
  }});
  if (panel==='a' || clave==='base') {{ PANEL.a.clave='base'; loadPanel('a', PANEL.a.tier, false); }}
  if (panel==='b' && clave!=='base') {{
    PANEL.b.clave = clave;
    document.getElementById('sel-inc').value = clave;
    if (!document.getElementById('panel-b').classList.contains('hidden')) loadPanel('b', PANEL.b.tier, false);
  }}
  if (clave!=='base' && panel!=='a') {{
    document.getElementById('sel-inc').value = clave;
    PANEL.b.clave = clave;
    if (!document.getElementById('panel-b').classList.contains('hidden')) loadPanel('b', PANEL.b.tier, false);
  }}
}}
function renderChart() {{
  const incs = DATA.filas.filter(f => f.corrida !== 'base');
  const labels = incs.map(f => f.corrida);
  const vals = incs.map(f => f.ratio_vs_base);
  Plotly.newPlot('chart-ratio', [{{
    x: labels, y: vals, type:'bar',
    marker:{{ color: vals.map(v => v<=DATA.ratio_viable ? '#059669' : v>DATA.ratio_fragmenta ? '#dc2626' : '#d97706') }},
  }}], {{
    title:'ratio_vs_base (umbral viable ≤'+DATA.ratio_viable+'×)',
    shapes:[
      {{ type:'line', x0:-0.5, x1:labels.length-0.5, y0:1, y1:1, line:{{color:'#2563eb',dash:'dash'}} }},
      {{ type:'line', x0:-0.5, x1:labels.length-0.5, y0:DATA.ratio_viable, y1:DATA.ratio_viable, line:{{color:'#059669',dash:'dot'}} }},
      {{ type:'line', x0:-0.5, x1:labels.length-0.5, y0:DATA.ratio_fragmenta, y1:DATA.ratio_fragmenta, line:{{color:'#dc2626',dash:'dot'}} }},
    ],
    margin:{{l:50,r:20,t:40,b:80}},
  }}, {{responsive:true}});
}}
document.addEventListener('DOMContentLoaded', async () => {{
  ['lc','a','b'].forEach(initZoom);
  await Promise.all([
    loadPanel('lc', RES_TIERS[0], false),
    loadPanel('a', RES_TIERS[0], false),
    loadPanel('b', RES_TIERS[0], false),
  ]);
  window.addEventListener('resize', () => {{
    ['lc','a','b'].forEach(s => {{ recalcFit(s); aplicarZoom(s, true); }});
  }});
  document.getElementById('sel-inc').addEventListener('change', e => seleccion(e.target.value, 'b'));
  document.getElementById('btn-compare').addEventListener('click', () => {{
    const btn = document.getElementById('btn-compare');
    const show = btn.classList.toggle('active');
    document.getElementById('panel-b').classList.toggle('hidden', !show);
    btn.textContent = show ? 'Vista simple' : 'Comparar base vs incremento';
    if (show) loadPanel('b', PANEL.b.tier, false).then(() => syncPeers('a'));
  }});
  ['chk-mosaic','chk-seg','chk-bnd','opacity-seg'].forEach(id => {{
    document.getElementById(id).addEventListener('input', () => {{ visCapas('a'); visCapas('b'); }});
  }});
  document.querySelectorAll('.fila-corrida').forEach(r => {{
    r.addEventListener('click', () => {{
      const k = r.dataset.key;
      if (k==='base') seleccion(k, 'a');
      else seleccion(k, 'b');
    }});
  }});
  renderChart();
}});
</script>
</body>
</html>"""


def panel_html(pid: str, titulo: str, cls: str, *, landcover: bool = False) -> str:
    if landcover:
        layers = f'<img class="layer" id="layer-landcover-{pid}" alt="Landcover" loading="lazy">'
    else:
        layers = f"""
              <img class="layer" id="layer-mosaic-{pid}" alt="mosaic" loading="lazy">
              <img class="layer" id="layer-seg-{pid}" alt="seg" loading="lazy">
              <img class="layer" id="layer-bnd-{pid}" alt="bnd" loading="lazy">"""
    return f"""
      <div class="panel {cls}" id="panel-{pid}">
        <header id="title-{pid}">{escape(titulo)}</header>
        <div class="zoom-bar">
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="in">+</button>
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="out">−</button>
          <button type="button" class="zoom-btn" data-panel="{pid}" data-action="reset">100%</button>
          <span id="zoom-label-{pid}">100%</span>
        </div>
        <div class="zoom-viewport" id="viewport-{pid}">
          <div class="zoom-stage" id="stage-{pid}">
            <div class="layer-stack">{layers}
            </div>
          </div>
        </div>
        <div class="stats-inline" id="stats-{pid}"></div>
      </div>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualizador incremental Felzenszwalb.")
    parser.add_argument("--tile", default="18HYD")
    parser.add_argument("--year", type=int, default=2010)
    parser.add_argument("--lc-year", type=int, default=None)
    parser.add_argument("--html", type=Path, default=_DEFAULT_HTML)
    parser.add_argument("--output-dir", type=Path, default=_INC_DIR)
    parser.add_argument("--skip-layers", action="store_true")
    args = parser.parse_args()

    tile = args.tile.upper()
    year = str(args.year)
    lc_year = args.lc_year if args.lc_year is not None else int(year)
    output_dir = args.output_dir.resolve()
    html_path = args.html.resolve()
    html_dir = html_path.parent

    filas = cargar_resumen(output_dir, tile, year)
    if not filas:
        print(f"[ERROR] Sin resumen_incremental_{tile}_{year}.csv en {output_dir}")
        return 1

    mosaic_tiers: dict[str, str] = {}
    if not args.skip_layers:
        tiers = exportar_capas(output_dir, _MOSAIC_184, tile, year)
        if tiers:
            mosaic_tiers = {k: sv.viz.ruta_publica(html_dir, output_dir / v) for k, v in tiers.items()}
    else:
        capas_dir = output_dir / CAPAS
        mosaic_tiers = sv.viz.descubrir_mosaic_tiers(html_dir, capas_dir, tile, year)

    capas = descubrir_capas(output_dir, html_dir, tile, year, filas)
    label_root = _DATA_ROOT / "labeling_overlays" / f"tile_{tile}_{year}_lc{lc_year}"
    landcover_tiers = cargar_landcover_tiers(html_dir, label_root, tile, lc_year)

    html = generar_html(tile, year, lc_year, filas, capas, mosaic_tiers, landcover_tiers)
    html_path.write_text(html, encoding="utf-8")
    print(f"[OK] Dashboard: {html_path}")
    print(f"[OK] Corridas: {len(filas)}, capas: {len(capas)}")
    print(f"[INFO] Servir: cd {html_dir} && python3 -m http.server 8765")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
