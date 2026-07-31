#!/usr/bin/env python3
"""
Build an interactive HTML viewer for SLIC+RAG segments.

Click a segment (map or ID search) to inspect:
  - Mean spectral signature per band (blue … swir2)
  - Spatial standard deviation per band (error bars)
  - Aggregated variacion_espectral

Usage:
  python build_spectral_viewer.py
  python build_spectral_viewer.py --grid-id 18GXA_3x3_c003_r003
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from html import escape
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.bands_184b import SIGNATURE_BANDS  # noqa: E402

from config.paths import output_dir  # noqa: E402

DEFAULT_SEG_ROOT = output_dir(2015)
DEFAULT_HTML = DEFAULT_SEG_ROOT / "viewer" / "segment_signatures_viewer.html"
MAX_SIDE = 1600
MOSAIC_NODATA = -9999.0
BAND_LABELS = [name for name, _ in SIGNATURE_BANDS]
BAND_COLORS = {
    "blue": "#3b82f6",
    "green": "#22c55e",
    "red": "#ef4444",
    "nir": "#8b5cf6",
    "swir1": "#f59e0b",
    "swir2": "#06b6d4",
}


def public_path(html_dir: Path, archivo: Path) -> str:
    return os.path.relpath(archivo.resolve(), html_dir.resolve()).replace("\\", "/")


def discover_rectangles(seg_root: Path, grid_id: str | None) -> list[dict]:
    rects: list[dict] = []
    for summary_path in sorted(seg_root.glob("*/*/*_summary.json")):
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        gid = data.get("grid_id", summary_path.parent.name)
        if grid_id and gid != grid_id:
            continue
        gpkg = summary_path.parent / f"{gid}_slic_ragp10_segments.gpkg"
        labels = Path(data["label_raster"])
        if not gpkg.is_file() or not labels.is_file():
            continue
        rects.append(
            {
                "grid_id": gid,
                "tile": data.get("tile", gid.split("_")[0]),
                "summary_path": summary_path,
                "gpkg_path": gpkg,
                "labels_path": labels,
                "mosaic_path": Path(data["mosaic_path"]),
                "n_segments": data.get("n_segments"),
                "buffer_px": data.get("buffer_px"),
            }
        )
    if not rects:
        raise FileNotFoundError(f"No rectangles with complete outputs in {seg_root}")
    return rects


def _quicklook_scale(h: int, w: int, max_side: int) -> float:
    return min(1.0, max_side / max(h, w))


def _normalize_rgb(bandas: np.ndarray, validos: np.ndarray) -> np.ndarray:
    rgb = np.zeros((*bandas.shape[:2], 3), dtype=np.float32)
    for c in range(3):
        canal = bandas[..., c].astype(np.float32)
        vals = canal[validos]
        if vals.size == 0:
            continue
        p2, p98 = np.percentile(vals, [2, 98])
        if p98 <= p2:
            p2, p98 = float(vals.min()), float(vals.max())
        esc = np.clip((canal - p2) / max(p98 - p2, 1e-6), 0, 1)
        rgb[..., c] = esc
    rgb[~validos] = 0
    return rgb


def _boundaries_rgba(labels: np.ndarray, validos: np.ndarray) -> np.ndarray:
    h, w = labels.shape
    borde = np.zeros((h, w), dtype=bool)
    borde[1:, :] |= labels[1:, :] != labels[:-1, :]
    borde[:-1, :] |= labels[:-1, :] != labels[1:, :]
    borde[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    borde[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    borde &= validos
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[borde] = [255, 255, 255, 210]
    return rgba


def _encode_pick_ids(labels: np.ndarray) -> np.ndarray:
    ids = labels.astype(np.uint32)
    rgb = np.zeros((*labels.shape, 3), dtype=np.uint8)
    rgb[..., 0] = ids & 0xFF
    rgb[..., 1] = (ids >> 8) & 0xFF
    rgb[..., 2] = (ids >> 16) & 0xFF
    return rgb


def export_rectangle_layers(
    rect: dict,
    assets_dir: Path,
    max_side: int,
) -> dict:
    gid = rect["grid_id"]
    assets_dir.mkdir(parents=True, exist_ok=True)

    idx_rgb = [3, 46, 128]  # blue, green, red para fondo
    with rasterio.open(rect["labels_path"]) as lbl_src:
        labels = lbl_src.read(1).astype(np.int32)
        transform = lbl_src.transform
        crs = lbl_src.crs.to_string() if lbl_src.crs else ""

    with rasterio.open(rect["mosaic_path"]) as m_src:
        from rasterio.windows import from_bounds

        bounds = rasterio.transform.array_bounds(labels.shape[0], labels.shape[1], transform)
        win = from_bounds(*bounds, transform=m_src.transform)
        win = win.round_offsets().round_lengths()
        stack = np.stack([m_src.read(i, window=win).astype(np.float32) for i in idx_rgb], axis=-1)
        nodata = MOSAIC_NODATA
        validos = np.all(np.isfinite(stack), axis=-1) & (stack != nodata).all(axis=-1)
        validos &= labels > 0

    if stack.shape[:2] != labels.shape:
        raise ValueError(f"Shape distinta labels/mosaico para {gid}")

    rgb = _normalizar_rgb(stack, validos)
    escala = _escala_para_quicklook(*labels.shape, max_side)
    if escala < 1.0:
        from skimage.transform import resize

        nh = max(1, int(round(labels.shape[0] * escala)))
        nw = max(1, int(round(labels.shape[1] * escala)))
        rgb_q = resize(rgb, (nh, nw, 3), order=1, preserve_range=True, anti_aliasing=True)
        labels_q = resize(labels, (nh, nw), order=0, preserve_range=True, anti_aliasing=False).astype(np.int32)
        validos_q = resize(validos.astype(np.float32), (nh, nw), order=0, preserve_range=True) > 0.5
    else:
        rgb_q, labels_q, validos_q = rgb, labels, validos

    base_name = f"{gid}_base.png"
    pick_name = f"{gid}_pick.png"
    bounds_name = f"{gid}_boundaries.png"

    Image.fromarray((np.clip(rgb_q, 0, 1) * 255).astype(np.uint8), mode="RGB").save(assets_dir / base_name)
    Image.fromarray(_encode_pick_ids(labels_q), mode="RGB").save(assets_dir / pick_name)
    Image.fromarray(_contornos_rgba(labels_q, validos_q), mode="RGBA").save(assets_dir / bounds_name)

    return {
        "grid_id": gid,
        "tile": rect["tile"],
        "width": int(labels_q.shape[1]),
        "height": int(labels_q.shape[0]),
        "base_png": base_name,
        "pick_png": pick_name,
        "boundaries_png": bounds_name,
        "n_segments": rect.get("n_segments"),
        "buffer_px": rect.get("buffer_px"),
        "crs": crs,
    }


def load_segments(gpkg_path: Path) -> list[dict]:
    gdf = gpd.read_file(gpkg_path)
    filas: list[dict] = []
    for _, row in gdf.iterrows():
        means = [float(row[f"mean_{b}"]) for b in BAND_LABELS]
        stds = [float(row[f"std_{b}"]) for b in BAND_LABELS]
        filas.append(
            {
                "segment_id": int(row["segment_id"]),
                "n_pixels": int(row["n_pixels"]),
                "area_ha": float(row["area_ha"]),
                "variacion_espectral": float(row["variacion_espectral"]),
                "means": means,
                "stds": stds,
            }
        )
    filas.sort(key=lambda x: x["segment_id"])
    return filas


def _png_data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def build_html(
    rects_meta: list[dict],
    segments_por_rect: dict[str, list[dict]],
    html_path: Path,
    assets_dir: Path,
    *,
    standalone: bool = False,
) -> None:
    html_dir = html_path.parent
    rects_payload = []
    for r in rects_meta:
        entry = {k: v for k, v in r.items() if not k.endswith("_name")}
        if standalone:
            entry["base_png"] = _png_data_uri(assets_dir / r["base_png"])
            entry["pick_png"] = _png_data_uri(assets_dir / r["pick_png"])
            entry["boundaries_png"] = _png_data_uri(assets_dir / r["boundaries_png"])
        else:
            entry["base_png"] = public_path(html_dir, assets_dir / r["base_png"])
            entry["pick_png"] = public_path(html_dir, assets_dir / r["pick_png"])
            entry["boundaries_png"] = public_path(html_dir, assets_dir / r["boundaries_png"])
        rects_payload.append(entry)
    payload = {
        "rects": rects_payload,
        "segments": segments_por_rect,
        "bands": BAND_LABELS,
        "band_colors": BAND_COLORS,
        "standalone": standalone,
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Segments — spectral signature</title>
<style>
:root {{
  --bg: #0f172a;
  --panel: #111827;
  --card: #1f2937;
  --line: #374151;
  --text: #e5e7eb;
  --muted: #9ca3af;
  --accent: #38bdf8;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}}
header {{
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}}
header h1 {{ margin: 0; font-size: 1.15rem; font-weight: 600; }}
.controls {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}}
.controls label {{ font-size: 0.85rem; color: var(--muted); display: flex; gap: 6px; align-items: center; }}
.controls select, .controls input {{
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 0.9rem;
}}
main {{
  display: grid;
  grid-template-columns: minmax(320px, 1.1fr) minmax(320px, 0.9fr);
  gap: 16px;
  padding: 16px;
}}
@media (max-width: 980px) {{ main {{ grid-template-columns: 1fr; }} }}
.panel {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px;
}}
.map-wrap {{
  position: relative;
  overflow: hidden;
  border-radius: 10px;
  background: #000;
  cursor: crosshair;
}}
.map-wrap img.layer {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: auto;
  display: block;
  pointer-events: none;
}}
.map-wrap canvas {{
  position: relative;
  width: 100%;
  height: auto;
  display: block;
}}
.hint {{ font-size: 0.82rem; color: var(--muted); margin-top: 8px; }}
.stats {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}}
.stat {{
  background: var(--card);
  border-radius: 10px;
  padding: 10px 12px;
}}
.stat .label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
.stat .value {{ font-size: 1.15rem; font-weight: 600; margin-top: 4px; }}
#chart {{
  width: 100%;
  height: 320px;
  background: var(--card);
  border-radius: 10px;
}}
.empty {{
  color: var(--muted);
  font-size: 0.95rem;
  padding: 40px 12px;
  text-align: center;
}}
.legend-band {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 12px;
  font-size: 0.82rem;
  color: var(--muted);
}}
.legend-band i {{
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
}}
</style>
</head>
<body>
<header>
  <h1>Segments — spectral signature</h1>
  <div class="controls">
    <label>Rectangle
      <select id="sel-rect"></select>
    </label>
    <label>Segmento
      <input id="inp-seg" type="number" min="1" placeholder="ID…">
    </label>
    <label><input id="chk-bounds" type="checkbox" checked> Boundaries</label>
  </div>
</header>
<main>
  <section class="panel">
    <div class="map-wrap" id="map-wrap">
      <canvas id="map"></canvas>
    </div>
    <p class="hint">Click the map to pick a segment. You can also search by ID.</p>
  </section>
  <section class="panel">
    <div id="detail">
      <p class="empty">Select a segment to view its spectral signature.</p>
    </div>
    <div id="chart"></div>
  </section>
</main>
<script>
const DATA = {data_json};

let currentRect = DATA.rects[0]?.grid_id || null;
let currentSeg = null;
let pickCanvas = null;
let baseImg = new Image();
let boundsImg = new Image();

function decodePick(r, g, b) {{
  return r + g * 256 + b * 65536;
}}

function rectMeta() {{
  return DATA.rects.find(r => r.grid_id === currentRect);
}}

function segmentsForRect() {{
  return DATA.segments[currentRect] || [];
}}

function segmentById(id) {{
  return segmentsForRect().find(s => s.segment_id === id) || null;
}}

function fillRectSelect() {{
  const sel = document.getElementById('sel-rect');
  sel.innerHTML = DATA.rects.map(r =>
    `<option value="${{r.grid_id}}">${{r.grid_id}} (${{r.n_segments ?? '?'}} seg)</option>`
  ).join('');
  sel.value = currentRect;
  sel.addEventListener('change', () => {{
    currentRect = sel.value;
    currentSeg = null;
    loadMap();
    renderDetail();
  }});
}}

async function loadPickLayer(url) {{
  const img = new Image();
  await new Promise((resolve, reject) => {{
    img.onload = resolve;
    img.onerror = reject;
    img.src = url;
  }});
  pickCanvas = document.createElement('canvas');
  pickCanvas.width = img.naturalWidth;
  pickCanvas.height = img.naturalHeight;
  const ctx = pickCanvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
}}

function drawMap() {{
  const canvas = document.getElementById('map');
  const ctx = canvas.getContext('2d');
  canvas.width = baseImg.naturalWidth;
  canvas.height = baseImg.naturalHeight;
  ctx.drawImage(baseImg, 0, 0);
  if (document.getElementById('chk-bounds').checked && boundsImg.src) {{
    ctx.drawImage(boundsImg, 0, 0);
  }}
  if (currentSeg) {{
    ctx.save();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.shadowColor = '#38bdf8';
    ctx.shadowBlur = 8;
    ctx.strokeRect(1, 1, canvas.width - 2, canvas.height - 2);
    ctx.restore();
  }}
}}

async function loadMap() {{
  const meta = rectMeta();
  if (!meta) return;
  baseImg = new Image();
  boundsImg = new Image();
  await new Promise((resolve, reject) => {{
    baseImg.onload = resolve;
    baseImg.onerror = reject;
    baseImg.src = meta.base_png;
  }});
  await loadPickLayer(meta.pick_png);
  await new Promise((resolve) => {{
    boundsImg.onload = resolve;
    boundsImg.onerror = resolve;
    boundsImg.src = meta.boundaries_png;
  }});
  drawMap();
}}

function pickSegment(clientX, clientY) {{
  if (!pickCanvas) return null;
  const canvas = document.getElementById('map');
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor((clientX - rect.left) * (canvas.width / rect.width));
  const y = Math.floor((clientY - rect.top) * (canvas.height / rect.height));
  if (x < 0 || y < 0 || x >= pickCanvas.width || y >= pickCanvas.height) return null;
  const ctx = pickCanvas.getContext('2d');
  const [r, g, b] = ctx.getImageData(x, y, 1, 1).data;
  const id = decodePick(r, g, b);
  return id > 0 ? id : null;
}}

function renderChart(seg) {{
  const chart = document.getElementById('chart');
  if (!seg) {{
    chart.innerHTML = '';
    return;
  }}
  const W = chart.clientWidth || 480;
  const H = 320;
  const pad = {{ l: 52, r: 16, t: 24, b: 48 }};
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;
  const means = seg.means;
  const stds = seg.stds;
  const maxY = Math.max(...means.map((m, i) => m + stds[i])) * 1.08;
  const minY = Math.max(0, Math.min(...means.map((m, i) => m - stds[i])) * 0.95);
  const n = DATA.bands.length;
  const step = innerW / n;
  const yScale = v => pad.t + innerH - ((v - minY) / Math.max(maxY - minY, 1)) * innerH;
  const points = means.map((m, i) => ({{
    x: pad.l + step * i + step * 0.5,
    y: yScale(m),
    m,
    s: stds[i],
    band: DATA.bands[i],
    color: DATA.band_colors[DATA.bands[i]] || '#38bdf8',
  }}));
  const linePath = points.map((p, i) => `${{i ? 'L' : 'M'}}${{p.x.toFixed(1)}},${{p.y.toFixed(1)}}`).join(' ');
  const upperPath = points.map((p, i) => {{
    const y = yScale(p.m + p.s);
    return `${{i ? 'L' : 'M'}}${{p.x.toFixed(1)}},${{y.toFixed(1)}}`;
  }}).join(' ');
  const lowerPath = points.map((p, i) => {{
    const y = yScale(Math.max(minY, p.m - p.s));
    return `${{i ? 'L' : 'M'}}${{p.x.toFixed(1)}},${{y.toFixed(1)}}`;
  }}).join(' ');
  const dash = 'stroke-dasharray="7 5"';

  let svg = `<svg viewBox="0 0 ${{W}} ${{H}}" width="100%" height="${{H}}">`;
  svg += `<line x1="${{pad.l}}" y1="${{pad.t + innerH}}" x2="${{W - pad.r}}" y2="${{pad.t + innerH}}" stroke="#4b5563"/>`;
  svg += `<path d="${{upperPath}}" fill="none" stroke="#94a3b8" stroke-width="1.8" ${{dash}} stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>`;
  svg += `<path d="${{lowerPath}}" fill="none" stroke="#94a3b8" stroke-width="1.8" ${{dash}} stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>`;
  svg += `<path d="${{linePath}}" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" opacity="0.95"/>`;
  for (const p of points) {{
    const yTop = yScale(p.m + p.s);
    const yBot = yScale(Math.max(minY, p.m - p.s));
    svg += `<line x1="${{p.x}}" y1="${{yTop}}" x2="${{p.x}}" y2="${{yBot}}" stroke="${{p.color}}" stroke-width="2" opacity="0.8" ${{dash}}/>`;
    svg += `<circle cx="${{p.x}}" cy="${{p.y}}" r="5" fill="${{p.color}}" stroke="#111827" stroke-width="1.5"/>`;
    svg += `<text x="${{p.x}}" y="${{H - 14}}" text-anchor="middle" fill="#9ca3af" font-size="11">${{p.band}}</text>`;
    svg += `<text x="${{p.x}}" y="${{yTop - 6}}" text-anchor="middle" fill="#e5e7eb" font-size="10">${{p.m.toFixed(0)}}</text>`;
  }}
  svg += `<text x="${{pad.l - 8}}" y="${{pad.t + 6}}" text-anchor="end" fill="#9ca3af" font-size="10">${{maxY.toFixed(0)}}</text>`;
  svg += `<text x="${{pad.l - 8}}" y="${{pad.t + innerH}}" text-anchor="end" fill="#9ca3af" font-size="10">${{minY.toFixed(0)}}</text>`;
  svg += `<text x="${{pad.l}}" y="16" fill="#9ca3af" font-size="11">Reflectance (DN) — solid = mean · dashed = ±1 spatial σ</text>`;
  svg += `</svg>`;
  chart.innerHTML = svg;
}}

function renderDetail() {{
  const box = document.getElementById('detail');
  const seg = currentSeg ? segmentById(currentSeg) : null;
  document.getElementById('inp-seg').value = currentSeg ?? '';
  if (!seg) {{
    box.innerHTML = '<p class="empty">Select a segment to view its spectral signature.</p>';
    renderChart(null);
    drawMap();
    return;
  }}
  const bandLegend = DATA.bands.map(b =>
    `<span class="legend-band"><i style="background:${{DATA.band_colors[b]}}"></i>${{b}}</span>`
  ).join('');
  box.innerHTML = `
    <div class="stats">
      <div class="stat"><div class="label">Segmento</div><div class="value">#${{seg.segment_id}}</div></div>
      <div class="stat"><div class="label">Area</div><div class="value">${{seg.area_ha.toFixed(2)}} ha</div></div>
      <div class="stat"><div class="label">Pixels</div><div class="value">${{seg.n_pixels.toLocaleString()}}</div></div>
      <div class="stat"><div class="label">Spectral variation</div><div class="value">${{seg.variacion_espectral.toFixed(2)}}</div></div>
    </div>
    <p style="margin:0 0 10px;font-size:0.82rem;color:var(--muted)">
      Spectral variation = media de σ espacial por banda (blue…swir2).
    </p>
    <div>${{bandLegend}}</div>
  `;
  renderChart(seg);
  drawMap();
}}

function selectSegment(id) {{
  if (!id || !segmentById(id)) {{
    currentSeg = null;
  }} else {{
    currentSeg = id;
  }}
  renderDetail();
}}

document.getElementById('map').addEventListener('click', e => {{
  const id = pickSegment(e.clientX, e.clientY);
  if (id) selectSegment(id);
}});

document.getElementById('inp-seg').addEventListener('change', e => {{
  const id = parseInt(e.target.value, 10);
  if (!Number.isNaN(id)) selectSegment(id);
}});

document.getElementById('chk-bounds').addEventListener('change', drawMap);

fillRectSelect();
loadMap().then(renderDetail);
</script>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build HTML viewer for per-segment spectral signatures.")
    p.add_argument("--seg-root", type=Path, default=DEFAULT_SEG_ROOT)
    p.add_argument("--grid-id", type=str, default=None, help="Single rectangle (default: all)")
    p.add_argument("--html", type=Path, default=DEFAULT_HTML)
    p.add_argument("--max-side", type=int, default=MAX_SIDE)
    p.add_argument(
        "--standalone",
        action="store_true",
        help="Standalone HTML (embedded images; no http.server)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rects = discover_rectangles(args.seg_root, args.grid_id)
    assets_dir = args.html.parent / "assets"

    rects_meta: list[dict] = []
    segments_por_rect: dict[str, list[dict]] = {}

    for rect in rects:
        gid = rect["grid_id"]
        print(f"Exporting layers → {gid}")
        rects_meta.append(export_rectangle_layers(rect, assets_dir, args.max_side))
        segments_por_rect[gid] = load_segments(rect["gpkg_path"])
        print(f"  {len(segmentos_por_rect[gid])} segments")

    build_html(rects_meta, segments_por_rect, args.html, assets_dir, standalone=args.standalone)
    print(f"\nViewer: {args.html}")
    if args.standalone:
        print("Standalone mode: abre el .html directamente (doble clic o arrastrar al navegador).")
    else:
        print("El servidor debe correr EN EL CLUSTER (donde está el archivo).")
        print("Desde tu PC, reenvía el puerto con SSH:")
        print("  ssh -L 8765:localhost:8765 lserey@leftraru2")
        print("Luego abre: http://localhost:8765/viewer/segmentos_firmas_viewer.html")
        print(f"\nO regenera autónomo: python build_spectral_viewer.py --standalone --grid-id ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
